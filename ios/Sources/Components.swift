import SwiftUI

// MARK: - Theme

enum Theme {
    static let bg = Color(red: 0.05, green: 0.07, blue: 0.13)
    static let card = Color(red: 0.10, green: 0.12, blue: 0.20)
    static let cardBorder = Color.white.opacity(0.07)
    static let accent = Color(red: 0.36, green: 0.55, blue: 1.0)
    static let free = Color(red: 0.20, green: 0.85, blue: 0.55)
    static let gradient = LinearGradient(colors: [Color(red: 0.36, green: 0.55, blue: 1.0), Color(red: 0.62, green: 0.35, blue: 1.0)],
                                         startPoint: .topLeading, endPoint: .bottomTrailing)
}

// MARK: - Ảnh

struct RemoteImage: View {
    let url: URL?
    let platform: Platform
    var contentMode: ContentMode = .fill

    var body: some View {
        AsyncImage(url: url, transaction: Transaction(animation: .easeOut(duration: 0.25))) { phase in
            switch phase {
            case .success(let image):
                image.resizable().aspectRatio(contentMode: contentMode)
            case .failure:
                placeholder
            case .empty:
                placeholder.overlay(ProgressView().tint(.white.opacity(0.6)))
            @unknown default:
                placeholder
            }
        }
    }

    private var placeholder: some View {
        ZStack {
            LinearGradient(colors: [platform.color.opacity(0.55), platform.color.opacity(0.18)],
                           startPoint: .topLeading, endPoint: .bottomTrailing)
            Image(systemName: platform.icon)
                .font(.system(size: 28, weight: .semibold))
                .foregroundColor(.white.opacity(0.85))
        }
    }
}

// MARK: - Badges

struct PillBadge: View {
    let text: String
    var icon: String? = nil
    var color: Color = .white
    var filled = false

    var body: some View {
        HStack(spacing: 4) {
            if let icon = icon { Image(systemName: icon).font(.system(size: 10, weight: .bold)) }
            Text(text).font(.system(size: 11, weight: .semibold)).lineLimit(1)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .foregroundColor(filled ? .white : color)
        .background(Capsule().fill(filled ? color : color.opacity(0.16)))
    }
}

struct PriceTag: View {
    let g: Giveaway
    var large = false

    var body: some View {
        HStack(spacing: 6) {
            if !g.worth.isEmpty {
                Text(g.worth)
                    .strikethrough(true, color: .white.opacity(0.6))
                    .foregroundColor(.white.opacity(0.55))
                    .font(.system(size: large ? 16 : 12, weight: .medium))
            }
            Text(g.isUpcoming ? "SẮP FREE" : "FREE")
                .font(.system(size: large ? 16 : 12, weight: .heavy))
                .foregroundColor(g.isUpcoming ? .orange : Theme.free)
        }
    }
}

struct CountdownLabel: View {
    let date: Date
    var prefix = ""
    var large = false

    var body: some View {
        TimelineView(.periodic(from: .now, by: Countdown.isUrgent(date) ? 1 : 30)) { context in
            let urgent = Countdown.isUrgent(date)
            HStack(spacing: 4) {
                Image(systemName: urgent ? "flame.fill" : "clock")
                Text(prefix + Countdown.text(until: date, now: context.date)).monospacedDigit()
            }
            .font(.system(size: large ? 14 : 11, weight: .bold))
            .foregroundColor(urgent ? .orange : .white.opacity(0.75))
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(Capsule().fill(urgent ? Color.orange.opacity(0.18) : Color.white.opacity(0.08)))
        }
    }
}

// MARK: - Chips lọc nền tảng

struct PlatformChips: View {
    @Binding var selected: Platform
    var counts: [String: Int] = [:]

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach([Platform.all, .ios, .windows, .game, .macos, .android, .other]) { p in
                    Button {
                        Haptics.tap()
                        withAnimation(.spring(response: 0.3)) { selected = p }
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: p.icon).font(.system(size: 12, weight: .semibold))
                            Text(p.title).font(.system(size: 13, weight: .semibold))
                            if p != .all, let c = counts[p.rawValue], c > 0 {
                                Text("\(c)").font(.system(size: 11, weight: .bold))
                                    .padding(.horizontal, 5).padding(.vertical, 1)
                                    .background(Capsule().fill(Color.white.opacity(selected == p ? 0.25 : 0.1)))
                            }
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .foregroundColor(selected == p ? .white : .white.opacity(0.75))
                        .background(
                            Capsule().fill(selected == p ? AnyShapeStyle(p.color.gradient) : AnyShapeStyle(Theme.card))
                        )
                        .overlay(Capsule().stroke(Theme.cardBorder))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal)
        }
    }
}

// MARK: - Card

struct GiveawayCard: View {
    let g: Giveaway
    @EnvironmentObject var store: GiveawayStore

    private var usesIconLayout: Bool { g.platformEnum == .ios || g.platformEnum == .macos || g.store == "appstore" }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if usesIconLayout {
                iconLayout
            } else {
                bannerLayout
            }
        }
        .background(RoundedRectangle(cornerRadius: 18).fill(Theme.card))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(Theme.cardBorder))
        .clipShape(RoundedRectangle(cornerRadius: 18))
        .opacity(store.isClaimed(g) ? 0.55 : 1)
        .contextMenu { contextActions }
    }

    private var iconLayout: some View {
        HStack(alignment: .top, spacing: 12) {
            RemoteImage(url: g.imageURL, platform: g.platformEnum)
                .frame(width: 72, height: 72)
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Color.white.opacity(0.08)))
            VStack(alignment: .leading, spacing: 6) {
                Text(g.cleanTitle)
                    .font(.system(size: 16, weight: .bold))
                    .foregroundColor(.white)
                    .lineLimit(2)
                metaRow
                HStack {
                    PriceTag(g: g)
                    Spacer()
                    statusBadges
                }
            }
        }
        .padding(12)
    }

    private var bannerLayout: some View {
        VStack(alignment: .leading, spacing: 0) {
            ZStack(alignment: .topLeading) {
                RemoteImage(url: g.imageURL, platform: g.platformEnum)
                    .frame(height: 150)
                    .frame(maxWidth: .infinity)
                    .clipped()
                LinearGradient(colors: [.clear, Theme.card.opacity(0.95)], startPoint: .center, endPoint: .bottom)
                HStack {
                    PillBadge(text: g.platformEnum.title, icon: g.platformEnum.icon, color: g.platformEnum.color, filled: true)
                    Spacer()
                    if let exp = g.expiryDate, !g.isUpcoming {
                        CountdownLabel(date: exp)
                    } else if let start = g.startDate, g.isUpcoming {
                        CountdownLabel(date: start, prefix: "Mở sau ")
                    }
                }
                .padding(10)
            }
            VStack(alignment: .leading, spacing: 6) {
                Text(g.cleanTitle)
                    .font(.system(size: 17, weight: .bold))
                    .foregroundColor(.white)
                    .lineLimit(2)
                HStack(spacing: 8) {
                    if !g.storeLabel.isEmpty {
                        Label(g.storeLabel, systemImage: "bag.fill")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.white.opacity(0.6))
                    }
                    if !g.codes.isEmpty {
                        PillBadge(text: "Có key", icon: "key.fill", color: .yellow)
                    }
                    Spacer()
                    PriceTag(g: g)
                }
                statusBadges
            }
            .padding(.horizontal, 12)
            .padding(.bottom, 12)
            .padding(.top, 2)
        }
    }

    private var metaRow: some View {
        HStack(spacing: 6) {
            PillBadge(text: g.platformEnum.title, icon: g.platformEnum.icon, color: g.platformEnum.color)
            if g.rating > 0 {
                Label(String(format: "%.1f", g.rating), systemImage: "star.fill")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.yellow)
            }
            if !g.codes.isEmpty {
                PillBadge(text: "Key", icon: "key.fill", color: .yellow)
            }
            if let exp = g.expiryDate {
                CountdownLabel(date: exp)
            }
        }
    }

    @ViewBuilder
    private var statusBadges: some View {
        HStack(spacing: 6) {
            if store.isSaved(g) { Image(systemName: "bookmark.fill").foregroundColor(Theme.accent) }
            if store.isClaimed(g) { Image(systemName: "checkmark.seal.fill").foregroundColor(Theme.free) }
            if g.isExpired { PillBadge(text: "Hết hạn", color: .red) }
        }
        .font(.system(size: 13))
    }

    @ViewBuilder
    private var contextActions: some View {
        Button { store.toggleSaved(g) } label: {
            Label(store.isSaved(g) ? "Bỏ lưu" : "Lưu lại", systemImage: store.isSaved(g) ? "bookmark.slash" : "bookmark")
        }
        Button { store.toggleClaimed(g) } label: {
            Label(store.isClaimed(g) ? "Bỏ đánh dấu đã nhận" : "Đánh dấu đã nhận", systemImage: "checkmark.seal")
        }
        if let url = g.claimURL {
            Link(destination: url) { Label("Nhận ngay", systemImage: "gift") }
            ShareLink(item: url) { Label("Chia sẻ", systemImage: "square.and.arrow.up") }
        }
    }
}

// MARK: - Trạng thái rỗng / lỗi

struct EmptyStateView: View {
    let icon: String
    let title: String
    let message: String
    var actionTitle: String? = nil
    var action: (() -> Void)? = nil

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 44, weight: .semibold))
                .foregroundStyle(Theme.gradient)
            Text(title).font(.headline).foregroundColor(.white)
            Text(message).font(.subheadline).foregroundColor(.white.opacity(0.6)).multilineTextAlignment(.center)
            if let actionTitle = actionTitle, let action = action {
                Button(actionTitle, action: action)
                    .buttonStyle(.borderedProminent)
                    .tint(Theme.accent)
                    .padding(.top, 4)
            }
        }
        .padding(32)
        .frame(maxWidth: .infinity)
    }
}

struct ToastView: View {
    let text: String
    var body: some View {
        Text(text)
            .font(.system(size: 14, weight: .semibold))
            .foregroundColor(.white)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(Capsule().fill(.ultraThinMaterial))
            .overlay(Capsule().stroke(Color.white.opacity(0.15)))
            .shadow(color: .black.opacity(0.3), radius: 12, y: 6)
            .padding(.horizontal, 24)
    }
}
