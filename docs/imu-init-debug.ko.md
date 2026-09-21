# IMU 초기화(VIBA1 미도달) 디버깅 절차

> English version [here](imu-init-debug.md).

**대상**: `mono-inertial` 노드가 `New Map created`(단안 초기화)까지는 반복적으로 성공하지만
`start VIBA 1`(IMU 초기화 2단계)에는 한 번도 도달하지 못하는 문제.
**작성 배경**: 2026-09-20 라이브 재검증 세션, `KTM4RL` Wi-Fi, 로그
`/mnt/ssd/live_e2e/issue10_oldwifi_back/slam_node.log` + `/mnt/ssd/live_e2e/bridge_oldwifi_back.log`
분석 결과를 근거로 작성. 일반적인 "RViz Path 안 그려짐" 체크리스트(토픽/frame_id/QoS/TF)는 이미
전부 확인 완료 상태(Path가 짧게라도 그려지는 건 확인됨)이므로 이 문서에서는 다루지 않는다 -
`docs/handoff.md`의 "Live re-verification session" 절 참고.

## 확인된 사실 (2026-09-20 세션 로그 근거)

이 절의 숫자는 전부 위 두 로그 파일을 직접 파싱해서 얻은 것이며, 다음 세션에서 새 로그로
재확인할 때 같은 방식(grep -c, 아래 상관관계 스크립트)을 그대로 쓰면 된다.

- `New Map created`: 115회 / `Fail to track local map!`: 113회 / `start VIBA`: **0회**
  → 단안 부트스트랩 자체는 문제가 아니다. IMU 초기화 문턱(키프레임 수 + 시간)까지 트래킹이
  버티질 못한다.
- `New Map created` 발생 후 **거의 예외 없이 로그 1~3줄 이내**(=다음으로 처리된 프레임 1개)에
  `TRACK_REF_KF: Less than 15 matches!!` → `Fail to track local map!` → 리셋이 뒤따른다.
  362개 이벤트 샘플에서 예외 없음.
- 같은 세션에서 브리지 노드(`ios_bridge_node.py`)가 **~10~12초 주기로 402회** "연결 끊김:
  timed out" → 재연결을 반복했다. 이 주기는 `recv_timeout=10.0`(기본값, `--recv-timeout`)과
  일치한다.
- ORB extractor 설정(`nFeatures=1500`, `iniThFAST=12`)과 `fps=25`는 로그의
  "ORB Extractor Parameters" 출력으로 실제 반영 확인됨 - 설정이 안 먹은 게 아니다.

## 리딩 가설

브리지의 `recv_timeout`이 주기적인 네트워크/iPhone 쪽 정체와 맞물려 ~10초마다 연결이 끊기고
재연결된다. 그 구간 동안 카메라 프레임이 통째로 누락되므로, 재연결 직후 SLAM 노드가 받는
"바로 다음 프레임"은 몇 초 전 프레임과 실제로는 크게 떨어진 장면이다 → 파라랙스/외형이 급변해
참조 키프레임과의 매칭이 15개 밑으로 떨어짐 → 즉시 트래킹 실패 → 리셋. 이 사이클이 반복되니
IMU 초기화에 필요한 연속 트래킹 구간(최소 키프레임 수 + 2초)을 절대 확보하지 못한다.

이게 맞다면 지금까지의 "모션 타이밍이 안 좋아서"라는 설명은 틀렸고, **네트워크 안정성 문제**다.

## 단계

### 1단계 - 리셋 시각과 재연결 시각의 상관관계 재확인

다른 세션 로그에도 같은 패턴이 있는지 아래로 확인 (파일 경로만 바꿔서 재사용):

```bash
python3 - <<'EOF'
import re
from datetime import datetime

bridge_log = "/mnt/ssd/live_e2e/<브리지 로그 경로>"
slam_log = "/mnt/ssd/live_e2e/<slam_node.log 경로>"

bridge_events = []
for l in open(bridge_log):
    m = re.match(r"\[\w+\] \[(\d+)\.\d+\] \[ios_bridge\]: (.+)", l)
    if m and ("연결됨" in m.group(2) or "끊김" in m.group(2)):
        bridge_events.append((float(m.group(1)), m.group(2).strip()))

reset_lines = []
prev_t = None
for l in open(slam_log):
    m = re.match(r"\[\w+\] \[(\d+)\.\d+\]", l)
    if m:
        prev_t = float(m.group(1))
    if "Fail to track local map" in l and prev_t:
        reset_lines.append(prev_t)

# 각 reset 시각에서 가장 가까운 브리지 이벤트까지의 시간차
import statistics
diffs = []
for rt in reset_lines:
    nearest = min(bridge_events, key=lambda be: abs(be[0]-rt))
    diffs.append(abs(nearest[0]-rt))
print(f"reset {len(reset_lines)}건, 가장 가까운 브리지 이벤트까지 평균 {statistics.mean(diffs):.2f}s, "
      f"중앙값 {statistics.median(diffs):.2f}s")
print(f"2초 이내인 비율: {sum(1 for d in diffs if d<2)/len(diffs)*100:.0f}%")
EOF
```

- **PASS 기준**: 리셋 시각 대부분(대략 70% 이상)이 브리지 재연결 이벤트 ±2초 이내에 겹침 →
  가설 확인, 2단계로
- **FAIL 기준**: 안 겹침 → 가설 기각, 4단계(모션/환경 원인)로 바로 이동

### 2단계 - 정체 원인이 브리지 코드 쪽인지 iPhone/Wi-Fi 링크 쪽인지 격리

브리지 노드 없이 `test_ios_tcp_client.py`로 iPhone에 직접 붙어서 60초 이상 관찰:

```bash
python3 scripts/test_ios_tcp_client.py --connect <iPhone IP> --duration 60
```

- **PASS 기준(재현됨)**: 브리지 없이도 동일 주기로 타임아웃/끊김이 재현 → 문제는 브리지
  코드가 아니라 iPhone/Wi-Fi 링크 자체 → 3단계로
- **FAIL 기준(재현 안 됨)**: 브리지를 거칠 때만 발생 → `ios_bridge_node.py`의 이벤트 루프/
  `_recv_exact_before_deadline` 로직 자체를 재검토 (예: deadline이 메시지 단위가 아니라
  누적으로 걸리고 있는 건 아닌지)

### 3단계 - iPhone Wi-Fi 절전/저전력 모드 배제

- iPhone 설정에서 저전력 모드(Low Power Mode) 끄고, 화면 계속 켜진 상태 유지하며 2단계를
  재실행
- 앱 코드 확인: `TCPServer.swift`가 소켓에 `TCP_NODELAY`(Nagle 비활성화)나 keep-alive를
  설정하고 있는지 확인 (`ios/SlamCapture/TCPServer.swift`)
- **PASS 기준**: 저전력 모드를 꺼도 여전히 ~10초 주기로 정체 재현 → iOS 설정 문제 아님,
  5단계(브리지 타임아웃 값 실험)로
- **FAIL 기준**: 저전력 모드 끄니 사라짐 → iOS 사용 전제 조건 문서화(README에 "저전력 모드
  끄고 사용" 명시)로 해결, 6단계(종단 확인)로

### 4단계 - (1단계가 FAIL인 경우만) 즉시-실패 매칭이 진짜 저텍스처/모션 때문인지 확인

- `New Map created` 직후와 그 다음 처리된 프레임, 두 장을 실제로 저장해서 육안 비교
  (`rqt_image_view`로 `/camera/image_raw`를 띄워두고 리셋 순간 캡처, 또는 브리지에 임시로
  프레임 dump 옵션 추가)
- **PASS 기준(두 프레임이 크게 다름 - 블러 심하거나 장면이 많이 바뀜)**: 이동 속도/모션 블러
  문제 → 초기화 직후 몇 초는 아주 천천히 움직이도록 프로토콜 조정
- **FAIL 기준(두 프레임이 육안으로 거의 같은데도 매칭 실패)**: 매칭/디스크립터 계산 자체의
  버그 가능성 → `ORBmatcher`/`TrackReferenceKeyFrame` 코드 레벨 조사 필요

### 5단계 - `recv_timeout` 완화 실험 (빠른 실험, 코드 변경 없이 CLI 인자만)

```bash
python3 scripts/ios_bridge_node.py <iPhone IP> 8765 --recv-timeout 60
```

- **PASS 기준**: 재연결 빈도가 급감하고, 같은 시간 동안 `start VIBA` 로그가 최소 1회 이상
  등장 → 근본 원인 확정. 정식 수정으로 `recv_timeout` 기본값 상향 또는 heartbeat/keep-alive
  도입을 PR로 진행
- **FAIL 기준**: 재연결은 줄었는데도 여전히 `Fail to track local map!`이 즉시 반복 →
  `recv_timeout`이 유일한 원인은 아니었다는 뜻, 4단계 병행

### 6단계 - 종단 확인

위에서 나온 수정을 적용한 뒤, 독립된 세션 3회 이상에서 `start VIBA 1` 로그가 등장하고 RViz
Path가 트래킹 리셋 없이 최소 수 초 이상 지속되는지 확인. 3회 중 3회 다 되면 완료로 간주.

## 요약 판정 트리

```
1단계 PASS (리셋≈재연결 시각 일치)
  → 2단계 PASS (브리지 없이도 재현) → 3단계
      → 3단계 PASS (저전력모드 꺼도 재현) → 5단계
      → 3단계 FAIL (저전력모드 끄니 해결) → 6단계
  → 2단계 FAIL (브리지에서만 재현) → 브리지 코드 재검토
1단계 FAIL (리셋과 재연결 시각 무관)
  → 4단계 → PASS(모션/블러) 또는 FAIL(매칭 버그 코드 조사)
```

## 이후 조사 결과 (2026-09-21) - 결론

위 5단계(`recv_timeout` 완화)는 실제로 부분 원인이었음이 확인됐다 — `ios_bridge_node.py`의
`_recv_exact_before_deadline()`이 메시지 하나 전체에 고정 데드라인을 거는 버그였고(idle
타임아웃이 아니었음), 이를 `_recv_exact_idle_timeout()`으로 고쳐 기본값(`--recv-timeout
10.0`) 그대로 재연결을 0회로 없앴다 (slam-tx2#20, PR #21). 하지만 이후에도 핵심 트래킹
실패(`Fail to track local map!`, 초기화 직후 즉시)는 해소되지 않았다. 이어서 다음을 추가로
검증/배제했다:

- **파랄락스 부족**: `TwoViewReconstruction.cc`에 계측을 추가해 실측한 결과, 초기화 시점
  파랄락스가 1~6.6도(대부분 1~3도)로 낮았다. `minParallax`를 1.0→3.0으로 올려 3.5~6.2도의
  확실히 좋은 초기화만 통과시켰는데도 **동일하게 즉시 실패** — 파랄락스는 원인이 아니었다.
  (실험 코드는 원복함.)
- **TrackReferenceKeyFrame 이후 단계(SearchLocalPoints/재투영)가 실제 병목**: 계측 결과, 원본
  매칭(`aux1`)은 대체로 풍부한데 최적화 후 인라이어가 들쭉날쭉했다. 다만 같은 계측 중 한 번은
  **90여 프레임을 인라이어 200개 이상으로 안정적으로 추적** — 이 파이프라인/데이터로 트래킹이
  잘 될 수 있다는 확실한 증거를 확보했다. 그 직후 IMU 초기화 시도(`scale too small`) 중
  크래시가 한 번 났고(`Optimizer.cc`의 4번째 null 가드 버그, 이미 수정/커밋됨 - 위 "라이브
  재검증 세션" 참고), gdb로 재현을 시도했으나 두 번째 시도에선 재현되지 않았다(타이밍
  의존적, 4개 가드는 정상 동작 확인됨).
- **bag 재생 자체가 비결정적이었다 (중요 발견)**: 완전히 동일한 bag을 재생해도 SLAM 결과가
  매번 달랐던 이유를, SLAM을 아예 빼고 순수 구독만으로 측정해 확인했다 — best-effort QoS +
  얕은 큐 때문에 재생마다 다른 메시지가 조용히 드랍되고 있었다(이미지 1184개 중
  1182~1184개, IMU 16525개 중 16007~16522개로 재생마다 유실량이 달랐음). `aisys-max/ORB_SLAM3_ROS2`에
  `reliable_sensor_qos` 파라미터를 추가해(라이브는 기본값 그대로 best-effort) bag 기반 비교를
  결정적으로 만들었다. 자세한 내용은 [docs/bag-replay-determinism.md](bag-replay-determinism.ko.md)
  참고(slam-tx2 PR #21). 다만 이렇게 입력을 완전히 동일하게 맞춘 뒤에도 SLAM 결과는 미세하게
  달랐다(42 vs 43 리셋) — 남은 비결정성은 ORB-SLAM3 자체의 멀티스레드 실행 순서(입력만으로
  고정 안 됨)에 있다.

**중요한 정정**: 지금 가장 자주 겪는 실패(`Fail to track local map!`, IMU 초기화 이전)는
`Optimizer::PoseOptimization()`이라는 **순수 시각 기반** 경로에서 일어난다
(`!mpAtlas->isImuInitialized()`일 때). 즉 Tbc/IMU 노이즈 캘리브레이션 정밀도(Kalibr 등)는
**이 실패와 무관**하다 - IMU가 아직 포즈 추정에 전혀 관여하지 않는 단계이기 때문이다. Kalibr
캘리브레이션은 IMU 초기화가 실제로 시작된 *이후*의 정확도에나 영향을 줄 수 있는데, 지금은
그 단계에 거의 도달하지도 못하고 있어 우선순위가 낮다.

**남은, 아직 검증 안 된 유력 가설**: 롤링 셔터 왜곡. 원본 특징점/매칭/파랄락스가 전부
양호한데도 정밀한 재투영 일관성이 필요한 단계에서만 실패하는 패턴과 부합한다. 확인하려면
실제 실패 순간(리셋 직전)의 프레임을 저장해 기하학적 왜곡을 직접 봐야 한다 - 아직 안 함.

**세션 결론 (2026-09-21)**: 이 세션의 목적은 iPhone Xs Max + TX2 조합으로 제품을 만드는 게
아니라 SLAM 파이프라인의 동작을 이해하는 것이었다. CPU/크래시/네트워크/파랄락스/전송
결정성 등 통제 가능한 모든 레버를 찾아 고치거나 배제했고, 남은 것(멀티스레드 비결정성,
가능성 있는 롤링 셔터 왜곡)은 이 하드웨어 조합의 근본적 특성에 가깝다고 판단해 여기서
조사를 일단 마무리한다. 재개할 경우 위 "롤링 셔터 확인"이 가장 자연스러운 다음 단계다.
```
