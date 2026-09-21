#!/usr/bin/env python3
"""(#20) bag 재생 중 /camera/image_raw, /imu에 실제로 도착하는 메시지 개수/순서를 측정한다.

best-effort QoS(기본값)로는 재생마다 다른 메시지가 조용히 드랍돼서, 같은 bag을 재생해도
SLAM 노드가 매번 다른 입력을 받는다(docs/imu-init-debug.md 참고). 이 스크립트로 두 번 재생해
결과를 비교하면 그 유실이 실제로 일어나는지, 얼마나 되는지 확인할 수 있다.

사용법 (터미널 A):
    source /mnt/ssd/ros2_foxy/install/setup.bash
    python3 scripts/measure_bag_delivery.py out.txt              # best-effort(기본, 라이브와 동일 QoS)
    python3 scripts/measure_bag_delivery.py out.txt --reliable    # reliable(결정적 재생 테스트용)

터미널 B (터미널 A가 뜬 뒤):
    # best-effort로 측정할 때:
    ros2 bag play <bag>
    # reliable로 측정할 때 (스크립트도 --reliable로 띄웠어야 함):
    ros2 bag play <bag> --qos-profile-overrides-path scripts/qos_reliable_override.yaml

재생이 끝나면 터미널 A를 Ctrl+C로 종료 - out.txt에 도착한 개수와 타임스탬프 시퀀스의 해시가
저장된다. 같은 bag을 두 번 이렇게 측정해서 해시가 같으면 완전히 결정적으로 도착했다는 뜻이다.
"""
import argparse
import sys

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from sensor_msgs.msg import Image, Imu


class DeliveryCounter(Node):
    def __init__(self, qos):
        super().__init__("bag_delivery_counter")
        self.images = []
        self.imus = []
        self.create_subscription(Image, "/camera/image_raw", self.on_img, qos)
        self.create_subscription(Imu, "/imu", self.on_imu, qos)

    def on_img(self, msg):
        self.images.append(msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec)

    def on_imu(self, msg):
        self.imus.append(msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out_path", help="결과를 저장할 파일 경로")
    parser.add_argument(
        "--reliable", action="store_true",
        help="reliable QoS(depth 200)로 구독 - scripts/qos_reliable_override.yaml로 재생한 bag과 짝을 맞출 것"
    )
    args = parser.parse_args()

    if args.reliable:
        qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=200,
        )
    else:
        qos = qos_profile_sensor_data

    rclpy.init()
    node = DeliveryCounter(qos)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass

    with open(args.out_path, "w") as f:
        f.write(f"images={len(node.images)}\n")
        f.write(f"imus={len(node.imus)}\n")
        f.write(f"image_stamps_hash={hash(tuple(node.images))}\n")
        f.write(f"imu_stamps_hash={hash(tuple(node.imus))}\n")
    print(f"저장됨: {args.out_path} (images={len(node.images)}, imus={len(node.imus)})")

    node.destroy_node()
    rclpy.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
