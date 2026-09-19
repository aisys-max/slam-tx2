# Indoor live e2e + live/replay equivalence validation (#7)

> 한국어 버전은 [여기](live-e2e-validation.ko.md)에 있습니다.

MVP (#1) completion criteria: capturing while walking indoors with the iPhone → bridge node
(#6) → SLAM node → trajectory publish works without crashing, and the SLAM node behaves
equivalently when the same Session is recorded/replayed.

## Progress (completed 2026-09-17)

Things found/fixed while actually running a full live session on real hardware for the first
time (2026-09-16~17), in chronological order:

1. **A bug where iOS `TCPServer.swift`'s `frameInFlight` backpressure flag gets stuck forever.**
   If a reconnect happens mid-transfer, there's no way to reset `frameInFlight`, so after that
   only IMU goes out and frames never do. Fixed by resetting it on every new connection in
   `accept()` (this repo, commit in the next session if not already committed —
   `ios/SlamCapture/TCPServer.swift`). **Requires an Xcode rebuild + reinstall on the iPhone to
   take effect.**
2. **`monocular-inertial-slam-node.cpp`'s subscription was on the default (reliable) QoS** — the
   bridge node publishes best-effort per the contract, so they never matched at all, meaning
   live capture received zero images/IMU. Fixed in `aisys-max/ORB_SLAM3_ROS2` with
   `rclcpp::QoS(depth).best_effort()`. (Why #3's EuRoC validation didn't catch this bug: `ros2
   bag play` replays a topic with unspecified QoS as reliable by default, so it happened to
   match by accident.)
3. **`SyncWithImu()` busy-waits with no sleep when there's nothing to process** — pegging one
   TX2 core continuously at 100%, competing for CPU with the executor thread that actually
   delivers callbacks on a TX2 with only 4 cores. Added a 1ms sleep to every "nothing to do"
   path.
4. **(Unresolved as of the night of 2026-09-16, root cause confirmed the morning of
   2026-09-17)**: even after fixing all three of the above, `GrabImu` kept getting called
   (~100Hz) but `GrabImage` was never called even once. The leading hypothesis at the time was
   DDS (FastRTPS) fragmentation interacting with best-effort. **This hypothesis was wrong**:
   even temporarily switching both the `/camera/image_raw` publish (bridge node) and subscribe
   (SLAM node) sides to reliable QoS and rebuilding/rerunning (for diagnosis only, violating the
   contract), `GrabImage` was still called 0 times. With reliable QoS, DDS retransmits lost
   fragments, so if it still doesn't work, it means it's not a fragmentation/QoS problem — after
   diagnosing, reverted both files back to best-effort and rebuilt.
   **Actual cause**: even connecting directly to the iPhone with `test_ios_tcp_client.py
   --connect`, bypassing the bridge node entirely, showed `Frame 0, IMU 790` — **the iPhone app
   itself wasn't sending a single frame.** This was the `frameInFlight` bug from item 1 itself:
   the code fix was in the repo, but the app the previous night had only been restarted, never
   rebuilt/reinstalled via Xcode, so over a night of repeated reconnects the flag got stuck
   permanently again. **What's needed next isn't diagnosis but deployment**: just rebuild
   `ios/SlamCapture` with Xcode on the Mac and reinstall on the iPhone. The temporary `[DEBUG]`
   logs left in `aisys-max/ORB_SLAM3_ROS2` (`GrabImu`/`GrabImage`/`SyncWithImu`) get removed
   once frames are confirmed actually coming in.
5. Also confirmed Wi-Fi direct is much faster than USB/iproxy (Frame ~21Hz vs ~5.9Hz, IMU
   ~90-99Hz vs ~50-69Hz) — meaning USB/iproxy bandwidth was the bottleneck, recorded in #10.
6. **After the iOS rebuild/reinstall in PR #14**: confirmed `Frame 222 (27.6Hz), IMU 785
   (97.8Hz)` over a direct connection → `GrabImage` now getting called normally all the way
   through bridge node → SLAM node. After this, there was one more instance of the "thought Path
   was added in RViz2 but it actually wasn't subscribed" mistake — only confirmed by seeing
   `Subscription count: 0` from `ros2 topic info /orb_slam3/trajectory --verbose`. The RViz Path
   display can appear in the list without actually being subscribed to its Topic field, so if
   nothing draws, check the subscriber count with this command first.
7. **Pure rotation (spinning in place) is the worst possible input for monocular SLAM** — no
   parallax means no triangulation, so tracking keeps getting lost/reinitializing. Switching to a
   path with actual translation (walking in a square, etc.) did get it to initialize, but this
   time it reset frequently with `Not enough motion for initializing. Reseting...` /
   `TRACK: Reset map because local mapper set the bad imu flag` — since `Tbc` is an identity-
   matrix approximation and the IMU noise is the EuRoC default rather than measured on the
   iPhone, VIO's initialization consistency checks seem to fail often (a known, fundamentally
   hard-to-fix-without-real-calibration consequence of an approximation already flagged as out
   of MVP scope — see `config/monocular-inertial/iPhoneXsMax.yaml`).
8. **`KeyFrameTrajectory.txt` was empty again** — this time for a different reason: shutdown
   happened to land right after a map reset, so the "current active map" was empty
   (`SaveKeyFrameTrajectoryTUM` saves only the active map at shutdown time, not the whole atlas).
   `/orb_slam3/trajectory` (pathMsg_) keeps accumulating regardless of map resets, so it doesn't
   have this problem — wrote `scripts/record_trajectory_tum.py` to continuously stream this
   topic into a TUM-format file (even if killed with Ctrl+C, the full trajectory up to that point
   remains). Attached this recorder to both the live and replay sides for re-validation.

## Results (2026-09-17)

Ran a live session (a square walk) and its bag replay, each with the recorder attached, and
compared:

```
Matched poses: 55 (of 121 replay poses / 158 live poses, --max-diff 0.1s)
ATE RMSE:   0.1773 m
ATE mean:   0.1298 m
ATE median: 0.0847 m
ATE max:    0.6604 m
```

Even with tracking resetting frequently, the entire pipeline — capture → bridge → SLAM →
trajectory publish → bag record → replay — ran to completion without crashing, and the
live/replay trajectories don't diverge, staying similar in shape within the same range.
**Judged to meet #7's completion criteria (crash-free operation + confirmed record/replay
equivalence).** Tracking stability itself (map reset frequency) is left as an out-of-MVP-scope
item that's fundamentally hard to improve without measured `Tbc`/IMU noise calibration.

## What you should know before reading this doc (background research)

- **The SLAM node originally didn't publish a live trajectory.** It only saved
  `KeyFrameTrajectory.txt` on exit. Added live publishing of `/orb_slam3/trajectory`
  (`nav_msgs/Path`, reliable QoS(10), `frame_id: map`) to `aisys-max/ORB_SLAM3_ROS2` — essential
  for viewing it in RViz2. `docs/ros2-topic-contract.md` records why `frame_id` is `map` (a
  trajectory needs a fixed world frame; `camera_link` moves with the camera so it can't be used).
- **There was no ORB-SLAM3 config YAML for the iPhone.** `config/monocular-inertial/EuRoC.yaml`
  is EuRoC-dataset-specific, so added a new `config/monocular-inertial/iPhoneXsMax.yaml` (using
  the #5 calibration values). **Two things in it are approximations** (also noted as comments
  in the YAML itself):
  - `Tbc` (camera-IMU extrinsic calibration) approximated as identity — not actually measured
    (already noted as "out of MVP scope" in the contract doc)
  - IMU noise parameters use the EuRoC defaults as-is — not measured on the iPhone
  - `Camera.fps`/`IMU.Frequency` are set lower, closer to the values actually measured in #6/#10
    rather than the protocol's target (~5.9Hz frame due to USB/iproxy bandwidth limits, IMU
    bursty at 50-99Hz)
- **RViz2 didn't exist in this TX2's ROS2 Foxy build** (excluded due to a rosdep issue in
  `docs/tx2-build-notes.md` #4). Rebuilt and added it — worked around Bionic's actual package
  names not matching the rosdep index (the `t64` suffix, based on Ubuntu 24.04) with
  `--skip-keys` (4 keys like `libqt5-core`; the already-installed Qt5/OpenGL dev packages were
  enough, only needed to additionally install `libassimp-dev`).
- **#3 already confirmed real-time (1.0x) processing itself has a reliability problem** (ATE
  1.18m replaying EuRoC at 1.0x, 0.093m at 0.3x). Live capture can't adjust playback speed, so
  this problem can show up as-is — "runs without crashing" can pass while trajectory quality is
  still bad. This is a known limitation (#10), not a new bug from this validation.
- **DISPLAY**: this TX2 is headless. To see RViz2, you need to log in directly through a monitor
  physically connected to the TX2 to get a graphical session (a real `DISPLAY`) — the SSH/remote
  terminal sessions used to do this work have no `DISPLAY`.

## Prerequisites

- Logged into the TX2 via a physical monitor (graphical session, for RViz2)
- Several separate SSH/terminal sessions (for iproxy, the bridge node, the SLAM node, bag
  record — referred to below as "Terminal A/B/C/D")
- The SlamCapture app running on the iPhone, connected to the TX2 over USB
- Confirm `calibration/iphone_xs_max_back_camera.yaml` exists (#5)

## 1. Preparing the live session

**Terminal A (physical monitor, graphical session)** — RViz2:
```bash
source /mnt/ssd/ros2_foxy/install/setup.bash
ros2 run rviz2 rviz2
```
Once it's up: change Fixed Frame to `map`, and Add → By topic → `/orb_slam3/trajectory` → Path.
It's also nice to add Add → By topic → `/camera/image_raw` → Image for reference.

**Terminal B** — iproxy:
```bash
iproxy 8765 8765
```

**Terminal C** — bridge node (#6):
```bash
source /mnt/ssd/ros2_foxy/install/setup.bash
cd /mnt/ssd/repos/slam-tx2
python3 scripts/ios_bridge_node.py localhost 8765
```
First confirm data is coming through via the `Connected` log and the verification procedure in
`docs/bridge-node.md` (`ros2 topic hz`, etc.).

**Terminal D** — SLAM node. Run it in a fresh directory every session:
```bash
source /mnt/ssd/ros2_foxy/install/setup.bash
mkdir -p /mnt/ssd/live_e2e/live_run && cd /mnt/ssd/live_e2e/live_run
ros2 run orbslam3 mono-inertial \
  /mnt/ssd/orb_slam3_stack/ORB_SLAM3/Vocabulary/ORBvoc.txt \
  /mnt/ssd/ros2_foxy/src/slam-tx2/orbslam3/config/monocular-inertial/iPhoneXsMax.yaml
```
Loading the vocabulary (145MB) takes a while — wait for a log like "There are 1 cameras" before
moving on.

**Terminal F** — trajectory recorder (start after the SLAM node is up; see item 8 above for why
it's needed):
```bash
source /mnt/ssd/ros2_foxy/install/setup.bash
python3 scripts/record_trajectory_tum.py /mnt/ssd/live_e2e/live_run/trajectory.tum
```
Don't rely on `KeyFrameTrajectory.txt` (a shutdown-time snapshot) — treat the `trajectory.tum`
this recorder produces as the canonical live trajectory. It's preserved without gaps even if
tracking resets mid-session.

## 2. Starting the recording + walking

**Terminal E** — bag recording (start after the SLAM node is up):
```bash
source /mnt/ssd/ros2_foxy/install/setup.bash
mkdir -p /mnt/ssd/live_e2e && cd /mnt/ssd/live_e2e
ros2 bag record /camera/image_raw /camera/camera_info /imu -o indoor_walk_bag
```
**`/orb_slam3/trajectory` is not recorded** — this bag will later be used as the SLAM node's
input during replay, and the old recorded trajectory would collide on the same topic with the
new trajectory the freshly-started SLAM node produces during replay. The bag only ever contains
"what the SLAM node receives as input".

Once recording starts, walk around indoors with the iPhone (a recognizable path — e.g. one loop
of a square, or back and forth down a hallway). Watch whether RViz2's Path is drawn qualitatively
similar to that path.

Once done walking:
1. Ctrl+C in Terminal E to stop recording
2. Ctrl+C in Terminal F (recorder) to stop (`live_run/trajectory.tum` gets its final save)
3. Ctrl+C in Terminal D to stop the SLAM node
4. Clean up Terminal C (bridge node) and B (iproxy) too

## 3. Replay validation

Start a new SLAM node in a different directory (without the bridge node/iPhone, bag only), and
attach a recorder to this one too:

```bash
source /mnt/ssd/ros2_foxy/install/setup.bash
mkdir -p /mnt/ssd/live_e2e/replay_run && cd /mnt/ssd/live_e2e/replay_run
ros2 run orbslam3 mono-inertial \
  /mnt/ssd/orb_slam3_stack/ORB_SLAM3/Vocabulary/ORBvoc.txt \
  /mnt/ssd/ros2_foxy/src/slam-tx2/orbslam3/config/monocular-inertial/iPhoneXsMax.yaml
```

Once loading finishes, start the recorder in another terminal first:
```bash
source /mnt/ssd/ros2_foxy/install/setup.bash
python3 scripts/record_trajectory_tum.py /mnt/ssd/live_e2e/replay_run/trajectory.tum
```
Then play back the bag:
```bash
source /mnt/ssd/ros2_foxy/install/setup.bash
ros2 bag play /mnt/ssd/live_e2e/indoor_walk_bag
```
(Keeping RViz2 open lets you watch the Path get drawn during replay too.)

Once replay finishes, Ctrl+C the recorder (`replay_run/trajectory.tum` gets its final save),
then stop the SLAM node too.

## 4. Comparing live vs. replay

Reuse `scripts/evaluate_ate.py` as-is (the TUM trajectory comparison tool built in #3 — a
general-purpose tool for comparing any two TUM trajectories, not groundtruth-only) — treat the
replay trajectory as the "estimate" and the live trajectory as the "reference", and compute the
alignment error (ATE) between them (using the `trajectory.tum` the recorder produces —
`KeyFrameTrajectory.txt` isn't used since its shutdown-time snapshot can be empty depending on
map reset timing):

```bash
python3 scripts/evaluate_ate.py \
  /mnt/ssd/live_e2e/replay_run/trajectory.tum \
  /mnt/ssd/live_e2e/live_run/trajectory.tum \
  --max-diff 0.1
```

What to record in the results:
- Whether both live and replay finished without crashing, and whether both `trajectory.tum`
  files are non-empty
- Their ATE (they don't need to be exactly equal — even slight differences in IMU
  initialization timing or when tracking got lost/reinitialized can spread the values apart.
  But if the magnitude is way off (e.g. only one side is off by tens of cm or more), that means
  the live and replay paths actually behaved differently, and the cause needs investigating)
- Whether the live trajectory seen in RViz2 actually matched the path walked, qualitatively
  (subjective judgment, a screenshot is recommended)
- Whether tracking got interrupted mid-session (logs like `Fail to track local map!`) or the map
  reset — an important observation for judging whether #10's performance gap actually had an
  effect
