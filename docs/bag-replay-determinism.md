# Bag replay determinism (#20)

> 한국어 버전은 [여기](bag-replay-determinism.ko.md)에 있습니다.

**Problem**: replaying the same bag multiple times with the same `ros2 bag play` produced
different SLAM tracking outcomes (reset frequency, where it succeeded/failed) every time —
without changing any code or config. This makes any "before/after" experiment methodology
meaningless: there's no way to tell whether a result changed because of the code change or
just because of replay luck.

## Root cause: best-effort QoS + a shallow queue drops a different set of messages every replay

`/camera/image_raw` and `/imu` use best-effort QoS on both ends, matching the live capture
contract (`docs/ros2-topic-contract.md`). Best-effort means "silently drop if the consumer can't
keep up momentarily" — exactly which messages get dropped depends on real-time timing (OS
scheduling, etc.) at replay time.

**Confirmed by direct measurement**: with SLAM code entirely out of the loop, a plain rclpy
subscriber (`scripts/measure_bag_delivery.py`) replayed the same bag twice and counted what
actually arrived:

```
Original bag: 1184 images, 16525 IMU messages

Replay 1: 1183 images, 16007 IMU messages
Replay 2: 1182 images, 16062 IMU messages
```

Even at the pure-subscription stage, with no SLAM processing involved at all, different counts
(and different timestamp sequences) arrived on each replay — "the same bag" was actually
delivering a slightly different subset every time.

## Fix: reliable QoS with a generous queue depth

Added a `reliable_sensor_qos` parameter to `aisys-max/ORB_SLAM3_ROS2@42f7729` (default `false`,
live capture behavior unchanged). Setting it to `true` switches both sensor subscriptions to
reliable QoS with a deeper queue (image: 200, IMU: 5000). The depth has to stay under FastRTPS's
default `max_samples` resource limit — setting it too high (2000/5000/20000 were all tried) fails
outright with "depth must be <= max_samples". 200 was confirmed to work fine at this project's
data volume (~25-30Hz images, ~97-100Hz IMU).

`ros2 bag play` needs a matching override via `scripts/qos_reliable_override.yaml` — if only the
publisher or only the subscriber is reliable, queue backpressure can still cause loss.

**Verified result**: measuring the same bag twice with `scripts/measure_bag_delivery.py
--reliable` gave identical image/IMU counts and identical timestamp-sequence hashes (1184/1184
images, 16522/16522 IMU, matching hashes) — the transport-layer non-determinism is confirmed
eliminated.

## Remaining non-determinism: ORB-SLAM3's own multi-threaded execution order

Even with delivery confirmed byte-identical, the SLAM node's tracking outcome across replays of
the identical bag still showed minor variation (e.g. 42 vs. 43 map resets, initial map point
counts of 596 vs. 473). Since the input is now provably identical, the remaining cause has to be
**inside** ORB-SLAM3 itself — Tracking and LocalMapping run as separate threads synchronizing
over shared state via mutexes, and their relative execution order isn't fixed by the input data
alone; it depends on OS thread scheduling. Fixing that would mean reworking ORB-SLAM3's
multi-threaded architecture itself — out of scope for this project.

## Usage

```bash
# Terminal A - SLAM node with reliable QoS
source /mnt/ssd/ros2_foxy/install/setup.bash
ros2 run orbslam3 mono-inertial <vocab> <settings> --ros-args -p reliable_sensor_qos:=true

# Terminal B - replay the bag with a matching reliable override
source /mnt/ssd/ros2_foxy/install/setup.bash
ros2 bag play <bag> --qos-profile-overrides-path scripts/qos_reliable_override.yaml

# (optional) verify delivery itself is deterministic, independent of SLAM
python3 scripts/measure_bag_delivery.py out.txt --reliable
```

**Warning**: `reliable_sensor_qos:=true` is for bag-replay-based regression testing only. Don't
use it for real iPhone live-capture verification — the bridge node always publishes best-effort
(the `docs/ros2-topic-contract.md` contract), so live verification should stay at the default
(`false`, best-effort).
