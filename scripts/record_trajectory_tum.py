#!/usr/bin/env python3
"""/orb_slam3/trajectory(nav_msgs/Path)를 실시간으로 TUM 포맷 파일에 계속 덮어써서 저장한다.

ORB-SLAM3의 SaveKeyFrameTrajectoryTUM()은 프로세스 종료 시점의 "현재 활성 맵"만 저장하는데,
IMU 초기화가 자주 리셋되는 라이브 세션에서는 하필 종료 시점에 맵이 막 리셋된 빈 상태일 수 있어
파일이 비어버린다 (aisys-max/slam-tx2#7, 2026-09-17 라이브 세션에서 실제로 발생). pathMsg_는
SLAM 노드 안에서 리셋과 무관하게 계속 누적되는 값이므로, 이 값을 매 콜백마다 파일로 흘려두면
프로세스를 언제 죽이든 그 시점까지의 전체 궤적이 남는다.

사용법:
    python3 scripts/record_trajectory_tum.py <output.tum>
    (Ctrl+C로 종료 - 종료 시점까지 받은 마지막 Path를 최종적으로 한 번 더 저장한다)
"""
import sys

import rclpy
from rclpy.node import Node
from nav_msgs.msg import Path


def pose_to_tum_line(pose_stamped) -> str:
    t = pose_stamped.header.stamp.sec + pose_stamped.header.stamp.nanosec * 1e-9
    p = pose_stamped.pose.position
    q = pose_stamped.pose.orientation
    return f"{t:.9f} {p.x:.9f} {p.y:.9f} {p.z:.9f} {q.x:.9f} {q.y:.9f} {q.z:.9f} {q.w:.9f}\n"


def write_tum(path: str, poses) -> None:
    with open(path, "w") as f:
        for pose_stamped in poses:
            f.write(pose_to_tum_line(pose_stamped))


def main():
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <output.tum>", file=sys.stderr)
        sys.exit(1)
    out_path = sys.argv[1]

    rclpy.init()
    node = Node("trajectory_tum_recorder")
    state = {"last_poses": []}

    def cb(msg: Path):
        state["last_poses"] = msg.poses
        write_tum(out_path, msg.poses)

    node.create_subscription(Path, "/orb_slam3/trajectory", cb, 10)
    print(f"[record_trajectory_tum] /orb_slam3/trajectory -> {out_path} 로 계속 저장합니다. Ctrl+C로 종료.")
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        write_tum(out_path, state["last_poses"])
        print(f"[record_trajectory_tum] 최종 {len(state['last_poses'])}개 pose 저장함: {out_path}")
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
