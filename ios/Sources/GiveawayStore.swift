import Foundation
import SwiftUI

@MainActor
final class GiveawayStore: ObservableObject {
    // Feed chính
    @Published var items: [Giveaway] = []
    @Published var total = 0
    @Published var isLoading = false
    @Published var isLoadingMore = false
    @Published var errorMessage: String?
    @Published var platform: Platform = .all { didSet { if oldValue != platform { Task { await refresh() } } } }
    @Published var sort: SortOption = .new { didSet { if oldValue != sort { Task { await refresh() } } } }
    @Published var searchText = ""

    // Tab phụ
    @Published var endingSoon: [Giveaway] = []
    @Published var upcoming: [Giveaway] = []
    @Published var stats: Stats?
    @Published var lastUpdated: Date?

    // Dữ liệu người dùng (lưu cục bộ)
    @Published private(set) var savedIDs: Set<Int> = []
    @Published private(set) var claimedIDs: Set<Int> = []
    @Published private(set) var savedItems: [Int: Giveaway] = [:]
    @Published var hideClaimed: Bool = UserDefaults.standard.object(forKey: "hideClaimed") as? Bool ?? true {
        didSet { UserDefaults.standard.set(hideClaimed, forKey: "hideClaimed") }
    }
    @Published var toast: String?

    private var page = 1
    private var hasMore = false
    private var searchTask: Task<Void, Never>?

    init() {
        let d = UserDefaults.standard
        savedIDs = Set(d.array(forKey: "savedIDs") as? [Int] ?? [])
        claimedIDs = Set(d.array(forKey: "claimedIDs") as? [Int] ?? [])
        savedItems = DiskCache.load([Int: Giveaway].self, from: "saved_items.json") ?? [:]
        if let cached = DiskCache.load([Giveaway].self, from: "feed.json") {
            items = cached
            total = cached.count
        }
        stats = DiskCache.load(Stats.self, from: "stats.json")
    }

    var visibleItems: [Giveaway] {
        hideClaimed ? items.filter { !claimedIDs.contains($0.id) } : items
    }

    var savedList: [Giveaway] {
        savedIDs.compactMap { savedItems[$0] }.sorted { ($0.firstSeenAt) > ($1.firstSeenAt) }
    }

    var claimedList: [Giveaway] {
        claimedIDs.compactMap { savedItems[$0] }.sorted { ($0.firstSeenAt) > ($1.firstSeenAt) }
    }

    var claimedWorth: Double {
        claimedIDs.compactMap { savedItems[$0]?.worthValue }.reduce(0, +)
    }

    // MARK: - Tải dữ liệu

    func refresh() async {
        isLoading = true
        errorMessage = nil
        page = 1
        do {
            let result = try await APIClient.giveaways(platform: platform, sort: sort, query: searchText, page: 1)
            items = result.items
            total = result.total
            hasMore = result.hasMore
            lastUpdated = Date()
            if platform == .all && searchText.isEmpty && sort == .new {
                DiskCache.save(result.items, as: "feed.json")
                NotificationManager.shared.markSeen(result.items)
            }
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
        async let s: Void = loadStats()
        async let e: Void = loadSecondary()
        _ = await (s, e)
    }

    func loadMoreIfNeeded(current item: Giveaway) async {
        guard hasMore, !isLoadingMore, item.id == items.last?.id else { return }
        isLoadingMore = true
        do {
            let result = try await APIClient.giveaways(platform: platform, sort: sort, query: searchText, page: page + 1)
            let existing = Set(items.map(\.id))
            items.append(contentsOf: result.items.filter { !existing.contains($0.id) })
            hasMore = result.hasMore
            page += 1
        } catch {
            toast = error.localizedDescription
        }
        isLoadingMore = false
    }

    func loadStats() async {
        if let s = try? await APIClient.stats() {
            stats = s
            DiskCache.save(s, as: "stats.json")
        }
    }

    func loadSecondary() async {
        async let ending = try? APIClient.giveaways(status: "ending", sort: .ending, perPage: 50)
        async let next = try? APIClient.giveaways(status: "upcoming", sort: .new, perPage: 30)
        let (e, u) = await (ending, next)
        if let e = e { endingSoon = e.items }
        if let u = u { upcoming = u.items }
    }

    func searchChanged() {
        searchTask?.cancel()
        searchTask = Task {
            try? await Task.sleep(nanoseconds: 400_000_000)
            guard !Task.isCancelled else { return }
            await refresh()
        }
    }

    func triggerScan() async {
        toast = await APIClient.triggerScan()
        try? await Task.sleep(nanoseconds: 8_000_000_000)
        await refresh()
    }

    /// Đồng bộ lại trạng thái các bài đã lưu (biết bài nào hết hạn).
    func syncSaved() async {
        let ids = Array(savedIDs.union(claimedIDs))
        guard let fresh = try? await APIClient.giveaways(ids: ids) else { return }
        for g in fresh { savedItems[g.id] = g }
        persistSaved()
    }

    // MARK: - Lưu / Đã nhận

    func isSaved(_ g: Giveaway) -> Bool { savedIDs.contains(g.id) }
    func isClaimed(_ g: Giveaway) -> Bool { claimedIDs.contains(g.id) }

    func toggleSaved(_ g: Giveaway) {
        if savedIDs.contains(g.id) {
            savedIDs.remove(g.id)
        } else {
            savedIDs.insert(g.id)
            savedItems[g.id] = g
            toast = "Đã lưu “\(g.cleanTitle)”"
        }
        persistSaved()
        Haptics.tap()
    }

    func toggleClaimed(_ g: Giveaway) {
        if claimedIDs.contains(g.id) {
            claimedIDs.remove(g.id)
        } else {
            claimedIDs.insert(g.id)
            savedItems[g.id] = g
            toast = "Đã đánh dấu nhận ✓"
        }
        persistSaved()
        Haptics.success()
    }

    private func persistSaved() {
        let d = UserDefaults.standard
        d.set(Array(savedIDs), forKey: "savedIDs")
        d.set(Array(claimedIDs), forKey: "claimedIDs")
        let keep = savedIDs.union(claimedIDs)
        savedItems = savedItems.filter { keep.contains($0.key) }
        DiskCache.save(savedItems, as: "saved_items.json")
    }
}

enum Haptics {
    static func tap() { UIImpactFeedbackGenerator(style: .light).impactOccurred() }
    static func success() { UINotificationFeedbackGenerator().notificationOccurred(.success) }
}
