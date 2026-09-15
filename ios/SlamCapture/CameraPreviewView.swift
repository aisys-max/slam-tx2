import AVFoundation
import SwiftUI

/// CaptureManager의 AVCaptureSession을 화면에 그대로 보여준다 (캘리브레이션(#5) 등 촬영 시
/// 체커보드가 프레임 안에 제대로 들어왔는지 확인할 수 있도록). 배포 타겟이 iOS 15라 SwiftUI
/// 네이티브 카메라 프리뷰(iOS 17+)를 쓸 수 없어 AVCaptureVideoPreviewLayer를 UIKit으로 감싼다.
struct CameraPreviewView: UIViewRepresentable {
    let session: AVCaptureSession

    func makeUIView(context: Context) -> PreviewUIView {
        let view = PreviewUIView()
        view.videoPreviewLayer.session = session
        // 잘려서 안 보이는 영역이 없어야 한다 — 실제로 저장되는 프레임과 동일한 영역을 봐야
        // 체커보드가 프레임 밖으로 나가는지 정확히 판단할 수 있다.
        view.videoPreviewLayer.videoGravity = .resizeAspect
        return view
    }

    func updateUIView(_ uiView: PreviewUIView, context: Context) {}

    final class PreviewUIView: UIView {
        override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }

        var videoPreviewLayer: AVCaptureVideoPreviewLayer {
            layer as! AVCaptureVideoPreviewLayer
        }

        // session을 대입한 직후엔 AVFoundation이 connection을 아직 만들지 않아 nil이다 —
        // makeUIView에서 바로 설정하면 조용히 아무 효과가 없다. layoutSubviews는 connection이
        // 생긴 뒤에도 반복 호출되므로 여기서 설정해야 실제로 적용된다.
        override func layoutSubviews() {
            super.layoutSubviews()
            // CaptureManager가 실제 데이터 출력 커넥션에 쓰는 방향과 동일하게 맞춘다
            // (CaptureManager.swift, 차량 거치 시 후면 카메라 기준) — 그래야 화면에 보이는
            // 방향이 실제로 저장되는 프레임 방향과 일치한다.
            videoPreviewLayer.connection?.videoOrientation = .landscapeRight
        }
    }
}
