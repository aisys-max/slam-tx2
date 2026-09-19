# Use ROS2 topics themselves as the seam, with no custom adapter layer

> 한국어 버전은 [여기](0003-no-custom-adapter-layer.ko.md)에 있습니다.

To handle Sessions (live vs. recorded), we initially planned a custom "adapter" abstraction
(file adapter / live adapter), but confirmed the ROS2 ecosystem already solves this problem and
removed that layer.

- `rosbag2` is designed with a layered architecture (`rosbag2_transport`/`rosbag2_cpp`/
  `rosbag2_storage`) so that, from a downstream node's perspective, recorded and live topics
  behave identically ([ros2/rosbag2](https://github.com/ros2/rosbag2)).
- `sensor_msgs/CameraInfo` is the REP 104-standardized way to carry calibration metadata paired
  with an `Image` topic by timestamp/frame_id ([REP 104](https://ros.org/reps/rep-0104.html)). A
  separate "session metadata" layer would just be reimplementing this.
- Real AD stacks, including Autoware, also have sensor drivers publish standard topics directly,
  and simulation/replay data is consumed as-is via the same topic convention with no internal
  interface changes
  ([Autoware: Integrating SODA.Sim](https://autoware.org/integrating-soda-sim-with-autoware-for-camera-based-evaluation/)).

A Session is therefore defined as "a flow of the project's standard sensor topics"; a file
source is implemented purely as `ros2 bag play`, and a live source purely as the bridge node
(USB stream → topic publish). Auxiliary logic like session start/end or source validation, if
ever needed, is handled at the launch-file/node-lifecycle level, not layered onto the sensor
data path itself.
