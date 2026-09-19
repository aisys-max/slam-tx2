# Building/running the iOS capture app (#4)

> 한국어 버전은 [여기](ios-app-setup.ko.md)에 있습니다.

This repo has no `.xcodeproj` — hand-crafting a project file in an environment without Xcode
(the TX2) risks it breaking, so **only the Swift source files** are committed. On a Mac with
Xcode, create the project with the steps below and add these files.

## 1. Create the Xcode project

1. Xcode → File → New → Project → **iOS → App**
2. Product Name: `SlamCapture`, Interface: **SwiftUI**, Language: **Swift**
3. Save location doesn't matter (temporary) — the sources get replaced with this repo's files
   below.

## 2. Replace the sources

Delete the newly created project's default `ContentView.swift` and `SlamCaptureApp.swift`, then
drag all of this repo's `ios/SlamCapture/*.swift` into the Xcode project navigator (check "Copy
items if needed", confirm the `SlamCapture` target is included).

File list:
- `SlamCaptureApp.swift` — app entry point
- `ContentView.swift` — status display UI
- `CameraPreviewView.swift` — a live preview showing the actual camera frame on screen (for
  checking framing during capture for e.g. calibration (#5))
- `CaptureController.swift` — controller wiring together camera/IMU/TCP server
- `CaptureManager.swift` — rear camera capture (AVFoundation)
- `MotionManager.swift` — IMU capture (CoreMotion)
- `TCPServer.swift` — TCP server (Network framework)
- `WireProtocol.swift` — wire protocol encoding (see [docs/ios-tcp-protocol.md](ios-tcp-protocol.md))

## 3. Info.plist permissions

Add the keys from this repo's `ios/SlamCapture/Info.plist` to the Xcode project's **Info** tab
(or the generated `Info.plist`):
- `NSCameraUsageDescription`
- `NSMotionUsageDescription`

(Recent Xcode templates often hide Info.plist inside project settings — in that case, add the
same key/value under target → Info tab → "Custom iOS Target Properties".)

## 4. Build/sign/run

1. Under target → Signing & Capabilities, sign with your own Apple ID (a free developer account
   works too)
2. Connect the iPhone Xs Max to the Mac over USB, select the device at the top of Xcode
3. ⌘R to build & run. On first run you may need to allow "untrusted developer" on the iPhone
   (Settings → General → VPN & Device Management)
4. Allow the camera/motion permission prompts

## 5. Verification (no TX2/USB needed, same Wi-Fi)

Once the app is running, the screen shows "Listening on port 8765...". From any computer on the
same network (Mac or otherwise):

```bash
python3 scripts/test_ios_tcp_client.py --connect <iPhone's IP> 8765
```

Find the iPhone's IP under Settings → Wi-Fi → connected network → the (i) icon. If it's working,
the frame/IMU message counts and format-verification results print out, and you'll see the
on-screen "frames sent"/"IMU samples sent" counters climbing too.

This step can be verified without the TX2 or iproxy/USB connection (#4 is independent of the #2
TX2 work — see the ticket description). Actual TX2 integration over USB (iproxy) is covered in
#6 (bridge node).
