# SLAM 노드는 zang09/ORB_SLAM3_ROS2를 fork해서 사용

공식 `UZ-SLAMLab/ORB_SLAM3`는 ROS2 노드가 아니므로, 이를 감싸는 ROS2 래퍼가 필요하다. 조사 결과 Foxy + stereo-inertial(카메라+IMU)을 지원하는 기존 구현으로 `zang09/ORB_SLAM3_ROS2`가 가장 근접했다 (활발히 유지보수되진 않지만, 처음부터 새로 작성하는 것보다 이를 fork해 필요한 부분만 패치하는 편이 낫다고 판단했다). 다른 후보였던 `Mechazo11/ros2_orb_slam3`는 Humble 전용이며 모노큘러만 지원해(IMU 없음) 우리 요구(Foxy, VIO)에 맞지 않았다.

유지보수가 뜸한 상위 저장소에 의존하는 리스크가 있으므로, 직접 fork해 필요한 패치를 우리 쪽에서 관리한다.
