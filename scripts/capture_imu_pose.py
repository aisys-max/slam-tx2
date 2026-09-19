#!/usr/bin/env python3
"""지정한 시간(초) 동안 `/imu`를 구독해서 가속도/자이로 평균+표준편차를 출력한다.

정지 자세에서의 중력 벡터를 읽어 `estimate_tbc_rotation.py`의 입력으로 쓰는 용도다 (#15).
표준편차가 크면 그 구간에 흔들림이 있었다는 뜻이고, 자이로 평균이 0에서 멀면 완전히
정지하지 못했다는 뜻이니 다시 측정할 것.

사용법:
    python3 scripts/capture_imu_pose.py <label> <seconds>
"""
import statistics
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Imu


class Capture(Node):
    def __init__(self):
        super().__init__("capture_imu_pose")
        qos = QoSProfile(depth=2000, reliability=ReliabilityPolicy.BEST_EFFORT, history=HistoryPolicy.KEEP_LAST)
        self.acc = []
        self.gyro = []
        self.create_subscription(Imu, "/imu", self.on_imu, qos)

    def on_imu(self, msg):
        a = msg.linear_acceleration
        g = msg.angular_velocity
        self.acc.append((a.x, a.y, a.z))
        self.gyro.append((g.x, g.y, g.z))


def main():
    label = sys.argv[1]
    seconds = float(sys.argv[2])
    rclpy.init()
    node = Capture()
    end = time.time() + seconds
    while time.time() < end:
        rclpy.spin_once(node, timeout_sec=0.05)

    n = len(node.acc)
    if n == 0:
        print(f"[{label}] no IMU samples received")
        rclpy.shutdown()
        return

    axm = statistics.mean(a[0] for a in node.acc)
    aym = statistics.mean(a[1] for a in node.acc)
    azm = statistics.mean(a[2] for a in node.acc)
    axs = statistics.pstdev(a[0] for a in node.acc)
    ays = statistics.pstdev(a[1] for a in node.acc)
    azs = statistics.pstdev(a[2] for a in node.acc)
    gxm = statistics.mean(g[0] for g in node.gyro)
    gym = statistics.mean(g[1] for g in node.gyro)
    gzm = statistics.mean(g[2] for g in node.gyro)

    mag = (axm**2 + aym**2 + azm**2) ** 0.5

    print(f"[{label}] n={n}")
    print(f"  acc mean = ({axm:+.4f}, {aym:+.4f}, {azm:+.4f})  |g|={mag:.4f} m/s^2")
    print(f"  acc std  = ({axs:.4f}, {ays:.4f}, {azs:.4f})  (std가 크면 흔들렸다는 뜻)")
    print(f"  gyro mean = ({gxm:+.4f}, {gym:+.4f}, {gzm:+.4f}) rad/s (0에 가까워야 정지 상태)")

    rclpy.shutdown()


if __name__ == "__main__":
    main()
