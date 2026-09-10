# 커스텀 어댑터 레이어 없이 ROS2 토픽 자체를 시임으로 사용

세션(라이브 vs 녹화)을 다루기 위해 자체 "어댑터" 추상화(파일 어댑터/라이브 어댑터)를 두려 했으나, ROS2 생태계가 이미 이 문제를 해결하고 있다는 걸 확인하고 이 레이어를 없앴다.

- `rosbag2`는 녹화된 토픽과 라이브 토픽이 다운스트림 노드 입장에서 완전히 동일하게 동작하도록 레이어드 아키텍처(`rosbag2_transport`/`rosbag2_cpp`/`rosbag2_storage`)로 설계되어 있다 ([ros2/rosbag2](https://github.com/ros2/rosbag2)).
- `sensor_msgs/CameraInfo`가 REP 104로 표준화된, `Image` 토픽과 타임스탬프/frame_id로 짝지어지는 캘리브레이션 메타데이터 운반 방식이다 ([REP 104](https://ros.org/reps/rep-0104.html)). 별도의 "세션 메타데이터" 레이어는 이를 중복 구현하는 것이다.
- Autoware를 비롯한 실제 AD 스택도 센서 드라이버가 표준 토픽을 직접 publish하고, 시뮬레이션/재생 데이터도 같은 토픽 규약을 쓰는 것만으로 내부 인터페이스 변경 없이 그대로 소비된다 ([Autoware: Integrating SODA.Sim](https://autoware.org/integrating-soda-sim-with-autoware-for-camera-based-evaluation/)).

따라서 세션은 "프로젝트 표준 센서 토픽의 흐름"으로 정의하고, 파일 소스는 `ros2 bag play`, 라이브 소스는 브리지 노드(USB 스트림 → 토픽 publish)로만 구현한다. 세션 시작/종료나 소스 검증 같은 부가 로직은 필요해지면 launch 파일/노드 생명주기 수준에서 다루고, 센서 데이터 경로 자체에는 얹지 않는다.
