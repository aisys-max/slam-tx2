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
        applyOrientation(to: view)
        return view
    }

    func updateUIView(_ uiView: PreviewUIView, context: Context) {
        applyOrientation(to: uiView)
    }

    private func applyOrientation(to view: PreviewUIView) {
        // CaptureManager가 실제 데이터 출력 커넥션에 쓰는 방향과 동일하게 맞춘다
        // (CaptureManager.swift, 차량 거치 시 후면 카메라 기준) — 그래야 화면에 보이는 방향이
        // 실제로 저장되는 프레임 방향과 일치한다.
        view.videoPreviewLayer.connection?.videoOrientation = .landscapeRight
    }

    final class PreviewUIView: UIView {
        override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }

        var videoPreviewLayer: AVCaptureVideoPreviewLayer {
            layer as! AVCaptureVideoPreviewLayer
        }
    }
}
