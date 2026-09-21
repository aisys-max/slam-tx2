# IMU Initialization (never reaching VIBA1) Debugging Procedure

> 한국어 버전은 [여기](imu-init-debug.ko.md)에 있습니다.

**Symptom**: the `mono-inertial` node repeatedly succeeds at `New Map created` (monocular
bootstrap) but never once reaches `start VIBA 1` (IMU initialization stage 2).
**Background**: written from analysis of the 2026-09-20 live re-verification session on the
`KTM4RL` Wi-Fi network, logs `/mnt/ssd/live_e2e/issue10_oldwifi_back/slam_node.log` +
`/mnt/ssd/live_e2e/bridge_oldwifi_back.log`. The generic "RViz Path not drawing" checklist
(topic/frame_id/QoS/TF) is already fully verified as passing (Path does draw briefly) and is
out of scope here — see the "Live re-verification session" section of `docs/handoff.md`.

## Established facts (from the 2026-09-20 session logs)

Every number in this section came from directly parsing the two log files above; reuse the
same approach (grep -c, the correlation script below) to re-check against a new session's logs.

- `New Map created`: 115 times / `Fail to track local map!`: 113 times / `start VIBA`:
  **0 times** → monocular bootstrap itself is not the problem. Tracking never survives long
  enough to reach the IMU-init threshold (minimum keyframe count + elapsed time).
- After `New Map created`, almost without exception (**within 1-3 log lines**, i.e. the very
  next processed frame) `TRACK_REF_KF: Less than 15 matches!!` → `Fail to track local map!` →
  reset follows. No exceptions across a 362-event sample.
- In the same session the bridge node (`ios_bridge_node.py`) logged 402 "연결 끊김: timed out"
  → reconnect cycles at a **~10-12 second period**. This period matches `recv_timeout=10.0`
  (the default, overridable via `--recv-timeout`).
- ORB extractor settings (`nFeatures=1500`, `iniThFAST=12`) and `fps=25` are confirmed applied
  via the "ORB Extractor Parameters" log output at startup — config is not the problem.

## Leading hypothesis

The bridge's `recv_timeout` combines with periodic network/iPhone-side stalls to drop and
reconnect the connection roughly every 10 seconds. Camera frames go missing entirely during
that gap, so the "next frame" the SLAM node receives right after reconnect is actually a scene
displaced by several real seconds of motion from the previous one → parallax/appearance jumps
too far → matches against the reference keyframe drop below 15 → immediate tracking failure →
reset. This cycle repeats before a continuous tracking window long enough for IMU init (minimum
keyframe count + 2s) can ever be established.

If this holds, the earlier "bad luck with motion timing" explanation was wrong — this is a
**network stability problem**.

## Steps

### Step 1 - Re-confirm the correlation between reset times and reconnect times

Check whether the same pattern shows up in other session logs (just swap the file paths):

```bash
python3 - <<'EOF'
import re
from datetime import datetime

bridge_log = "/mnt/ssd/live_e2e/<bridge log path>"
slam_log = "/mnt/ssd/live_e2e/<slam_node.log path>"

bridge_events = []
for l in open(bridge_log):
    m = re.match(r"\[\w+\] \[(\d+)\.\d+\] \[ios_bridge\]: (.+)", l)
    if m and ("연결됨" in m.group(2) or "끊김" in m.group(2)):
        bridge_events.append((float(m.group(1)), m.group(2).strip()))

reset_lines = []
prev_t = None
for l in open(slam_log):
    m = re.match(r"\[\w+\] \[(\d+)\.\d+\]", l)
    if m:
        prev_t = float(m.group(1))
    if "Fail to track local map" in l and prev_t:
        reset_lines.append(prev_t)

import statistics
diffs = []
for rt in reset_lines:
    nearest = min(bridge_events, key=lambda be: abs(be[0]-rt))
    diffs.append(abs(nearest[0]-rt))
print(f"{len(reset_lines)} resets, mean gap to nearest bridge event {statistics.mean(diffs):.2f}s, "
      f"median {statistics.median(diffs):.2f}s")
print(f"fraction within 2s: {sum(1 for d in diffs if d<2)/len(diffs)*100:.0f}%")
EOF
```

- **PASS criterion**: most resets (roughly 70%+) fall within ±2s of a bridge reconnect event
  → hypothesis confirmed, go to Step 2
- **FAIL criterion**: no correlation → hypothesis rejected, skip directly to Step 4
  (motion/environment cause)

### Step 2 - Isolate whether the stall is in the bridge code or the iPhone/Wi-Fi link

Connect directly to the iPhone with `test_ios_tcp_client.py`, bypassing the bridge, for 60+
seconds:

```bash
python3 scripts/test_ios_tcp_client.py --connect <iPhone IP> --duration 60
```

- **PASS (reproduces)**: the same-period timeout/disconnect reproduces even without the bridge
  → the problem is the iPhone/Wi-Fi link itself, not the bridge code → Step 3
- **FAIL (does not reproduce)**: only happens through the bridge → re-examine
  `ios_bridge_node.py`'s event loop / `_recv_exact_before_deadline` logic (e.g. check whether
  the deadline is accidentally cumulative across messages rather than per-message)

### Step 3 - Rule out iPhone Wi-Fi power-saving / Low Power Mode

- Turn off Low Power Mode on the iPhone, keep the screen on, and re-run Step 2
- Code check: confirm whether `TCPServer.swift` sets `TCP_NODELAY` (disables Nagle) or
  keep-alive on the socket (`ios/SlamCapture/TCPServer.swift`)
- **PASS**: the ~10s-period stall still reproduces with Low Power Mode off → not an iOS setting
  issue, go to Step 5 (bridge timeout experiment)
- **FAIL**: disappears once Low Power Mode is off → document this as a usage precondition
  (README: "turn off Low Power Mode before capturing"), go to Step 6 (end-to-end confirmation)

### Step 4 - (only if Step 1 FAILed) Confirm whether the immediate match failure is really
low-texture/motion related

- Save the two actual frames — right after `New Map created` and the very next processed frame
  — and compare them visually (view `/camera/image_raw` live with `rqt_image_view` and capture
  at the moment of reset, or temporarily add a frame-dump option to the bridge)
- **PASS (frames differ a lot — heavy blur or a very different scene)**: motion speed/blur
  problem → adjust the capture protocol to move very slowly for the first few seconds after
  init
- **FAIL (frames look nearly identical to the eye, yet matching still fails)**: possible bug in
  the matching/descriptor computation itself → needs a code-level look at
  `ORBmatcher`/`TrackReferenceKeyFrame`

### Step 5 - `recv_timeout` relaxation experiment (fast, no code change, CLI flag only)

```bash
python3 scripts/ios_bridge_node.py <iPhone IP> 8765 --recv-timeout 60
```

- **PASS**: reconnect frequency drops sharply, and `start VIBA` appears at least once in the
  same amount of capture time → root cause confirmed. Follow up with a proper fix (raise the
  default `recv_timeout`, or add a heartbeat/keep-alive) as a PR
- **FAIL**: reconnects drop but `Fail to track local map!` still repeats immediately →
  `recv_timeout` was not the sole cause, pursue Step 4 in parallel

### Step 6 - End-to-end confirmation

After applying whichever fix came out of the steps above, confirm across 3+ independent
sessions that `start VIBA 1` appears and RViz's Path persists without a tracking reset for at
least several seconds. Consider it done once all 3 succeed.

## Decision tree summary

```
Step 1 PASS (reset times ≈ reconnect times)
  → Step 2 PASS (reproduces without bridge) → Step 3
      → Step 3 PASS (still reproduces with Low Power Mode off) → Step 5
      → Step 3 FAIL (resolved by turning it off) → Step 6
  → Step 2 FAIL (only reproduces through bridge) → re-examine bridge code
Step 1 FAIL (reset times unrelated to reconnects)
  → Step 4 → PASS (motion/blur) or FAIL (investigate matching bug in code)
```

## Follow-up findings (2026-09-21) - conclusion

Step 5 above (`recv_timeout` relaxation) turned out to be a real partial cause —
`ios_bridge_node.py`'s `_recv_exact_before_deadline()` had a bug: a fixed deadline for the whole
message rather than a true idle timeout. Fixed as `_recv_exact_idle_timeout()`, which eliminated
reconnects entirely at the *default* `--recv-timeout 10.0` (slam-tx2#20, PR #21). But the core
tracking failure (`Fail to track local map!`, immediately after init) remained unresolved even
after that. The following were additionally tested/ruled out:

- **Insufficient parallax**: instrumented `TwoViewReconstruction.cc` and measured actual
  parallax at init time — 1-6.6 degrees, mostly clustered at 1-3. Raising `minParallax` from
  1.0 to 3.0 accepted only clearly-good inits (3.5-6.2 degrees) but **failed just as
  immediately** — parallax was not the cause. (Experimental code reverted.)
- **The real bottleneck is past TrackReferenceKeyFrame, in SearchLocalPoints/reprojection**:
  instrumentation showed raw matches (`aux1`) were generally plentiful, but post-optimization
  inliers varied wildly. Notably, one instrumented run tracked **~90 frames continuously with
  200+ inliers** — solid proof this pipeline/data *can* track well. Right after that, a crash
  occurred during an actual IMU-init attempt (`scale too small`) — the 4th null-guard bug in
  `Optimizer.cc` (already fixed/committed, see "Live re-verification session" above). A second
  gdb repro attempt didn't reproduce it (timing-dependent), but confirmed the 4 existing guards
  work correctly.
- **The bag replay itself was non-deterministic (key finding)**: why identical bag replays
  produced different SLAM outcomes was confirmed by measuring with SLAM entirely out of the
  loop, using a plain subscriber — best-effort QoS + a shallow queue was silently dropping a
  different set of messages every replay (image count varied 1182-1184 of 1184 recorded, IMU
  count varied 16007-16522 of 16525 recorded). Added a `reliable_sensor_qos` parameter to
  `aisys-max/ORB_SLAM3_ROS2` (live capture stays best-effort by default) to make bag-based
  comparisons deterministic. See [docs/bag-replay-determinism.md](bag-replay-determinism.md)
  for details (slam-tx2 PR #21). Even with input confirmed byte-identical, though, SLAM's
  outcome still varied slightly (42 vs. 43 resets) — the remaining non-determinism is inside
  ORB-SLAM3's own multi-threaded execution order (not fixed by input data alone).

**An important correction**: the failure hit most often right now (`Fail to track local map!`,
before IMU init) happens in a **purely vision-based** code path -
`Optimizer::PoseOptimization()`, taken specifically when `!mpAtlas->isImuInitialized()`. That
means Tbc/IMU-noise calibration precision (e.g. via Kalibr) is **unrelated to this failure** -
IMU isn't involved in pose estimation at all at this stage yet. A proper Kalibr calibration
could only matter *after* IMU initialization actually gets underway, which this setup rarely
even reaches — making it a low-priority next step.

**Remaining, unverified leading hypothesis**: rolling-shutter distortion. Consistent with the
observed pattern — raw features, matching, and parallax are all fine, yet the failure is
specific to the stage requiring precise reprojection consistency. Confirming this requires
saving frames from the actual moment of failure (right before a reset) and inspecting them for
geometric skew — not yet done.

**Session conclusion (2026-09-21)**: this session's goal was to understand how the SLAM
pipeline behaves with the iPhone Xs Max + TX2 combination, not to ship a product on it. Every
controllable lever (CPU, crashes, network, parallax, transport determinism) was found and either
fixed or ruled out; what remains (ORB-SLAM3's inherent multi-threaded non-determinism, and
possibly rolling-shutter distortion) looks like a fundamental characteristic of this hardware
combination rather than something left to fix in software. Pausing the investigation here. If
resumed, "confirm the rolling-shutter hypothesis" above is the natural next step.
