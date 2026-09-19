# SLAM Pipeline

> 한국어 버전은 [여기](CONTEXT.ko.md)에 있습니다.

A domain glossary for the SLAM system that processes iPhone camera+IMU data on a Jetson TX2 via
ROS2 (Foxy) to produce a trajectory/map.

## Language

**Session**:
A flow, over time, of the project's standard sensor topics (`sensor_msgs/Image`,
`sensor_msgs/Imu`, `sensor_msgs/CameraInfo`). Whether it's recorded with rosbag2 or a live topic
stream, both use the same topic convention, so they're interchangeable.
_Avoid_: recording, dataset, capture (use "capture" only for the act of creating a Session),
adapter/file adapter/live adapter (no longer used — a Session is expressed as the ROS2 topics
themselves, with no custom layer)

**Frame**:
One `sensor_msgs/Image` message within a Session. The `sensor_msgs/CameraInfo` paired by the
same timestamp/frame_id carries the calibration metadata alongside it.
_Avoid_: image, shot

**IMU Sample**:
One `sensor_msgs/Imu` message within a Session.
_Avoid_: IMU data, sensor value

**Bridge Node**:
A ROS2 node that reads the raw stream coming in over USB (iproxy tunnel) from the iPhone and
publishes it as the project's standard sensor topics. It plays the same role as a real
camera/IMU driver node — only this one node knows about USB communication with the iPhone;
everything below it (the SLAM node, etc.) only ever sees topics.
_Avoid_: live adapter, connector

**SLAM Node**:
A ROS2 node that subscribes to the project's standard sensor topics, runs ORB-SLAM3
(visual-inertial), and publishes the trajectory. It behaves identically whether the topics come
from the Bridge Node (live) or from `ros2 bag play` (recorded replay).
_Avoid_: replay pipeline (an older design term from when there was an adapter layer, no longer
used), "SLAM pipeline" used alone

**Trajectory**:
The sequence of estimated camera poses over time that the SLAM Node publishes for a Session.
Represented as a ROS2 topic (e.g. `nav_msgs/Path`).
_Avoid_: path, result
