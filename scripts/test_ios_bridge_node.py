#!/usr/bin/env python3
"""ios_bridge_node.py 단위 테스트 (#6).

메시지 변환 함수(build_image/build_camera_info/build_imu)와 BridgeConnection의 재연결 상태
머신을 실제 소켓/iPhone/ROS2 노드 없이 검증한다. sensor_msgs 메시지 타입을 생성하므로 ROS2
Foxy 워크스페이스를 source한 상태에서 실행해야 한다 (scripts/euroc_to_rosbag2.py와 동일한 전제).

사용법:
    source /mnt/ssd/ros2_foxy/install/setup.bash
    python3 scripts/test_ios_bridge_node.py
"""
import os
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import rclpy  # noqa: E402

from ios_bridge_node import (  # noqa: E402
    BridgeConnection,
    _make_ros_logger,
    build_camera_info,
    build_image,
    build_imu,
    load_calibration,
)
from test_ios_tcp_client import encode_frame, encode_imu  # noqa: E402


def test_build_image():
    stride, height, width = 648, 2, 640  # stride > width: 카메라가 행마다 패딩을 넣는 흔한 경우
    pixels = bytes(i % 256 for i in range(stride * height))
    frame = {
        "timestamp_ns": 1_700_000_000_123456789,
        "width": width,
        "height": height,
        "stride": stride,
        "pixels": pixels,
    }
    msg = build_image(frame)
    assert msg.encoding == "mono8"
    assert msg.width == width and msg.height == height
    assert msg.step == stride, "step은 stride(패딩 포함) 그대로여야 한다 - width를 쓰면 정렬이 깨진다"
    assert bytes(msg.data) == pixels
    assert msg.header.frame_id == "camera_link"
    assert msg.header.stamp.sec == 1_700_000_000
    assert msg.header.stamp.nanosec == 123456789
    print("test_build_image 통과")


def test_build_camera_info():
    calibration = {
        "width": 640,
        "height": 480,
        "distortion_model": "plumb_bob",
        "D": [0.1, -0.2, 0.001, 0.002, 0.05],
        "K": [500.0, 0.0, 320.0, 0.0, 500.0, 240.0, 0.0, 0.0, 1.0],
        "R": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        "P": [500.0, 0.0, 320.0, 0.0, 0.0, 500.0, 240.0, 0.0, 0.0, 0.0, 1.0, 0.0],
    }
    msg = build_camera_info(1_700_000_000_000000000, calibration)
    assert msg.width == 640 and msg.height == 480
    assert msg.distortion_model == "plumb_bob"
    assert list(msg.d) == calibration["D"]
    assert list(msg.k) == calibration["K"]
    assert list(msg.r) == calibration["R"]
    assert list(msg.p) == calibration["P"]
    assert msg.header.frame_id == "camera_link"
    print("test_build_camera_info 통과")


def test_build_imu():
    imu = {
        "timestamp_ns": 1_700_000_000_500000000,
        "angular_velocity": (0.01, -0.02, 0.03),
        "linear_acceleration": (0.1, -9.7, 0.2),
    }
    msg = build_imu(imu)
    assert (msg.angular_velocity.x, msg.angular_velocity.y, msg.angular_velocity.z) == imu["angular_velocity"]
    assert (msg.linear_acceleration.x, msg.linear_acceleration.y, msg.linear_acceleration.z) == imu["linear_acceleration"]
    assert msg.orientation_covariance[0] == -1.0, "orientation 미사용 표시 (docs/ros2-topic-contract.md)"
    assert msg.header.frame_id == "camera_link"
    print("test_build_imu 통과")


def test_load_calibration_rejects_malformed_yaml():
    """K/R/P는 sensor_msgs/CameraInfo IDL에서 고정 길이 배열이라, 길이가 틀리면 publish 시점의
    알 수 없는 에러 대신 로드 시점에 어떤 필드가 왜 틀렸는지 밝혀야 한다."""
    bad_yaml = (
        "width: 640\nheight: 480\ndistortion_model: plumb_bob\n"
        "D: [0.0, 0.0, 0.0, 0.0, 0.0]\n"
        "K: [1.0, 0.0, 0.0]\n"  # 9개여야 하는데 3개뿐
        "R: [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]\n"
        "P: [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0]\n"
    )
    fd, path = tempfile.mkstemp(suffix=".yaml")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(bad_yaml)
        try:
            load_calibration(path)
            assert False, "길이가 틀린 K는 ValueError를 내야 한다"
        except ValueError as e:
            assert "K" in str(e)
    finally:
        os.unlink(path)
    print("test_load_calibration_rejects_malformed_yaml 통과")


def test_load_real_calibration_file():
    """#5에서 커밋된 실제 캘리브레이션 결과가 여전히 문제없이 로드되는지 (회귀 확인)."""
    path = Path(__file__).parent.parent / "calibration" / "iphone_xs_max_back_camera.yaml"
    calibration = load_calibration(path)
    assert calibration["width"] == 640 and calibration["height"] == 480
    print("test_load_real_calibration_file 통과")


def test_ros_logger_survives_alternating_severities():
    """실기기에서 재현된 버그: node.get_logger()를 한 줄에서 getattr(logger, level)(msg)로
    dispatch하면, rclpy가 호출부 줄 번호로 severity를 기억해뒀다가 같은 줄에서 severity가
    바뀔 때(info -> error) ValueError('Logger severity cannot be changed between calls.')를
    던진다. _make_ros_logger()는 레벨마다 다른 줄에서 호출해 이를 피해야 한다."""
    rclpy.init()
    try:
        node = rclpy.create_node("test_ios_bridge_logger")
        try:
            log = _make_ros_logger(node)
            log("info", "연결됨")
            log("error", "연결 끊김: 테스트")  # 버그가 있었다면 여기서 ValueError
            log("warning", "재연결 시도")
            log("info", "연결됨")
        finally:
            node.destroy_node()
    finally:
        rclpy.shutdown()
    print("test_ros_logger_survives_alternating_severities 통과")


class FakeSocket:
    """recv()가 주어진 바이트 스트림을 순서대로 반환하다가 소진되면 지정한 예외를 던져
    실제 연결 끊김(ConnectionResetError 등)을 흉내낸다."""

    def __init__(self, data, disconnect_exc):
        self._data = data
        self._pos = 0
        self._disconnect_exc = disconnect_exc
        self.timeout = None

    def settimeout(self, t):
        self.timeout = t

    def recv(self, n):
        if self._pos >= len(self._data):
            raise self._disconnect_exc
        chunk = self._data[self._pos : self._pos + n]
        self._pos += len(chunk)
        return chunk

    def close(self):
        pass


def test_reconnect_and_resume():
    """접속 실패 -> 재시도 -> 연결 -> 중간에 끊김 -> 재연결 -> 재개까지 상태 머신을 검증한다.
    #6 acceptance criteria: 끊기면 명확히 실패하고 재연결되면 정상 재개, 무한 대기 없음."""
    frame1 = encode_frame(1, 2, 1, 2, b"\x01\x02")
    imu1 = encode_imu(2, (0.0, 0.0, 0.0), (0.0, 0.0, 9.8))
    frame2 = encode_frame(3, 2, 1, 2, b"\x03\x04")

    sock1 = FakeSocket(frame1 + imu1, disconnect_exc=ConnectionResetError("simulated drop"))
    sock2 = FakeSocket(frame2, disconnect_exc=ConnectionResetError("simulated drop"))

    connect_calls = [ConnectionRefusedError("no route to host"), sock1, sock2]

    def fake_socket_factory(host, port, timeout):
        action = connect_calls.pop(0)
        if isinstance(action, Exception):
            raise action
        return action

    frames_received = []
    imu_received = []
    stop_event = threading.Event()

    def on_frame(frame):
        frames_received.append(frame)
        if len(frames_received) == 2:
            stop_event.set()

    def on_imu(imu):
        imu_received.append(imu)

    logs = []
    connection = BridgeConnection(
        "fake-host",
        1234,
        on_frame,
        on_imu,
        connect_timeout=1.0,
        recv_timeout=1.0,
        retry_delay=0.01,  # 테스트를 빠르게 하려고 짧게 잡음 - 실제로는 CLI --retry-delay로 조정
        socket_factory=fake_socket_factory,
        log=lambda level, msg: logs.append((level, msg)),
    )
    connection.run(stop_event)

    assert connect_calls == [], "connect가 정확히 3번(실패 1, 성공 2) 시도돼야 한다"
    assert [f["timestamp_ns"] for f in frames_received] == [1, 3], "끊김 이후에도 다음 프레임을 이어받아야 한다"
    assert len(imu_received) == 1 and imu_received[0]["timestamp_ns"] == 2

    # connect/recv 모두 타임아웃이 실제로 걸렸는지 (무한 대기 없음 요구사항의 핵심 근거).
    # _recv_exact_before_deadline()은 메시지 하나를 읽는 동안 남은 시간을 recv()마다 다시
    # 계산해서 넘기므로 recv_timeout보다 살짝 작은 값이 찍힌다 (경과 시간만큼 줄어듦).
    assert sock1.timeout is not None and 0 < sock1.timeout <= 1.0
    assert sock2.timeout is not None and 0 < sock2.timeout <= 1.0

    assert any("접속 실패" in msg for _, msg in logs), "접속 실패가 명확히 로그로 남아야 한다"
    assert any("연결 끊김" in msg for _, msg in logs), "끊김이 명확히 로그로 남아야 한다"
    print("test_reconnect_and_resume 통과")


def self_test():
    test_build_image()
    test_build_camera_info()
    test_build_imu()
    test_load_calibration_rejects_malformed_yaml()
    test_load_real_calibration_file()
    test_ros_logger_survives_alternating_severities()
    test_reconnect_and_resume()
    print("모든 테스트 통과")
    return 0


if __name__ == "__main__":
    sys.exit(self_test())
