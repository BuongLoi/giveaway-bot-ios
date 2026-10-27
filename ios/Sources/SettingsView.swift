import SwiftUI
import UserNotifications

struct SettingsView: View {
    @EnvironmentObject var store: GiveawayStore
    @State private var notificationsOn = NotificationManager.shared.enabled
    @State private var platforms = NotificationManager.shared.platforms
    @State private var authStatus: UNAuthorizationStatus = .notDetermined
    @State private var serverURL = UserDefaults.standard.string(forKey: "serverURL") ?? ""
    @State private var checking = false
    @Environment(\.openURL) private var openURL

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Toggle(isOn: $notificationsOn) {
                        Label("Thông báo giveaway mới", systemImage: "bell.badge.fill")
                    }
                    .onChange(of: notificationsOn) { on in
                        Task {
                            if on {
                                let granted = await NotificationManager.shared.requestAuthorization()
                                if !granted { notificationsOn = false; store.toast = "Hãy cho phép thông báo trong Cài đặt iOS" }
                            } else {
                                NotificationManager.shared.enabled = false
                            }
                            authStatus = await NotificationManager.shared.authorizationStatus()
                        }
                    }
                    if authStatus == .denied {
                        Button("Mở Cài đặt iOS để cấp quyền") {
                            if let url = URL(string: UIApplication.openSettingsURLString) { openURL(url) }
                        }
                    }
                    if notificationsOn {
                        ForEach(Platform.notifiable) { p in
                            Toggle(isOn: Binding(
                                get: { platforms.contains(p.rawValue) },
                                set: { on in
                                    if on { platforms.insert(p.rawValue) } else { platforms.remove(p.rawValue) }
                                    NotificationManager.shared.platforms = platforms
                                })) {
                                Label(p.title, systemImage: p.icon).foregroundColor(.primary)
                            }
                            .tint(p.color)
                        }
                        Button {
                            Task { await NotificationManager.shared.sendTest() }
                        } label: { Label("Gửi thông báo thử", systemImage: "paperplane") }
                        Button {
                            checking = true
                            Task {
                                let n = await NotificationManager.shared.checkForNew()
                                store.toast = n > 0 ? "Có \(n) giveaway mới!" : (n == 0 ? "Chưa có bài mới" : "Lỗi kết nối")
                                checking = false
                            }
                        } label: {
                            HStack {
                                Label("Kiểm tra bài mới ngay", systemImage: "arrow.clockwise")
                                if checking { Spacer(); ProgressView() }
                            }
                        }
                    }
                } header: {
                    Text("Thông báo")
                } footer: {
                    Text("iOS tự quyết định thời điểm chạy nền (thường 15 phút – vài giờ). Hãy bật “Làm mới ứng dụng trong nền” cho Giveaway Hunter trong Cài đặt iOS. Muốn nhận tức thì, dùng bot Telegram.")
                }

                Section("Hiển thị") {
                    Toggle("Ẩn bài đã nhận khỏi trang chính", isOn: $store.hideClaimed)
                }

                Section {
                    TextField(APIClient.defaultServer, text: $serverURL)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .onSubmit(saveServer)
                    Button("Lưu & tải lại", action: saveServer)
                    Button {
                        if let url = URL(string: APIClient.serverURL + "/giveaways") { openURL(url) }
                    } label: { Label("Mở bản web", systemImage: "safari") }
                } header: {
                    Text("Máy chủ")
                } footer: {
                    Text("Để trống để dùng máy chủ mặc định.")
                }

                Section("Thống kê") {
                    row("Đang miễn phí", "\(store.stats?.activeTotal ?? 0)")
                    row("Tổng giá trị đang free", formatMoney(store.stats?.totalWorth ?? 0))
                    row("Sắp free", "\(store.stats?.upcoming ?? 0)")
                    row("Bạn đã tiết kiệm", formatMoney(store.claimedWorth))
                    if let scan = DateParser.parse(store.stats?.lastScanAt) {
                        row("Lần quét gần nhất", RelativeTime.text(scan))
                    }
                }

                Section {
                    row("Phiên bản", Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "3.0")
                } footer: {
                    Text("Nguồn: Epic Games, GamerPower (Steam/GOG/itch.io/Prime), GiveawayOfTheDay, SharewareOnSale, Reddit r/AppHookup, 9to5Toys…")
                }
            }
            .scrollContentBackground(.hidden)
            .background(Theme.bg.ignoresSafeArea())
            .navigationTitle("Cài đặt")
            .task {
                authStatus = await NotificationManager.shared.authorizationStatus()
                if authStatus == .denied { notificationsOn = false; NotificationManager.shared.enabled = false }
            }
        }
    }

    private func row(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label)
            Spacer()
            Text(value).foregroundColor(.secondary)
        }
    }

    private func saveServer() {
        UserDefaults.standard.set(serverURL.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "serverURL")
        Task { await store.refresh() }
        store.toast = "Đã lưu máy chủ"
    }
}
