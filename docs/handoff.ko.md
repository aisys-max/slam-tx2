# Handoff (2026-09-20 기준)

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

**라이브 재검증 세션 (2026-09-20, 진행 중)** — 위 항목대로 전체 RViz 라이브 확인을 다시
돌렸다. 그 과정에서 실제 문제 여러 개를 더 찾아 고쳤지만, 이 글을 쓰는 시점까지
**`/orb_slam3/trajectory`가 라이브에서 Path를 성공적으로 그린 적은 아직 없다** — IMU
초기화가 완료되기 전에 계속 실패/리셋된다. 지금까지 배제/수정된 것들:

- **TX2가 `MAXP_CORE_ARM` 전력 모드였다** (6코어 중 4코어만 온라인, ~2.0GHz 상한),
  `MAXN`이 아니었다. 전환(`sudo nvpmodel -m 0 && sudo jetson_clocks`) 후 SLAM+RViz까지 다
  띄운 상태에서 `/camera/image_raw`가 ~6~8Hz → ~24~30Hz로 회복됐다. **재부팅하면 이 설정은
  유지되지 않는다** — 재부팅 후 프레임레이트가 다시 낮으면 재적용할 것.
- **벤더링된 업스트림 ORB-SLAM3에서 실제 크래시 버그 2개를 찾아 패치했다** (이 저장소도
  `aisys-max/ORB_SLAM3_ROS2`도 아니라, `/mnt/ssd/orb_slam3_stack/ORB_SLAM3` — `UZ-SLAMLab/ORB_SLAM3`를
  포크 없이 그냥 클론해둔 별도 디렉터리를 로컬에서만 패치하고 `lib/libORB_SLAM3.so`를
  리빌드한 것). **이 패치는 어디에도 커밋돼 있지 않아서 이 디렉터리가 리셋/재클론되면
  사라진다** — 아래 "다음에 할 만한 일" 참고, 제대로 된 포크가 필요하다.
  1. `Optimizer::PoseInertialOptimizationLastFrame`(`src/Optimizer.cc`)가 `pFp->mpcpi`가
     null인데도 `EdgePriorPoseImu(pFp->mpcpi)`를 그대로 생성했다 (기존 코드가 이미 null을
     감지해서 `"pFp->mpcpi does not exist!!!"`를 로그로 남기긴 했지만, 그러고도 null
     포인터를 그대로 넘겼다) — `EdgePriorPoseImu` 생성자가 조건 없이 역참조해서 세그폴트.
     `scale too small` IMU 초기화 실패가 반복된 몇 초 뒤 안정적으로 재현됐다. null이면 그
     엣지(와 나중의 `GetHessian()` 사용)를 건너뛰도록 수정.
  2. `LocalMapping::InitializeIMU`의 중력 정렬 단계(`src/LocalMapping.cc`,
     `Sophus::SO3f::exp(v*ang/nv)`로 `Rwg` 계산)가 `nv = cross(gI, dirG).norm()`로 나누는데,
     추정된 중력 방향이 기준 축과 (거의) 평행/역평행이면 이 값이 (거의) 0이 된다 — 실제로
     자주 벌어지는 경우다, 폰을 수평으로 들면 중력 추정치가 정확히 그 지점 근처로 나오기
     때문. 그 결과 NaN이 생기고, 나중에 `Sophus::SO3::exp` 자체의 내부 assertion에서
     크래시했다(`"SO3::exp failed! omega: -nan -nan -nan"`). `nv`가 `1e-6f` 미만이면
     (정렬돼 있으면 단위행렬, 역정렬이면 고정된 180도 회전으로) 특수 처리하도록 수정,
     0에 가까운 값으로 나누지 않게 했다.
  3. 위 수정 #2 이후, **다른** 호출 지점에서 같은 `SO3::exp` NaN 크래시가 재발했다:
     `Preintegrated::GetDeltaRotation()`/`GetUpdatedDeltaRotation()`(`src/ImuTypes.cc`)가
     `Sophus::SO3f::exp(JRg * dbg)`(자이로 바이어스 보정)를 NaN 가드 없이 계산한다 —
     degenerate/실패한 최적화(`scale too small` 반복)가 어떤 키프레임의 바이어스 추정치를
     NaN으로 오염시켜 놓으면, 나중 프레임에서 이 무관한 코드 경로를 타면서 같은 assertion으로
     크래시했다. 회전 벡터를 `exp()`에 넘기기 전에 `.allFinite()`를 확인해, NaN이면 바이어스
     보정 없음(0 벡터)으로 대체하도록 수정.
- **`config/monocular-inertial/iPhoneXsMax.yaml`의 튜닝값이 낡아있었다**, 전부 갱신:
  `Camera.fps` 10.0→25.0 (#10 수정 전 ~5.9Hz 현실에 맞춰뒀던 값 — 이제 실측 ~24~30Hz와
  2~3배 차이나서 ORB-SLAM3 내부 타이밍 휴리스틱을 어긋나게 하고 있었음),
  `ORBextractor.nFeatures` 1000→1500 (`TRACK_REF_KF: Less than 15 matches!!`가 초반 리셋을
  유발하는 게 관찰됨), `ORBextractor.iniThFAST` 20→12 (맵 포인트 개수가 특징점 상한보다
  계속 훨씬 적게(1500개 중 80~300개) 잡혔음 — 실내 저조도 때문으로 추정, 임계값을 낮추니
  포인트 수가 최대 ~365개까지 측정 가능한 수준으로 늘어남).
- **오래 유지된 브리지 노드 TCP 연결이 느려진다**: 수십 분 지나면 Wi-Fi 신호가 좋아도 RTT가
  부풀고(25ms → 100~200ms) 처리량이 무너지며, 브리지 프로세스가 완전히 멈춘 적도 한 번
  있었다(커널 소켓 버퍼에 `Recv-Q`가 안 읽힌 채 쌓임). 새로 연결하면(브리지 kill 후 재시작)
  속도가 확실히 회복된다 — TCP 혼잡 제어 이력이 손에 들고 다니는 폰의 실제 Wi-Fi 끊김과
  겹쳐 누적되는 것으로 추정(장기 해결책은 아래 "다음에 할 만한 일" 참고).
- **iOS 앱에 Start/Stop 캡처 버튼 추가** ([#19](https://github.com/aisys-max/slam-tx2/pull/19),
  머지됨, `ios/SlamCapture/`) — 시험 전/후 이동·대기 동작이 데이터에 섞이지 않도록. 카메라/IMU
  하드웨어와 TCP 리스닝은 앱 실행 시 자동으로 켜지지만, Start를 눌러야 TX2로 실제 전송이
  시작된다.
- **세션 도중 root 파일시스템(`/`, `mmcblk0p1`)이 100% 찼다** — 위 mono-inertial 크래시마다
  `/var/lib/apport/coredump/`에 ~1GB짜리 코어덤프가 쌓인 게 원인(gdb로 잡으려고
  `ulimit -c unlimited`를 켜뒀었음). 이러면 디스크 관련 에러 메시지 없이 도구 출력/셸
  명령이 조용히 실패한다. 정리 완료(아래 자주 막히는 지점 참고) — 약 3.8GB 여유로 복구.
  또 이런 "output lost"/`ENOSPC` 느낌의 이상한 에러가 나면 `df -h /`부터 확인할 것.
- **새로 확인된, 아직 원인 불명인 실패 패턴: SLAM 프로세스는 살아있는데 ROS2 노드가 사라짐** —
  `ros2 node list`에 더 이상 안 뜨고, `/orb_slam3/trajectory`의 publisher 수와
  `/camera/image_raw`의 subscriber 수가 둘 다 0이 되고, 프로세스 CPU 사용량이 완전히
  평평해진다(`/proc/<pid>/stat`의 `utime`/`stime`이 몇 초 동안 거의 안 늘어남) — 그런데 OS
  프로세스 자체는 살아있다(`ps`상 좀비가 아니고, 여전히 멀티스레드로 실행 중). 아직 근본
  원인을 못 잡았다 — gdb를 붙인 채로 재현해야 확인 가능할 듯. 지금은 SLAM 노드를 죽이고
  재시작하는 것만이 알려진 우회법이다.

위 항목들 중 어느 것도 단독으로 라이브 초기화 실패를 완전히 해소하지 못했다. 남은 실패
패턴은 `Fail to track local map!`(보통 맵이 IMU 초기화를 시도하는 문턱인 키프레임 10개/2초에
도달하기도 전), `scale too small`(IMU 초기화는 시도됐지만 visual-inertial 스케일 추정치가
degenerate하게 나옴), 가끔 `Not enough motion for initializing`/`bad imu flag`, 그리고 이제
위의 "노드가 사라짐" 문제 사이를 오간다.

**근본 원인 분석 세션 (2026-09-20, 계속) — 체계적 진단으로 전환.** 위까지는 시도와 관찰
위주였는데, 이후로는 로그를 실제로 파싱해서 근거를 만들고 가설을 하나씩 검증하는 방식으로
전환했다. 절차와 근거는 [docs/imu-init-debug.md](imu-init-debug.ko.md)에 정리했다 (일반적인
"Path 안 그려짐" 체크리스트가 아니라, 이 프로젝트에서 실제로 관찰된 실패 패턴 전용). 요약:

- **`New Map created`는 계속 성공(115회 관찰)하는데 `start VIBA`(IMU 초기화 2단계)는 거의
  0회** — 단안 부트스트랩 자체는 문제가 아니고, 초기화 직후 트래킹을 못 버티는 게 핵심.
- **브리지 노드가 ~10~12초 주기로(같은 세션에서 402회) "연결 끊김: timed out" → 재연결을
  반복**하고 있었고, 이 주기는 `ios_bridge_node.py`의 `recv_timeout=10.0` 기본값과 일치했다.
  리셋 시각과 재연결 시각의 상관관계를 스크립트로 직접 확인함(`docs/imu-init-debug.ko.md`
  1단계). `--recv-timeout 60`으로 재시도하니 **재연결이 0회로 사라지고, `start VIBA 1`이
  같은 시간 동안 2회 발생**(그 전까지 세션 전체에서 0회였던 것과 대비) — 네트워크 재연결이
  진짜 기여 요인이었음을 확인. 다만 VIBA 1이 두 번 다 트래킹 스레드의 동시 리셋과 겹쳐
  결국 실패로 끝났고, `Fail to track local map!`은 여전히 반복됨 — **부분적 원인**이었을 뿐
  전체 해결은 아니다.
- **화질/텍스처/CPU 경합은 배제됨**: 프레임을 직접 덤프해서 선명도(Laplacian variance
  평균 209, 심하게 흐린 프레임 0%)와 ORB 키포인트 수(평균 1371개, 100개 미만 0%)를 측정,
  둘 다 충분했다. RViz2를 꺼서 시스템 부하를 낮춰봐도(load average 5.4→4.3) 결과 변화 없음.
- **`Tracking.cc`에 임시 계측을 추가해 진짜 병목을 특정**: `TrackLocalMap()`의
  `if(mCurrentFrame.mnId<mnLastRelocFrameId+mMaxFrames && mnMatchesInliers<50) return false;`
  — 리셋 직후 `mMaxFrames`(=fps=25, 약 1초) 동안 로컬맵 인라이어 매치가 **50개 이상**
  필요한 엄격한 게이트. 게다가 이 창을 벗어나도 IMU 미초기화 상태에선 여전히 50개가
  필요해서(15개로 완화되는 건 IMU 초기화 **후**부터), 사실상 "IMU 초기화 전엔 항상
  50개 필요 → 50개를 못 채우면 IMU 초기화도 안 됨"이라는 닭과 달걀 구조였다. 실측
  인라이어 값은 대부분 25~48 사이로 문턱 바로 아래에서 반복 실패.
- **50→30으로 낮추는 실험은 결론이 안 났다**: 재시도마다 실제 걷는 동작이 달라서
  직접 비교가 안 됐고(어떤 시도는 인라이어가 1~9까지 떨어짐 — 모션 자체가 더 거칠었을
  가능성), `start VIBA`는 여전히 0회. **이 실험 코드는 원복 완료.**
- **반복 비교를 위해 걷기 세션 하나를 `ros2 bag record`로 녹화해 baseline으로 확보**
  (`/mnt/ssd/live_e2e/baseline_walk/walk_bag`, 215초, 이미지 1184장/IMU 16525개 — 단
  best-effort QoS라 bag 기록 중 이미지 손실이 있어 원본보다 낮은 프레임레이트로
  기록됐을 수 있음, 참고용으로만 쓸 것). `ros2 bag play`로 재생하면 실제로 걷지 않아도
  코드/설정 변경 전후를 동일 입력으로 비교 가능함을 확인함.
- **이 baseline bag 재생 중 새 크래시를 하나 더 발견**(`EXIT_CODE=245`,
  `"Not preintegrated measurement"` 직후 로그 끊김) — 라이브 테스트에선 한 번도 안 걸렸던
  경로. `Optimizer.cc`의 `InertialOptimization`/`FullInertialBA`에서 `mpImuPreintegrated`가
  null인 키프레임을 가드 없이 역참조하는 지점이 총 4곳 있었음(1곳은 경고만 찍고 그대로
  역참조, 3곳은 경고조차 없이 역참조) — 전부 null이면 해당 엣지를 건너뛰도록 수정, 같은
  bag으로 재검증하니 217초 재생 끝까지 크래시 없이 생존.
- **이제 크래시 수정 4개 전부를 `https://github.com/aisys-max/ORB_SLAM3`(업스트림 포크,
  커밋 `e444ea4`)에 커밋+푸시했다** — 더 이상 로컬에만 존재하는 유실 위험 상태가 아니다.
  아래 "저장소/환경 구조"에 반영.

**요약**: 크래시 계열 문제(총 4개)는 전부 찾아서 고치고 포크에 영속화했다. 네트워크
재연결 문제도 원인을 규명하고 `--recv-timeout 60`으로 완화했다. 하지만 **핵심 트래킹
문제(리셋 직후 50개 인라이어 문턱을 거의 못 넘음)는 아직 미해결**이고, 이 글을 쓰는
시점까지 2026-09-20 세션의 어떤 시도도 RViz에 라이브로 Path를 지속적으로 그리는 데
성공하지 못했다.

## 다음에 할 만한 일

1. **`TrackLocalMap()`의 리셋 직후 50-인라이어 게이트를 더 정밀하게 공략할 것** —
   `docs/imu-init-debug.md`에서 확인한 핵심 병목. 임계값을 단순히 낮추는 실험은
   (모션을 반복 재현할 수 없어) 결론이 안 났다 — 이제 baseline bag이 있으니, **bag
   재생으로 동일 입력을 놓고** 임계값을 여러 단계로 바꿔가며 제대로 비교할 것. 또는
   임계값을 안 건드리고, 리셋 직후 초기 맵의 맵포인트 품질/개수 자체를 늘리는 쪽(더
   넓은 파랄락스로 2-view init하도록 유도, 초기 맵의 아웃라이어 제거 강화 등)도 검토.
2. **위 "SLAM 노드가 ROS2 그래프에서 사라지는" 문제 근본 원인을 찾을 것** — 이번
   세션엔 `/rviz` 노드에서도 같은 증상이 관찰됨(재시작 없이는 subscription이 안 살아남음).
   gdb로 재현해서 실제 죽는 스레드의 백트레이스를 잡을 것.
3. **오래 유지된 브리지 TCP 연결이 느려지는 문제를 더 파볼 것** — `--recv-timeout 60`으로
   재연결 빈도는 크게 줄었지만 근본 해결은 아니다. `TCP_NODELAY`/소켓 버퍼 튜닝, 또는
   주기적 선제 재연결이 도움되는지 확인.
4. **차량 실측 / 17 Pro Max + LiDAR 확장** — #1 스펙의 Out of Scope에 명시된 다음 단계.
   토픽 기반 구조라 `sensor_msgs/PointCloud2` 추가만으로 확장 가능하도록 설계되어 있다
   (설계 의도만 있고 구현은 없음). 트래킹이 안정적임을 확인한 뒤 진행하는 게 순서상 맞을 것.

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
11. **TX2 전력 모드는 재부팅하면 유지되지 않는다.** 재부팅 후 프레임레이트가 이유 없이
   낮으면 `nvpmodel -q`부터 확인할 것 — `MAXP_CORE_ARM`(4코어)로 돌아가 있을 수 있다.
   `sudo nvpmodel -m 0 && sudo jetson_clocks`로 `MAXN`(6코어, 최대 클럭) 적용. MAXN으로
   오래 돌릴 땐 온도도 같이 볼 것(`cat /sys/devices/virtual/thermal/thermal_zone*/temp`) —
   팬이 응답하도록 설정 안 돼 있을 수 있다(`nvpmodel`이 `fan mode is not set!` 경고를 낸다).
12. **(2026-09-20 해소됨) `/mnt/ssd/orb_slam3_stack/ORB_SLAM3`의 크래시 수정 4개는 이제
   `https://github.com/aisys-max/ORB_SLAM3`(업스트림 포크, `origin` 리모트, 커밋 `e444ea4`)에
   커밋+푸시돼 있다** — `upstream` 리모트는 원본 `UZ-SLAMLab/ORB_SLAM3`를 가리킨다. 거기서
   뭔가 더 바꾸면 반드시 커밋+푸시하고, `libORB_SLAM3.so`도 리빌드할 것
   (`cd .../ORB_SLAM3/build && make ORB_SLAM3`). 디렉터리 자체가 리셋/재클론되면 이제
   `git clone https://github.com/aisys-max/ORB_SLAM3.git`으로 안전하게 복구 가능하다.
13. **`ulimit -c unlimited` 상태에서 프로세스가 크래시하면 이 TX2의 root 파일시스템이
   금방 찬다.** mono-inertial이 크래시할 때마다 `/var/lib/apport/coredump/`에 ~1GB
   코어덤프가 남았다(지우려면 `sudo rm` 필요, root 소유). root 파티션이 28G뿐이고 이번
   세션 시작 전부터 이미 빠듯했어서(~360MB 여유), 크래시 몇 번이면 `ENOSPC`에 걸려 디스크
   관련이라는 티도 안 나는 이상한 에러로 도구 출력/셸 명령이 깨진다. 명령이 이상하게
   실패하기 시작하면 무엇보다 먼저 `df -h /`를 확인할 것. 다시 찰 경우 안전하게 지워도
   되는 후보: `/var/lib/apport/coredump/`, `~/.cache/uv`, `~/.cache/pip` (전부 필요하면
   재생성됨).

## 저장소/환경 구조

- 메인 저장소(이 repo, `aisys-max/slam-tx2`): PR 기반 워크플로. iOS 앱, 브리지 노드, 문서,
  검증 스크립트.
- ORB-SLAM3 ROS2 래퍼(`aisys-max/ORB_SLAM3_ROS2`, 별도 repo, main 직커밋 워크플로): 클론
  위치 `/mnt/ssd/ros2_foxy/src/slam-tx2/orbslam3`. SLAM 노드 C++ 코드가 여기 있음.
- ROS2 Foxy 빌드: `/mnt/ssd/ros2_foxy` (colcon 워크스페이스, git 추적 안 됨).
- 벤더링된 ORB-SLAM3 코어(`aisys-max/ORB_SLAM3`, `UZ-SLAMLab/ORB_SLAM3` 포크, main 직커밋
  워크플로): 클론 위치 `/mnt/ssd/orb_slam3_stack/ORB_SLAM3` (`origin`=포크, `upstream`=원본).
  크래시 수정 4개가 여기 커밋돼 있음. `libORB_SLAM3.so`를 `aisys-max/ORB_SLAM3_ROS2`가
  링크해서 씀 — 여기서 수정하면 반드시 `make ORB_SLAM3`로 리빌드할 것.
- 캡처 산출물: `/mnt/ssd/live_e2e/` (bag, trajectory.tum 등 — 세션마다 새 디렉터리 권장).
  `baseline_walk/walk_bag`는 반복 비교용 baseline (215초 실내 걷기, 이미지 손실 있을 수
  있어 참고용).

## 관련 문서

- [ros2-topic-contract.md](ros2-topic-contract.ko.md) — 토픽/QoS/frame_id 계약
- [ios-tcp-protocol.md](ios-tcp-protocol.ko.md) — iPhone↔TX2 와이어 프로토콜
- [ios-app-setup.md](ios-app-setup.ko.md) — iOS 앱 Xcode 프로젝트 설정
- [camera-calibration.md](camera-calibration.ko.md) — 체커보드 캘리브레이션 절차
- [bridge-node.md](bridge-node.ko.md) — 브리지 노드 설정/실행/검증
- [euroc-validation.md](euroc-validation.ko.md) — EuRoC 기반 SLAM 노드 검증(#3)
- [live-e2e-validation.md](live-e2e-validation.ko.md) — 라이브 e2e 검증 전체 기록(#7)
- [imu-init-debug.md](imu-init-debug.ko.md) — IMU 초기화(VIBA1 미도달) 근본 원인 진단 절차/근거
- [tx2-build-notes.md](tx2-build-notes.ko.md) — TX2 빌드 환경 노트
- `docs/adr/` — 설계 결정(타임스탬프 기준, ROS2 Foxy 채택, 어댑터 레이어 미채택, SLAM 래퍼 선택)
