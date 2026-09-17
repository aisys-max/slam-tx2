# Handoff (2026-09-17 기준)

새 세션/새 사람이 이 프로젝트를 이어받을 때 먼저 읽는 문서. 도메인 용어는 [CONTEXT.md](../CONTEXT.md),
설계 결정은 `docs/adr/`, 각 컴포넌트 상세는 아래 "관련 문서" 참고.

## 현재 상태

**MVP(#1) 완료.** iPhone Xs Max 카메라+IMU → Wi-Fi/USB → TX2 브리지 노드 → ORB-SLAM3
mono-inertial ROS2 노드 → `/orb_slam3/trajectory` publish까지 크래시 없이 동작하고,
`ros2 bag record`/`play`로 라이브/재생 동등성(ATE RMSE 0.177m)까지 확인했다. #2~#7 전부
닫힘. 자세한 검증 과정/결과는 [docs/live-e2e-validation.md](live-e2e-validation.md) 참고.

**열린 이슈**: [#10](https://github.com/aisys-max/slam-tx2/issues/10) — TX2 실시간(20Hz)
mono-inertial 처리 성능 격차. MVP 스펙(#1)의 Out of Scope에 명시된 "실시간 성능 최적화"
항목이라 MVP 완료를 막지 않았지만, 실사용을 위해선 다뤄야 한다.

## 다음에 할 만한 일

1. **#10 성능 격차** — USB/iproxy보다 Wi-Fi 직결이 훨씬 빠르다는 게 이미 확인됨
   (Frame ~21Hz vs ~5.9Hz, IMU ~90-99Hz vs ~50-69Hz, #10에 기록됨). 목표 20Hz에는 아직
   못 미친다.
2. **트래킹 안정성** — 라이브 세션에서 `Not enough motion for initializing` /
   `bad imu flag`로 맵 리셋이 잦다. 원인은 `config/monocular-inertial/iPhoneXsMax.yaml`의
   `Tbc`(단위행렬 근사)와 IMU 노이즈 파라미터(EuRoC 기본값 그대로)가 실측이 아니기 때문 —
   실측 캘리브레이션(카메라-IMU 외부 파라미터, Allan variance 등)을 하면 개선될 가능성이 크다.
3. **차량 실측 / 17 Pro Max + LiDAR 확장** — #1 스펙의 Out of Scope에 명시된 다음 단계.
   토픽 기반 구조라 `sensor_msgs/PointCloud2` 추가만으로 확장 가능하도록 설계되어 있다
   (설계 의도만 있고 구현은 없음).

## 라이브 세션을 다시 돌리려면

`docs/live-e2e-validation.md`의 "0. 사전 준비"~"4. 라이브 vs 재생 비교" 절차를 그대로 따르면
된다. 요약:

1. iPhone에서 `SlamCapture` 앱 실행 (Wi-Fi 직결 권장 — USB/iproxy보다 빠름, IP는 iPhone
   설정에서 확인)
2. `python3 scripts/ios_bridge_node.py <iPhone IP> 8765` (브리지 노드)
3. `ros2 run orbslam3 mono-inertial <vocab> <config yaml>` (SLAM 노드, 새 디렉터리에서)
4. `python3 scripts/record_trajectory_tum.py <output.tum>` (궤적 recorder — 아래 "자주
   막히는 지점" 3번 참고, `KeyFrameTrajectory.txt`보다 이걸 신뢰할 것)
5. RViz2 (물리 모니터에서 실행 — X11 forwarding은 TX2/NVIDIA-Tegra GLX 드라이버가 indirect
   rendering을 지원 안 해서 실패함): Fixed Frame `map`, Add → `/orb_slam3/trajectory` Path

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
   (`docs/ros2-topic-contract.md` 참고) — 둘 중 하나만 reliable이면 아예 매칭이 안 돼서
   메시지가 하나도 안 온다.
7. **rclpy 로거는 콜사이트별로 severity가 고정된다.** 한 줄에서 `getattr(logger, level)(msg)`
   식으로 여러 severity를 번갈아 호출하면 `ValueError`가 난다 (`scripts/ios_bridge_node.py`의
   `_make_ros_logger` 참고).
8. **ROS2 소스는 매번 이렇게 잡아야 함** (`COLCON_TRACE` unbound-variable 이슈 때문에):
   ```bash
   set +u; source /mnt/ssd/ros2_foxy/install/setup.bash; set -u
   ```

## 저장소/환경 구조

- 메인 저장소(이 repo, `aisys-max/slam-tx2`): PR 기반 워크플로. iOS 앱, 브리지 노드, 문서,
  검증 스크립트.
- ORB-SLAM3 ROS2 래퍼(`aisys-max/ORB_SLAM3_ROS2`, 별도 repo, main 직커밋 워크플로): 클론
  위치 `/mnt/ssd/ros2_foxy/src/slam-tx2/orbslam3`. SLAM 노드 C++ 코드가 여기 있음.
- ROS2 Foxy 빌드: `/mnt/ssd/ros2_foxy` (colcon 워크스페이스, git 추적 안 됨).
- 캡처 산출물: `/mnt/ssd/live_e2e/` (bag, trajectory.tum 등 — 세션마다 새 디렉터리 권장).

## 관련 문서

- [ros2-topic-contract.md](ros2-topic-contract.md) — 토픽/QoS/frame_id 계약
- [ios-tcp-protocol.md](ios-tcp-protocol.md) — iPhone↔TX2 와이어 프로토콜
- [ios-app-setup.md](ios-app-setup.md) — iOS 앱 Xcode 프로젝트 설정
- [camera-calibration.md](camera-calibration.md) — 체커보드 캘리브레이션 절차
- [bridge-node.md](bridge-node.md) — 브리지 노드 설정/실행/검증
- [euroc-validation.md](euroc-validation.md) — EuRoC 기반 SLAM 노드 검증(#3)
- [live-e2e-validation.md](live-e2e-validation.md) — 라이브 e2e 검증 전체 기록(#7)
- [tx2-build-notes.md](tx2-build-notes.md) — TX2 빌드 환경 노트
- `docs/adr/` — 설계 결정(타임스탬프 기준, ROS2 Foxy 채택, 어댑터 레이어 미채택, SLAM 래퍼 선택)
