import AVFoundation
import Foundation
import os

/// 후면 카메라 프레임을 캡처해 WireProtocol.encodeFrame으로 TCPServer에 보낸다.
/// 스펙: 해상도 640x480~752x480, 20~30fps 시작 값 (docs/ros2-topic-contract.md).
/// mono8은 캡처한 YUV420 버퍼의 Y-plane(휘도)을 그대로 쓴다 — 별도 그레이스케일
/// 변환 없이 CPU 부담을 줄인다 (docs/ios-tcp-protocol.md).
final class CaptureManager: NSObject {
    private let session = AVCaptureSession()
    private let videoOutputQueue = DispatchQueue(label: "com.slamtx2.videoOutput")
    private let log = Logger(subsystem: "com.slamtx2.slamcapture", category: "CaptureManager")

    private let onFrame: (Data) -> Void

    init(onFrame: @escaping (Data) -> Void) {
        self.onFrame = onFrame
        super.init()
    }

    func requestAuthorizationAndStart() {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            configureAndStart()
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
                if granted {
                    self?.configureAndStart()
                } else {
                    self?.log.error("카메라 권한 거부됨")
                }
            }
        default:
            log.error("카메라 권한 없음 (설정에서 허용 필요)")
        }
    }

    private func configureAndStart() {
        session.beginConfiguration()
        session.sessionPreset = .vga640x480  // 스펙 640x480~752x480 범위 시작 값

        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back),
              let input = try? AVCaptureDeviceInput(device: device),
              session.canAddInput(input) else {
            log.error("후면 카메라 입력 구성 실패")
            session.commitConfiguration()
            return
        }
        session.addInput(input)

        let output = AVCaptureVideoDataOutput()
        // 420YpCbCr8BiPlanarFullRange: plane 0이 순수 휘도(Y) 데이터라 mono8로 바로 쓸 수 있다.
        output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_420YpCbCr8BiPlanarFullRange]
        output.alwaysDiscardsLateVideoFrames = true
        output.setSampleBufferDelegate(self, queue: videoOutputQueue)
        guard session.canAddOutput(output) else {
            log.error("비디오 출력 구성 실패")
            session.commitConfiguration()
            return
        }
        session.addOutput(output)

        if let connection = output.connection(with: .video) {
            connection.videoOrientation = .landscapeRight  // 차량 거치 시 후면 카메라 기준 (필요시 조정)
        }

        // 20~30fps 범위로 맞춘다 (스펙 시작 값).
        if let range = device.activeFormat.videoSupportedFrameRateRanges.first {
            let fps = min(max(30, range.minFrameRate), range.maxFrameRate)
            try? device.lockForConfiguration()
            device.activeVideoMinFrameDuration = CMTime(value: 1, timescale: Int32(fps))
            device.activeVideoMaxFrameDuration = CMTime(value: 1, timescale: Int32(fps))
            device.unlockForConfiguration()
        }

        session.commitConfiguration()
        session.startRunning()
        log.info("카메라 세션 시작")
    }

    func stop() {
        session.stopRunning()
    }
}

extension CaptureManager: AVCaptureVideoDataOutputSampleBufferDelegate {
    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }

        // presentationTimeStamp는 하드웨어 캡처 시각(콜백 지연 없음) - ADR-0001이 요구하는
        // "캡처 시각"에 정확히 대응하고, CoreMotion의 systemUptime과 같은 타임베이스를 쓴다.
        let pts = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
        let timestampNs = MonotonicClock.ns(fromUptimeSeconds: CMTimeGetSeconds(pts))

        CVPixelBufferLockBaseAddress(pixelBuffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, .readOnly) }

        guard let yPlane = CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 0) else { return }
        let width = UInt32(CVPixelBufferGetWidthOfPlane(pixelBuffer, 0))
        let height = UInt32(CVPixelBufferGetHeightOfPlane(pixelBuffer, 0))
        let stride = UInt32(CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 0))
        let pixels = Data(bytes: yPlane, count: Int(stride * height))

        let message = WireProtocol.encodeFrame(
            timestampNs: timestampNs, width: width, height: height, stride: stride, pixels: pixels
        )
        onFrame(message)
    }
}
