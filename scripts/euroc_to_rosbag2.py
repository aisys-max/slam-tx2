#!/usr/bin/env python3
"""EuRoC MAV(ASL 포맷) 시퀀스를 프로젝트 표준 센서 토픽(docs/ros2-topic-contract.md)을 담은
rosbag2(sqlite3)로 변환한다.

이 TX2의 ROS2 Foxy 빌드에는 rosbag2_py(파이썬 바인딩)가 없어서 - Foxy 시점엔 아직 추가되지
않았다 - sqlite3 표준 라이브러리로 rosbag2의 sqlite3 스토리지 포맷(topics/messages 테이블,
metadata.yaml)을 직접 만든다. 스키마는 `ros2 bag record`로 만든 실제 bag을 열어 확인했다:

    CREATE TABLE topics(id INTEGER PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL,
                         serialization_format TEXT NOT NULL, offered_qos_profiles TEXT NOT NULL)
    CREATE TABLE messages(id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL,
                           timestamp INTEGER NOT NULL, data BLOB NOT NULL)

사용법 (ROS2 Foxy 워크스페이스를 source한 뒤):
    python3 scripts/euroc_to_rosbag2.py <EuRoC mav0 디렉터리> <출력 bag 디렉터리>
"""
import csv
import sqlite3
import sys
import yaml
from pathlib import Path

import cv2

from rclpy.serialization import serialize_message
from sensor_msgs.msg import Image, Imu, CameraInfo
from std_msgs.msg import Header

FRAME_ID = "camera_link"  # docs/ros2-topic-contract.md: 프레임 좌표계는 이번 MVP 범위에서 고정


def stamp_from_ns(msg_header: Header, ts_ns: int) -> None:
    msg_header.stamp.sec = ts_ns // 1_000_000_000
    msg_header.stamp.nanosec = ts_ns % 1_000_000_000
    msg_header.frame_id = FRAME_ID


def load_camera_info(cam0_dir: Path):
    with open(cam0_dir / "sensor.yaml") as f:
        sensor = yaml.safe_load(f)
    fx, fy, cx, cy = sensor["intrinsics"]
    k1, k2, p1, p2 = sensor["distortion_coefficients"]
    width, height = sensor["resolution"]
    return width, height, fx, fy, cx, cy, k1, k2, p1, p2


def build_camera_info(ts_ns: int, calib) -> CameraInfo:
    width, height, fx, fy, cx, cy, k1, k2, p1, p2 = calib
    msg = CameraInfo()
    stamp_from_ns(msg.header, ts_ns)
    msg.width = width
    msg.height = height
    msg.distortion_model = "plumb_bob"
    msg.d = [k1, k2, p1, p2, 0.0]
    msg.k = [fx, 0.0, cx, 0.0, fy, cy, 0.0, 0.0, 1.0]
    msg.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
    msg.p = [fx, 0.0, cx, 0.0, 0.0, fy, cy, 0.0, 0.0, 0.0, 1.0, 0.0]
    return msg


def iter_images(cam0_dir: Path):
    with open(cam0_dir / "data.csv") as f:
        reader = csv.reader(row for row in f if not row.startswith("#"))
        for ts_str, filename in reader:
            yield int(ts_str), cam0_dir / "data" / filename


def iter_imu(imu0_dir: Path):
    with open(imu0_dir / "data.csv") as f:
        reader = csv.reader(row for row in f if not row.startswith("#"))
        for row in reader:
            ts_str, wx, wy, wz, ax, ay, az = row
            yield int(ts_str), float(wx), float(wy), float(wz), float(ax), float(ay), float(az)


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <EuRoC mav0 dir> <output bag dir>", file=sys.stderr)
        return 1

    mav0_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    cam0_dir = mav0_dir / "cam0"
    imu0_dir = mav0_dir / "imu0"

    if out_dir.exists():
        print(f"출력 디렉터리가 이미 존재합니다: {out_dir}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True)

    calib = load_camera_info(cam0_dir)
    width, height = calib[0], calib[1]

    db_path = out_dir / f"{out_dir.name}_0.db3"
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    cur.execute(
        "CREATE TABLE topics(id INTEGER PRIMARY KEY,name TEXT NOT NULL,type TEXT NOT NULL,"
        "serialization_format TEXT NOT NULL,offered_qos_profiles TEXT NOT NULL)"
    )
    cur.execute(
        "CREATE TABLE messages(id INTEGER PRIMARY KEY,topic_id INTEGER NOT NULL,"
        "timestamp INTEGER NOT NULL, data BLOB NOT NULL)"
    )

    topics = {
        "/camera/image_raw": "sensor_msgs/msg/Image",
        "/camera/camera_info": "sensor_msgs/msg/CameraInfo",
        "/imu": "sensor_msgs/msg/Imu",
    }
    topic_ids = {}
    for name, type_ in topics.items():
        cur.execute(
            "INSERT INTO topics (name, type, serialization_format, offered_qos_profiles) "
            "VALUES (?, ?, 'cdr', '')",
            (name, type_),
        )
        topic_ids[name] = cur.lastrowid

    print("이미지/CameraInfo 메시지 준비 중...")
    rows = []
    n_images = 0
    for ts_ns, png_path in iter_images(cam0_dir):
        img = cv2.imread(str(png_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            print(f"이미지를 읽을 수 없음, 건너뜀: {png_path}", file=sys.stderr)
            continue
        if img.shape[1] != width or img.shape[0] != height:
            print(f"경고: {png_path} 크기가 sensor.yaml과 다름 ({img.shape[1]}x{img.shape[0]})", file=sys.stderr)

        image_msg = Image()
        stamp_from_ns(image_msg.header, ts_ns)
        image_msg.height = img.shape[0]
        image_msg.width = img.shape[1]
        image_msg.encoding = "mono8"
        image_msg.is_bigendian = 0
        image_msg.step = img.shape[1]
        image_msg.data = img.tobytes()
        rows.append((topic_ids["/camera/image_raw"], ts_ns, serialize_message(image_msg)))

        info_msg = build_camera_info(ts_ns, calib)
        rows.append((topic_ids["/camera/camera_info"], ts_ns, serialize_message(info_msg)))
        n_images += 1

    print(f"IMU 메시지 준비 중... ({n_images}개 프레임 변환 완료)")
    n_imu = 0
    for ts_ns, wx, wy, wz, ax, ay, az in iter_imu(imu0_dir):
        imu_msg = Imu()
        stamp_from_ns(imu_msg.header, ts_ns)
        imu_msg.angular_velocity.x = wx
        imu_msg.angular_velocity.y = wy
        imu_msg.angular_velocity.z = wz
        imu_msg.linear_acceleration.x = ax
        imu_msg.linear_acceleration.y = ay
        imu_msg.linear_acceleration.z = az
        imu_msg.orientation_covariance[0] = -1.0  # orientation 미사용 (docs/ros2-topic-contract.md)
        rows.append((topic_ids["/imu"], ts_ns, serialize_message(imu_msg)))
        n_imu += 1

    print(f"{len(rows)}개 메시지를 타임스탬프 순으로 정렬해 기록합니다...")
    rows.sort(key=lambda r: r[1])
    cur.executemany("INSERT INTO messages (topic_id, timestamp, data) VALUES (?, ?, ?)", rows)
    con.commit()

    t_start = rows[0][1]
    t_end = rows[-1][1]
    counts = {name: sum(1 for r in rows if r[0] == tid) for name, tid in topic_ids.items()}

    topics_yaml = "\n".join(
        f"""    - topic_metadata:
        name: {name}
        type: {type_}
        serialization_format: cdr
        offered_qos_profiles: ""
      message_count: {counts[name]}"""
        for name, type_ in topics.items()
    )
    metadata = f"""rosbag2_bagfile_information:
  version: 4
  storage_identifier: sqlite3
  relative_file_paths:
    - {db_path.name}
  duration:
    nanoseconds: {t_end - t_start}
  starting_time:
    nanoseconds_since_epoch: {t_start}
  message_count: {len(rows)}
  topics_with_message_count:
{topics_yaml}
  compression_format: ""
  compression_mode: ""
"""
    (out_dir / "metadata.yaml").write_text(metadata)

    con.close()
    print(f"완료: {out_dir} ({n_images} frames, {n_imu} IMU samples, {len(rows)} messages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
