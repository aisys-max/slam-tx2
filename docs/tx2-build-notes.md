# TX2 build notes (#2 TX2 infrastructure setup)

> 한국어 버전은 [여기](tx2-build-notes.ko.md)에 있습니다.

Records the problems and fixes encountered actually running `scripts/setup_tx2.sh` on a real
TX2 (JetPack 4.6.x / L4T R32.7.6). Ordered the same way they were actually encountered.

## 1. `apt-get update` ends with exit 100

`/etc/apt/sources.list.d/ros2.list` had an incorrect URL (`http://ros.org`, should be
`http://packages.ros.org/ros2/ubuntu`), causing a 404 every time. `ros2-latest.list` already had
the correct entry so `apt-get install` worked fine, so this was ignored and we proceeded — a
root-cause fix (editing the file) needs sudo access beyond `apt`/`apt-get`, so it wasn't touched
within this ticket's scope.

## 2. Official ORB-SLAM3 requires OpenCV 4.4+

`CMakeLists.txt:33` is `find_package(OpenCV 4.4)`, `FATAL_ERROR` if missing. The only OpenCV
candidate on the TX2 was 4.1.1 from NVIDIA's official repo (Ubuntu bionic universe only has
3.2.0), and 4.4+ wasn't available via apt.

**Fix**: as planned in ADR-0002, built OpenCV 4.5.4 from source with CUDA 10.2 + cuDNN 8.2.1
support (`/mnt/ssd/opencv_build`, `CMAKE_INSTALL_PREFIX` set to a custom path, separate from the
system OpenCV, no sudo needed). The build itself took about 1 hour 40 minutes. There was a
report of g2o failing to compile against OpenCV 4.1.1 (UZ-SLAMLab/ORB_SLAM3#308, Jetson Xavier
NX), but it built fine with 4.5.4 — so that issue was specific to OpenCV 4.1.1 itself.

Since memory pressure was significant, added 8GB of swap on the TX2's SSD (`/mnt/ssd/swapfile`)
before proceeding (11GB swap total, 8GB RAM).

## 3. `ros2.repos`'s Fast-DDS can't find the `2.1.x` branch

The `2.1.x` branch pinned by Foxy for `eProsima/Fast-DDS` had been renamed upstream (presumably
to `2.1.4.x`). Resolved by checking out the closest pinned tag, `v2.1.4`.

## 4. `rosdep` asks for package names that don't exist on Bionic

Since Foxy hit EOL in 2020 and was dropped entirely from the `rosdistro` index, `rosdep`'s
generic mapping rules got updated based on newer distros (e.g. the `t64` suffix from the 24.04
line), causing it to look for package names that don't exist on Bionic (18.04) (e.g.
`libqt5widgets5t64`).

**Fix**: since the root of the problem was packages out of scope for this MVP anyway (RViz2,
rqt, demos, performance tests, the ROS1 bridge), removed them entirely from the source tree
(`src/ros2/rviz`, `src/ros-visualization`, `src/ros/ros_tutorials`, `src/ros2/demos`,
`src/ros2/examples`, `src/ros2/performance_test_fixture`, `src/ros2/ros1_bridge`,
`src/ros2/launch_ros/test_launch_ros`). A few other rosdep keys (`python-mock`,
`ament_cmake_ros_core`, etc. — test-only dependencies) were skipped with `--skip-keys`. The
build succeeded afterward (237 packages, 0 failures).

## 5. `vision_opencv` (`cv_bridge`) isn't in `ros2.repos`

`zang09/ORB_SLAM3_ROS2` depends on `cv_bridge`, but `cv_bridge` lives in a separate repo
(`ros-perception/vision_opencv`), not `ros2/ros2.repos`. Cloned the `foxy` branch and built it
separately.

## 6. Patches to the `zang09/ORB_SLAM3_ROS2` fork

Two patches applied to our fork (`aisys-max/ORB_SLAM3_ROS2`):

- `CMakeModules/FindORB_SLAM3.cmake`: `ORB_SLAM3_ROOT_DIR`'s default was hardcoded to
  `~/Install/ORB_SLAM/ORB_SLAM3` — fixed so it can be overridden via an env var/`-D` to use our
  path (`/mnt/ssd/...`).
- `CMakeLists.txt`: (a) removed the hardcoded `/opt/ros/foxy` python3.8 path from the
  `PYTHONPATH` setting (we use python3.6/Bionic). (b)
  `${ORB_SLAM3_ROOT_DIR}/Thirdparty/Sophus` was missing from `include_directories`, causing a
  build failure with `sophus/se3.hpp: No such file or directory` — fixed by adding it.

## 7. Issues found re-verifying `scripts/setup_tx2.sh` from scratch

Moved the existing build output aside as `*_verified_backup` and re-ran the script from a
genuinely empty state.

- `source install/setup.bash` dying under `set -u` with `COLCON_TRACE: unbound variable`, the
  resumed-run path skipping vcs import/the Fast-DDS fix/GUI package removal, and reuse of a
  stale `CMakeCache.txt` — these three were found via `/code-review` and fixed in the PR (see
  the PR for details).
- **`vcs import` kills the script under `set -e`**: `ros2.repos` still pins
  `eProsima/Fast-DDS` to the now-nonexistent `2.1.x` ref, so `vcs import` always returns a
  nonzero exit code (even though only that one repo fails while the other 98 succeed). `set -e`
  treats this as a fatal error, so the script died before even reaching the Fast-DDS `v2.1.4`
  fix on the very next line — and the error message was buried mid-log (inside `vcs import`'s
  own output), making it look like it silently stopped for an unknown reason. Fixed the same way
  as `apt-get update`, with `vcs import src < ros2.repos || true`.
- After this fix, running `bash scripts/setup_tx2.sh` from a completely empty state passed all
  the way through with `EXIT_CODE=0` (`ros2 doctor` — All 4 checks passed,
  `ros2 pkg executables orbslam3` → mono/rgbd/stereo/stereo-inertial).

## Results

Re-ran `scripts/setup_tx2.sh` from a completely empty state (`*_verified_backup`) start to
finish and verified `EXIT_CODE=0`.

- ROS2 Foxy: 237 packages built successfully, `ros2 doctor` — All 4 checks passed
- Official ORB-SLAM3 (against OpenCV 4.5.4): build succeeded
- `orbslam3` (zang09 fork) ROS2 package: build succeeded, `ros2 pkg executables orbslam3` →
  `mono`, `rgbd`, `stereo`, `stereo-inertial`
  - A `monocular-inertial` executable doesn't exist in this fork yet (mono is non-inertial
    only). Needs to be added in #3 (EuRoC validation, starting from mono-inertial).
- `iproxy`, `ideviceinfo`, `idevice_id` installed
