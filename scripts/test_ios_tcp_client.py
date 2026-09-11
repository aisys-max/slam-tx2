#!/usr/bin/env python3
"""docs/ios-tcp-protocol.md 를 구현한 참조 클라이언트 겸 자체 테스트.

- `--self-test`: 실제 iPhone 없이, 프로토콜 문서의 바이트 레이아웃대로 합성 메시지를 만들어
  아래 파서가 정확히 왕복(인코딩 -> 디코딩)하는지 확인한다. ios/SlamCapture/WireProtocol.swift가
  실제로 만드는 바이트와 이 파서가 맞는지는 Swift 코드를 직접 실행해보기 전까지는 "문서 대비
  일치"만 보장한다 - Swift 쪽에서 실제로 검증하려면 --connect를 쓸 것.
- `--connect <host> <port>`: 실제 iPhone 앱(#4)에 접속해서 프레임/IMU를 받아 개수·포맷·
  타임스탬프 단조증가 여부를 출력한다.

사용법:
    python3 scripts/test_ios_tcp_client.py --self-test
    python3 scripts/test_ios_tcp_client.py --connect 192.168.1.42 8765 [--duration 10]
"""
import argparse
import socket
import struct
import sys
import time

TYPE_FRAME = 0x01
TYPE_IMU = 0x02

FRAME_HEADER = struct.Struct(">QIII")   # timestamp_ns, width, height, stride
IMU_PAYLOAD = struct.Struct(">Qdddddd")  # timestamp_ns, wx,wy,wz, ax,ay,az


class ProtocolError(Exception):
    pass


def recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ProtocolError(f"연결이 끊김 ({len(buf)}/{n} 바이트만 받음)")
        buf.extend(chunk)
    return bytes(buf)


def read_message(reader):
    """reader: recv_exact(n) 같은 콜러블. (type, payload) 반환."""
    header = reader(5)
    msg_type, length = struct.unpack(">BI", header)
    payload = reader(length)
    return msg_type, payload


def decode_frame(payload):
    header_size = FRAME_HEADER.size
    timestamp_ns, width, height, stride = FRAME_HEADER.unpack(payload[:header_size])
    pixels = payload[header_size:]
    expected = stride * height
    if len(pixels) != expected:
        raise ProtocolError(f"프레임 픽셀 크기 불일치: 기대 {expected}, 실제 {len(pixels)}")
    return {"timestamp_ns": timestamp_ns, "width": width, "height": height, "stride": stride, "pixels": pixels}


def decode_imu(payload):
    if len(payload) != IMU_PAYLOAD.size:
        raise ProtocolError(f"IMU payload 크기 불일치: 기대 {IMU_PAYLOAD.size}, 실제 {len(payload)}")
    ts, wx, wy, wz, ax, ay, az = IMU_PAYLOAD.unpack(payload)
    return {"timestamp_ns": ts, "angular_velocity": (wx, wy, wz), "linear_acceleration": (ax, ay, az)}


# --- 합성 인코더 (자체 테스트용, docs/ios-tcp-protocol.md 그대로) ---

def encode_message(msg_type, payload):
    return struct.pack(">BI", msg_type, len(payload)) + payload


def encode_frame(timestamp_ns, width, height, stride, pixels):
    payload = FRAME_HEADER.pack(timestamp_ns, width, height, stride) + pixels
    return encode_message(TYPE_FRAME, payload)


def encode_imu(timestamp_ns, angular_velocity, linear_acceleration):
    payload = IMU_PAYLOAD.pack(timestamp_ns, *angular_velocity, *linear_acceleration)
    return encode_message(TYPE_IMU, payload)


def self_test():
    width, height, stride = 8, 4, 8
    pixels = bytes(range(width * height))
    frame_bytes = encode_frame(1_700_000_000_123456789, width, height, stride, pixels)
    imu_bytes = encode_imu(1_700_000_000_123456789, (0.01, -0.02, 0.03), (0.1, -9.7, 0.2))

    stream = frame_bytes + imu_bytes
    pos = 0

    def reader(n):
        nonlocal pos
        chunk = stream[pos:pos + n]
        pos += n
        return chunk

    msg_type, payload = read_message(reader)
    assert msg_type == TYPE_FRAME, msg_type
    frame = decode_frame(payload)
    assert frame["width"] == width and frame["height"] == height and frame["stride"] == stride
    assert frame["pixels"] == pixels
    assert frame["timestamp_ns"] == 1_700_000_000_123456789

    msg_type, payload = read_message(reader)
    assert msg_type == TYPE_IMU, msg_type
    imu = decode_imu(payload)
    assert imu["angular_velocity"] == (0.01, -0.02, 0.03)
    assert imu["linear_acceleration"] == (0.1, -9.7, 0.2)

    assert pos == len(stream), "스트림 끝까지 정확히 소비했는지 확인"

    print("self-test 통과: Frame/IMU 인코딩-디코딩 왕복이 docs/ios-tcp-protocol.md와 일치합니다.")
    return 0


def connect_and_listen(host, port, duration):
    print(f"{host}:{port} 접속 중...")
    sock = socket.create_connection((host, port), timeout=10)
    sock.settimeout(duration + 5)
    print(f"연결됨. {duration}초 동안 수신합니다...")

    frame_count = 0
    imu_count = 0
    last_ts = {"frame": None, "imu": None}
    out_of_order = {"frame": 0, "imu": 0}
    start = time.monotonic()

    try:
        while time.monotonic() - start < duration:
            msg_type, payload = read_message(lambda n: recv_exact(sock, n))
            if msg_type == TYPE_FRAME:
                frame = decode_frame(payload)
                frame_count += 1
                if frame_count <= 3:
                    print(f"  Frame #{frame_count}: {frame['width']}x{frame['height']} "
                          f"stride={frame['stride']} ts={frame['timestamp_ns']}")
                if last_ts["frame"] is not None and frame["timestamp_ns"] < last_ts["frame"]:
                    out_of_order["frame"] += 1
                last_ts["frame"] = frame["timestamp_ns"]
            elif msg_type == TYPE_IMU:
                imu = decode_imu(payload)
                imu_count += 1
                if imu_count <= 3:
                    print(f"  IMU #{imu_count}: ts={imu['timestamp_ns']} "
                          f"w={imu['angular_velocity']} a={imu['linear_acceleration']}")
                if last_ts["imu"] is not None and imu["timestamp_ns"] < last_ts["imu"]:
                    out_of_order["imu"] += 1
                last_ts["imu"] = imu["timestamp_ns"]
            else:
                print(f"알 수 없는 메시지 타입: 0x{msg_type:02x}", file=sys.stderr)
    except socket.timeout:
        pass
    finally:
        sock.close()

    elapsed = time.monotonic() - start
    print(f"\n{elapsed:.1f}초 동안 Frame {frame_count}개 ({frame_count/elapsed:.1f} Hz), "
          f"IMU {imu_count}개 ({imu_count/elapsed:.1f} Hz)")
    print(f"타임스탬프 역전: Frame {out_of_order['frame']}회, IMU {out_of_order['imu']}회")

    if frame_count == 0:
        print("경고: 프레임을 하나도 못 받음", file=sys.stderr)
        return 1
    if imu_count == 0:
        print("경고: IMU 샘플을 하나도 못 받음", file=sys.stderr)
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--connect", nargs=2, metavar=("HOST", "PORT"))
    parser.add_argument("--duration", type=float, default=10.0, help="--connect 수신 시간(초)")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if args.connect:
        host, port = args.connect
        return connect_and_listen(host, int(port), args.duration)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
