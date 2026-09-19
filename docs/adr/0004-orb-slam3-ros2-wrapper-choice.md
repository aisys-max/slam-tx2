# Fork zang09/ORB_SLAM3_ROS2 for the SLAM node

> 한국어 버전은 [여기](0004-orb-slam3-ros2-wrapper-choice.ko.md)에 있습니다.

The official `UZ-SLAMLab/ORB_SLAM3` is not a ROS2 node, so a ROS2 wrapper around it is needed.
After investigating, `zang09/ORB_SLAM3_ROS2` was the closest existing implementation supporting
Foxy + stereo-inertial (camera+IMU) (it's not actively maintained, but we judged forking and
patching only what we need to be better than writing one from scratch). The other candidate,
`Mechazo11/ros2_orb_slam3`, is Humble-only and monocular-only (no IMU), which doesn't fit our
requirements (Foxy, VIO).

Since we depend on an infrequently-maintained upstream repo, we fork it directly and manage
whatever patches we need ourselves.
