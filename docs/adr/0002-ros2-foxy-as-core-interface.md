# Adopt ROS2 (Foxy) as the core interface for sensor data

> 한국어 버전은 [여기](0002-ros2-foxy-as-core-interface.ko.md)에 있습니다.

This project's goal is not just a finished system, but a development process that resembles
real autonomous-driving engineering as closely as possible. Real AD stacks handle camera/IMU
data as ROS(2) topics, record/replay them with rosbag, and visualize them in RViz. Accordingly,
we decided to represent the iPhone→TX2 sensor data path as ROS2 topics
(`sensor_msgs/Image`, `sensor_msgs/Imu`, `sensor_msgs/CameraInfo`) rather than a custom binary
session format.

The TX2 already had ROS2 Eloquent (EOL 2020) installed, but Eloquent's ecosystem is effectively
dead and most ROS2 wrappers for ORB-SLAM3 target Foxy, so we upgrade to Foxy. On JetPack 4.6
(Ubuntu 18.04/Bionic), Foxy isn't an officially supported combination (Foxy's official target is
20.04/Focal), but it's the combination NVIDIA Isaac ROS and the Jetson community standardly use
via source builds. Given this project needs direct access to USB (iproxy) and camera devices, we
chose a host source build over a Docker image.
