#!/usr/bin/env python3
"""두 TUM 궤적(timestamp tx ty tz qx qy qz qw)의 ATE(Absolute Trajectory Error)를 계산한다.

TUM RGB-D 벤치마크의 표준 절차(Sturm et al. 2012)를 그대로 구현한다:
1. 타임스탬프로 두 궤적을 매칭(최근접, 최대 시간차 이내)
2. Umeyama(1991) 방법으로 SE(3) 정합(회전+이동, 스케일 없음)
   - ORB-SLAM3 mono-inertial은 IMU 덕분에 metric scale을 직접 추정하므로 스케일 정합은 하지 않는다
     (모노큘러 단독이면 스케일이 불명확해 Sim(3) 정합이 필요하지만, 이 프로젝트는 IMU를 쓴다).
3. 정합 후 위치 오차의 RMSE를 ATE로 보고한다.

사용법:
    python3 scripts/evaluate_ate.py <estimated.txt> <groundtruth.txt> [--max-diff 0.02]
"""
import argparse
import numpy as np


def read_tum(path):
    poses = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            t = float(parts[0])
            xyz = np.array([float(v) for v in parts[1:4]])
            poses[t] = xyz
    return poses


def associate(est, gt, max_diff):
    gt_times = sorted(gt.keys())
    gt_times_arr = np.array(gt_times)
    matches = []
    for t_est in sorted(est.keys()):
        idx = int(np.argmin(np.abs(gt_times_arr - t_est)))
        diff = abs(gt_times_arr[idx] - t_est)
        if diff <= max_diff:
            matches.append((t_est, gt_times[idx]))
    return matches


def umeyama_alignment(src, dst):
    """src, dst: Nx3. src를 dst에 맞추는 회전 R, 이동 t를 반환 (스케일 없음)."""
    mu_src = src.mean(axis=0)
    mu_dst = dst.mean(axis=0)
    src_centered = src - mu_src
    dst_centered = dst - mu_dst

    cov = dst_centered.T @ src_centered / len(src)
    U, _, Vt = np.linalg.svd(cov)
    S = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S[2, 2] = -1
    R = U @ S @ Vt
    t = mu_dst - R @ mu_src
    return R, t


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("estimated")
    parser.add_argument("groundtruth")
    parser.add_argument("--max-diff", type=float, default=0.02, help="매칭 최대 시간차(초)")
    args = parser.parse_args()

    est = read_tum(args.estimated)
    gt = read_tum(args.groundtruth)
    matches = associate(est, gt, args.max_diff)

    if len(matches) < 3:
        print(f"매칭된 포즈가 너무 적습니다 ({len(matches)}개) - 타임스탬프 기준이 맞는지 확인하세요.")
        return 1

    src = np.array([est[t_est] for t_est, _ in matches])
    dst = np.array([gt[t_gt] for _, t_gt in matches])

    R, t = umeyama_alignment(src, dst)
    aligned = (R @ src.T).T + t

    errors = np.linalg.norm(aligned - dst, axis=1)
    rmse = np.sqrt(np.mean(errors ** 2))
    mean_err = np.mean(errors)
    median_err = np.median(errors)
    max_err = np.max(errors)

    print(f"매칭된 포즈: {len(matches)}개 (추정 궤적 {len(est)}개 / GT {len(gt)}개 중)")
    print(f"ATE RMSE:   {rmse:.4f} m")
    print(f"ATE mean:   {mean_err:.4f} m")
    print(f"ATE median: {median_err:.4f} m")
    print(f"ATE max:    {max_err:.4f} m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
