# iPhone → TX2 USB streaming wire protocol (#4)

> 한국어 버전은 [여기](ios-tcp-protocol.ko.md)에 있습니다.

The iOS capture app acts as a TCP server (fixed port **8765**), and the TX2-side bridge node
(#6) connects as a client to this port tunneled via iproxy (see the spec's Implementation
Decisions). This document is the byte-level contract between them.

Only this segment (iPhone↔TX2) uses a custom binary format — conversion into ROS2 topics only
happens **after** the bridge node ([docs/ros2-topic-contract.md](ros2-topic-contract.md)).

## Framing

Every integer/float field is **big-endian (network byte order)**. Each message:

```
[1 byte  type]
[4 bytes payload_length]   (uint32, big-endian, number of payload bytes)
[payload_length bytes]
```

`type`:
| Value | Meaning |
|---|---|
| `0x01` | Frame (camera image) |
| `0x02` | IMU sample |

## Frame (`type = 0x01`) payload

```
[8 bytes timestamp_ns]  (uint64, capture time — iPhone monotonic clock, nanoseconds. ADR-0001)
[4 bytes width]         (uint32)
[4 bytes height]        (uint32)
[4 bytes stride]        (uint32, bytes per row — usually equal to width since it's mono8)
[width*height bytes]    (mono8 grayscale, row-major, no padding — read by skipping `stride` bytes per row)
```

Encoding is always **mono8** (the Y-plane of a YUV420 capture, used as-is — see
`docs/ios-app-setup.md`). No color is sent.

## IMU sample (`type = 0x02`) payload

```
[8 bytes timestamp_ns]        (uint64, capture time — same clock basis as frames)
[8 bytes angular_velocity_x]  (float64, rad/s)
[8 bytes angular_velocity_y]  (float64, rad/s)
[8 bytes angular_velocity_z]  (float64, rad/s)
[8 bytes linear_acceleration_x] (float64, m/s^2)
[8 bytes linear_acceleration_y] (float64, m/s^2)
[8 bytes linear_acceleration_z] (float64, m/s^2)
```

CoreMotion reports acceleration in G units, so it's sent **after multiplying by 9.80665 to
convert to m/s^2** (see `MotionManager.swift`).

## Connection/lifecycle

- The app starts listening on port 8765 as soon as it launches (iPhone = TCP server, TX2 =
  client — a spec decision).
- Only one client is supported at a time. A new connection closes the previous one.
- Frames/IMU samples are sent in the order they were captured (no reordering) — sorting/syncing
  by timestamp is the receiving side's (bridge node's) responsibility.
- If the connection drops, the app returns to listening and accepts reconnects. There's no
  separate reconnection protocol (retransmission, ack, etc.) — data lost during the disconnect
  is gone for good.

## Testing

`scripts/test_ios_tcp_client.py` is a reference client implementing this protocol, doubling as
a self-test:
- `--self-test`: without a real iPhone, builds synthetic frame/IMU messages per this document's
  byte layout and confirms the parser round-trips them (encode→decode) correctly.
- `--connect <iPhone IP> 8765`: connects to the real iPhone app and prints the count, format, and
  monotonic-timestamp check of received frames/IMU samples (the "verifiable with a test client"
  criterion from #4).
