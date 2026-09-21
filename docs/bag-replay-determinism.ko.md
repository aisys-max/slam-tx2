# bag 재생 결정성 (#20)

> English version [here](bag-replay-determinism.md).

**배경**: [docs/imu-init-debug.md](imu-init-debug.ko.md)의 IMU 초기화(VIBA1 미도달) 근본
원인 조사 중, 실험 방법론 자체의 문제로 발견됨 — 임계값 실험(50 vs 30)을 "공정 비교"하려고
같은 bag을 재생했는데 결과가 재현되지 않아서 이 문서의 조사로 이어졌다.

**문제**: 같은 `ros2 bag play`로 같은 bag을 여러 번 재생해도, SLAM 노드의 트래킹 결과(맵
리셋 빈도, 성공/실패 지점)가 매번 다르게 나왔다 — 코드/설정을 하나도 안 바꿨는데도. 이러면
임계값/파라미터를 바꿔가며 "전후 비교"를 하는 실험 방법론 자체가 무의미해진다: 결과가 달라진
게 변경 때문인지 단순히 재생 우연 때문인지 구분이 안 된다.

## 근본 원인: best-effort QoS + 얕은 큐가 재생마다 다른 메시지를 드랍한다

`/camera/image_raw`, `/imu`는 라이브 캡처 계약대로 best-effort QoS로 publish/subscribe된다
(`docs/ros2-topic-contract.md`). best-effort는 "받는 쪽이 순간적으로 못 따라가면 조용히
버린다"는 정책이라, 정확히 어떤 메시지가 버려지는지는 재생 시점의 실시간 타이밍(OS 스케줄링
등)에 따라 달라진다.

**직접 측정으로 확인**: SLAM 코드는 전혀 개입시키지 않고, 순수 rclpy 구독자
(`scripts/measure_bag_delivery.py`)로 같은 bag을 두 번 재생해 실제 도착한 메시지 개수를
비교했다:

```
원본 bag: 이미지 1184개, IMU 16525개

1차 재생: 이미지 1183개, IMU 16007개
2차 재생: 이미지 1182개, IMU 16062개
```

SLAM이 전혀 관여하지 않은 순수 구독 단계에서부터 이미 재생마다 다른 개수(그리고 다른
타임스탬프 시퀀스)가 도착하고 있었다 — "같은 bag"이 실제로는 "매번 살짝 다른 부분집합"을
넣고 있었던 셈이다.

## 해결: reliable QoS + 넉넉한 큐 depth

`aisys-max/ORB_SLAM3_ROS2@42f7729`에 `reliable_sensor_qos` 파라미터를 추가했다 (기본값
`false`, 라이브 캡처 동작은 그대로 best-effort). `true`로 주면 두 센서 구독 모두 reliable +
넉넉한 depth(이미지 200, IMU 5000)로 전환된다. depth는 FastRTPS 기본 리소스 한도
(`max_samples`)보다 낮아야 한다 — 너무 크게 잡으면(예: 2000/5000/20000 실측 시도 중 일부)
"depth must be <= max_samples" 에러로 구독/발행 자체가 실패한다. 200 정도면 이 프로젝트의
데이터 볼륨(이미지 ~25-30Hz, IMU ~97-100Hz)에서 문제없이 동작함을 확인했다.

`ros2 bag play`도 짝을 맞춰 `scripts/qos_reliable_override.yaml`로 재생해야 한다 - 발행
쪽만 reliable이고 구독 쪽이 best-effort거나 그 반대면 큐 백프레셔에 따라 여전히 유실이 생길
수 있다.

**검증 결과**: `scripts/measure_bag_delivery.py --reliable`로 같은 bag을 두 번 측정한 결과,
이미지/IMU 개수와 타임스탬프 시퀀스의 해시까지 완전히 동일했다 (이미지 1184/1184, IMU
16522/16522, 해시 일치) — 전송 계층의 비결정성은 확실히 제거됐다.

## 남은 비결정성: ORB-SLAM3 자체의 멀티스레드 실행 순서

전송 데이터를 완전히 동일하게 맞춘 뒤에도, SLAM 노드의 트래킹 결과는 여전히 미세하게 달랐다
(예: 맵 리셋 42회 vs 43회, 초기 맵 포인트 수 596 vs 473). 입력이 완전히 같은데 결과가
다르다는 건, 남은 원인이 ORB-SLAM3 **내부**(Tracking/LocalMapping이 별도 스레드로 뮤텍스를
통해 공유 상태에 접근하는 순서)에 있다는 뜻이다. 이 상대적 실행 순서는 입력 데이터만으로
고정되지 않고 OS 스레드 스케줄링에 달려 있어서, 고치려면 ORB-SLAM3의 멀티스레드 아키텍처
자체를 바꿔야 한다 - 이 프로젝트 범위 밖으로 남겨둔다.

## 사용법

```bash
# 터미널 A - SLAM 노드를 reliable QoS로
source /mnt/ssd/ros2_foxy/install/setup.bash
ros2 run orbslam3 mono-inertial <vocab> <settings> --ros-args -p reliable_sensor_qos:=true

# 터미널 B - bag도 짝을 맞춰 reliable로 재생
source /mnt/ssd/ros2_foxy/install/setup.bash
ros2 bag play <bag> --qos-profile-overrides-path scripts/qos_reliable_override.yaml

# (선택) 전달 데이터 자체가 결정적인지 별도로 검증하고 싶으면
python3 scripts/measure_bag_delivery.py out.txt --reliable
```

**주의**: `reliable_sensor_qos:=true`는 bag 재생 기반 회귀 테스트 전용이다. 실제 iPhone
라이브 캡처 검증에는 쓰지 말 것 - 브리지 노드는 항상 best-effort로 publish하므로
(`docs/ros2-topic-contract.md` 계약), 라이브 검증은 기본값(`false`, best-effort)으로 해야
한다.
