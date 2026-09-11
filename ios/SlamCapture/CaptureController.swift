import Foundation
import Combine

/// CaptureManager(카메라) + MotionManager(IMU) + TCPServer를 엮는다.
/// ContentView가 관찰할 수 있도록 연결 상태/카운터를 @Published로 노출한다.
final class CaptureController: ObservableObject {
    @Published var isConnected = false
    @Published var framesSent = 0
    @Published var imuSamplesSent = 0

    private let server: TCPServer
    private lazy var captureManager = CaptureManager { [weak self] frameMessage in
        self?.server.sendFrame(frameMessage)
        DispatchQueue.main.async { self?.framesSent += 1 }
    }
    private lazy var motionManager = MotionManager { [weak self] imuMessage in
        self?.server.send(imuMessage)
        DispatchQueue.main.async { self?.imuSamplesSent += 1 }
    }

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
}
