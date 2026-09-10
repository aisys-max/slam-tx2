#!/usr/bin/env bash
# TX2 인프라 구축 (#2): ROS2 Foxy + Pangolin + 공식 ORB-SLAM3 + zang09 fork(orbslam3 ROS2 노드) + iproxy
#
# 이 스크립트는 2026-09-10 TX2(JetPack 4.6.x / L4T R32.7.6, Ubuntu 18.04 Bionic)에서
# 실제로 실행해 검증한 절차를 그대로 옮긴 것이다. 배경과 각 우회책의 이유는
# docs/tx2-build-notes.md 를 참고할 것.
#
# 전제조건:
#   - /mnt/ssd 에 충분한 여유 공간이 있는 외장 SSD가 마운트되어 있을 것
#   - apt-get/apt 에 대한 NOPASSWD sudo 권한이 있을 것
#     (예: /etc/sudoers.d/nvidia-apt-nopasswd 에 "nvidia ALL=(ALL) NOPASSWD: /usr/bin/apt-get, /usr/bin/apt")
#   - 최초 1회, 아래 스왑 설정은 이 스크립트가 자동으로 하지 않는다 (root 권한 범위 밖):
#       sudo fallocate -l 8G /mnt/ssd/swapfile && sudo chmod 600 /mnt/ssd/swapfile
#       sudo mkswap /mnt/ssd/swapfile && sudo swapon /mnt/ssd/swapfile
#
# 실행: bash scripts/setup_tx2.sh 2>&1 | tee /mnt/ssd/setup_tx2.log
# (전체 완료까지 CUDA 지원 OpenCV 빌드만으로 1~2시간, ROS2 Foxy 빌드까지 합쳐 3시간 이상 걸릴 수 있다)

set -euo pipefail

SSD_ROOT=/mnt/ssd
ROS2_WS=$SSD_ROOT/ros2_foxy
ORB_STACK=$SSD_ROOT/orb_slam3_stack
OPENCV_BUILD=$SSD_ROOT/opencv_build
OPENCV_INSTALL=$OPENCV_BUILD/install
JOBS=3   # TX2는 코어/메모리가 제한적이라 병렬도를 낮게 유지한다 (nproc=4, RAM=8GB)

# ROS2/colcon이 생성하는 setup.bash는 COLCON_TRACE 등을 기본값 없이 참조해서
# `set -u`(nounset) 아래에서 소싱하면 "unbound variable"로 죽는다 — 소싱하는 동안만 풀어준다.
source_ros2_setup() {
  set +u
  # shellcheck disable=SC1091
  source "$ROS2_WS/install/setup.bash"
  set -u
}

echo "== 1. apt 패키지 설치 (iproxy, colcon, 빌드 도구) =="
sudo apt-get update || true   # /etc/apt/sources.list.d/ros2.list 의 잘못된 www.ros.org 항목 때문에 exit 100이 날 수 있음 (무해, 아래 참고)
sudo apt-get install -y --no-install-recommends \
  libusbmuxd-tools libimobiledevice-utils python3-colcon-common-extensions \
  libgl1-mesa-dev libglew-dev libpython3-dev libegl1-mesa-dev libwayland-dev \
  libxkbcommon-dev wayland-protocols ffmpeg libavcodec-dev libavutil-dev \
  libavformat-dev libswscale-dev libavdevice-dev libpng-dev \
  libjpeg-dev libtiff-dev libv4l-dev libxvidcore-dev libx264-dev libgtk-3-dev \
  libatlas-base-dev gfortran python3-dev python3-numpy libtbb2 libtbb-dev \
  libdc1394-22-dev pkg-config

echo "== 2. Pangolin v0.6 빌드 (ORB-SLAM3 호환 버전) =="
mkdir -p "$ORB_STACK"
if [ ! -d "$ORB_STACK/Pangolin" ]; then
  git clone --recursive https://github.com/stevenlovegrove/Pangolin.git "$ORB_STACK/Pangolin"
fi
cd "$ORB_STACK/Pangolin"
git checkout v0.6
git submodule update --init --recursive
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j"$JOBS"
# 시스템 전역 설치(sudo make install) 없이, 아래 단계들은 이 build/ 트리를 -DPangolin_DIR 로 직접 참조한다.

echo "== 3. OpenCV 4.5.4(CUDA 10.2 + cuDNN) 소스 빌드 =="
# 공식 ORB-SLAM3는 find_package(OpenCV 4.4) 를 요구하는데, TX2의 NVIDIA 공식 OpenCV는 4.1.1뿐이다.
# (Ubuntu bionic universe 에는 3.2.0만 있어 apt로는 해결 불가 — docs/tx2-build-notes.md 참고)
mkdir -p "$OPENCV_BUILD"
if [ ! -d "$OPENCV_BUILD/opencv" ]; then
  git clone --depth 1 --branch 4.5.4 https://github.com/opencv/opencv.git "$OPENCV_BUILD/opencv"
  git clone --depth 1 --branch 4.5.4 https://github.com/opencv/opencv_contrib.git "$OPENCV_BUILD/opencv_contrib"
fi
mkdir -p "$OPENCV_BUILD/opencv/build" && cd "$OPENCV_BUILD/opencv/build"
cmake -D CMAKE_BUILD_TYPE=RELEASE \
  -D CMAKE_INSTALL_PREFIX="$OPENCV_INSTALL" \
  -D OPENCV_EXTRA_MODULES_PATH="$OPENCV_BUILD/opencv_contrib/modules" \
  -D WITH_CUDA=ON -D CUDA_ARCH_BIN=6.2 -D CUDA_ARCH_PTX="" \
  -D WITH_CUDNN=ON -D OPENCV_DNN_CUDA=ON -D ENABLE_NEON=ON \
  -D WITH_GSTREAMER=ON -D WITH_LIBV4L=ON -D BUILD_opencv_python3=ON \
  -D BUILD_TESTS=OFF -D BUILD_PERF_TESTS=OFF -D BUILD_EXAMPLES=OFF \
  -D OPENCV_GENERATE_PKGCONFIG=ON ..
make -j"$JOBS"
make install

echo "== 4. 공식 ORB-SLAM3 빌드 (Thirdparty 먼저, 메인 라이브러리는 그 다음) =="
if [ ! -d "$ORB_STACK/ORB_SLAM3" ]; then
  git clone https://github.com/UZ-SLAMLab/ORB_SLAM3.git "$ORB_STACK/ORB_SLAM3"
fi
for m in DBoW2 g2o Sophus; do
  # 이전 시도의 CMakeCache.txt가 남아있으면 -DOpenCV_DIR 등을 무시하고 캐시된 값을 재사용하므로 매번 새로 구성한다.
  rm -rf "$ORB_STACK/ORB_SLAM3/Thirdparty/$m/build"
  mkdir -p "$ORB_STACK/ORB_SLAM3/Thirdparty/$m/build"
  cd "$ORB_STACK/ORB_SLAM3/Thirdparty/$m/build"
  cmake .. -DCMAKE_BUILD_TYPE=Release -DOpenCV_DIR="$OPENCV_INSTALL/lib/cmake/opencv4"
  make -j"$JOBS"
done
cd "$ORB_STACK/ORB_SLAM3/Vocabulary" && tar -xf ORBvoc.txt.tar.gz
rm -rf "$ORB_STACK/ORB_SLAM3/build"
mkdir -p "$ORB_STACK/ORB_SLAM3/build" && cd "$ORB_STACK/ORB_SLAM3/build"
cmake .. -DCMAKE_BUILD_TYPE=Release \
  -DOpenCV_DIR="$OPENCV_INSTALL/lib/cmake/opencv4" \
  -DPangolin_DIR="$ORB_STACK/Pangolin/build"
make -j"$JOBS"

echo "== 5. ROS2 Foxy 소스 체크아웃 (GUI/데모/테스트 전용 패키지는 제외) =="
mkdir -p "$ROS2_WS/src"
cd "$ROS2_WS"
if [ ! -f ros2.repos ]; then
  curl -sSL -o ros2.repos https://raw.githubusercontent.com/ros2/ros2/foxy/ros2.repos
fi
# vcs import는 이미 클론된 저장소를 건드리지 않고 재실행 가능하므로 매번 실행한다 — vcs import가
# (네트워크 오류 등으로) 중간에 끊기면 일부 저장소만 존재하는 상태가 되는데, 이 블록 전체를
# "src/ros2 디렉터리가 있으면 건너뛴다"로 가드하면 Fast-DDS 브랜치 수정과 GUI/데모 패키지 제거까지
# 함께 건너뛰어져 버린다.
# ros2.repos가 여전히 eProsima/Fast-DDS를 존재하지 않는 "2.1.x" ref로 고정하고 있어서
# (docs/tx2-build-notes.md #3) vcs import는 이 저장소 checkout에서 매번 0이 아닌 종료 코드를
# 반환한다 — 이 한 저장소는 바로 다음 줄에서 v2.1.4로 직접 고정하므로 무해하다.
vcs import src < ros2.repos || true
# Foxy가 예전에 가리키던 Fast-DDS 의 "2.1.x" 브랜치가 업스트림에서 이름이 바뀌었다 (docs/tx2-build-notes.md)
if [ -d src/eProsima/Fast-DDS ]; then
  (cd src/eProsima/Fast-DDS && git checkout v2.1.4)
fi
# RViz/rqt 등은 이번 티켓 범위 밖이고, rosdep가 Bionic용 이름을 못 찾는 원인이기도 하다
rm -rf src/ros2/rviz src/ros-visualization src/ros/ros_tutorials \
       src/ros2/demos src/ros2/examples src/ros2/performance_test_fixture \
       src/ros2/ros1_bridge src/ros2/launch_ros/test_launch_ros
if [ ! -d src/ros-perception/vision_opencv ]; then
  mkdir -p src/ros-perception
  git clone -b foxy https://github.com/ros-perception/vision_opencv.git src/ros-perception/vision_opencv
  rm -rf src/ros-perception/vision_opencv/opencv_tests
fi

echo "== 6. rosdep (foxy가 rosdistro 인덱스에서 빠져 있어 일부 키를 skip) =="
export ROS_PYTHON_VERSION=3
rosdep update
rosdep install --from-paths src --ignore-src --rosdistro foxy -y \
  --skip-keys "fastcdr rti-connext-dds-5.3.1 urdfdom_headers python-mock ament_cmake_ros_core performance_test_fixture demo_nodes_cpp demo_nodes_py lifecycle"

echo "== 7. ROS2 Foxy 빌드 =="
colcon build --symlink-install --parallel-workers 1 \
  --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF
source_ros2_setup

echo "== 8. cv_bridge / image_geometry 빌드 (ros2.repos엔 없음, 별도 clone) =="
colcon build --symlink-install --packages-select cv_bridge image_geometry \
  --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
    -DOpenCV_DIR="$OPENCV_INSTALL/lib/cmake/opencv4"
source_ros2_setup

echo "== 9. zang09/ORB_SLAM3_ROS2 fork 빌드 (aisys-max/ORB_SLAM3_ROS2) =="
mkdir -p src/slam-tx2
if [ ! -d src/slam-tx2/orbslam3 ]; then
  git clone https://github.com/aisys-max/ORB_SLAM3_ROS2.git src/slam-tx2/orbslam3
fi
export ORB_SLAM3_ROOT_DIR="$ORB_STACK/ORB_SLAM3"
colcon build --symlink-install --packages-select orbslam3 \
  --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
    -DOpenCV_DIR="$OPENCV_INSTALL/lib/cmake/opencv4" \
    -DPangolin_DIR="$ORB_STACK/Pangolin/build" \
    -DORB_SLAM3_ROOT_DIR="$ORB_SLAM3_ROOT_DIR"
source_ros2_setup

echo "== 완료 =="
ros2 doctor
ros2 pkg executables orbslam3
