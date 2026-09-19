# Handoff (as of 2026-09-19)

> 한국어 버전은 [여기](handoff.ko.md)에 있습니다.

The doc a new session/new person reads first when picking up this project. Domain terms are in
[CONTEXT.md](../CONTEXT.md), design decisions in `docs/adr/`, per-component detail in "Related
docs" below. **The node/script wiring and the RViz live-check procedure are laid out with a
diagram in the repo root [README.md](../README.md)** — read README.md before this doc if you
want to run a live session again.

## Current status

**MVP (#1) complete.** iPhone Xs Max camera+IMU → Wi-Fi/USB → TX2 bridge node → ORB-SLAM3
mono-inertial ROS2 node → `/orb_slam3/trajectory` publish all work without crashing, and
live/replay equivalence (ATE RMSE 0.177m) has been confirmed with `ros2 bag record`/`play`.
#2-#7 are all closed. See [docs/live-e2e-validation.md](live-e2e-validation.md) for the detailed
validation process/results.

**[#15](https://github.com/aisys-max/slam-tx2/issues/15) closed (2026-09-19)** — a bug where the
RViz trajectory was drawn differently from/interrupted relative to actual motion. The root cause
was that every map reset gives the SLAM node a new coordinate origin, but
`/orb_slam3/trajectory` didn't distinguish this and published poses before/after stitched
together into one — fixed in `aisys-max/ORB_SLAM3_ROS2@6b6b24e` to clear the trajectory on
reset, verified live. Also done alongside it:

- **Measured Tbc/IMU noise calibration** (`aisys-max/ORB_SLAM3_ROS2@6132195`, without Kalibr):
  estimated the Tbc rotation from the gravity vector at 3 static poses, measured IMU noise
  parameters via 2 hours of stationary Allan variance. The old EuRoC defaults had been assuming
  a much worse sensor than the iPhone's actual IMU (AccWalk overestimated 33x, GyroWalk 5.6x,
  NoiseAcc 4x). Scripts: `scripts/capture_imu_pose.py`, `scripts/estimate_tbc_rotation.py`,
  `scripts/compute_allan_variance.py`. Raw measurements are recorded in the
  [#15 comments](https://github.com/aisys-max/slam-tx2/issues/15).
- Added **`scripts/analyze_tum_quality.py`** — quantitatively detects resets/publish
  gaps/instantaneous jumps in a TUM trajectory file. Reusable for future tracking-quality
  regression checks.
- Added **`README.md`** (repo root) — node/topic wiring diagram + reproducible RViz live-check
  procedure.

Even after calibration, the reset frequency only improved (~1/s → ~1 per ~17s), it wasn't fully
resolved, and the remaining bottleneck has been handed off to
[#10](https://github.com/aisys-max/slam-tx2/issues/10) below — frame rate is still low (~5.8Hz),
with `Fail to track local map!` observed repeatedly.

**Open issue**: [#10](https://github.com/aisys-max/slam-tx2/issues/10) — a real-time (20Hz)
mono-inertial processing performance gap on the TX2. Triaged to `bug`+`ready-for-agent`
(2026-09-19), with an agent brief posted on the issue. It's an item explicitly listed as Out of
Scope in the MVP spec (#1) ("real-time performance optimization"), so it didn't block MVP
completion, but #15's remaining tracking-instability issue effectively hinges on it, so it needs
to be tackled next for real-world use.

## What's worth doing next

1. **#10 performance gap (top priority, ready-for-agent)** — the original hypothesis
   ("USB/iproxy bandwidth is the bottleneck") was shaken by a 2026-09-19 retest: even over
   Wi-Fi direct, going through the bridge node still only got ~1.27-5.8Hz while the bridge node
   process occupied 95-100% CPU, whereas a past test connecting directly via a raw socket
   without the bridge node (`test_ios_tcp_client.py --connect`) hit 27.6Hz — **the new leading
   candidate is that the bottleneck is CPU-bound in the bridge node itself (e.g. the rclpy
   publish path), not network transport**. See the
   [#10 comment](https://github.com/aisys-max/slam-tx2/issues/10) for details and the agent
   brief.
2. **Vehicle field testing / 17 Pro Max + LiDAR expansion** — the next stage explicitly listed
   as Out of Scope in the #1 spec. Designed to be extensible just by adding
   `sensor_msgs/PointCloud2`, since it's topic-based (design intent only, not implemented). Makes
   sense to sequence this after #10 is resolved and tracking is stabilized.

## To run a live session again

**The procedure + node/script wiring diagram are laid out in [README.md](../README.md)** — not
duplicated here. If you need more detailed background (why each step does what it does), see
"0. Prerequisites" through "4. Live vs. replay comparison" in
`docs/live-e2e-validation.md`.

## Common sticking points (all things we've actually hit)

1. **Fixing only the iOS app's code without rebuilding doesn't take effect.** Restarting the app
   alone never applies a Swift source change on the device — an Xcode rebuild + reinstall on the
   Mac is required.
2. **RViz2's Path can look "added" while not actually being subscribed.** The Path item can
   appear in the Displays panel without an actual subscription, so if nothing draws, check
   `Subscription count` with `ros2 topic info /orb_slam3/trajectory --verbose` (the rviz node
   needs to be present).
3. **`KeyFrameTrajectory.txt` is a shutdown-time snapshot, so it comes out empty if you kill the
   process right after a map reset.** Use `scripts/record_trajectory_tum.py` to stream
   `/orb_slam3/trajectory` to a file in real time instead.
4. **Pure rotation (panning/spinning in place) is the worst input for monocular SLAM.** It needs
   a path with actual translation (walking a square, etc.) to initialize.
5. **Replaying a bag while the bridge node is still alive mixes it with live data.** Always
   `pkill -f ios_bridge_node.py` to kill the bridge node before replay validation.
6. **DDS best-effort/reliable QoS must match on both sides.** The bridge node (publisher) uses
   `qos_profile_sensor_data` (best-effort), and the SLAM node's subscription is matched with
   `.best_effort()` too (see `docs/ros2-topic-contract.md`) — if only one side is reliable, they
   don't match at all and zero messages get through.
7. **rclpy's logger has its severity fixed per call site.** Calling several different
   severities from one line via `getattr(logger, level)(msg)` raises a `ValueError` (see
   `_make_ros_logger` in `scripts/ios_bridge_node.py`).
8. **ROS2 needs to be sourced this way every time** (because of the `COLCON_TRACE`
   unbound-variable issue):
   ```bash
   set +u; source /mnt/ssd/ros2_foxy/install/setup.bash; set -u
   ```
9. **`ios_bridge_node.py` can nearly monopolize one CPU core while frame rate craters**
   (observed 2026-09-19: dropped as low as ~1.27Hz). Restarting the bridge node sometimes helps
   temporarily (~5.8Hz), but the root cause isn't fixed yet — see
   [#10](https://github.com/aisys-max/slam-tx2/issues/10). `ros2 topic hz` can return nothing
   but empty output since its QoS doesn't match a best-effort publisher, so on ROS2 Foxy (which
   has no `--qos-reliability`-style option), measure actual frame rate with a separate rclpy
   script that subscribes with best-effort QoS directly instead.

## Repo/environment layout

- Main repo (this one, `aisys-max/slam-tx2`): PR-based workflow. iOS app, bridge node, docs,
  validation scripts.
- ORB-SLAM3 ROS2 wrapper (`aisys-max/ORB_SLAM3_ROS2`, a separate repo, direct-commit-to-main
  workflow): cloned at `/mnt/ssd/ros2_foxy/src/slam-tx2/orbslam3`. The SLAM node's C++ code lives
  here.
- ROS2 Foxy build: `/mnt/ssd/ros2_foxy` (colcon workspace, not git-tracked).
- Capture output: `/mnt/ssd/live_e2e/` (bags, trajectory.tum, etc. — a fresh directory per
  session is recommended).

## Related docs

- [ros2-topic-contract.md](ros2-topic-contract.md) — topic/QoS/frame_id contract
- [ios-tcp-protocol.md](ios-tcp-protocol.md) — iPhone↔TX2 wire protocol
- [ios-app-setup.md](ios-app-setup.md) — iOS app Xcode project setup
- [camera-calibration.md](camera-calibration.md) — checkerboard calibration procedure
- [bridge-node.md](bridge-node.md) — bridge node setup/running/verification
- [euroc-validation.md](euroc-validation.md) — EuRoC-based SLAM node validation (#3)
- [live-e2e-validation.md](live-e2e-validation.md) — full record of live e2e validation (#7)
- [tx2-build-notes.md](tx2-build-notes.md) — TX2 build environment notes
- `docs/adr/` — design decisions (timestamp basis, adopting ROS2 Foxy, no adapter layer, SLAM
  wrapper choice)
