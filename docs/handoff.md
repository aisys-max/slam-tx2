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
resolved, and the remaining bottleneck was handed off to
[#10](https://github.com/aisys-max/slam-tx2/issues/10) below — frame rate was still low (~5.8Hz),
with `Fail to track local map!` observed repeatedly.

**[#10](https://github.com/aisys-max/slam-tx2/issues/10) fixed and verified live (2026-09-19)** —
the bottleneck turned out to be CPU-bound in the bridge node itself, not network transport.
Root cause: `sensor_msgs/Image`'s rosidl-generated `data` setter (`_image.py`) runs an
element-wise `isinstance`/range check over the whole array in pure Python whenever the assigned
value isn't already an `array.array` — for a 640x480 frame (307,200 bytes) that's ~157ms/frame
(a ~6.4Hz ceiling on that field alone), matching the observed ~5.8Hz almost exactly.
[`build_image()`](../scripts/ios_bridge_node.py) previously assigned `frame["pixels"]` (`bytes`)
directly, hitting that slow path every frame; wrapping it in `array.array("B", ...)` before
assignment hits the setter's fast path (`isinstance(value, array.array)`) instead. Verified live
against the iPhone over Wi-Fi direct: `/camera/image_raw` went from ~5.8Hz to **~27.3Hz**, bridge
node CPU dropped from 95-100% to **~13-16%**, and `/imu` improved too (~97Hz, up from an uneven
50-69Hz) with no regression.

**Live re-verification session (2026-09-20, in progress)** — re-ran the full RViz live-check per
the item above. Found and fixed several more real issues along the way, but as of this writing
**`/orb_slam3/trajectory` still hasn't successfully drawn a Path live** — IMU initialization keeps
failing/resetting before completing. What's been ruled out/fixed so far:

- **TX2 was in `MAXP_CORE_ARM` power mode** (only 4 of 6 cores online, ~2.0GHz cap) instead of
  `MAXN`. Switching (`sudo nvpmodel -m 0 && sudo jetson_clocks`) took `/camera/image_raw` from
  ~6-8Hz back up to ~24-30Hz under full SLAM+RViz load. **This does not persist across reboot** —
  re-apply it if a fresh boot regresses frame rate again.
- **Two real crash bugs found and patched in the vendored upstream ORB-SLAM3** (NOT this repo or
  `aisys-max/ORB_SLAM3_ROS2` — a separate, unforked clone of `UZ-SLAMLab/ORB_SLAM3` at
  `/mnt/ssd/orb_slam3_stack/ORB_SLAM3`, patched locally only and rebuilt into `lib/libORB_SLAM3.so`).
  **These patches are not committed anywhere and will be lost if that directory is
  reset/re-cloned** — see "What's worth doing next" below, this needs a proper fork.
  1. `Optimizer::PoseInertialOptimizationLastFrame` (`src/Optimizer.cc`) constructed
     `EdgePriorPoseImu(pFp->mpcpi)` even when `pFp->mpcpi` is null (the existing code already
     detected this and logged `"pFp->mpcpi does not exist!!!"`, but passed the null pointer in
     anyway) — `EdgePriorPoseImu`'s constructor dereferences it unconditionally, segfaulting.
     This reproduced reliably a few seconds after repeated `scale too small` IMU-init failures.
     Fixed by skipping the edge (and its later `GetHessian()` use) when the pointer is null.
  2. `LocalMapping::InitializeIMU`'s gravity-alignment step (`src/LocalMapping.cc`, computing
     `Rwg` via `Sophus::SO3f::exp(v*ang/nv)`) divides by `nv = cross(gI, dirG).norm()`, which is
     (near-)zero whenever the estimated gravity direction is (near-)parallel or antiparallel to
     the reference axis — a real case, since a levelly-held phone's gravity estimate often lands
     right there. That produces NaN, which crashed the process later inside
     `Sophus::SO3::exp`'s own internal assertion (`"SO3::exp failed! omega: -nan -nan -nan"`).
     Fixed by special-casing `nv` below `1e-6f` (identity if aligned, a fixed 180° rotation if
     antiparallel) instead of dividing by ~0.
  3. Same `SO3::exp` NaN crash recurred from a **different** call site after fix #2 above:
     `Preintegrated::GetDeltaRotation()`/`GetUpdatedDeltaRotation()` (`src/ImuTypes.cc`) compute
     `Sophus::SO3f::exp(JRg * dbg)` (a gyro-bias correction) with no NaN guard — a degenerate/failed
     optimization (repeated `scale too small`) can leave a KeyFrame's bias estimate NaN-contaminated,
     which then reaches this unrelated code path on a later frame and crashes the same assertion.
     Fixed by checking `.allFinite()` on the rotation vector before calling `exp()`, falling back to
     no bias correction (zero vector) if NaN.
- **`config/monocular-inertial/iPhoneXsMax.yaml` had stale/suboptimal tuning**, all updated:
  `Camera.fps` 10.0→25.0 (was set for the pre-#10-fix ~5.9Hz reality, now 2-3x off from the
  actual ~24-30Hz and skewing ORB-SLAM3's internal timing heuristics), `ORBextractor.nFeatures`
  1000→1500 (`TRACK_REF_KF: Less than 15 matches!!` was observed causing early resets),
  `ORBextractor.iniThFAST` 20→12 (map point counts were consistently well under the feature cap,
  ~80-300 of 1500 — likely under-lit indoor scenes; the lower threshold measurably increased
  point counts, up to ~365).
- **Long-lived bridge node TCP connections degrade**: after tens of minutes, RTT balloons
  (25ms → 100-200ms) and throughput collapses even with good Wi-Fi signal, and the bridge process
  has been observed to fully stall (`Recv-Q` backing up in the kernel socket buffer, unread) once.
  A fresh reconnect (kill + restart `ios_bridge_node.py`) reliably restores full speed - suspected
  TCP congestion-control history compounding with real Wi-Fi hiccups from a hand-carried phone
  (see "What's worth doing next" for a longer-term fix).
- **Added a Start/Stop capture button to the iOS app** ([#19](https://github.com/aisys-max/slam-tx2/pull/19),
  merged, `ios/SlamCapture/`) so a test run's data isn't polluted by setup/idle motion before and
  after — camera/IMU hardware and the TCP listener still start automatically on launch, but
  nothing is sent to the TX2 until Start is tapped.
- **Root filesystem filled to 100% (`/`, `mmcblk0p1`) mid-session**, from `/var/lib/apport/coredump/`
  accumulating ~1GB core dumps from each of the mono-inertial crashes above (`ulimit -c unlimited`
  was set to capture them for gdb). This silently breaks tool output capture/shell commands with
  no obvious error pointing at disk space. Cleaned up (see sticking point below) — freed back to
  ~3.8GB available. If tools start failing with odd "output lost"/`ENOSPC`-flavored errors again,
  check `df -h /` first.
- **Found a new, unexplained failure mode: the SLAM node process survives but its ROS2 node
  disappears** — `ros2 node list` stops showing it, `/orb_slam3/trajectory`'s publisher count and
  `/camera/image_raw`'s subscriber count both drop to 0, and the process's CPU usage flatlines
  (near-zero `utime`/`stime` deltas in `/proc/<pid>/stat` over several seconds) while the raw OS
  process is still alive (not a zombie in the `ps` sense, still multi-threaded and running). Not
  yet root-caused — would need a fresh gdb-attached repro to catch. Killing and restarting the
  SLAM node is the only known workaround so far.

None of the above have fully resolved the live initialization failure by themselves. The
remaining failure modes cycle between `Fail to track local map!` (usually before the map even
reaches the 10-keyframe/2s threshold to attempt IMU init), `scale too small` (IMU init attempted
but the visual-inertial scale estimate came out degenerate), occasionally `Not enough motion
for initializing` / `bad imu flag`, and now the "node disappears" issue above. This now looks
like it may be a mix of inherent brittleness in ORB-SLAM3's mono-inertial cold-start in a small,
moderately-lit indoor space with a hand-held phone, plus at least one more real bug still to
find — see "What's worth doing next". **As of this writing, no attempt in the 2026-09-20 session
has successfully drawn a live Path in RViz.**

## What's worth doing next

1. **Root-cause the "SLAM node disappears from the ROS2 graph" issue above** — this is the
   current blocker on top of everything else being fixed. Repro under gdb (like the two earlier
   crashes were caught) to get a real backtrace of whichever thread is dying; the working
   hypothesis is an uncaught C++ exception unwinding and destroying the rclcpp node/System object
   on the main thread without terminating the process, but that's unconfirmed.
2. **Fork `UZ-SLAMLab/ORB_SLAM3` (or patch `aisys-max/ORB_SLAM3_ROS2`'s build to vendor it) to
   persist the three crash fixes above** — right now they only exist as uncommitted local edits in
   `/mnt/ssd/orb_slam3_stack/ORB_SLAM3`, a plain clone of upstream with no fork/remote of our own.
   Any reset of that directory silently reintroduces all three crashes. Do this before anyone
   relies on this build again, and before debugging item 1 above eats more disk via core dumps
   (see the disk-space sticking point below).
3. **Get one successful live IMU initialization end-to-end and capture what conditions produced
   it** — none of the 2026-09-20 session's attempts succeeded despite MAXN, all three crash fixes,
   and the YAML retuning above. Try: more deliberate motion (continuous, not stop-and-check-in
   between attempts — the conversational back-and-forth of a live debugging session may itself
   have been breaking up the continuous good-tracking window IMU init needs), a brighter/more
   textured room, or eventually a longer uninterrupted walk (30s+) rather than short bursts.
4. **Investigate the long-lived bridge TCP connection degradation** (see above) — reconnecting
   works around it but isn't a real fix. Possibly worth a periodic proactive reconnect, or
   investigating whether `TCP_NODELAY`/socket buffer tuning helps.
5. **Vehicle field testing / 17 Pro Max + LiDAR expansion** — the next stage explicitly listed
   as Out of Scope in the #1 spec. Designed to be extensible just by adding
   `sensor_msgs/PointCloud2`, since it's topic-based (design intent only, not implemented). Makes
   sense to sequence this after tracking is confirmed stable post-#10.

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
9. **(Fixed 2026-09-19, [#10](https://github.com/aisys-max/slam-tx2/issues/10)) `ios_bridge_node.py`
   used to nearly monopolize one CPU core while frame rate cratered** (observed dropping as low
   as ~1.27Hz) — root cause was `sensor_msgs/Image.data`'s generated setter doing an element-wise
   Python-level type check on every frame; fixed by wrapping the assigned value in
   `array.array("B", ...)`. If you see a bridge node pegging a core again, check for a
   regression here first before assuming it's transport/USB.
10. **`ros2 topic hz` can return nothing but empty output** since its QoS doesn't match a
   best-effort publisher, so on ROS2 Foxy (which has no `--qos-reliability`-style option),
   measure actual frame rate with a separate rclpy script that subscribes with best-effort QoS
   directly instead.
11. **TX2 power mode doesn't persist across reboot.** If frame rate is inexplicably low again
   after a reboot, check `nvpmodel -q` — it may have reverted to `MAXP_CORE_ARM` (4 cores). Run
   `sudo nvpmodel -m 0 && sudo jetson_clocks` for `MAXN` (6 cores, max clocks). Watch temps
   (`cat /sys/devices/virtual/thermal/thermal_zone*/temp`) if running MAXN for a long session —
   the fan may not have been configured to respond (`nvpmodel` warns `fan mode is not set!`).
12. **The vendored upstream ORB-SLAM3 at `/mnt/ssd/orb_slam3_stack/ORB_SLAM3` has three local,
   uncommitted crash fixes** (null-pointer segfault in `Optimizer.cc`, two NaN crashes in
   `LocalMapping.cc` and `ImuTypes.cc` — see the 2026-09-20 session notes above). It's a plain
   clone of `UZ-SLAMLab/ORB_SLAM3`, not a fork, so nothing tracks these changes — if the directory
   gets reset or re-cloned, all three crashes come back silently. `libORB_SLAM3.so` must be
   rebuilt (`cd .../ORB_SLAM3/build && make ORB_SLAM3`) after any change there.
13. **`ulimit -c unlimited` + a crashing process on this TX2 fills the root filesystem fast.**
   Each mono-inertial crash left a ~1GB core dump in `/var/lib/apport/coredump/` (needs
   `sudo rm` to clear, owned by root). The root partition is only 28G and was already tight
   (~360MB free) before this session even started, so a handful of crashes is enough to hit
   `ENOSPC` and break tool output/shell commands with no obvious disk-related error message. If
   commands start failing strangely, check `df -h /` before anything else. Safe-to-clear
   candidates if it fills again: `/var/lib/apport/coredump/`, `~/.cache/uv`, `~/.cache/pip` (all
   regenerate on demand).

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
