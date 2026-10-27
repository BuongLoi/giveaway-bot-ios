import SwiftUI

@main
struct GiveawayHunterApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var store = GiveawayStore()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .preferredColorScheme(.dark)
        }
        .onChange(of: scenePhase) { phase in
            switch phase {
            case .active:
                Task { await store.refresh() }
            case .background:
                NotificationManager.shared.scheduleRefresh()
            default:
                break
            }
        }
    }
}

struct RootView: View {
    @EnvironmentObject var store: GiveawayStore
    @State private var selectedTab = 0
    @State private var openedGiveaway: Giveaway?

    var body: some View {
        TabView(selection: $selectedTab) {
            FeedView()
                .tabItem { Label("Khám phá", systemImage: "gift.fill") }
                .tag(0)
            EndingView()
                .tabItem { Label("Hạn chót", systemImage: "hourglass") }
                .badge(store.stats?.endingSoon ?? 0)
                .tag(1)
            SavedView()
                .tabItem { Label("Của tôi", systemImage: "bookmark.fill") }
                .tag(2)
            SettingsView()
                .tabItem { Label("Cài đặt", systemImage: "gearshape.fill") }
                .tag(3)
        }
        .tint(Theme.accent)
        .overlay(alignment: .bottom) {
            if let toast = store.toast {
                ToastView(text: toast)
                    .padding(.bottom, 70)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .task(id: toast) {
                        try? await Task.sleep(nanoseconds: 2_500_000_000)
                        withAnimation { store.toast = nil }
                    }
            }
        }
        .animation(.spring(response: 0.35), value: store.toast)
        .sheet(item: $openedGiveaway) { g in
            NavigationStack {
                DetailView(g: g)
                    .toolbar {
                        ToolbarItem(placement: .navigationBarLeading) {
                            Button("Đóng") { openedGiveaway = nil }
                        }
                    }
            }
            .environmentObject(store)
        }
        .onReceive(NotificationCenter.default.publisher(for: .openGiveaway)) { note in
            guard let id = note.object as? Int else { return }
            Task {
                if let g = try? await APIClient.giveaways(ids: [id]).first {
                    openedGiveaway = g
                }
            }
        }
        .task { await store.syncSaved() }
    }
}
