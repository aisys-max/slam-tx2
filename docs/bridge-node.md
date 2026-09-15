# 브리지 노드 (#6)

iPhone TCP 스트림(#4, `docs/ios-tcp-protocol.md`)을 iproxy로 USB 터널링받아, 프로젝트 표준
ROS2 센서 토픽(`docs/ros2-topic-contract.md`)으로 publish하는 노드. 구현은
[`scripts/ios_bridge_node.py`](../scripts/ios_bridge_node.py).

## 사전 준비

- TX2에 ROS2 Foxy 워크스페이스가 빌드되어 있을 것 (#2, `scripts/setup_tx2.sh` /
  `docs/tx2-build-notes.md`)
- iPhone에서 캡처 앱(#4)이 실행 중이고 USB로 TX2에 연결되어 있을 것
- 캘리브레이션 결과(#5)가 `calibration/iphone_xs_max_back_camera.yaml`에 있을 것 (기본 경로 —
  `--calibration`으로 다른 파일 지정 가능)

## 실행

1. ROS2 Foxy 워크스페이스를 source:
   ```bash
   source /mnt/ssd/ros2_foxy/install/setup.bash
   ```
2. iproxy로 iPhone의 TCP 서버(포트 8765)를 로컬 포트로 터널링 (별도 터미널/백그라운드):
   ```bash
   iproxy 8765 8765
   ```
   여러 iOS 기기가 붙어있으면 `idevice_id -l`로 UDID를 확인해 `iproxy 8765 8765 <UDID>`로 특정
   기기를 지정한다.
3. 브리지 노드 실행:
   ```bash
   python3 scripts/ios_bridge_node.py localhost 8765
   ```
   `--calibration`, `--connect-timeout`(기본 5초), `--recv-timeout`(기본 10초 — 이 시간 동안
   데이터가 없으면 끊긴 것으로 보고 재연결), `--retry-delay`(기본 2초)로 조정 가능.

## 검증

이 TX2의 ROS2 Foxy 빌드에는 rqt/RViz가 없다 (`docs/tx2-build-notes.md` #4 — Bionic용 rosdep
매핑이 깨져 있어 이번 MVP 범위 밖인 GUI 패키지를 빌드에서 제외함). CLI로 확인한다:

```bash
ros2 topic list                      # /camera/image_raw, /camera/camera_info, /imu 가 보여야 함
ros2 topic hz /camera/image_raw      # ~20-30Hz
ros2 topic hz /imu                   # ~99Hz (iPhone Xs Max 실측치, #4 참고 — 목표 200Hz는 시작값)
ros2 topic echo /camera/camera_info  # #5 캘리브레이션 값(K/D/R/P)이 채워져 있는지 확인
ros2 topic echo /imu                 # orientation_covariance[0] == -1.0 인지 확인 (orientation 미사용)
```

`header.stamp`는 iPhone 캡처 시각(모노토닉 나노초) 기준이며 (ADR-0001), TX2가 메시지를 받은
시각이 아니다 — `ros2 topic echo`로 찍히는 `stamp`가 시스템 현재 시각과 다를 수 있는 게 정상이다
(iPhone 부팅 이후 uptime 기준 클럭이라 벽시계와 다른 기준점을 씀).

## 연결 끊김/재연결

- `iproxy`/USB가 끊기면(또는 iPhone 앱이 재시작되면) 브리지 노드는 소켓 타임아웃으로 이를
  감지해 로그(`연결 끊김: ...` 또는 `접속 실패: ...`)를 남기고 `--retry-delay` 간격으로
  재연결을 계속 시도한다. connect/recv 모두 타임아웃이 걸려 있어 어떤 상황에서도 무한정
  멈춰있지 않는다.
- 재연결되면 자동으로 스트림을 이어받아 정상 publish를 재개한다. 끊긴 동안의 프레임/IMU는
  유실된다 (재전송 없음 — `docs/ios-tcp-protocol.md`의 연결 생명주기 규칙과 동일).
- 단위 테스트(`scripts/test_ios_bridge_node.py`)가 이 재연결 상태 머신을 가짜 소켓으로
  검증한다: 접속 실패 → 재시도 → 연결 → 중간 끊김 → 재연결 → 스트림 재개까지.
