# Bridge node (#6)

> 한국어 버전은 [여기](bridge-node.ko.md)에 있습니다.

A node that receives the iPhone TCP stream (#4, `docs/ios-tcp-protocol.md`) tunneled over USB
via iproxy, and publishes it as the project's standard ROS2 sensor topics
(`docs/ros2-topic-contract.md`). Implementation:
[`scripts/ios_bridge_node.py`](../scripts/ios_bridge_node.py).

## Prerequisites

- A ROS2 Foxy workspace must be built on the TX2 (#2, `scripts/setup_tx2.sh` /
  `docs/tx2-build-notes.md`)
- The capture app (#4) must be running on the iPhone and connected to the TX2 over USB
- The calibration result (#5) must be at `calibration/iphone_xs_max_back_camera.yaml` (default
  path — a different file can be given with `--calibration`)

## Running it

1. Source the ROS2 Foxy workspace:
   ```bash
   source /mnt/ssd/ros2_foxy/install/setup.bash
   ```
2. Tunnel the iPhone's TCP server (port 8765) to a local port with iproxy (separate
   terminal/background):
   ```bash
   iproxy 8765 8765
   ```
   If multiple iOS devices are connected, check the UDID with `idevice_id -l` and target a
   specific device with `iproxy 8765 8765 <UDID>`.
3. Run the bridge node:
   ```bash
   python3 scripts/ios_bridge_node.py localhost 8765
   ```
   Adjustable via `--calibration`, `--connect-timeout` (default 5s), `--recv-timeout` (default
   10s — if no data arrives within this time it's treated as disconnected and reconnected), and
   `--retry-delay` (default 2s).

## Verification

This TX2's ROS2 Foxy build doesn't have rqt/RViz (`docs/tx2-build-notes.md` #4 — Bionic's rosdep
mapping is broken, so GUI packages, out of scope for this MVP, were excluded from the build).
Verify via CLI instead:

```bash
ros2 topic list                      # should show /camera/image_raw, /camera/camera_info, /imu
ros2 topic hz /camera/image_raw      # ~20-30Hz
ros2 topic hz /imu                   # ~99Hz (measured on iPhone Xs Max, see #4 — target 200Hz is the starting value)
ros2 topic echo /camera/camera_info  # confirm the #5 calibration values (K/D/R/P) are populated
ros2 topic echo /imu                 # confirm orientation_covariance[0] == -1.0 (orientation unused)
```

`header.stamp` is based on iPhone capture time (monotonic nanoseconds) (ADR-0001), not the time
the TX2 received the message — it's normal for the `stamp` printed by `ros2 topic echo` to
differ from the current system time (it's a clock based on uptime since the iPhone booted, a
different reference point than wall-clock time).

## Disconnect/reconnect

- If iproxy/USB disconnects (or the iPhone app restarts), the bridge node detects this via a
  socket timeout, logs it (`Connection lost: ...` or `Connect failed: ...`), and keeps retrying
  to reconnect at `--retry-delay` intervals. Both connect and recv have timeouts, so it never
  hangs indefinitely under any circumstance.
- Once reconnected, it automatically resumes the stream and normal publishing. Frames/IMU
  samples lost during the disconnect are gone for good (no retransmission — same as the
  connection lifecycle rule in `docs/ios-tcp-protocol.md`).
- The unit tests (`scripts/test_ios_bridge_node.py`) verify this reconnect state machine with a
  fake socket: connect failure → retry → connect → mid-stream disconnect → reconnect → stream
  resumes.
