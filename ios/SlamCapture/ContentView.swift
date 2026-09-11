import SwiftUI

struct ContentView: View {
    @ObservedObject var controller: CaptureController

    var body: some View {
        VStack(spacing: 16) {
            Text("SLAM Capture")
                .font(.title)
            Text(controller.isConnected ? "TX2 연결됨" : "포트 8765에서 대기 중...")
                .foregroundColor(controller.isConnected ? .green : .secondary)
            Text("프레임 전송: \(controller.framesSent)")
            Text("IMU 샘플 전송: \(controller.imuSamplesSent)")
        }
        .padding()
        .onAppear { controller.start() }
        .onDisappear { controller.stop() }
    }
}
