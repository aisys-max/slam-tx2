#!/usr/bin/env python3
"""정지 자세 3가지에서 읽은 중력 벡터로 카메라-IMU 회전(Tbc의 회전 성분)을 추정한다 (#15).

Kalibr 등 외부 캘리브레이션 도구 없이, 아래 세 자세에서 `/imu`의 `linear_acceleration` 평균을
입력으로 받아 계산한다 (평행이동은 폰 내부에서 카메라-IMU가 몇 mm 떨어진 수준이라 0으로 근사 -
이 스크립트는 회전만 추정한다):

1. **pose_down**  : 카메라(후면)가 바닥을 향하게(화면이 위로 가게) 눕힘 → 중력이 카메라 +Z(광축, 화면
   안쪽 방향)와 같은 방향
2. **pose_up**    : 뒤집어서 카메라가 하늘을 향하게 눕힘 → 중력이 카메라 -Z 방향 (bias 상쇄용 검증 측정)
3. **pose_level** : 폰을 세워서 카메라가 수평 정면을 향하고 폰 상단이 위를 향하게 → 중력이 카메라
   +Y(이미지 아래쪽) 방향

세 값 모두 `scripts/capture_imu_pose.py <label> <seconds>`로 캡처한 `acc mean` 벡터를 그대로
넣으면 된다.

사용법:
    python3 scripts/estimate_tbc_rotation.py \\
        --pose-down -0.1372 0.0528 -9.8033 \\
        --pose-up 0.1653 0.0584 9.8477 \\
        --pose-level -9.7764 0.0926 0.4249
"""
import argparse

import numpy as np


def normalize(v):
    v = np.array(v, dtype=float)
    return v / np.linalg.norm(v)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pose-down", nargs=3, type=float, required=True, metavar=("X", "Y", "Z"))
    parser.add_argument("--pose-up", nargs=3, type=float, required=True, metavar=("X", "Y", "Z"))
    parser.add_argument("--pose-level", nargs=3, type=float, required=True, metavar=("X", "Y", "Z"))
    args = parser.parse_args()

    v_down = normalize(args.pose_down)
    v_up = normalize(args.pose_up)
    v_level = normalize(args.pose_level)

    # bias 상쇄: pose_down과 -pose_up은 이론상 같은 방향(카메라 +Z = 중력 방향)이어야 하므로 평균낸다.
    col_z = normalize(v_down - v_up)
    col_y = v_level
    # 오른손 좌표계 가정(OpenCV/카메라 표준: X=오른쪽, Y=아래, Z=광축) - x = y cross z
    col_x = normalize(np.cross(col_y, col_z))
    # col_y를 col_x, col_z에 정확히 직교하도록 재계산(측정 오차로 완벽히 직교하지 않을 수 있음)
    col_y = normalize(np.cross(col_z, col_x))

    R = np.column_stack([col_x, col_y, col_z])

    print("R_bc (camera -> IMU/body frame), 열 = [Xc, Yc, Zc]가 매핑되는 방향:")
    print(R)
    print()
    print(f"det(R) = {np.linalg.det(R):.6f} (1에 가까워야 정상적인 회전)")
    print(f"orthogonality error = {np.max(np.abs(R.T @ R - np.eye(3))):.6f} (0에 가까울수록 좋음)")
    print()
    print("pose_down / pose_up bias 상쇄 확인 (같은 방향이어야 함):")
    print(f"  v_down = {v_down}")
    print(f"  -v_up  = {-v_up}")
    print(f"  각도 차이: {np.degrees(np.arccos(np.clip(np.dot(v_down, -v_up), -1, 1))):.2f}도")
    print()
    print("ORB-SLAM3 YAML Tbc data 필드용 (평행이동 0 근사, 4x4 row-major):")
    data = list(R[0]) + [0.0] + list(R[1]) + [0.0] + list(R[2]) + [0.0] + [0.0, 0.0, 0.0, 1.0]
    print("data: [" + ", ".join(f"{v: .6f}" for v in data) + "]")


if __name__ == "__main__":
    main()
