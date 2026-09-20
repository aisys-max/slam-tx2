import SwiftUI

struct ContentView: View {
    @ObservedObject var controller: CaptureController

    var body: some View {
        ZStack(alignment: .top) {
            CameraPreviewView(session: controller.previewSession)
                .edgesIgnoringSafeArea(.all)

            VStack(spacing: 16) {
                Text("SLAM Capture")
                    .font(.title)
                Text(controller.isConnected ? "TX2 연결됨" : "포트 8765에서 대기 중...")
                    .foregroundColor(controller.isConnected ? .green : .secondary)
                Text(controller.isStreaming ? "캡처 중" : "대기 중 (Start를 눌러 시작)")
                    .foregroundColor(controller.isStreaming ? .green : .secondary)
                Text("프레임 전송: \(controller.framesSent)")
                Text("IMU 샘플 전송: \(controller.imuSamplesSent)")

                Button(controller.isStreaming ? "Stop" : "Start") {
                    if controller.isStreaming {
                        controller.stopStreaming()
                    } else {
                        controller.startStreaming()
                    }
                }
                .font(.title2)
                .padding(.horizontal, 32)
                .padding(.vertical, 8)
                .background(controller.isStreaming ? Color.red : Color.green)
                .foregroundColor(.white)
                .cornerRadius(8)
            }
            .padding()
            .background(Color.black.opacity(0.5))
            .cornerRadius(8)
            .foregroundColor(.white)
            .padding()
        }
        // controller.start()는 카메라/IMU 하드웨어와 TCP 리스닝만 켠다 - 실제 전송은 꺼진 채로
        // 시작하므로(isStreaming=false), 시험 구간은 Start 버튼으로 명시적으로 열어야 한다.
        .onAppear { controller.start() }
        .onDisappear { controller.stop() }
    }
}
