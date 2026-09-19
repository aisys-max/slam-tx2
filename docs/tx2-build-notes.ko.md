# TX2 빌드 노트 (#2 TX2 인프라 구축)

> English version [here](tx2-build-notes.md).

`scripts/setup_tx2.sh`를 실제로 TX2(JetPack 4.6.x / L4T R32.7.6)에서 실행하며 만난 문제와 대응을 기록한다. 순서는 실제로 겪은 순서와 같다.

## 1. `apt-get update`가 exit 100으로 끝남

`/etc/apt/sources.list.d/ros2.list`에 잘못된 URL(`http://ros.org`, 정상은 `http://packages.ros.org/ros2/ubuntu`)이 있어 매번 404가 난다. `ros2-latest.list`에 올바른 항목이 이미 있어 `apt-get install`은 정상 동작하므로 무시하고 진행했다 — 근본 수정(파일 편집)은 `apt`/`apt-get` 외 sudo 권한이 필요해 이번 티켓 범위에서는 건드리지 않았다.

## 2. 공식 ORB-SLAM3가 OpenCV 4.4+ 를 요구

`CMakeLists.txt:33`이 `find_package(OpenCV 4.4)`이고 없으면 `FATAL_ERROR`. TX2의 OpenCV는 NVIDIA 공식 저장소의 4.1.1이 유일한 후보였고(Ubuntu bionic universe엔 3.2.0만 있음), apt로는 4.4+를 구할 수 없었다.

**대응**: ADR-0002에서 예정했던 대로, OpenCV 4.5.4를 CUDA 10.2 + cuDNN 8.2.1 지원으로 소스 빌드했다 (`/mnt/ssd/opencv_build`, `CMAKE_INSTALL_PREFIX`를 커스텀 경로로 잡아 시스템 OpenCV와 분리, sudo 불필요). 빌드 자체는 약 1시간 40분 걸렸다. g2o가 OpenCV 4.1.1에서 컴파일 실패했다는 보고(UZ-SLAMLab/ORB_SLAM3#308, Jetson Xavier NX)가 있었는데, 4.5.4로는 문제없이 빌드됐다 — 즉 그 이슈는 OpenCV 4.1.1 자체의 문제였다.

메모리 부담이 커서 TX2 SSD(`/mnt/ssd/swapfile`)에 8GB 스왑을 추가로 확보한 뒤 진행했다 (총 11GB 스왑, RAM 8GB).

## 3. `ros2.repos`의 Fast-DDS가 `2.1.x` 브랜치를 못 찾음

Foxy가 고정한 `eProsima/Fast-DDS`의 `2.1.x` 브랜치가 업스트림에서 이름이 바뀌었다(`2.1.4.x`로 추정). 가장 가까운 고정 태그 `v2.1.4`로 체크아웃해 해결했다.

## 4. `rosdep`가 Bionic에 존재하지 않는 패키지명을 요구

Foxy가 2020년 EOL되어 `rosdistro` 인덱스에서 완전히 빠지면서, `rosdep`의 일반 매핑 규칙이 최신 배포판(24.04 계열의 `t64` 접미사 등) 기준으로 갱신되어 Bionic(18.04)엔 존재하지 않는 패키지명(`libqt5widgets5t64` 등)을 찾으려 했다.

**대응**: 문제의 근원이 RViz2/rqt/데모/성능테스트/ROS1 브리지처럼 이번 MVP 범위 밖인 패키지들이었으므로, 소스 트리에서 아예 제거했다 (`src/ros2/rviz`, `src/ros-visualization`, `src/ros/ros_tutorials`, `src/ros2/demos`, `src/ros2/examples`, `src/ros2/performance_test_fixture`, `src/ros2/ros1_bridge`, `src/ros2/launch_ros/test_launch_ros`). 그 외 몇 개 rosdep 키(`python-mock`, `ament_cmake_ros_core` 등 테스트 전용 의존성)는 `--skip-keys`로 건너뛰었다. 이후 빌드는 성공했다 (237개 패키지, 실패 0).

## 5. `vision_opencv`(`cv_bridge`)는 `ros2.repos`에 없음

`zang09/ORB_SLAM3_ROS2`가 `cv_bridge`에 의존하는데, `cv_bridge`는 `ros2/ros2.repos`가 아니라 별도 저장소(`ros-perception/vision_opencv`)에 있다. `foxy` 브랜치를 clone해서 별도로 빌드했다.

## 6. `zang09/ORB_SLAM3_ROS2` fork 패치

우리 fork(`aisys-max/ORB_SLAM3_ROS2`)에 다음 두 가지를 패치했다:

- `CMakeModules/FindORB_SLAM3.cmake`: `ORB_SLAM3_ROOT_DIR` 기본값이 `~/Install/ORB_SLAM/ORB_SLAM3`로 하드코딩되어 있어, 환경변수/`-D` 오버라이드로 우리 경로(`/mnt/ssd/...`)를 쓸 수 있게 고쳤다.
- `CMakeLists.txt`: (a) `/opt/ros/foxy` python3.8 경로를 하드코딩한 `PYTHONPATH` 설정을 제거 (우리는 python3.6/Bionic). (b) `include_directories`에 `${ORB_SLAM3_ROOT_DIR}/Thirdparty/Sophus`가 빠져 있어 `sophus/se3.hpp: No such file or directory`로 빌드가 실패했다 — 추가해서 해결.

## 7. `scripts/setup_tx2.sh`를 처음부터 재검증하며 발견한 문제

기존 빌드 결과물을 `*_verified_backup`으로 옮겨두고 스크립트를 진짜 빈 상태에서 다시 돌려봤다.

- `set -u` 아래에서 `source install/setup.bash`가 `COLCON_TRACE: unbound variable`로 죽는 문제, 중단된 재실행 시 vcs import/Fast-DDS 수정/GUI 패키지 제거를 건너뛰는 문제, stale `CMakeCache.txt` 재사용 문제 — 이 세 가지는 `/code-review`로 찾아 PR에 반영했다 (자세한 내용은 PR 참고).
- **`vcs import`가 `set -e` 아래에서 스크립트를 죽임**: `ros2.repos`가 여전히 `eProsima/Fast-DDS`를 존재하지 않는 `2.1.x` ref로 고정하고 있어서, `vcs import`는 (그 저장소 하나만 실패하고 나머지 98개는 정상 처리했는데도) 매번 0이 아닌 종료 코드를 반환한다. `set -e`가 이걸 치명적 에러로 취급해서, 바로 다음 줄에 있는 Fast-DDS `v2.1.4` 수정 코드가 실행되기도 전에 스크립트가 죽었다 — 에러 메시지도 전체 로그 중간(vcs import 자체 출력 안)에 묻혀 있어서 마치 원인 불명으로 조용히 멈춘 것처럼 보였다. `apt-get update`와 같은 패턴으로 `vcs import src < ros2.repos || true`로 고쳤다.

이 수정 이후 `bash scripts/setup_tx2.sh`를 완전히 빈 상태에서 실행해 `EXIT_CODE=0`으로 끝까지 통과하는 것을 확인했다 (`ros2 doctor` — All 4 checks passed, `ros2 pkg executables orbslam3` → mono/rgbd/stereo/stereo-inertial).

## 결과

`scripts/setup_tx2.sh`를 완전히 빈 상태(`*_verified_backup`)에서 처음부터 끝까지 재실행해 `EXIT_CODE=0`으로 검증 완료.

- ROS2 Foxy: 237개 패키지 빌드 성공, `ros2 doctor` — All 4 checks passed
- 공식 ORB-SLAM3(OpenCV 4.5.4 기준): 빌드 성공
- `orbslam3`(zang09 fork) ROS2 패키지: 빌드 성공, `ros2 pkg executables orbslam3` → `mono`, `rgbd`, `stereo`, `stereo-inertial`
  - `monocular-inertial` 실행 파일은 이 fork에 아직 없다 (mono는 non-inertial뿐). #3(EuRoC 검증, mono-inertial부터 시작)에서 추가해야 한다.
- `iproxy`, `ideviceinfo`, `idevice_id` 설치됨
