# SLAM Pipeline

> English version [here](CONTEXT.md).

iPhone 카메라+IMU 데이터를 Jetson TX2에서 ROS2(Foxy)로 처리해 궤적/지도를 생성하는 SLAM 시스템의 도메인 용어집.

## Language

**세션 (Session)**:
프로젝트 표준 센서 토픽(`sensor_msgs/Image`, `sensor_msgs/Imu`, `sensor_msgs/CameraInfo`)의 시간에 따른 흐름. rosbag2로 녹화된 형태든 실시간 토픽 스트림이든 동일한 토픽 규약을 쓰므로 서로 구분 없이 대체 가능하다.
_Avoid_: 레코딩, 데이터셋, 캡처(캡처는 세션을 만드는 행위를 가리킬 때만 사용), 어댑터/파일 어댑터/라이브 어댑터(더 이상 쓰지 않음 — 세션은 커스텀 레이어 없이 ROS2 토픽 자체로 표현된다)

**프레임 (Frame)**:
세션 안의 `sensor_msgs/Image` 메시지 한 개. 같은 타임스탬프/frame_id로 짝지어진 `sensor_msgs/CameraInfo`가 캘리브레이션 메타데이터를 함께 실어 나른다.
_Avoid_: 이미지, 샷

**IMU 샘플 (IMU Sample)**:
세션 안의 `sensor_msgs/Imu` 메시지 한 개.
_Avoid_: IMU 데이터, 센서값

**브리지 노드 (Bridge Node)**:
iPhone에서 USB(iproxy 터널)로 들어오는 원시 스트림을 읽어 프로젝트 표준 센서 토픽으로 publish하는 ROS2 노드. 실제 카메라/IMU 드라이버 노드와 동등한 역할을 한다 — 이 노드 하나만 iPhone과의 USB 통신을 알고, 그 아래(SLAM 노드 등)는 토픽만 본다.
_Avoid_: 라이브 어댑터, 커넥터

**SLAM 노드 (SLAM Node)**:
프로젝트 표준 센서 토픽을 구독해 ORB-SLAM3(visual-inertial)를 실행하고 궤적을 publish하는 ROS2 노드. 토픽이 브리지 노드(라이브)에서 오든 `ros2 bag play`(녹화본 재생)에서 오든 동일하게 동작한다.
_Avoid_: 재생 파이프라인(어댑터 레이어가 있던 이전 설계 용어, 더 이상 쓰지 않음), SLAM 파이프라인 단독 사용

**궤적 (Trajectory)**:
SLAM 노드가 세션에 대해 publish하는, 시간에 따른 추정 카메라 포즈의 연속. ROS2 토픽(예: `nav_msgs/Path`)으로 표현된다.
_Avoid_: 경로, 결과
