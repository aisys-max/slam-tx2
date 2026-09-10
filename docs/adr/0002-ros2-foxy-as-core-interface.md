# ROS2(Foxy)를 센서 데이터의 핵심 인터페이스로 채택

이 프로젝트의 목표는 완성된 시스템뿐 아니라 개발 과정 자체를 실제 자율주행 엔지니어링에 가깝게 만드는 것이다. 실제 AD 스택은 카메라/IMU 데이터를 ROS(2) 토픽으로 다루고 rosbag으로 녹화·재생하며 RViz로 시각화한다. 이에 따라 iPhone→TX2 센서 데이터 경로를 커스텀 바이너리 세션 포맷이 아니라 ROS2 토픽(`sensor_msgs/Image`, `sensor_msgs/Imu`, `sensor_msgs/CameraInfo`)으로 표현하기로 결정했다.

TX2에는 이미 ROS2 Eloquent(2020년 EOL)가 설치되어 있었으나, Eloquent는 생태계가 사실상 죽었고 ORB-SLAM3용 ROS2 래퍼들도 대부분 Foxy를 대상으로 하므로 Foxy로 업그레이드한다. JetPack 4.6(Ubuntu 18.04/Bionic)에서 Foxy는 공식 지원 조합은 아니지만(Foxy 공식 타깃은 20.04/Focal), NVIDIA Isaac ROS 및 Jetson 커뮤니티가 소스 빌드로 표준적으로 사용하는 조합이다. USB(iproxy)·카메라 장치에 직접 접근해야 하는 이 프로젝트 특성상 Docker 이미지보다 호스트 소스 빌드를 선택했다.
