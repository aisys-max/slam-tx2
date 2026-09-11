import Foundation

/// docs/ios-tcp-protocol.md 의 바이트 레이아웃을 그대로 구현한다.
/// 이 파일과 그 문서는 함께 바뀌어야 한다 — 필드를 추가/변경하면 문서도 고칠 것.
enum WireMessageType: UInt8 {
    case frame = 0x01
    case imu = 0x02
}

enum WireProtocol {
    /// [1 byte type][4 bytes big-endian length][payload] 프레임으로 감싼다.
    static func encodeMessage(type: WireMessageType, payload: Data) -> Data {
        var out = Data(capacity: 1 + 4 + payload.count)
        out.append(type.rawValue)
        out.append(bigEndianBytes(UInt32(payload.count)))
        out.append(payload)
        return out
    }

    static func encodeFrame(timestampNs: UInt64, width: UInt32, height: UInt32, stride: UInt32, pixels: Data) -> Data {
        var payload = Data(capacity: 8 + 4 + 4 + 4 + pixels.count)
        payload.append(bigEndianBytes(timestampNs))
        payload.append(bigEndianBytes(width))
        payload.append(bigEndianBytes(height))
        payload.append(bigEndianBytes(stride))
        payload.append(pixels)
        return encodeMessage(type: .frame, payload: payload)
    }

    static func encodeImu(
        timestampNs: UInt64,
        angularVelocity: (x: Double, y: Double, z: Double),
        linearAcceleration: (x: Double, y: Double, z: Double)
    ) -> Data {
        var payload = Data(capacity: 8 + 8 * 6)
        payload.append(bigEndianBytes(timestampNs))
        payload.append(bigEndianBytes(angularVelocity.x))
        payload.append(bigEndianBytes(angularVelocity.y))
        payload.append(bigEndianBytes(angularVelocity.z))
        payload.append(bigEndianBytes(linearAcceleration.x))
        payload.append(bigEndianBytes(linearAcceleration.y))
        payload.append(bigEndianBytes(linearAcceleration.z))
        return encodeMessage(type: .imu, payload: payload)
    }

    private static func bigEndianBytes(_ value: UInt32) -> Data {
        withUnsafeBytes(of: value.bigEndian) { Data($0) }
    }

    private static func bigEndianBytes(_ value: UInt64) -> Data {
        withUnsafeBytes(of: value.bigEndian) { Data($0) }
    }

    private static func bigEndianBytes(_ value: Double) -> Data {
        withUnsafeBytes(of: value.bitPattern.bigEndian) { Data($0) }
    }
}

/// 현재(캡처) 시각을 iPhone 모노토닉 클럭 기준 나노초로 반환한다 (ADR-0001).
/// mach_continuous_time 계열은 CMSampleBuffer.presentationTimeStamp / CMDeviceMotion.timestamp가
/// 쓰는 것과 같은 타임베이스(systemUptime)라서, 프레임과 IMU 타임스탬프가 서로 비교 가능하다.
enum MonotonicClock {
    static func nowNs() -> UInt64 {
        UInt64(ProcessInfo.processInfo.systemUptime * 1_000_000_000)
    }

    static func ns(fromUptimeSeconds seconds: TimeInterval) -> UInt64 {
        UInt64(max(0, seconds) * 1_000_000_000)
    }
}
