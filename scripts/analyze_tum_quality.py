#!/usr/bin/env python3
"""TUM 궤적 파일(`record_trajectory_tum.py`의 출력)의 궤적 품질을 정량 점검한다.

지상 참값(ground truth) 없이도 잡아낼 수 있는 이상 징후 세 가지를 검출한다 (#15):

1. **리셋**: 위치가 갑자기 (0, 0, 0)으로 떨어지는 지점 — SLAM 노드가 맵을 재초기화하면서
   포즈가 새 좌표계 원점 근처로 튄 흔적.
2. **발행 gap**: 연속된 두 포즈 사이의 시간 간격이 비정상적으로 큰 구간 — 트래킹이 LOST
   상태였던 동안 `/orb_slam3/trajectory`에 아무것도 발행되지 않아 RViz에서 궤적이 끊겨
   보이는 원인.
3. **순간 점프**: 짧은 시간 안에 위치가 크게 이동한 구간 — 좌표계가 바뀐 포즈가 이전
   포즈 뒤에 이어붙었을 때 나타나는 징후.

셋 다 "리셋이 잦고 그걸 궤적이 구분하지 않는다"는 근본 원인의 서로 다른 증상이다 —
`monocular-inertial-slam-node.cpp`의 리셋 시 궤적 초기화 수정(#15) 전/후 비교나, 향후
Tbc/IMU 노이즈 재측정 전/후 비교에 회귀 신호로 쓸 수 있다.

사용법:
    python3 scripts/analyze_tum_quality.py <trajectory.tum> [<trajectory2.tum> ...]
    python3 scripts/analyze_tum_quality.py --max-gap 0.5 --max-jump 0.5 <trajectory.tum>

이상 징후가 하나도 없으면 각 파일에 대해 exit code 0, 하나라도 있으면 1을 반환한다
(CI/스크립트에서 pass/fail 신호로 쓸 수 있게).
"""
import argparse
import math
import sys


def read_tum(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            rows.append([float(v) for v in line.split()])
    return rows


def is_zero_pos(row, eps=1e-9):
    return all(abs(v) < eps for v in row[1:4])


def analyze(path, max_gap, max_jump):
    rows = read_tum(path)
    result = {"path": path, "rows": len(rows), "resets": [], "gaps": [], "jumps": []}
    if len(rows) < 2:
        return result

    prev = rows[0]
    for i, row in enumerate(rows[1:], start=1):
        dt = row[0] - prev[0]
        dx, dy, dz = row[1] - prev[1], row[2] - prev[2], row[3] - prev[3]
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)

        if is_zero_pos(row) and not is_zero_pos(prev):
            result["resets"].append((i, row[0]))
        if dt > max_gap:
            result["gaps"].append((i, row[0], dt))
        if dist > max_jump and dt < 2.0:
            result["jumps"].append((i, row[0], dist, dt))

        prev = row
    return result


def print_report(result):
    print(f"=== {result['path']} ===")
    print(f"rows: {result['rows']}")
    for i, t in result["resets"]:
        print(f"  RESET  row={i} t={t:.3f}")
    for i, t, dt in result["gaps"]:
        print(f"  GAP    row={i} t={t:.3f} dt={dt:.3f}s")
    for i, t, dist, dt in result["jumps"]:
        print(f"  JUMP   row={i} t={t:.3f} dist={dist:.3f}m dt={dt:.3f}s")
    total = len(result["resets"]) + len(result["gaps"]) + len(result["jumps"])
    print(f"total anomalies: {total}")
    print()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("trajectories", nargs="+", help="분석할 TUM 궤적 파일 경로(들)")
    parser.add_argument("--max-gap", type=float, default=0.5, help="이보다 큰 발행 간격(초)을 gap으로 표시 (기본 0.5)")
    parser.add_argument("--max-jump", type=float, default=0.5, help="이보다 큰 순간 이동(m)을 jump로 표시 (기본 0.5)")
    args = parser.parse_args()

    any_anomaly = False
    for path in args.trajectories:
        result = analyze(path, args.max_gap, args.max_jump)
        print_report(result)
        if result["resets"] or result["gaps"] or result["jumps"]:
            any_anomaly = True

    sys.exit(1 if any_anomaly else 0)


if __name__ == "__main__":
    main()
