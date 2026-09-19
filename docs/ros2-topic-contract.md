# Project standard sensor topic contract

> 한국어 버전은 [여기](ros2-topic-contract.ko.md)에 있습니다.

The bridge node, the SLAM node, and `ros2 bag record`/`play` all follow this contract. A live
source and a rosbag2 replay are fully interchangeable through these topics alone
([ADR-0003](adr/0003-no-custom-adapter-layer.md)).

| Topic | Type | Publish rate (target) | Notes |
|---|---|---|---|
| `/camera/image_raw` | `sensor_msgs/msg/Image` | 20-30Hz | Rear camera frame (as of the mono-inertial baseline, mono8 or bgr8) |
| `/camera/camera_info` | `sensor_msgs/msg/CameraInfo` | 1:1 sync with `image_raw` | REP 104. `header.frame_id` must match `image_raw` |
| `/imu` | `sensor_msgs/msg/Imu` | ~200Hz | Accelerometer+gyro. The orientation field is unused (covariance[0] = -1) |
| `/orb_slam3/trajectory` | `nav_msgs/msg/Path` | Every time the SLAM node estimates a pose | SLAM node output. `header.frame_id` is `map` (see exception below) |

## Common rules

- Every message's `header.stamp` is based on iPhone capture time (monotonic clock)
  ([ADR-0001](adr/0001-timestamp-basis.md)). TX2 receipt time is never used.
- The sensor topics' (`image_raw`, `camera_info`, `imu`) `header.frame_id` is fixed to
  `camera_link` (if IMU-camera extrinsic calibration is needed later, add `imu_link` etc. and
  connect it with a static `tf` — out of scope for this MVP). **Exception**: `/orb_slam3/trajectory`
  uses `map` — a trajectory needs to plot points relative to a world frame that's fixed over
  time (the origin captured at SLAM initialization), and `camera_link` can't be used for this
  since it's attached to the camera and moves every frame (see `monocular-inertial-slam-node.cpp`
  in `aisys-max/ORB_SLAM3_ROS2`). When the map resets, poses before/after have different
  coordinate frames, but the topic itself carries no distinction for that — a known limitation.
- QoS: the sensor topics (`image_raw`, `camera_info`, `imu`) use `rclcpp::SensorDataQoS()`
  (best-effort, low depth) — standard practice for real-time sensor streams. `trajectory` uses
  `rclcpp::QoS(10)` (reliable), since it's a result that must not be lost.
- A file source (rosbag2 replay) and a live source (bridge node) must publish these same topic
  names/types/QoS, and must not deliver data to the SLAM node by any other means.

## For a LiDAR extension

Just add `sensor_msgs/msg/PointCloud2` as e.g. `/lidar/points` — no change to the existing topic
contract is needed.
