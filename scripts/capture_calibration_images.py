#!/usr/bin/env python3
"""캘리브레이션용 체커보드 이미지를 iPhone 캡처 앱(#4)에서 받아 저장한다.

docs/ios-tcp-protocol.md의 Frame 메시지(mono8)를 test_ios_tcp_client.py의 파서로 디코딩해
일정 간격으로 PNG로 저장한다. 촬영 절차는 docs/camera-calibration.md 참고.

사용법 (iPhone 앱 실행 후, 같은 Wi-Fi에서):
    python3 scripts/capture_calibration_images.py <iPhone IP> 8765 \\
        --out calib_images/ --count 20 --interval 2
"""
import argparse
import socket
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from test_ios_tcp_client import TYPE_FRAME, decode_frame, read_message, recv_exact  # noqa: E402


def frame_to_image(frame):
    """decode_frame() 결과(mono8, stride 포함)를 (height, width) numpy 배열로 변환."""
    raw = np.frombuffer(frame["pixels"], dtype=np.uint8).reshape(frame["height"], frame["stride"])
    return raw[:, : frame["width"]]


def capture(host, port, out_dir, count, interval):
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"{host}:{port} 접속 중...")
    sock = socket.create_connection((host, port), timeout=10)
    sock.settimeout(interval + 10)
    print(f"연결됨. 체커보드를 여러 각도/거리로 움직이며 {interval}초 간격으로 {count}장을 저장합니다.")

    saved = 0
    last_save = 0.0
    try:
        while saved < count:
            msg_type, payload = read_message(lambda n: recv_exact(sock, n))
            if msg_type != TYPE_FRAME:
                continue
            frame = decode_frame(payload)
            now = time.monotonic()
            if now - last_save < interval:
                continue
            img = frame_to_image(frame)
            path = out_dir / f"calib_{saved:03d}_{frame['timestamp_ns']}.png"
            cv2.imwrite(str(path), img)
            saved += 1
            last_save = now
            print(f"  저장 {saved}/{count}: {path.name} ({frame['width']}x{frame['height']})")
    finally:
        sock.close()

    print(f"\n완료: {saved}장을 {out_dir}에 저장함.")
    if saved < count:
        print("경고: 목표 장수를 채우지 못하고 연결이 끊겼습니다.", file=sys.stderr)
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("host")
    parser.add_argument("port", type=int)
    parser.add_argument("--out", type=Path, default=Path("calib_images"), help="저장 디렉터리")
    parser.add_argument("--count", type=int, default=20, help="저장할 이미지 장수")
    parser.add_argument("--interval", type=float, default=2.0, help="저장 간격(초) — 체커보드를 옮길 시간")
    args = parser.parse_args()

    return capture(args.host, args.port, args.out, args.count, args.interval)


if __name__ == "__main__":
    sys.exit(main())
