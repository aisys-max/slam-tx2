import Foundation
import Network
import os

/// docs/ios-tcp-protocol.md: iPhone이 TCP 서버, TX2가 클라이언트로 접속한다.
/// 한 번에 하나의 연결만 지원 — 새 연결이 오면 이전 연결을 닫는다.
final class TCPServer {
    private let port: NWEndpoint.Port
    private var listener: NWListener?
    private var currentConnection: NWConnection?
    private let queue = DispatchQueue(label: "com.slamtx2.tcpserver")
    private let log = Logger(subsystem: "com.slamtx2.slamcapture", category: "TCPServer")

    private(set) var isConnected = false
    var onStateChange: ((Bool) -> Void)?

    // 프레임(최대 ~360KB, 20~30fps)이 네트워크가 소화할 수 있는 속도보다 빨리 나오면
    // NWConnection.send가 완료 전 계속 쌓여 메모리가 무한정 자랄 수 있다. IMU(72바이트,
    // 200Hz)는 무시할 만한 크기라 그대로 보내고, 프레임만 "전송 중이면 새 프레임은 버린다"로
    // 제한한다 — MonocularInertialNode::GrabImage의 최신-것만-유지 패턴과 같은 발상이다.
    private var frameInFlight = false

    init(port: UInt16 = 8765) {
        self.port = NWEndpoint.Port(rawValue: port)!
    }

    func start() {
        let params = NWParameters.tcp
        guard let listener = try? NWListener(using: params, on: port) else {
            log.error("리스너 생성 실패 (포트 \(self.port.rawValue, privacy: .public))")
            return
        }
        self.listener = listener

        listener.newConnectionHandler = { [weak self] connection in
            self?.accept(connection)
        }
        listener.stateUpdateHandler = { [weak self] state in
            if case .failed(let error) = state {
                self?.log.error("리스너 실패: \(String(describing: error), privacy: .public)")
            }
        }
        listener.start(queue: queue)
        log.info("포트 \(self.port.rawValue, privacy: .public)에서 리스닝 시작")
    }

    func stop() {
        currentConnection?.cancel()
        listener?.cancel()
    }

    /// 인코딩된 메시지(WireProtocol.encode*)를 현재 연결로 보낸다. 연결이 없으면 조용히 버린다
    /// (docs/ios-tcp-protocol.md: 끊긴 동안의 데이터는 유실 — 재전송하지 않는다). IMU처럼 작고
    /// 빈도 높은 메시지용 — 큰 프레임은 sendFrame(_:)을 쓸 것.
    func send(_ data: Data) {
        guard let connection = currentConnection else { return }
        connection.send(content: data, completion: .contentProcessed { [weak self] error in
            if let error = error {
                self?.log.error("전송 실패: \(String(describing: error), privacy: .public)")
            }
        })
    }

    /// 프레임 전용 전송: 이전 프레임이 아직 네트워크로 나가는 중이면 이번 프레임은 버린다.
    /// 큰 페이로드가 전송 완료를 기다리며 무한정 쌓이는 걸 막는다 (위 frameInFlight 주석 참고).
    func sendFrame(_ data: Data) {
        guard let connection = currentConnection else { return }
        queue.async { [weak self] in
            guard let self = self, !self.frameInFlight else { return }
            self.frameInFlight = true
            connection.send(content: data, completion: .contentProcessed { [weak self] error in
                if let error = error {
                    self?.log.error("프레임 전송 실패: \(String(describing: error), privacy: .public)")
                }
                self?.queue.async { self?.frameInFlight = false }
            })
        }
    }

    private func accept(_ connection: NWConnection) {
        // 새 연결이 오면 이전 연결을 닫는다 (프로토콜 문서 참고).
        currentConnection?.cancel()
        currentConnection = connection

        connection.stateUpdateHandler = { [weak self] state in
            guard let self = self else { return }
            switch state {
            case .ready:
                self.log.info("클라이언트 연결됨")
                self.isConnected = true
                self.onStateChange?(true)
            case .failed, .cancelled:
                if self.currentConnection === connection {
                    self.currentConnection = nil
                    self.isConnected = false
                    self.onStateChange?(false)
                }
            default:
                break
            }
        }
        connection.start(queue: queue)
    }
}
