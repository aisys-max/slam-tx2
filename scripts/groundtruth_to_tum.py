#!/usr/bin/env python3
"""EuRoC state_groundtruth_estimate0/data.csv를 TUM 궤적 포맷(timestamp tx ty tz qx qy qz qw)으로
변환한다. EuRoC CSV는 쿼터니언을 w,x,y,z 순서로 주지만 TUM은 x,y,z,w 순서를 쓴다.

사용법: python3 scripts/groundtruth_to_tum.py <state_groundtruth_estimate0/data.csv> <출력 .txt>
"""
import csv
import sys


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <groundtruth data.csv> <output .txt>", file=sys.stderr)
        return 1

    with open(sys.argv[1]) as fin, open(sys.argv[2], "w") as fout:
        reader = csv.reader(row for row in fin if not row.startswith("#"))
        n = 0
        for row in reader:
            ts_ns = int(row[0])
            px, py, pz = row[1], row[2], row[3]
            qw, qx, qy, qz = row[4], row[5], row[6], row[7]
            t_sec = ts_ns / 1e9
            fout.write(f"{t_sec:.6f} {px} {py} {pz} {qx} {qy} {qz} {qw}\n")
            n += 1
    print(f"{n}개 포즈를 TUM 포맷으로 변환했습니다: {sys.argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
