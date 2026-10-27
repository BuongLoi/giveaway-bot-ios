import Foundation
import UserNotifications
import BackgroundTasks
import UIKit

/// Thông báo cục bộ khi có giveaway mới.
/// Vì .ipa không ký nên không dùng được APNs; thay vào đó iOS sẽ định kỳ đánh thức app
/// (Background App Refresh) để gọi API và bắn Local Notification cho các nền tảng đã chọn.
final class NotificationManager: NSObject, UNUserNotificationCenterDelegate {
    static let shared = NotificationManager()
    static let refreshTaskID = "me.buongloi.giveaway.refresh"

    private let defaults = UserDefaults.standard
    private let lastCheckKey = "lastNotifyCheck"
    private let seenKey = "notifiedIDs"

    var enabled: Bool {
        get { defaults.bool(forKey: "notificationsEnabled") }
        set { defaults.set(newValue, forKey: "notificationsEnabled") }
    }

    var platforms: Set<String> {
        get {
            if let arr = defaults.array(forKey: "notifyPlatforms") as? [String] { return Set(arr) }
            return ["ios", "windows", "macos", "game"]
        }
        set { defaults.set(Array(newValue), forKey: "notifyPlatforms") }
    }

    // MARK: - Quyền

    func requestAuthorization() async -> Bool {
        let center = UNUserNotificationCenter.current()
        let granted = (try? await center.requestAuthorization(options: [.alert, .sound, .badge])) ?? false
        enabled = granted
        if granted { scheduleRefresh() }
        return granted
    }

    func authorizationStatus() async -> UNAuthorizationStatus {
        await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
    }

    // MARK: - Background refresh

    func registerBackgroundTask() {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: Self.refreshTaskID, using: nil) { task in
            guard let refresh = task as? BGAppRefreshTask else { task.setTaskCompleted(success: false); return }
            self.handle(refresh)
        }
    }

    func scheduleRefresh() {
        guard enabled else { return }
        let request = BGAppRefreshTaskRequest(identifier: Self.refreshTaskID)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 20 * 60)
        do {
            try BGTaskScheduler.shared.submit(request)
        } catch {
            print("BGTask submit error: \(error)")
        }
    }

    private func handle(_ task: BGAppRefreshTask) {
        scheduleRefresh()
        let work = Task {
            let count = await checkForNew()
            task.setTaskCompleted(success: count >= 0)
        }
        task.expirationHandler = { work.cancel() }
    }

    /// Kiểm tra bài mới kể từ lần kiểm tra trước. Trả về số thông báo đã gửi (-1 nếu lỗi).
    @discardableResult
    func checkForNew() async -> Int {
        guard enabled else { return 0 }
        let since = defaults.string(forKey: lastCheckKey) ?? DateParser.string(Date(timeIntervalSinceNow: -6 * 3600))
        do {
            let page = try await APIClient.giveaways(status: "active", sort: .new, perPage: 50, since: since)
            if let serverTime = page.serverTime { defaults.set(serverTime, forKey: lastCheckKey) }
            var seen = Set(defaults.array(forKey: seenKey) as? [Int] ?? [])
            let fresh = page.items.filter { platforms.contains($0.platform) && !seen.contains($0.id) }
            for g in fresh.prefix(5) { await post(g) }
            if fresh.count > 5 { await postSummary(extra: fresh.count - 5) }
            fresh.forEach { seen.insert($0.id) }
            defaults.set(Array(seen.suffix(500)), forKey: seenKey)
            return fresh.count
        } catch {
            return -1
        }
    }

    /// Gọi khi người dùng đã xem feed trong app để không báo lại các bài đó.
    func markSeen(_ items: [Giveaway]) {
        var seen = Set(defaults.array(forKey: seenKey) as? [Int] ?? [])
        items.forEach { seen.insert($0.id) }
        defaults.set(Array(seen.suffix(500)), forKey: seenKey)
        if let newest = items.compactMap({ $0.firstSeenAt.isEmpty ? nil : $0.firstSeenAt }).max() {
            defaults.set(newest, forKey: lastCheckKey)
        }
    }

    private func post(_ g: Giveaway) async {
        let content = UNMutableNotificationContent()
        content.title = "🎁 \(g.platformEnum.title) miễn phí: \(g.cleanTitle)"
        var body = g.worth.isEmpty ? "Đang FREE" : "\(g.worth) → FREE"
        if let exp = g.expiryDate { body += " • còn \(Countdown.text(until: exp))" }
        if !g.storeLabel.isEmpty { body += " • \(g.storeLabel)" }
        content.body = body
        content.sound = .default
        content.userInfo = ["giveawayID": g.id]
        content.threadIdentifier = g.platform
        let request = UNNotificationRequest(identifier: "g-\(g.id)", content: content, trigger: nil)
        try? await UNUserNotificationCenter.current().add(request)
    }

    private func postSummary(extra: Int) async {
        let content = UNMutableNotificationContent()
        content.title = "Giveaway Hunter"
        content.body = "Còn \(extra) giveaway mới khác đang chờ bạn."
        content.sound = .default
        let request = UNNotificationRequest(identifier: "summary-\(Date().timeIntervalSince1970)", content: content, trigger: nil)
        try? await UNUserNotificationCenter.current().add(request)
    }

    func sendTest() async {
        let content = UNMutableNotificationContent()
        content.title = "🎁 Thông báo thử"
        content.body = "Giveaway Hunter sẽ báo cho bạn khi có app/game miễn phí mới."
        content.sound = .default
        let request = UNNotificationRequest(identifier: "test", content: content,
                                            trigger: UNTimeIntervalNotificationTrigger(timeInterval: 2, repeats: false))
        try? await UNUserNotificationCenter.current().add(request)
    }

    // MARK: - Delegate

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound, .list])
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        if let id = response.notification.request.content.userInfo["giveawayID"] as? Int {
            DispatchQueue.main.async {
                NotificationCenter.default.post(name: .openGiveaway, object: id)
            }
        }
        completionHandler()
    }
}

extension Notification.Name {
    static let openGiveaway = Notification.Name("openGiveaway")
}

final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        UNUserNotificationCenter.current().delegate = NotificationManager.shared
        NotificationManager.shared.registerBackgroundTask()
        return true
    }
}
