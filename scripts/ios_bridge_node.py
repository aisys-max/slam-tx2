#!/usr/bin/env python3
"""iPhone TCP 스트림(#4, iproxy로 USB 터널링됨)을 프로젝트 표준 ROS2 센서 토픽으로 publish하는
브리지 노드 (#6). docs/ios-tcp-protocol.md의 Frame/IMU 메시지를 읽어
/camera/image_raw, /camera/camera_info(#5 캘리브레이션 값), /imu 로 publish한다
(docs/ros2-topic-contract.md). header.stamp는 iPhone 캡처 시각 기준이다 (ADR-0001).

USB/iproxy 연결이 끊기면 명확히 로그를 남기고 재연결을 시도한다 - connect/recv 모두 타임아웃이
있어 어떤 소켓 연산도 무한정 대기하지 않는다 (BridgeConnection 참고).

사용법 (iproxy로 iPhone TCP 서버(포트 8765)를 로컬 포트로 터널링한 뒤,
ROS2 Foxy 워크스페이스를 source한 상태에서):
    iproxy 8765 8765 &
    python3 scripts/ios_bridge_node.py localhost 8765

기본 캘리브레이션 파일은 calibration/iphone_xs_max_back_camera.yaml (--calibration으로 변경 가능).

단위 테스트: scripts/test_ios_bridge_node.py 참고 (ROS2 Foxy 소싱 필요).
"""
import argparse
import socket
import sys
import threading
import time
from pathlib import Path

import rclpy
import yaml
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image, Imu

sys.path.insert(0, str(Path(__file__).parent))
from test_ios_tcp_client import (  # noqa: E402
    TYPE_FRAME,
    TYPE_IMU,
    ProtocolError,
    decode_frame,
    decode_imu,
    read_message,
)


def _recv_exact_before_deadline(sock, n, deadline):
    """recv_exact()와 동일하지만 개별 recv() 호출마다 타임아웃을 새로 주는 대신 메시지 하나를
    읽는 전체 시간을 deadline으로 못박는다. sock.settimeout()을 매 recv() 호출 전에 초기화하면
    (recv_exact()가 그렇다) 느리게 한 바이트씩 흘려보내는 연결에서 메시지 하나를 읽는 데 걸리는
    시간이 무한정 늘어날 수 있어 - #6의 "무한 대기 없음" 요구사항이 깨진다."""
    buf = bytearray()
    while len(buf) < n:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise socket.timeout(f"{n}바이트 수신 중 recv_timeout 초과 ({len(buf)}/{n} 바이트만 받음)")
        sock.settimeout(remaining)
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ProtocolError(f"연결이 끊김 ({len(buf)}/{n} 바이트만 받음)")
        buf.extend(chunk)
    return bytes(buf)

FRAME_ID = "camera_link"  # docs/ros2-topic-contract.md: 이번 MVP는 단일 frame_id
DEFAULT_CALIBRATION = Path(__file__).parent.parent / "calibration" / "iphone_xs_max_back_camera.yaml"


def stamp_from_ns(header, ts_ns):
    """header.stamp를 iPhone 캡처 시각(나노초, 모노토닉 클럭) 기준으로 채운다 (ADR-0001)."""
    header.stamp.sec = ts_ns // 1_000_000_000
    header.stamp.nanosec = ts_ns % 1_000_000_000
    header.frame_id = FRAME_ID


def build_image(frame):
    """decode_frame() 결과 -> sensor_msgs/Image (mono8). stride는 그대로 step에 넣는다 -
    ROS Image.step은 실제 행 바이트 수를 뜻하므로 카메라가 width보다 넓게 패딩해도 크롭 없이
    바로 쓸 수 있다."""
    msg = Image()
    stamp_from_ns(msg.header, frame["timestamp_ns"])
    msg.height = frame["height"]
    msg.width = frame["width"]
    msg.encoding = "mono8"
    msg.is_bigendian = 0
    msg.step = frame["stride"]
    msg.data = frame["pixels"]
    return msg


def build_camera_info(ts_ns, calibration):
    """캘리브레이션(#5) YAML 딕셔너리 -> sensor_msgs/CameraInfo. YAML 필드가 이미
    CameraInfo 필드명(D/K/R/P/width/height/distortion_model)과 그대로 대응한다."""
    msg = CameraInfo()
    stamp_from_ns(msg.header, ts_ns)
    msg.width = int(calibration["width"])
    msg.height = int(calibration["height"])
    msg.distortion_model = calibration["distortion_model"]
    msg.d = [float(v) for v in calibration["D"]]
    msg.k = [float(v) for v in calibration["K"]]
    msg.r = [float(v) for v in calibration["R"]]
    msg.p = [float(v) for v in calibration["P"]]
    return msg


def build_imu(imu):
    """decode_imu() 결과 -> sensor_msgs/Imu. orientation은 미사용이라 covariance[0] = -1
    (docs/ros2-topic-contract.md)."""
    msg = Imu()
    stamp_from_ns(msg.header, imu["timestamp_ns"])
    (msg.angular_velocity.x, msg.angular_velocity.y, msg.angular_velocity.z) = imu["angular_velocity"]
    (msg.linear_acceleration.x, msg.linear_acceleration.y, msg.linear_acceleration.z) = imu["linear_acceleration"]
    msg.orientation_covariance[0] = -1.0
    return msg


# sensor_msgs/CameraInfo의 k/r/p는 IDL에 고정 길이 배열로 선언돼 있어 - 캘리브레이션 값이
# CameraInfo를 채우기 직전이 아니라 로드하는 시점에 틀렸다고 말해줘야, 다른 --calibration 파일을
# 쓸 때 어떤 필드가 왜 잘못됐는지 바로 알 수 있다.
_REQUIRED_CALIBRATION_LENGTHS = {"D": 5, "K": 9, "R": 9, "P": 12}


def load_calibration(path):
    with open(path) as f:
        calibration = yaml.safe_load(f)

    missing = [key for key in ("width", "height", "distortion_model", *_REQUIRED_CALIBRATION_LENGTHS) if key not in calibration]
    if missing:
        raise ValueError(f"{path}: 캘리브레이션 필드 누락: {missing}")
    for key, expected_len in _REQUIRED_CALIBRATION_LENGTHS.items():
        actual_len = len(calibration[key])
        if actual_len != expected_len:
            raise ValueError(f"{path}: {key}는 길이 {expected_len}이어야 하는데 {actual_len}임")

    return calibration


class BridgeConnection:
    """iPhone TCP 스트림에 접속해 프레임/IMU 콜백을 호출한다.

    연결 실패/끊김 시 명확히 로그를 남기고 retry_delay 뒤 재연결을 시도한다. connect/recv 모두
    타임아웃이 걸려 있어 어떤 소켓 연산도 무한정 대기하지 않는다 - 재시도 사이 대기도
    stop_event로 즉시 깨울 수 있어 종료 요청에 무한정 안 막힌다.

    socket_factory/log를 주입할 수 있어 실제 네트워크/ROS2 없이 재연결 상태 머신을 단위 테스트할
    수 있다 (scripts/test_ios_bridge_node.py 참고).
    """

    def __init__(
        self,
        host,
        port,
        on_frame,
        on_imu,
        *,
        connect_timeout=5.0,
        recv_timeout=10.0,
        retry_delay=2.0,
        socket_factory=None,
        log=None,
    ):
        self.host = host
        self.port = port
        self.on_frame = on_frame
        self.on_imu = on_imu
        self.connect_timeout = connect_timeout
        self.recv_timeout = recv_timeout
        self.retry_delay = retry_delay
        self.socket_factory = socket_factory or (
            lambda host, port, timeout: socket.create_connection((host, port), timeout=timeout)
        )
        self.log = log or (lambda level, msg: print(f"[{level}] {msg}", file=sys.stderr))

    def run(self, stop_event):
        while not stop_event.is_set():
            try:
                sock = self.socket_factory(self.host, self.port, self.connect_timeout)
            except OSError as e:
                self.log("error", f"{self.host}:{self.port} 접속 실패: {e} - {self.retry_delay}초 후 재시도")
                if stop_event.wait(self.retry_delay):
                    return
                continue

            self.log("info", f"{self.host}:{self.port} 연결됨")
            try:
                self._stream(sock, stop_event)
            except (ProtocolError, OSError) as e:
                self.log("error", f"연결 끊김: {e}")
            finally:
                sock.close()

            if stop_event.is_set():
                return
            self.log("info", f"{self.retry_delay}초 후 재연결 시도")
            if stop_event.wait(self.retry_delay):
                return

    def _stream(self, sock, stop_event):
        while not stop_event.is_set():
            deadline = time.monotonic() + self.recv_timeout
            msg_type, payload = read_message(lambda n: _recv_exact_before_deadline(sock, n, deadline))
            if msg_type == TYPE_FRAME:
                self.on_frame(decode_frame(payload))
            elif msg_type == TYPE_IMU:
                self.on_imu(decode_imu(payload))
            else:
                self.log("warning", f"알 수 없는 메시지 타입: 0x{msg_type:02x}")


class BridgeNode:
    """CaptureManager가 아니라 ROS2 publisher 쪽 어댑터 - BridgeConnection의 콜백을 받아
    표준 토픽으로 publish하기만 한다 (ADR-0003: 커스텀 어댑터 레이어 없이 토픽 그 자체가 계약)."""

    def __init__(self, node: Node, calibration: dict):
        self.calibration = calibration
        self.image_pub = node.create_publisher(Image, "/camera/image_raw", qos_profile_sensor_data)
        self.info_pub = node.create_publisher(CameraInfo, "/camera/camera_info", qos_profile_sensor_data)
        self.imu_pub = node.create_publisher(Imu, "/imu", qos_profile_sensor_data)

    def on_frame(self, frame):
        self.image_pub.publish(build_image(frame))
        self.info_pub.publish(build_camera_info(frame["timestamp_ns"], self.calibration))

    def on_imu(self, imu):
        self.imu_pub.publish(build_imu(imu))


def _make_ros_logger(node: Node):
    """BridgeConnection의 log(level, msg) 콜백을 node.get_logger()에 연결한다.

    getattr(node.get_logger(), level)(msg) 한 줄로 dispatch하면 실제 실기기에서 크래시가 났다 -
    rclpy 로거가 "몇 번째 줄에서 호출됐는지"로 severity를 기억해뒀다가, 같은 줄에서 severity가
    바뀌면(예: 처음엔 info로 "연결됨", 나중엔 error로 "연결 끊김") ValueError를 던진다. 그래서
    info/warning/error를 각각 다른 줄에서 호출해야 한다."""

    def log(level, msg):
        if level == "info":
            node.get_logger().info(msg)
        elif level == "warning":
            node.get_logger().warning(msg)
        elif level == "error":
            node.get_logger().error(msg)
        else:
            node.get_logger().info(msg)

    return log


def run_node(host, port, calibration_path, connect_timeout, recv_timeout, retry_delay):
    calibration = load_calibration(calibration_path)

    rclpy.init()
    node = rclpy.create_node("ios_bridge")
    bridge = BridgeNode(node, calibration)

    stop_event = threading.Event()
    connection = BridgeConnection(
        host,
        port,
        bridge.on_frame,
        bridge.on_imu,
        connect_timeout=connect_timeout,
        recv_timeout=recv_timeout,
        retry_delay=retry_delay,
        log=_make_ros_logger(node),
    )
    conn_thread = threading.Thread(target=connection.run, args=(stop_event,), daemon=True)
    conn_thread.start()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        conn_thread.join(timeout=connect_timeout + recv_timeout + 1.0)
        if conn_thread.is_alive():
            # _recv_exact_before_deadline()의 recv_timeout 경계보다 오래 살아있다는 건 뭔가 이
            # 상한을 벗어났다는 뜻이다 - node.destroy_node() 이후에도 그 스레드가
            # publish()를 부를 수 있으니 원인 파악용으로 명확히 남긴다.
            node.get_logger().warning("연결 스레드가 예상 시간 안에 종료되지 않음 (데몬 스레드로 계속 실행됨)")
        node.destroy_node()
        rclpy.shutdown()
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("host", help="iproxy로 터널링된 로컬 호스트 (보통 localhost)")
    parser.add_argument("port", type=int, help="iproxy로 터널링된 로컬 포트")
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION, help="CameraInfo YAML 경로 (#5)")
    parser.add_argument("--connect-timeout", type=float, default=5.0, help="접속 시도 타임아웃(초)")
    parser.add_argument("--recv-timeout", type=float, default=10.0, help="수신 타임아웃(초) - 이 시간 동안 데이터가 없으면 끊긴 것으로 보고 재연결")
    parser.add_argument("--retry-delay", type=float, default=2.0, help="재연결 대기 시간(초)")
    args = parser.parse_args()

    return run_node(args.host, args.port, args.calibration, args.connect_timeout, args.recv_timeout, args.retry_delay)


if __name__ == "__main__":
    sys.exit(main())
