import AVFoundation
import Foundation
import Combine

/// CaptureManager(카메라) + MotionManager(IMU) + TCPServer를 엮는다.
/// ContentView가 관찰할 수 있도록 연결 상태/카운터를 @Published로 노출한다.
final class CaptureController: ObservableObject {
    @Published var isConnected = false
    @Published var framesSent = 0
    @Published var imuSamplesSent = 0
    // 실제 시험 구간을 표시하는 Start/Stop 상태 - 카메라/IMU 하드웨어와 TCP 연결 자체는
    // start()/stop()(앱 생명주기)이 관리하고, 이건 그 위에서 "지금 전송해도 되는지"만 게이팅한다.
    // 이렇게 분리해야 시험 시작/종료를 눌러도 재연결 지연 없이 바로 반영된다.
    @Published var isStreaming = false

    private let server: TCPServer
    private lazy var captureManager = CaptureManager { [weak self] frameMessage in
        self?.server.sendFrame(frameMessage)
        DispatchQueue.main.async { self?.framesSent += 1 }
    }
    private lazy var motionManager = MotionManager { [weak self] imuMessage in
        self?.server.send(imuMessage)
        DispatchQueue.main.async { self?.imuSamplesSent += 1 }
    }

    /// 캘리브레이션(#5) 등 촬영 시 화면에 실제 카메라 프레임을 보여주기 위한 미리보기용 세션.
    var previewSession: AVCaptureSession { captureManager.session }

    init(port: UInt16 = 8765) {
        server = TCPServer(port: port)
        server.onStateChange = { [weak self] connected in
            DispatchQueue.main.async { self?.isConnected = connected }
        }
    }

    func start() {
        server.start()
        captureManager.requestAuthorizationAndStart()
        motionManager.start(updateHz: 200.0)
    }

    func stop() {
        captureManager.stop()
        motionManager.stop()
        server.stop()
    }

    /// 시험 시작 - 이 시점 이후의 프레임/IMU만 TX2로 전송된다.
    func startStreaming() {
        isStreaming = true
        captureManager.setStreaming(true)
        motionManager.setStreaming(true)
    }

    /// 시험 종료 - 하드웨어/연결은 그대로 두고 전송만 멈춘다(다음 Start를 바로 누를 수 있게).
    func stopStreaming() {
        isStreaming = false
        captureManager.setStreaming(false)
        motionManager.setStreaming(false)
    }
}
