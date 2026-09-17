# 실내 라이브 e2e + 라이브/재생 동등성 검증 (#7)

MVP(#1) 완성 기준: iPhone을 들고 실내를 걸으며 캡처 → 브리지 노드(#6) → SLAM 노드 → 궤적
publish까지 크래시 없이 동작하고, 같은 세션을 녹화/재생했을 때 SLAM 노드가 동등하게 동작하는지
확인한다.

## 진행 상황 (2026-09-17 완료)

첫 실기기 시도(2026-09-16~17)에서 라이브 세션 전체를 실제로 띄워보며 발견/수정한 것들, 시간 순:

1. **iOS `TCPServer.swift`의 `frameInFlight` 백프레셔 플래그가 영원히 고정되는 버그.**
   전송 중에 재연결이 오면 `frameInFlight`를 리셋할 방법이 없어서, 그 뒤로는 IMU만 나가고
   프레임은 전혀 안 나간다. `accept()`에서 새 연결마다 리셋하도록 수정함 (이 저장소, 아직 커밋
   안 했으면 다음 세션에서 커밋 - `ios/SlamCapture/TCPServer.swift`). **Xcode로 재빌드해서
   iPhone에 다시 설치해야 반영된다.**
2. **`monocular-inertial-slam-node.cpp`의 구독이 기본(reliable) QoS였다** — 브리지 노드는
   계약대로 best-effort로 publish하니 아예 매칭이 안 돼서 라이브 캡처로는 이미지/IMU를 하나도
   못 받고 있었다. `aisys-max/ORB_SLAM3_ROS2`에서 `rclcpp::QoS(depth).best_effort()`로 수정.
   (#3 EuRoC 검증이 이 버그를 못 잡은 이유: `ros2 bag play`가 QoS 미지정 토픽을 기본 reliable로
   재생해서 우연히 맞았을 뿐.)
3. **`SyncWithImu()`가 처리할 게 없을 때 sleep 없이 busy-wait** — TX2 코어 하나를 100% 계속
   태워서, 코어 4개뿐인 TX2에서 실제 콜백을 전달하는 executor 스레드와 CPU를 놓고 경쟁했다.
   모든 "할 일 없음" 경로에 1ms sleep 추가.
4. **(2026-09-16 밤 기준 미해결이었던 것, 2026-09-17 아침에 원인 확정)**: 위 세 가지를 다
   고친 뒤에도 `GrabImu`는 계속 호출되는데(~100Hz) `GrabImage`는 단 한 번도 호출되지 않았다.
   당시 유력했던 가설은 DDS(FastRTPS) 조각화(fragmentation) + best-effort 상호작용이었다.
   **이 가설은 틀렸다**: `/camera/image_raw` 발행(브리지 노드)/구독(SLAM 노드) 양쪽을 모두
   임시로 reliable QoS로 바꿔 재빌드/재실행해도(진단용, 계약 위반) `GrabImage`는 여전히 0회.
   reliable이면 DDS가 유실된 조각을 재전송하므로, 이래도 안 되면 조각화/QoS 문제가 아니라는
   뜻 — 진단 후 두 파일 모두 best-effort로 원복하고 재빌드함.
   **실제 원인**: 브리지 노드를 거치지 않고 `test_ios_tcp_client.py --connect`로 iPhone에
   직접 붙어봐도 `Frame 0개, IMU 790개` — **iPhone 앱 자체가 프레임을 하나도 안 보내고
   있었다.** 이는 1번의 `frameInFlight` 버그 그 자체다: 코드 수정은 저장소에 있지만, 어젯밤
   앱은 재시작만 했을 뿐 Xcode로 재빌드/재설치를 안 해서, 밤새 재연결이 반복되는 사이 플래그가
   다시 영원히 고정된 상태로 돌아간 것. **다음에 할 일은 진단이 아니라 배포**: Mac에서
   `ios/SlamCapture`를 Xcode로 재빌드해서 iPhone에 다시 설치하는 것뿐이다.
   `aisys-max/ORB_SLAM3_ROS2`에 남겨둔 `[DEBUG]` 임시 로그(`GrabImu`/`GrabImage`/
   `SyncWithImu`)는 프레임이 실제로 들어오기 시작하는 걸 확인한 뒤 지운다.
5. Wi-Fi 직결이 USB/iproxy보다 훨씬 빠르다는 것도 확인됨 (Frame ~21Hz vs ~5.9Hz, IMU ~90-99Hz
   vs ~50-69Hz) - USB/iproxy 대역폭이 병목이었다는 뜻, #10에 기록함.
6. **PR #14의 iOS 재빌드/재설치 후**: 직접 연결로 `Frame 222개(27.6Hz), IMU 785개(97.8Hz)`
   확인 → 브리지 노드 → SLAM 노드까지 `GrabImage`가 정상 호출됨. 이후 RViz2에서 "Path 추가한
   줄 알았는데 실제로는 안 붙어 있던" 실수가 한 번 더 있었다 - `ros2 topic info
   /orb_slam3/trajectory --verbose`로 `Subscription count: 0`을 보고서야 확인함. RViz Path
   디스플레이가 목록에 있어 보여도 Topic 필드가 실제로 안 붙어있을 수 있으니, 안 그려지면
   이 명령으로 구독자 수부터 확인할 것.
7. **순수 회전(제자리 돌기)은 단안 SLAM에 최악의 입력이다** - 평행 이동(parallax)이 없어
   삼각측량이 안 되고 트래킹이 계속 유실/재초기화된다. 사각형으로 걷는 등 이동이 있는 경로로
   바꾸니 초기화가 되긴 했지만, 이번엔 `Not enough motion for initializing. Reseting...` /
   `TRACK: Reset map because local mapper set the bad imu flag`로 자주 리셋됨 - `Tbc`가
   단위행렬 근사치이고 IMU 노이즈가 iPhone 실측이 아닌 EuRoC 기본값이라 VIO 초기화 일관성
   검증이 자주 실패하는 것으로 보인다 (실측 캘리브레이션 없이는 근본적으로 해결이 어려운,
   이미 알려진 MVP 범위 밖 근사치의 결과 - config/monocular-inertial/iPhoneXsMax.yaml 참고).
8. **`KeyFrameTrajectory.txt`가 또 비어 있었다** - 이번엔 다른 이유: 종료 시점에 하필 맵이 막
   리셋된 직후라 "현재 활성 맵"이 비어 있었다 (`SaveKeyFrameTrajectoryTUM`은 atlas 전체가 아니라
   종료 시점 활성 맵만 저장). `/orb_slam3/trajectory`(pathMsg_)는 맵 리셋과 무관하게 계속
   누적되는 값이라 이 문제를 겪지 않으므로, `scripts/record_trajectory_tum.py`를 새로 만들어
   이 토픽을 실시간으로 TUM 포맷 파일에 계속 흘려 쓰도록 했다 (Ctrl+C로 죽여도 그 시점까지의
   전체 궤적이 남는다). 라이브/재생 양쪽에 이 recorder를 붙여서 재검증함.

## 결과 (2026-09-17)

recorder를 붙인 상태로 라이브 세션(사각형 walk)과 그 bag 재생을 각각 실행해 비교:

```
매칭된 포즈: 55개 (재생 궤적 121개 / 라이브 궤적 158개 중, --max-diff 0.1s)
ATE RMSE:   0.1773 m
ATE mean:   0.1298 m
ATE median: 0.0847 m
ATE max:    0.6604 m
```

트래킹이 자주 리셋되는 상태에서도 크래시 없이 캡처→브리지→SLAM→궤적 publish→bag 녹화→재생
전체 파이프라인이 끝까지 동작했고, 라이브/재생 궤적이 발산하지 않고 같은 범위 안에서 비슷한
형태를 보인다. **#7의 완료 기준(크래시 없는 동작 + 녹화/재생 동등성 확인)을 충족한다고 판단**.
트래킹 안정성 자체(맵 리셋 빈도)는 `Tbc`/IMU 노이즈 실측 캘리브레이션이 없는 한 근본적으로
개선하기 어려운, MVP 범위 밖 항목으로 남겨둔다.

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

**터미널 D** — SLAM 노드. 세션마다 새 디렉터리에서 실행:
```bash
source /mnt/ssd/ros2_foxy/install/setup.bash
mkdir -p /mnt/ssd/live_e2e/live_run && cd /mnt/ssd/live_e2e/live_run
ros2 run orbslam3 mono-inertial \
  /mnt/ssd/orb_slam3_stack/ORB_SLAM3/Vocabulary/ORBvoc.txt \
  /mnt/ssd/ros2_foxy/src/slam-tx2/orbslam3/config/monocular-inertial/iPhoneXsMax.yaml
```
어휘(vocabulary, 145MB) 로딩에 시간이 걸린다 — "There are 1 cameras" 같은 로그가 뜰 때까지
기다린 뒤 다음 단계로.

**터미널 F** — 궤적 recorder (SLAM 노드가 뜬 뒤 시작; 왜 필요한지는 아래 8번 참고):
```bash
source /mnt/ssd/ros2_foxy/install/setup.bash
python3 scripts/record_trajectory_tum.py /mnt/ssd/live_e2e/live_run/trajectory.tum
```
`KeyFrameTrajectory.txt`(종료 시점 스냅샷)에 의존하지 말고 이 recorder가 만드는
`trajectory.tum`을 라이브 궤적의 정본으로 쓴다 - 트래킹이 중간에 리셋돼도 누락 없이 남는다.

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
2. 터미널 F(recorder)에서 Ctrl+C로 종료 (`live_run/trajectory.tum` 최종 저장됨)
3. 터미널 D에서 Ctrl+C로 SLAM 노드 종료
4. 터미널 C(브리지 노드), B(iproxy)도 정리

## 3. 재생 검증

새 SLAM 노드를 다른 디렉터리에서 띄운 뒤 (브리지 노드/iPhone 없이, bag만으로), 여기에도
recorder를 붙인다:

```bash
source /mnt/ssd/ros2_foxy/install/setup.bash
mkdir -p /mnt/ssd/live_e2e/replay_run && cd /mnt/ssd/live_e2e/replay_run
ros2 run orbslam3 mono-inertial \
  /mnt/ssd/orb_slam3_stack/ORB_SLAM3/Vocabulary/ORBvoc.txt \
  /mnt/ssd/ros2_foxy/src/slam-tx2/orbslam3/config/monocular-inertial/iPhoneXsMax.yaml
```

로딩 끝난 뒤 다른 터미널에서 recorder를 먼저 시작하고:
```bash
source /mnt/ssd/ros2_foxy/install/setup.bash
python3 scripts/record_trajectory_tum.py /mnt/ssd/live_e2e/replay_run/trajectory.tum
```
그 다음 bag을 재생한다:
```bash
source /mnt/ssd/ros2_foxy/install/setup.bash
ros2 bag play /mnt/ssd/live_e2e/indoor_walk_bag
```
(RViz2를 계속 띄워두면 재생 중에도 Path가 그려지는 걸 볼 수 있다.)

재생이 끝나면 recorder를 Ctrl+C로 종료(`replay_run/trajectory.tum` 최종 저장됨), 그 다음
SLAM 노드도 종료.

## 4. 라이브 vs 재생 비교

`scripts/evaluate_ate.py`(#3에서 만든 TUM 궤적 비교 도구, groundtruth 전용이 아니라 임의의 두
TUM 궤적을 비교하는 범용 도구)를 그대로 재사용한다 — 재생 궤적을 "추정치", 라이브 궤적을
"참조"로 놓고 둘 사이의 정합 오차(ATE)를 계산 (recorder가 쓰는 `trajectory.tum`을 사용 -
`KeyFrameTrajectory.txt`는 맵 리셋 타이밍에 따라 종료 시점 스냅샷이 비어 있을 수 있어 쓰지
않는다):

```bash
python3 scripts/evaluate_ate.py \
  /mnt/ssd/live_e2e/replay_run/trajectory.tum \
  /mnt/ssd/live_e2e/live_run/trajectory.tum \
  --max-diff 0.1
```

결과 기록에 남길 것:
- 라이브/재생 둘 다 크래시 없이 끝났는지, `trajectory.tum`이 둘 다 비어있지 않은지
- 둘의 ATE (완전히 같을 필요는 없다 — IMU 초기화 타이밍이나 트래킹 유실/재초기화 시점이 조금만
  달라도 값이 벌어질 수 있다. 다만 자릿수가 크게 다르면(예: 한쪽만 수십 cm 이상 어긋남) 라이브
  경로와 재생 경로가 실제로 다르게 동작했다는 뜻이니 원인을 봐야 한다)
- RViz2에서 본 라이브 궤적이 실제로 걸은 경로와 정성적으로 맞았는지 (주관적 판단, 스크린샷 권장)
- 트래킹이 중간에 끊기거나(`Fail to track local map!` 등 로그) 맵이 리셋됐는지 — #10 성능 격차의
  실제 영향 여부를 판단하는 데 중요한 관찰이다
