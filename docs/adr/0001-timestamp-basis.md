# Session timestamps are based on iPhone capture time

> 한국어 버전은 [여기](0001-timestamp-basis.ko.md)에 있습니다.

USB transfer latency is not constant, so if the TX2's receipt time were used as the session's
timestamp basis, the relative timing between camera and IMU would jitter, which could break
visual-inertial initialization/alignment. All frame and IMU sample timestamps in a Session
therefore use the capture time from the iPhone's monotonic clock, never the TX2's receipt time.
