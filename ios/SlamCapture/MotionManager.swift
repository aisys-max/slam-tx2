import CoreMotion
import Foundation
import os

/// 가속도계+자이로를 raw로 각 200Hz로 받아 WireProtocol.encodeImu로 TCPServer에 보낸다.
/// CMMotionManager.startDeviceMotionUpdates(자세 추정 포함)는 쓰지 않는다 — 프로젝트 결정상
/// iPhone에서는 raw 센서 데이터만 보내고 어떤 융합/VIO도 하지 않기로 했다 (project memory).
/// accelerometer/gyroscope는 각자 자기 페이스로 콜백이 오므로, 매 콜백마다 "그 시점의
/// 최신 값"으로 두 값을 짝지어 하나의 IMU 샘플을 만든다 — 실제 IMU 하드웨어가 두 축을
/// 동시에 샘플링하는 것의 근사치다.
final class MotionManager {
    private let motionManager = CMMotionManager()
    private let log = Logger(subsystem: "com.slamtx2.slamcapture", category: "MotionManager")

    private let onSample: (Data) -> Void

    // 9.80665 m/s^2 (표준 중력) - CoreMotion 가속도는 G 단위로 온다.
    private let gravityMs2 = 9.80665

    private var latestAcceleration: (x: Double, y: Double, z: Double, timestampNs: UInt64)?
    private var latestRotationRate: (x: Double, y: Double, z: Double)?
    private let lock = NSLock()

    // Start/Stop 버튼으로 게이팅: CoreMotion 폴링은 계속하되(재시작 지연 없음), false인 동안은
    // onSample을 호출하지 않는다. 기존 lock으로 함께 보호한다.
    private var isStreaming = false

    init(onSample: @escaping (Data) -> Void) {
        self.onSample = onSample
    }

    func setStreaming(_ streaming: Bool) {
        lock.lock()
        isStreaming = streaming
        lock.unlock()
    }

    func start(updateHz: Double = 200.0) {
        guard motionManager.isAccelerometerAvailable, motionManager.isGyroAvailable else {
            log.error("가속도계 또는 자이로를 사용할 수 없음")
            return
        }

        let interval = 1.0 / updateHz
        motionManager.accelerometerUpdateInterval = interval
        motionManager.gyroUpdateInterval = interval

        let queue = OperationQueue()
        queue.name = "com.slamtx2.motionQueue"

        motionManager.startGyroUpdates(to: queue) { [weak self] data, error in
            guard let self = self, let data = data else { return }
            self.lock.lock()
            self.latestRotationRate = (data.rotationRate.x, data.rotationRate.y, data.rotationRate.z)
            self.lock.unlock()
        }

        motionManager.startAccelerometerUpdates(to: queue) { [weak self] data, error in
            guard let self = self, let data = data else { return }
            let timestampNs = MonotonicClock.ns(fromUptimeSeconds: data.timestamp)
            let acc = (
                x: data.acceleration.x * self.gravityMs2,
                y: data.acceleration.y * self.gravityMs2,
                z: data.acceleration.z * self.gravityMs2
            )

            self.lock.lock()
            self.latestAcceleration = (acc.x, acc.y, acc.z, timestampNs)
            let gyro = self.latestRotationRate
            let streaming = self.isStreaming
            self.lock.unlock()

            guard streaming else { return }
            guard let gyro = gyro else { return }  // 첫 자이로 샘플이 아직 안 왔으면 건너뜀
            let message = WireProtocol.encodeImu(
                timestampNs: timestampNs,
                angularVelocity: gyro,
                linearAcceleration: acc
            )
            self.onSample(message)
        }
    }

    func stop() {
        motionManager.stopAccelerometerUpdates()
        motionManager.stopGyroUpdates()
    }
}
