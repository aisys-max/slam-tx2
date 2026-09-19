# Handoff (2026-09-19 기준)

> English version [here](handoff.md).

새 세션/새 사람이 이 프로젝트를 이어받을 때 먼저 읽는 문서. 도메인 용어는 [CONTEXT.md](../CONTEXT.ko.md),
설계 결정은 `docs/adr/`, 각 컴포넌트 상세는 아래 "관련 문서" 참고. **노드/스크립트 연결 관계와
RViz 라이브 확인 절차는 저장소 루트 [README.md](../README.ko.md)에 다이어그램과 함께 정리돼 있다 —
라이브 세션을 다시 돌리려면 이 문서보다 README.md를 먼저 볼 것.**

## 현재 상태

**MVP(#1) 완료.** iPhone Xs Max 카메라+IMU → Wi-Fi/USB → TX2 브리지 노드 → ORB-SLAM3
mono-inertial ROS2 노드 → `/orb_slam3/trajectory` publish까지 크래시 없이 동작하고,
`ros2 bag record`/`play`로 라이브/재생 동등성(ATE RMSE 0.177m)까지 확인했다. #2~#7 전부
닫힘. 자세한 검증 과정/결과는 [docs/live-e2e-validation.md](live-e2e-validation.ko.md) 참고.

**[#15](https://github.com/aisys-max/slam-tx2/issues/15) 닫힘 (2026-09-19)** — RViz 궤적이
실제 움직임과 다르게/끊겨 그려지던 버그. 근본 원인은 맵 리셋마다 SLAM 노드가 새 좌표계
원점을 잡는데 `/orb_slam3/trajectory`가 그걸 구분 안 하고 이전/이후 포즈를 하나로 이어붙여
publish하던 것 — `aisys-max/ORB_SLAM3_ROS2@6b6b24e`에서 리셋 시 궤적을 비우도록 수정,
라이브로 검증 완료. 같이 진행한 것들:

- **Tbc/IMU 노이즈 실측 캘리브레이션** (`aisys-max/ORB_SLAM3_ROS2@6132195`, Kalibr 없이):
  정지 자세 3개의 중력 벡터로 Tbc 회전 추정, 2시간 정지 Allan variance로 IMU 노이즈 파라미터
  실측. 기존 EuRoC 기본값이 iPhone IMU를 훨씬 나쁜 센서로 가정하고 있었다(AccWalk 33배,
  GyroWalk 5.6배, NoiseAcc 4배 과대평가). 스크립트: `scripts/capture_imu_pose.py`,
  `scripts/estimate_tbc_rotation.py`, `scripts/compute_allan_variance.py`. 원 측정치는
  [#15 코멘트](https://github.com/aisys-max/slam-tx2/issues/15)에 기록.
- **`scripts/analyze_tum_quality.py`** 추가 — TUM 궤적 파일에서 리셋/발행 gap/순간 점프를
  정량 검출. 향후 트래킹 품질 회귀 확인에 재사용.
- **`README.md`** 추가 (저장소 루트) — 노드/토픽 연결 다이어그램 + RViz 라이브 확인 재현 절차.

캘리브레이션 후에도 리셋 빈도는 개선됐을 뿐(초당 ~1회 → ~17초당 1회) 완전히 해소되지
않았고, 남은 병목은 아래 [#10](https://github.com/aisys-max/slam-tx2/issues/10)으로
이관됐다 — 프레임레이트가 여전히 낮아(~5.8Hz) `Fail to track local map!`가 반복 관찰됨.

**[#10](https://github.com/aisys-max/slam-tx2/issues/10) 수정 및 실기기 검증 완료
(2026-09-19)** — 병목은 네트워크 전송이 아니라 브리지 노드 자체의 CPU-bound 처리였다. 근본
원인: rosidl이 생성한 `sensor_msgs/Image`의 `data` setter(`_image.py`)가, 대입되는 값이
`array.array`가 아니면 배열 전체를 파이썬 레벨로 원소별 `isinstance`/범위 검증한다 —
640x480 프레임(307,200바이트) 기준 ~157ms/frame(이 필드 하나만으로 상한 ~6.4Hz), 실측
~5.8Hz와 거의 정확히 일치했다. [`build_image()`](../scripts/ios_bridge_node.py)가 기존엔
`frame["pixels"]`(`bytes`)를 그대로 대입해 매 프레임 이 느린 경로를 탔는데,
`array.array("B", ...)`로 미리 감싸 대입하면 setter의 fast path(`isinstance(value,
array.array)`)를 타게 된다. iPhone에 Wi-Fi 직결로 라이브 검증: `/camera/image_raw`가
~5.8Hz → **~27.3Hz**로, 브리지 노드 CPU가 95~100% → **~13~16%**로 개선됐고, `/imu`도
(불균일하던 50~69Hz → ~97Hz로) 회귀 없이 함께 좋아졌다.

## 다음에 할 만한 일

1. **#10 수정 후 전체 라이브 SLAM 세션 재검증** — #15의 남은 트래킹 불안정(리셋,
   `Fail to track local map!`)이 브리지 노드 프레임레이트에 달려 있다는 가설이 있었다.
   `/camera/image_raw`가 이제 목표치(20~30Hz)에 근접하므로, [README.md](../README.md)의
   RViz 라이브 확인 절차를 다시 돌려서 이 불안정이 얼마나 해소됐는지 확인할 가치가 있다.
2. **차량 실측 / 17 Pro Max + LiDAR 확장** — #1 스펙의 Out of Scope에 명시된 다음 단계.
   토픽 기반 구조라 `sensor_msgs/PointCloud2` 추가만으로 확장 가능하도록 설계되어 있다
   (설계 의도만 있고 구현은 없음). #10 수정 후 트래킹이 안정적임을 확인한 뒤 진행하는 게
   순서상 맞을 것.

## 라이브 세션을 다시 돌리려면

**절차 + 노드/스크립트 연결 다이어그램은 [README.md](../README.ko.md)에 정리돼 있다** — 여기서
중복 설명하지 않는다. 더 세세한 배경(각 단계에서 뭘 왜 그렇게 하는지)이 필요하면
`docs/live-e2e-validation.ko.md`의 "0. 사전 준비"~"4. 라이브 vs 재생 비교" 참고.

## 자주 막히는 지점 (다 겪어본 것들)

1. **iOS 앱을 코드만 고치고 재빌드를 안 하면 반영 안 됨.** 앱 재시작만으로는 Swift 소스 변경이
   기기에 절대 반영되지 않는다 — Mac에서 Xcode로 재빌드 + 재설치 필수.
2. **RViz2 Path가 "추가된 것처럼 보이는데 실제로는 안 붙어있을 수 있다.** Displays 패널에
   Path 항목이 보여도 실제 구독이 안 될 수 있으니, 안 그려지면
   `ros2 topic info /orb_slam3/trajectory --verbose`로 `Subscription count`를 확인할 것
   (rviz 노드가 있어야 함).
3. **`KeyFrameTrajectory.txt`는 종료 시점 스냅샷이라 맵이 막 리셋된 순간에 죽이면 비어버린다.**
   `scripts/record_trajectory_tum.py`로 `/orb_slam3/trajectory`를 실시간으로 흘려 저장할 것.
4. **제자리 회전(패닝/스핀)은 단안 SLAM 최악의 입력.** 평행 이동이 있는 경로(사각형 걷기 등)로
   움직여야 초기화된다.
5. **브리지 노드가 살아있는 채로 bag 재생하면 라이브 데이터와 섞인다.** 재생 검증 전엔 반드시
   `pkill -f ios_bridge_node.py`로 브리지 노드를 죽일 것.
6. **DDS best-effort/reliable QoS는 반드시 양쪽이 맞아야 한다.** 브리지 노드(발행)는
   `qos_profile_sensor_data`(best-effort), SLAM 노드 구독도 `.best_effort()`로 맞춰져 있음
   (`docs/ros2-topic-contract.ko.md` 참고) — 둘 중 하나만 reliable이면 아예 매칭이 안 돼서
   메시지가 하나도 안 온다.
7. **rclpy 로거는 콜사이트별로 severity가 고정된다.** 한 줄에서 `getattr(logger, level)(msg)`
   식으로 여러 severity를 번갈아 호출하면 `ValueError`가 난다 (`scripts/ios_bridge_node.py`의
   `_make_ros_logger` 참고).
8. **ROS2 소스는 매번 이렇게 잡아야 함** (`COLCON_TRACE` unbound-variable 이슈 때문에):
   ```bash
   set +u; source /mnt/ssd/ros2_foxy/install/setup.bash; set -u
   ```
9. **(2026-09-19 수정됨, [#10](https://github.com/aisys-max/slam-tx2/issues/10)) 예전엔
   `ios_bridge_node.py`가 CPU 한 코어를 거의 독점하면서 프레임레이트가 뚝 떨어졌다**
   (~1.27Hz까지 관찰). 원인은 `sensor_msgs/Image.data`의 생성된 setter가 매 프레임 파이썬
   레벨로 원소별 타입 검증을 하던 것 — 대입값을 `array.array("B", ...)`로 감싸 수정.
   브리지 노드가 다시 한 코어를 독점하는 걸 보면, 전송/USB 문제로 넘겨짚기 전에 여기부터
   회귀했는지 확인할 것.
10. **`ros2 topic hz`는 best-effort 발행자와 QoS가 안 맞아 빈 값만 나올 수 있다.** 실제
   프레임레이트 확인은 `--qos-reliability`류 옵션이 없는 ROS2 Foxy에서는 별도 rclpy
   스크립트(best-effort QoS로 직접 구독)로 잴 것.

## 저장소/환경 구조

- 메인 저장소(이 repo, `aisys-max/slam-tx2`): PR 기반 워크플로. iOS 앱, 브리지 노드, 문서,
  검증 스크립트.
- ORB-SLAM3 ROS2 래퍼(`aisys-max/ORB_SLAM3_ROS2`, 별도 repo, main 직커밋 워크플로): 클론
  위치 `/mnt/ssd/ros2_foxy/src/slam-tx2/orbslam3`. SLAM 노드 C++ 코드가 여기 있음.
- ROS2 Foxy 빌드: `/mnt/ssd/ros2_foxy` (colcon 워크스페이스, git 추적 안 됨).
- 캡처 산출물: `/mnt/ssd/live_e2e/` (bag, trajectory.tum 등 — 세션마다 새 디렉터리 권장).

## 관련 문서

- [ros2-topic-contract.md](ros2-topic-contract.ko.md) — 토픽/QoS/frame_id 계약
- [ios-tcp-protocol.md](ios-tcp-protocol.ko.md) — iPhone↔TX2 와이어 프로토콜
- [ios-app-setup.md](ios-app-setup.ko.md) — iOS 앱 Xcode 프로젝트 설정
- [camera-calibration.md](camera-calibration.ko.md) — 체커보드 캘리브레이션 절차
- [bridge-node.md](bridge-node.ko.md) — 브리지 노드 설정/실행/검증
- [euroc-validation.md](euroc-validation.ko.md) — EuRoC 기반 SLAM 노드 검증(#3)
- [live-e2e-validation.md](live-e2e-validation.ko.md) — 라이브 e2e 검증 전체 기록(#7)
- [tx2-build-notes.md](tx2-build-notes.ko.md) — TX2 빌드 환경 노트
- `docs/adr/` — 설계 결정(타임스탬프 기준, ROS2 Foxy 채택, 어댑터 레이어 미채택, SLAM 래퍼 선택)
