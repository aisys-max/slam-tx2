# 프로젝트 표준 센서 토픽 계약

> English version [here](ros2-topic-contract.md).

브리지 노드, SLAM 노드, `ros2 bag record`/`play` 모두 이 계약을 따른다. 라이브 소스와 rosbag2 재생이 이 토픽들만으로 서로 완전히 대체 가능하다 ([ADR-0003](adr/0003-no-custom-adapter-layer.md)).

| 토픽 | 타입 | 발행 주기(목표) | 비고 |
|---|---|---|---|
| `/camera/image_raw` | `sensor_msgs/msg/Image` | 20~30Hz | 후면 카메라 프레임 (mono-inertial 시작 기준, mono8 또는 bgr8) |
| `/camera/camera_info` | `sensor_msgs/msg/CameraInfo` | `image_raw`와 1:1 동기 | REP 104. `header.frame_id`가 `image_raw`와 동일해야 함 |
| `/imu` | `sensor_msgs/msg/Imu` | ~200Hz | 가속도계+자이로. orientation 필드는 미사용(covariance[0] = -1) |
| `/orb_slam3/trajectory` | `nav_msgs/msg/Path` | SLAM 노드가 포즈를 추정할 때마다 | SLAM 노드 출력. `header.frame_id`는 `map`(아래 예외 참고) |

## 공통 규칙

- 모든 메시지의 `header.stamp`는 iPhone 캡처 시각(모노토닉 클럭) 기준이다 ([ADR-0001](adr/0001-timestamp-basis.md)). TX2 수신 시각을 쓰지 않는다.
- 센서 토픽(`image_raw`, `camera_info`, `imu`)의 `header.frame_id`는 `camera_link`로 고정한다 (이후 IMU-카메라 외부 캘리브레이션이 필요해지면 `imu_link` 등을 추가하고 정적 `tf`로 연결한다 — 이번 MVP 범위 밖). **예외**: `/orb_slam3/trajectory`는 `map`을 쓴다 — 궤적은 시간에 걸쳐 고정된 세계 좌표계(SLAM 초기화 시 잡힌 원점) 기준으로 점을 찍어야 하는데, `camera_link`는 카메라에 고정돼 매 프레임 같이 움직이는 프레임이라 여기엔 쓸 수 없다 (`aisys-max/ORB_SLAM3_ROS2`의 `monocular-inertial-slam-node.cpp` 참고). 맵이 리셋되면 이전/이후 포즈의 좌표계가 달라지는데 토픽 자체엔 그 구분이 없다 — 알려진 한계.
- QoS: 센서 토픽(`image_raw`, `camera_info`, `imu`)은 `rclcpp::SensorDataQoS()`(best-effort, depth 낮음)를 사용한다 — 실시간 센서 스트림 관례. `trajectory`는 `rclcpp::QoS(10)`(reliable)을 사용한다 — 유실되면 안 되는 결과물이기 때문이다.
- 파일 소스(rosbag2 재생)와 라이브 소스(브리지 노드)는 이 토픽 이름/타입/QoS를 동일하게 publish해야 하며, 그 외의 방식으로 SLAM 노드에 데이터를 전달하지 않는다.

## LiDAR 확장 시

`sensor_msgs/msg/PointCloud2`를 `/lidar/points` 등으로 추가하기만 하면 된다 — 기존 토픽 계약을 변경하지 않는다.
