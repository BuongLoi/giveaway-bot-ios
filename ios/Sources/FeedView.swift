import SwiftUI

struct FeedView: View {
    @EnvironmentObject var store: GiveawayStore

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(spacing: 14, pinnedViews: []) {
                    StatsHeader()
                        .padding(.horizontal)
                    PlatformChips(selected: $store.platform, counts: store.stats?.platforms ?? [:])
                    sortBar.padding(.horizontal)

                    if let error = store.errorMessage, store.items.isEmpty {
                        EmptyStateView(icon: "wifi.exclamationmark", title: "Chưa tải được dữ liệu",
                                       message: error, actionTitle: "Thử lại") {
                            Task { await store.refresh() }
                        }
                    } else if store.items.isEmpty && store.isLoading {
                        ForEach(0..<4, id: \.self) { _ in SkeletonCard().padding(.horizontal) }
                    } else if store.visibleItems.isEmpty {
                        EmptyStateView(icon: "gift", title: "Chưa có giveaway",
                                       message: store.searchText.isEmpty ? "Không có bài nào cho bộ lọc này. Kéo xuống để làm mới."
                                                                         : "Không tìm thấy kết quả cho “\(store.searchText)”.")
                    } else {
                        ForEach(store.visibleItems) { g in
                            NavigationLink(value: g) {
                                GiveawayCard(g: g)
                            }
                            .buttonStyle(.plain)
                            .padding(.horizontal)
                            .task { await store.loadMoreIfNeeded(current: g) }
                        }
                        if store.isLoadingMore {
                            ProgressView().tint(.white).padding()
                        }
                    }
                }
                .padding(.vertical, 8)
            }
            .background(Theme.bg.ignoresSafeArea())
            .refreshable { await store.refresh() }
            .searchable(text: $store.searchText, placement: .navigationBarDrawer(displayMode: .automatic),
                        prompt: "Tìm app, game, phần mềm…")
            .onChange(of: store.searchText) { _ in store.searchChanged() }
            .navigationTitle("Giveaway Hunter")
            .navigationDestination(for: Giveaway.self) { g in DetailView(g: g) }
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        Haptics.tap()
                        Task { await store.triggerScan() }
                    } label: {
                        Image(systemName: "bolt.fill").foregroundStyle(Theme.gradient)
                    }
                    .accessibilityLabel("Quét nguồn mới")
                }
            }
        }
    }

    private var sortBar: some View {
        HStack {
            Text("\(store.total) giveaway đang mở")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(.white.opacity(0.6))
            Spacer()
            Menu {
                Picker("Sắp xếp", selection: $store.sort) {
                    ForEach(SortOption.allCases) { s in Label(s.title, systemImage: s.icon).tag(s) }
                }
                Toggle("Ẩn bài đã nhận", isOn: $store.hideClaimed)
            } label: {
                Label(store.sort.title, systemImage: "arrow.up.arrow.down")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(Theme.accent)
            }
        }
    }
}

struct StatsHeader: View {
    @EnvironmentObject var store: GiveawayStore

    var body: some View {
        HStack(spacing: 10) {
            statBox(value: "\(store.stats?.activeTotal ?? store.total)", label: "Đang free", icon: "gift.fill", color: Theme.free)
            statBox(value: formatMoney(store.stats?.totalWorth ?? 0), label: "Tổng giá trị", icon: "dollarsign.circle.fill", color: .yellow)
            statBox(value: "\(store.stats?.endingSoon ?? 0)", label: "Sắp hết 48h", icon: "flame.fill", color: .orange)
        }
    }

    private func statBox(value: String, label: String, icon: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Image(systemName: icon).foregroundColor(color).font(.system(size: 14, weight: .bold))
            Text(value).font(.system(size: 20, weight: .heavy)).foregroundColor(.white).minimumScaleFactor(0.6).lineLimit(1)
            Text(label).font(.system(size: 11, weight: .medium)).foregroundColor(.white.opacity(0.55))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 16).fill(Theme.card))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Theme.cardBorder))
    }
}

func formatMoney(_ v: Double) -> String {
    if v >= 1000 { return String(format: "$%.1fk", v / 1000) }
    return String(format: "$%.0f", v)
}

struct SkeletonCard: View {
    @State private var pulse = false
    var body: some View {
        HStack(spacing: 12) {
            RoundedRectangle(cornerRadius: 16).fill(Color.white.opacity(0.08)).frame(width: 72, height: 72)
            VStack(alignment: .leading, spacing: 8) {
                RoundedRectangle(cornerRadius: 4).fill(Color.white.opacity(0.08)).frame(height: 14)
                RoundedRectangle(cornerRadius: 4).fill(Color.white.opacity(0.06)).frame(width: 120, height: 12)
                RoundedRectangle(cornerRadius: 4).fill(Color.white.opacity(0.06)).frame(width: 80, height: 12)
            }
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 18).fill(Theme.card))
        .opacity(pulse ? 0.5 : 1)
        .onAppear { withAnimation(.easeInOut(duration: 0.9).repeatForever()) { pulse = true } }
    }
}

// MARK: - Sắp hết hạn / Sắp free

struct EndingView: View {
    @EnvironmentObject var store: GiveawayStore

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 14) {
                    section(title: "🔥 Sắp hết hạn (48 giờ)", items: store.endingSoon.filter { !$0.isExpired },
                            empty: "Không có giveaway nào sắp hết hạn.")
                    section(title: "⏳ Sắp miễn phí", items: store.upcoming,
                            empty: "Chưa có lịch free sắp tới.")
                }
                .padding(.vertical, 8)
            }
            .background(Theme.bg.ignoresSafeArea())
            .refreshable { await store.loadSecondary() }
            .navigationTitle("Hạn chót")
            .navigationDestination(for: Giveaway.self) { g in DetailView(g: g) }
        }
    }

    @ViewBuilder
    private func section(title: String, items: [Giveaway], empty: String) -> some View {
        Text(title).font(.system(size: 18, weight: .bold)).foregroundColor(.white).padding(.horizontal)
        if items.isEmpty {
            Text(empty).font(.subheadline).foregroundColor(.white.opacity(0.5)).padding(.horizontal)
        } else {
            ForEach(items) { g in
                NavigationLink(value: g) { GiveawayCard(g: g) }
                    .buttonStyle(.plain)
                    .padding(.horizontal)
            }
        }
    }
}

// MARK: - Đã lưu / Đã nhận

struct SavedView: View {
    @EnvironmentObject var store: GiveawayStore
    @State private var tab = 0

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Picker("", selection: $tab) {
                    Text("Đã lưu (\(store.savedIDs.count))").tag(0)
                    Text("Đã nhận (\(store.claimedIDs.count))").tag(1)
                }
                .pickerStyle(.segmented)
                .padding()

                if tab == 1 && !store.claimedIDs.isEmpty {
                    HStack {
                        Image(systemName: "sparkles").foregroundColor(.yellow)
                        Text("Bạn đã tiết kiệm được \(formatMoney(store.claimedWorth))")
                            .font(.system(size: 15, weight: .bold)).foregroundColor(.white)
                        Spacer()
                    }
                    .padding(12)
                    .background(RoundedRectangle(cornerRadius: 14).fill(Theme.free.opacity(0.15)))
                    .padding(.horizontal)
                }

                let list = tab == 0 ? store.savedList : store.claimedList
                if list.isEmpty {
                    Spacer()
                    EmptyStateView(icon: tab == 0 ? "bookmark" : "checkmark.seal",
                                   title: tab == 0 ? "Chưa lưu bài nào" : "Chưa nhận bài nào",
                                   message: "Nhấn giữ một giveaway hoặc mở chi tiết để lưu / đánh dấu đã nhận.")
                    Spacer()
                } else {
                    ScrollView {
                        LazyVStack(spacing: 14) {
                            ForEach(list) { g in
                                NavigationLink(value: g) { GiveawayCard(g: g) }
                                    .buttonStyle(.plain)
                                    .padding(.horizontal)
                            }
                        }
                        .padding(.vertical, 8)
                    }
                    .refreshable { await store.syncSaved() }
                }
            }
            .background(Theme.bg.ignoresSafeArea())
            .navigationTitle("Của tôi")
            .navigationDestination(for: Giveaway.self) { g in DetailView(g: g) }
        }
    }
}
