import SwiftUI

@main
struct SlamCaptureApp: App {
    @StateObject private var controller = CaptureController()

    var body: some Scene {
        WindowGroup {
            ContentView(controller: controller)
        }
    }
}
