# SLAM node validation against the EuRoC dataset (#3)

> 한국어 버전은 [여기](euroc-validation.ko.md)에 있습니다.

A record of validating the SLAM node (`orbslam3` mono-inertial) by replaying EuRoC V1_01_easy
with `scripts/run_euroc_validation.sh`.

## Getting the dataset

The original ETH server (`robotics.ethz.ch`) wasn't reachable from this TX2's network (timeout),
the ETH Research Collection page returned a 500 error, and the community rosbag2 mirror (a
Google Drive link maintained by OpenVINS) also wasn't accessible (presumably quota exhausted).
We ended up proceeding with a standard EuRoC ASL-format zip (`mav0/cam0`, `mav0/imu0`,
`mav0/state_groundtruth_estimate0`, etc.) the user obtained through another route.

**Required input**: a `<V1_01_easy>/mav0/` directory (zip extracted) — automatic download isn't
covered by this scope.

## rosbag2 conversion

This TX2's ROS2 Foxy build doesn't have `rosbag2_py` (the Python bindings) — it's a package that
hadn't been added yet as of Foxy. `scripts/euroc_to_rosbag2.py` writes the sqlite3 storage
schema (`topics`/`messages` tables, confirmed by opening a real bag made with `ros2 bag record`)
directly to build a rosbag2. Confirmed it's recognized correctly by `ros2 bag info`.

The topics it produces follow the project's standard contract
([docs/ros2-topic-contract.md](ros2-topic-contract.md)): `/camera/image_raw`,
`/camera/camera_info` (pinhole+radtan calibration from cam0/sensor.yaml), `/imu`.

## Writing the `orbslam3` mono-inertial node from scratch

`zang09/ORB_SLAM3_ROS2` (forked in #2) only had mono (non-inertial), stereo, and
stereo-inertial — no mono-inertial — so it was written from scratch modeled on
stereo-inertial's IMU buffering/sync pattern (see commits in `aisys-max/ORB_SLAM3_ROS2`). Issues
found/fixed during development:

- Missing `Thirdparty/Sophus` include path → compile failure (same issue as the other nodes,
  also hit in #2)
- **Hang on shutdown**: `SyncWithImu()` was an unconditional `while(1)`, so the destructor's
  `syncThread_->join()` hung forever even after SIGINT — confirmed the node actually didn't die
  after bag replay finished, then fixed it by adding a `std::atomic<bool>` stop flag.
- Turned off the Pangolin viewer (`visualization`) for headless operation so it works without
  X11 — this TX2 has no DISPLAY set.

## The effect of replay speed on accuracy (important)

Initially replaying at `--rate 1.0` (real-time):
- `Fail to track local map!` occurred repeatedly, multiple map resets
- **ATE RMSE 1.18m** — 1-1.5 orders of magnitude off the reference literature level (a few cm),
  below the bar

Suspected cause: if the TX2 can't keep up with 20Hz real-time processing, `GrabImage()`'s
single-slot buffer (which discards the previous unprocessed frame when a new one arrives)
silently drops frames, and that's the hypothesis for what degrades trajectory quality.

Slowing replay speed to `--rate 0.3`:
- Zero `Fail to track local map!` occurrences, VIBA 1/2 (IMU initialization) completed normally,
  no map resets
- **ATE RMSE 0.093m** — same order of magnitude as the reference literature, passes the bar

**Conclusion**: getting this node to process reliably in real time (1.0x) on the TX2 needs
separate performance optimization — out of scope for this ticket. Offline validation (what this
script does) worked around it by lowering the replay speed to give it processing headroom. Real
iPhone live capture (#6/#7) forces real-time processing on the TX2, so this limitation needs to
be kept in mind, and frame rate/resolution/ORB feature count etc. may need tuning — worth
leaving as a separate issue.

## Results

- Reproduced from scratch and confirmed with
  `bash scripts/run_euroc_validation.sh <mav0 dir> <output dir> 0.3` (exit 0)
- ATE RMSE 0.093-0.094m (nearly identical across two runs) — same order of magnitude as the EuRoC
  V1_01_easy VIO level reported in the reference literature
- Trajectory (`KeyFrameTrajectory.txt`, TUM format) saved without crashing
- ATE evaluation implements the standard TUM benchmark procedure directly (Sturm et al. 2012)
  (`scripts/evaluate_ate.py`) — the `evo` package's dependencies didn't match this TX2's Python
  3.6 (requires a newer numpy that doesn't support py3.6), so it couldn't be installed
