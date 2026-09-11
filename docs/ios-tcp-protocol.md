# iPhone → TX2 USB 스트리밍 와이어 프로토콜 (#4)

iOS 캡처 앱이 TCP 서버로 동작하고(고정 포트 **8765**), TX2 쪽 브리지 노드(#6)가 iproxy로 터널링된 이 포트에 클라이언트로 접속한다 (스펙 Implementation Decisions 참고). 이 문서가 그 사이의 바이트 단위 계약이다.

이 구간(iPhone↔TX2)만 커스텀 바이너리를 쓴다 — ROS2 토픽으로 변환되는 건 브리지 노드 **이후**부터다 ([docs/ros2-topic-contract.md](ros2-topic-contract.md)).

## 프레이밍

모든 정수/실수 필드는 **빅엔디안(network byte order)**. 각 메시지:

```
[1 byte  type]
[4 bytes payload_length]   (uint32, big-endian, payload 바이트 수)
[payload_length 바이트]
```

`type`:
| 값 | 의미 |
|---|---|
| `0x01` | Frame (카메라 이미지) |
| `0x02` | IMU 샘플 |

## Frame (`type = 0x01`) payload

```
[8 bytes timestamp_ns]  (uint64, 캡처 시각 — iPhone 모노토닉 클럭, 나노초. ADR-0001)
[4 bytes width]         (uint32)
[4 bytes height]        (uint32)
[4 bytes stride]        (uint32, 한 행의 바이트 수 — mono8이므로 보통 width와 같음)
[width*height 바이트]    (mono8 그레이스케일, row-major, 패딩 없음 — stride만큼 건너뛰며 읽을 것)
```

인코딩은 항상 **mono8**이다 (YUV420 캡처의 Y-plane을 그대로 사용 — `docs/ios-app-setup.md` 참고). 색상은 보내지 않는다.

## IMU 샘플 (`type = 0x02`) payload

```
[8 bytes timestamp_ns]        (uint64, 캡처 시각 — 프레임과 동일한 클럭 기준)
[8 bytes angular_velocity_x]  (float64, rad/s)
[8 bytes angular_velocity_y]  (float64, rad/s)
[8 bytes angular_velocity_z]  (float64, rad/s)
[8 bytes linear_acceleration_x] (float64, m/s^2)
[8 bytes linear_acceleration_y] (float64, m/s^2)
[8 bytes linear_acceleration_z] (float64, m/s^2)
```

CoreMotion은 가속도를 G 단위로 주므로 **9.80665를 곱해 m/s^2로 변환한 뒤** 보낸다 (`MotionManager.swift` 참고).

## 연결/생명주기

- 앱은 시작하자마자 포트 8765에서 리스닝을 시작한다 (iPhone = TCP 서버, TX2 = 클라이언트 — 스펙 결정 사항).
- 한 번에 하나의 클라이언트만 지원한다. 새 연결이 들어오면 이전 연결을 닫는다.
- 프레임/IMU 순서는 캡처된 순서 그대로 보낸다(재정렬 없음) — 타임스탬프로 정렬/동기화하는 건 받는 쪽(브리지 노드)의 책임이다.
- 연결이 끊기면 앱은 리스닝 상태로 돌아가 재연결을 받는다. 별도 재연결 프로토콜(재전송, ack 등)은 없다 — 끊긴 동안의 데이터는 유실된다.

## 테스트

`scripts/test_ios_tcp_client.py`가 이 프로토콜을 구현한 참조 클라이언트 겸 자체 테스트다:
- `--self-test`: 실제 iPhone 없이, 이 문서의 바이트 레이아웃대로 합성 프레임/IMU 메시지를 만들어 파서가 왕복(인코딩→디코딩) 정확히 읽어내는지 확인한다.
- `--connect <iPhone IP> 8765`: 실제 iPhone 앱에 접속해 받은 프레임/IMU 개수, 포맷, 타임스탬프 단조증가 여부를 출력한다 (#4의 "테스트 클라이언트로 검증 가능" 기준).
