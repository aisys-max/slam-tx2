# 실내 라이브 e2e + 라이브/재생 동등성 검증 (#7)

MVP(#1) 완성 기준: iPhone을 들고 실내를 걸으며 캡처 → 브리지 노드(#6) → SLAM 노드 → 궤적
publish까지 크래시 없이 동작하고, 같은 세션을 녹화/재생했을 때 SLAM 노드가 동등하게 동작하는지
확인한다.

## 이 문서를 쓰기 전에 알아야 할 것 (사전 조사 결과)

- **SLAM 노드는 원래 실시간 궤적을 publish하지 않았다.** `KeyFrameTrajectory.txt` 파일만
  종료 시 저장했다. `aisys-max/ORB_SLAM3_ROS2`에 `/orb_slam3/trajectory`(`nav_msgs/Path`,
  reliable QoS(10), `frame_id: map`) 라이브 publish를 추가했다 — RViz2로 보려면 필수였다.
  `docs/ros2-topic-contract.md`에 `frame_id`가 왜 `map`인지(궤적은 고정된 세계 좌표계가
  필요, `camera_link`는 카메라와 같이 움직여서 안 됨) 기록해뒀다.
- **iPhone용 ORB-SLAM3 설정 YAML이 없었다.** `config/monocular-inertial/EuRoC.yaml`은 EuRoC
  데이터셋 전용이라 새로 `config/monocular-inertial/iPhoneXsMax.yaml`을 추가했다 (#5 캘리브레이션
  값 사용). **두 가지는 근사치다** (YAML 안에 주석으로도 남겨둠):
  - `Tbc`(카메라-IMU 외부 캘리브레이션)를 단위행렬로 근사 — 실제 측정 안 함 (계약 문서에도
    "이번 MVP 범위 밖"으로 명시돼 있던 부분)
  - IMU 노이즈 파라미터는 EuRoC 기본값을 그대로 씀 — iPhone 실측 아님
  - `Camera.fps`/`IMU.Frequency`는 프로토콜 목표치가 아니라 #6/#10에서 실측된 값에 가깝게 낮춰
    잡음 (USB/iproxy 대역폭 한계로 프레임 ~5.9Hz, IMU 버스트 50~99Hz)
- **RViz2가 이 TX2 ROS2 Foxy 빌드엔 없었다** (`docs/tx2-build-notes.md` #4에서 rosdep 문제로
  제외). 다시 빌드해 추가했다 — Bionic 실제 패키지명이 rosdep 인덱스(t64 접미사, Ubuntu 24.04
  기준)와 안 맞는 문제를 `--skip-keys`로 우회했다 (`libqt5-core` 등 4개 키, 이미 설치돼 있던
  Qt5/OpenGL dev 패키지로 충분했고 `libassimp-dev`만 추가 설치).
- **실시간(1.0배속) 처리 자체가 신뢰성 문제가 있다는 게 #3에서 이미 확인됨** (EuRoC를 1.0배속
  재생 시 ATE 1.18m, 0.3배속으론 0.093m). 라이브 캡처는 배속 조절이 불가능하므로 이 문제가
  그대로 나타날 수 있다 — "크래시 없이 동작"은 통과해도 궤적 품질은 나쁠 수 있다. 이건 알려진
  한계(#10)지 이번 검증의 새로운 버그가 아니다.
- **DISPLAY**: 이 TX2는 헤드리스다. RViz2를 보려면 TX2에 물리 연결된 모니터로 직접 로그인해
  그래픽 세션(진짜 `DISPLAY`)을 얻어야 한다 — 지금 이 작업을 하고 있는 SSH/원격 터미널
  세션들은 `DISPLAY`가 없다.

## 사전 준비

- TX2에 물리 모니터로 로그인 (그래픽 세션, RViz2용)
- 별도로 SSH/터미널 세션 여러 개 (iproxy, 브리지 노드, SLAM 노드, bag record용 — 아래는
  "터미널 A/B/C/D"로 구분)
- iPhone에서 SlamCapture 앱 실행, USB로 TX2에 연결
- `calibration/iphone_xs_max_back_camera.yaml` 존재 확인 (#5)

## 1. 라이브 세션 준비

**터미널 A (물리 모니터, 그래픽 세션)** — RViz2:
```bash
source /mnt/ssd/ros2_foxy/install/setup.bash
ros2 run rviz2 rviz2
```
뜨면: Fixed Frame을 `map`으로 바꾸고, Add → By topic → `/orb_slam3/trajectory` → Path 추가.
참고 삼아 Add → By topic → `/camera/image_raw` → Image도 추가해두면 좋다.

**터미널 B** — iproxy:
```bash
iproxy 8765 8765
```

**터미널 C** — 브리지 노드 (#6):
```bash
source /mnt/ssd/ros2_foxy/install/setup.bash
cd /mnt/ssd/repos/slam-tx2
python3 scripts/ios_bridge_node.py localhost 8765
```
`연결됨` 로그와 `docs/bridge-node.md`의 검증 절차(`ros2 topic hz` 등)로 데이터가 오는지 먼저
확인할 것.

**터미널 D** — SLAM 노드. 작업 디렉터리에 `KeyFrameTrajectory.txt`가 저장되므로 세션마다
새 디렉터리에서 실행:
```bash
source /mnt/ssd/ros2_foxy/install/setup.bash
mkdir -p /mnt/ssd/live_e2e/live_run && cd /mnt/ssd/live_e2e/live_run
ros2 run orbslam3 mono-inertial \
  /mnt/ssd/orb_slam3_stack/ORB_SLAM3/Vocabulary/ORBvoc.txt \
  /mnt/ssd/ros2_foxy/src/slam-tx2/orbslam3/config/monocular-inertial/iPhoneXsMax.yaml
```
어휘(vocabulary, 145MB) 로딩에 시간이 걸린다 — "There are 1 cameras" 같은 로그가 뜰 때까지
기다린 뒤 다음 단계로.

## 2. 녹화 시작 + 걷기

**터미널 E** — bag 녹화 (SLAM 노드가 뜬 뒤 시작):
```bash
source /mnt/ssd/ros2_foxy/install/setup.bash
mkdir -p /mnt/ssd/live_e2e && cd /mnt/ssd/live_e2e
ros2 bag record /camera/image_raw /camera/camera_info /imu -o indoor_walk_bag
```
**`/orb_slam3/trajectory`는 녹화하지 않는다** — 나중에 재생할 때 이 bag을 SLAM 노드의 입력으로
쓸 건데, 녹화된 옛 궤적과 재생 시 새로 켠 SLAM 노드가 만드는 새 궤적이 같은 토픽에서 충돌하면
안 되기 때문이다. bag은 어디까지나 "SLAM 노드가 받는 입력"만 담는다.

녹화가 시작되면 iPhone을 들고 실내를 걸어다닌다 (알아볼 수 있는 경로 — 예: 사각형으로 한 바퀴,
또는 복도 왕복). RViz2의 Path가 그 경로와 정성적으로 비슷하게 그려지는지 지켜본다.

다 걸었으면:
1. 터미널 E에서 Ctrl+C로 녹화 종료
2. 터미널 D에서 Ctrl+C로 SLAM 노드 종료 (종료 시 `live_run/KeyFrameTrajectory.txt` 저장됨)
3. 터미널 C(브리지 노드), B(iproxy)도 정리

## 3. 재생 검증

새 SLAM 노드를 다른 디렉터리에서 띄운 뒤 (브리지 노드/iPhone 없이, bag만으로):

```bash
source /mnt/ssd/ros2_foxy/install/setup.bash
mkdir -p /mnt/ssd/live_e2e/replay_run && cd /mnt/ssd/live_e2e/replay_run
ros2 run orbslam3 mono-inertial \
  /mnt/ssd/orb_slam3_stack/ORB_SLAM3/Vocabulary/ORBvoc.txt \
  /mnt/ssd/ros2_foxy/src/slam-tx2/orbslam3/config/monocular-inertial/iPhoneXsMax.yaml
```

로딩 끝난 뒤 다른 터미널에서:
```bash
source /mnt/ssd/ros2_foxy/install/setup.bash
ros2 bag play /mnt/ssd/live_e2e/indoor_walk_bag
```
(RViz2를 계속 띄워두면 재생 중에도 Path가 그려지는 걸 볼 수 있다.)

재생이 끝나면 SLAM 노드를 Ctrl+C로 종료 (`replay_run/KeyFrameTrajectory.txt` 저장됨).

## 4. 라이브 vs 재생 비교

`scripts/evaluate_ate.py`(#3에서 만든 TUM 궤적 비교 도구, groundtruth 전용이 아니라 임의의 두
TUM 궤적을 비교하는 범용 도구)를 그대로 재사용한다 — 라이브 궤적을 "추정치", 재생 궤적을
"참조"로 놓고 둘 사이의 정합 오차(ATE)를 계산:

```bash
python3 scripts/evaluate_ate.py \
  /mnt/ssd/live_e2e/live_run/KeyFrameTrajectory.txt \
  /mnt/ssd/live_e2e/replay_run/KeyFrameTrajectory.txt
```

결과 기록에 남길 것:
- 라이브/재생 둘 다 크래시 없이 끝났는지, `KeyFrameTrajectory.txt`가 둘 다 생성됐는지
- 둘의 ATE (완전히 같을 필요는 없다 — IMU 초기화 타이밍이나 트래킹 유실/재초기화 시점이 조금만
  달라도 값이 벌어질 수 있다. 다만 자릿수가 크게 다르면(예: 한쪽만 수십 cm 이상 어긋남) 라이브
  경로와 재생 경로가 실제로 다르게 동작했다는 뜻이니 원인을 봐야 한다)
- RViz2에서 본 라이브 궤적이 실제로 걸은 경로와 정성적으로 맞았는지 (주관적 판단, 스크린샷 권장)
- 트래킹이 중간에 끊기거나(`Fail to track local map!` 등 로그) 맵이 리셋됐는지 — #10 성능 격차의
  실제 영향 여부를 판단하는 데 중요한 관찰이다
