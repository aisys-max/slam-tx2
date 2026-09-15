# iOS 캡처 앱 빌드/실행 (#4)

이 저장소엔 `.xcodeproj`가 없다 — Xcode가 없는 환경(TX2)에서 프로젝트 파일을 손으로 만들면 깨질 위험이 커서, **Swift 소스 파일만** 커밋해뒀다. Mac + Xcode에서 아래 절차로 프로젝트를 만들고 이 파일들을 추가하면 된다.

## 1. Xcode 프로젝트 생성

1. Xcode → File → New → Project → **iOS → App**
2. Product Name: `SlamCapture`, Interface: **SwiftUI**, Language: **Swift**
3. 저장 위치는 아무 데나(임시) — 아래에서 소스를 이 저장소의 파일로 교체한다.

## 2. 소스 교체

새로 만들어진 프로젝트의 기본 `ContentView.swift`, `SlamCaptureApp.swift`를 지우고, 이 저장소의 `ios/SlamCapture/*.swift` 전부를 Xcode 프로젝트 네비게이터로 드래그해서 추가한다 ("Copy items if needed" 체크, 타겟에 `SlamCapture` 포함 확인).

파일 목록:
- `SlamCaptureApp.swift` — 앱 진입점
- `ContentView.swift` — 상태 표시 UI
- `CameraPreviewView.swift` — 화면에 실제 카메라 프레임을 보여주는 라이브 프리뷰 (캘리브레이션(#5) 등 촬영 시 프레이밍 확인용)
- `CaptureController.swift` — 카메라/IMU/TCP서버를 엮는 컨트롤러
- `CaptureManager.swift` — 후면 카메라 캡처 (AVFoundation)
- `MotionManager.swift` — IMU 캡처 (CoreMotion)
- `TCPServer.swift` — TCP 서버 (Network framework)
- `WireProtocol.swift` — 와이어 프로토콜 인코딩 ([docs/ios-tcp-protocol.md](ios-tcp-protocol.md) 참고)

## 3. Info.plist 권한 설정

Xcode 프로젝트의 **Info** 탭(또는 생성된 `Info.plist`)에 이 저장소의 `ios/SlamCapture/Info.plist`에 있는 키를 추가한다:
- `NSCameraUsageDescription`
- `NSMotionUsageDescription`

(최신 Xcode 템플릿은 Info.plist를 프로젝트 설정 안에 숨기는 경우가 많다 — 그럴 땐 타겟 → Info 탭에서 "Custom iOS Target Properties"에 같은 키/값을 추가하면 된다.)

## 4. 빌드/서명/실행

1. 타겟 → Signing & Capabilities에서 본인 Apple ID(무료 개발자 계정도 가능)로 서명
2. iPhone Xs Max를 USB로 Mac에 연결, Xcode 상단에서 기기 선택
3. ⌘R로 빌드 & 실행. 처음 실행 시 iPhone에서 "신뢰하지 않는 개발자" 설정을 허용해야 할 수 있다 (설정 → 일반 → VPN 및 기기 관리)
4. 카메라/모션 권한 팝업을 허용한다

## 5. 검증 (TX2/USB 없이, 같은 Wi-Fi에서)

앱이 실행되면 화면에 "포트 8765에서 대기 중..."이 뜬다. 같은 네트워크의 아무 컴퓨터(Mac이든 다른 기기든)에서:

```bash
python3 scripts/test_ios_tcp_client.py --connect <iPhone의 IP> 8765
```

iPhone의 IP는 설정 → Wi-Fi → 연결된 네트워크의 (i) 아이콘에서 확인. 정상이면 프레임/IMU 메시지 개수와 포맷 검증 결과가 출력되고, 화면의 "프레임 전송"/"IMU 샘플 전송" 카운터도 같이 올라가는 걸 볼 수 있다.

이 단계는 TX2나 iproxy/USB 연결 없이 확인 가능하다 (#4는 #2 TX2 작업과 독립적 — 티켓 설명 참고). USB(iproxy) 통한 실제 TX2 연동은 #6(브리지 노드)에서 다룬다.
