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
    /// (docs/ios-tcp-protocol.md: 끊긴 동안의 데이터는 유실 — 재전송하지 않는다).
    func send(_ data: Data) {
        guard let connection = currentConnection else { return }
        connection.send(content: data, completion: .contentProcessed { [weak self] error in
            if let error = error {
                self?.log.error("전송 실패: \(String(describing: error), privacy: .public)")
            }
        })
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
