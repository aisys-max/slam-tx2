#!/usr/bin/env python3
"""정지 상태로 장시간 기록한 `/imu` rosbag2로 Allan variance를 계산해 ORB-SLAM3 IMU 노이즈
파라미터(NoiseGyro/NoiseAcc/GyroWalk/AccWalk)를 추정한다 (#15).

`euroc_to_rosbag2.py`와 같은 이유로 이 TX2의 ROS2 Foxy 빌드엔 `rosbag2_py`가 없어서, bag의
sqlite3 스토리지를 표준 라이브러리 `sqlite3`로 직접 읽고 `rclpy.serialization.deserialize_message`로
CDR 페이로드를 디코딩한다.

계산 방법 (IEEE-STD-952 overlapping Allan variance):
1. 각 축(x/y/z)의 rate 데이터를 dt로 적분해 "각/속도 적산값" theta[k]를 만든다.
2. 클러스터 크기 m(로그 간격)마다 overlapping AVAR(τ=m*dt)를 계산한다:
   AVAR(τ) = 1/(2τ²(N-2m)) * sum_k (theta[k+2m] - 2*theta[k+m] + theta[k])^2
3. log-log(τ, sqrt(AVAR)) 기울기가 -0.5에 가장 가까운 구간에서 τ=1s 지점 값을 읽어 노이즈
   밀도(N, ORB-SLAM3의 NoiseGyro/NoiseAcc)로, 기울기 +0.5에 가장 가까운 구간에서 τ=3s 지점
   값을 읽어 랜덤워크(K, GyroWalk/AccWalk)로 쓴다 - Allan variance 문헌의 표준 관례.
4. x/y/z 세 축의 값을 평균해 ORB-SLAM3 YAML이 요구하는 스칼라 값을 만든다.

사용법:
    python3 scripts/compute_allan_variance.py <bag 디렉터리>
    (bag 디렉터리 안에 <name>_0.db3와 metadata.yaml이 있어야 함 - `ros2 bag record /imu -o <name>`
    결과물)
"""
import sqlite3
import sys
from pathlib import Path

import numpy as np
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import Imu


def read_imu_bag(bag_dir: Path):
    db3_files = list(bag_dir.glob("*.db3"))
    if not db3_files:
        raise FileNotFoundError(f"{bag_dir}에 .db3 파일이 없음")

    t, acc, gyro = [], [], []
    for db3 in db3_files:
        conn = sqlite3.connect(str(db3))
        cur = conn.cursor()
        cur.execute("SELECT id FROM topics WHERE name = '/imu'")
        row = cur.fetchone()
        if row is None:
            conn.close()
            continue
        topic_id = row[0]
        cur.execute("SELECT timestamp, data FROM messages WHERE topic_id = ? ORDER BY timestamp", (topic_id,))
        for ts_ns, blob in cur.fetchall():
            msg = deserialize_message(bytes(blob), Imu)
            t.append(ts_ns * 1e-9)
            acc.append((msg.linear_acceleration.x, msg.linear_acceleration.y, msg.linear_acceleration.z))
            gyro.append((msg.angular_velocity.x, msg.angular_velocity.y, msg.angular_velocity.z))
        conn.close()

    order = np.argsort(t)
    t = np.array(t)[order]
    acc = np.array(acc)[order]
    gyro = np.array(gyro)[order]
    return t, acc, gyro


def overlapping_allan_deviation(rate, dt, n_clusters=60):
    """rate: 1D 배열(각속도 또는 가속도), dt: 샘플 간격(초). (taus, allan_dev) 반환."""
    n = len(rate)
    theta = np.concatenate([[0.0], np.cumsum(rate) * dt])  # 길이 n+1

    max_m = n // 3
    ms = np.unique(np.logspace(0, np.log10(max_m), n_clusters).astype(int))
    ms = ms[ms >= 1]

    taus, adevs = [], []
    for m in ms:
        tau = m * dt
        k_max = n - 2 * m
        if k_max <= 1:
            continue
        diff = theta[2 * m:2 * m + k_max] - 2 * theta[m:m + k_max] + theta[0:k_max]
        avar = np.sum(diff ** 2) / (2.0 * tau ** 2 * k_max)
        taus.append(tau)
        adevs.append(np.sqrt(avar))

    return np.array(taus), np.array(adevs)


def fit_target_slope(taus, adevs, target_slope, read_tau):
    """log-log 기울기가 target_slope에 가장 가까운 인접 구간을 찾고, 그 구간의 선형 피팅으로
    read_tau 지점의 값을 추정한다."""
    log_t = np.log10(taus)
    log_a = np.log10(adevs)
    slopes = np.diff(log_a) / np.diff(log_t)
    idx = np.argmin(np.abs(slopes - target_slope))
    # idx, idx+1 주변 점 몇 개를 묶어 선형 피팅 (노이즈에 덜 민감하게)
    lo = max(0, idx - 2)
    hi = min(len(taus), idx + 3)
    coeffs = np.polyfit(log_t[lo:hi], log_a[lo:hi], 1)
    value_at_read_tau = 10 ** (coeffs[0] * np.log10(read_tau) + coeffs[1])
    fitted_slope = coeffs[0]
    return value_at_read_tau, fitted_slope


def analyze_axis(rate, dt):
    taus, adevs = overlapping_allan_deviation(rate, dt)
    n_density, n_slope = fit_target_slope(taus, adevs, -0.5, read_tau=1.0)
    k_randomwalk, k_slope = fit_target_slope(taus, adevs, 0.5, read_tau=3.0)
    return n_density, n_slope, k_randomwalk, k_slope


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    bag_dir = Path(sys.argv[1])

    t, acc, gyro = read_imu_bag(bag_dir)
    n = len(t)
    duration = t[-1] - t[0]
    dt = duration / (n - 1)
    print(f"samples: {n}, duration: {duration:.1f}s ({duration/3600:.2f}h), mean dt: {dt*1000:.2f}ms (~{1/dt:.1f}Hz)")
    print()

    gyro_n, acc_n = [], []
    gyro_k, acc_k = [], []
    for axis, label in enumerate("xyz"):
        n_g, slope_n_g, k_g, slope_k_g = analyze_axis(gyro[:, axis], dt)
        n_a, slope_n_a, k_a, slope_k_a = analyze_axis(acc[:, axis], dt)
        gyro_n.append(n_g)
        acc_n.append(n_a)
        gyro_k.append(k_g)
        acc_k.append(k_a)
        print(f"gyro[{label}]: N={n_g:.6e} rad/s/sqrt(Hz) (slope {slope_n_g:+.2f})  "
              f"K={k_g:.6e} rad/s^2/sqrt(Hz) (slope {slope_k_g:+.2f})")
        print(f"acc [{label}]: N={n_a:.6e} m/s^2/sqrt(Hz) (slope {slope_n_a:+.2f})  "
              f"K={k_a:.6e} m/s^3/sqrt(Hz) (slope {slope_k_a:+.2f})")

    print()
    print("=== ORB-SLAM3 YAML 값 (x/y/z 평균) ===")
    print(f"IMU.NoiseGyro: {np.mean(gyro_n):.6e}")
    print(f"IMU.NoiseAcc: {np.mean(acc_n):.6e}")
    print(f"IMU.GyroWalk: {np.mean(gyro_k):.6e}")
    print(f"IMU.AccWalk: {np.mean(acc_k):.6e}")


if __name__ == "__main__":
    main()
