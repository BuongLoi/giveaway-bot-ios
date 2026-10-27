import SwiftUI

struct DetailView: View {
    let g: Giveaway
    @EnvironmentObject var store: GiveawayStore
    @Environment(\.openURL) private var openURL
    @State private var copiedCode: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                header
                VStack(alignment: .leading, spacing: 16) {
                    titleBlock
                    priceBlock
                    actionButtons
                    if !g.codes.isEmpty { codesBlock }
                    if !g.description.isEmpty { descriptionBlock }
                    infoBlock
                }
                .padding(.horizontal)
            }
            .padding(.bottom, 32)
        }
        .background(Theme.bg.ignoresSafeArea())
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItemGroup(placement: .navigationBarTrailing) {
                Button { store.toggleSaved(g) } label: {
                    Image(systemName: store.isSaved(g) ? "bookmark.fill" : "bookmark")
                }
                if let url = g.claimURL {
                    ShareLink(item: url, subject: Text(g.cleanTitle),
                              message: Text("🎁 \(g.cleanTitle) đang miễn phí!")) {
                        Image(systemName: "square.and.arrow.up")
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var header: some View {
        let iconStyle = g.platformEnum == .ios || g.platformEnum == .macos || g.store == "appstore"
        if iconStyle {
            ZStack {
                RemoteImage(url: g.imageURL, platform: g.platformEnum)
                    .frame(height: 220).frame(maxWidth: .infinity).clipped()
                    .blur(radius: 30).opacity(0.6)
                RemoteImage(url: g.imageURL, platform: g.platformEnum)
                    .frame(width: 128, height: 128)
                    .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
                    .shadow(color: .black.opacity(0.4), radius: 16, y: 8)
            }
            .frame(height: 220)
            .clipped()
        } else {
            RemoteImage(url: g.imageURL, platform: g.platformEnum)
                .frame(height: 220).frame(maxWidth: .infinity).clipped()
                .overlay(LinearGradient(colors: [.clear, Theme.bg], startPoint: .center, endPoint: .bottom))
        }
    }

    private var titleBlock: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(g.cleanTitle)
                .font(.system(size: 24, weight: .heavy))
                .foregroundColor(.white)
            HStack(spacing: 6) {
                PillBadge(text: g.platformEnum.title, icon: g.platformEnum.icon, color: g.platformEnum.color, filled: true)
                if !g.storeLabel.isEmpty { PillBadge(text: g.storeLabel, icon: "bag.fill", color: Theme.accent) }
                if g.rating > 0 { PillBadge(text: String(format: "%.1f", g.rating), icon: "star.fill", color: .yellow) }
                if g.isExpired { PillBadge(text: "Đã hết hạn", color: .red, filled: true) }
            }
        }
    }

    private var priceBlock: some View {
        HStack {
            PriceTag(g: g, large: true)
            Spacer()
            if g.isUpcoming, let start = g.startDate {
                CountdownLabel(date: start, prefix: "Mở sau ", large: true)
            } else if let exp = g.expiryDate {
                CountdownLabel(date: exp, prefix: "Còn ", large: true)
            } else {
                Text("Chưa rõ hạn").font(.system(size: 13)).foregroundColor(.white.opacity(0.5))
            }
        }
        .padding(14)
        .background(RoundedRectangle(cornerRadius: 16).fill(Theme.card))
    }

    private var actionButtons: some View {
        VStack(spacing: 10) {
            if let url = g.claimURL {
                Button {
                    Haptics.tap()
                    openURL(url)
                } label: {
                    Label(g.store == "appstore" ? "Mở App Store để nhận" : "Nhận ngay", systemImage: "gift.fill")
                        .font(.system(size: 17, weight: .bold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .foregroundColor(.white)
                        .background(RoundedRectangle(cornerRadius: 14).fill(Theme.gradient))
                }
                .disabled(g.isUpcoming)
                .opacity(g.isUpcoming ? 0.5 : 1)
            }
            HStack(spacing: 10) {
                Button { store.toggleClaimed(g) } label: {
                    Label(store.isClaimed(g) ? "Đã nhận" : "Đánh dấu đã nhận",
                          systemImage: store.isClaimed(g) ? "checkmark.seal.fill" : "checkmark.seal")
                        .font(.system(size: 14, weight: .semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .foregroundColor(store.isClaimed(g) ? Theme.free : .white)
                        .background(RoundedRectangle(cornerRadius: 12).fill(Theme.card))
                }
                if let post = g.postURL, g.url != g.claimUrl {
                    Button { openURL(post) } label: {
                        Label("Bài gốc", systemImage: "doc.text")
                            .font(.system(size: 14, weight: .semibold))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 12)
                            .foregroundColor(.white)
                            .background(RoundedRectangle(cornerRadius: 12).fill(Theme.card))
                    }
                }
            }
        }
    }

    private var codesBlock: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("License key / Code", systemImage: "key.fill")
                .font(.system(size: 16, weight: .bold)).foregroundColor(.yellow)
            ForEach(g.codes, id: \.self) { code in
                Button {
                    UIPasteboard.general.string = code
                    Haptics.success()
                    copiedCode = code
                    store.toast = "Đã copy key"
                } label: {
                    HStack {
                        Text(code).font(.system(size: 15, weight: .semibold, design: .monospaced))
                            .foregroundColor(.white).textSelection(.enabled)
                        Spacer()
                        Image(systemName: copiedCode == code ? "checkmark" : "doc.on.doc")
                            .foregroundColor(copiedCode == code ? Theme.free : Theme.accent)
                    }
                    .padding(12)
                    .background(RoundedRectangle(cornerRadius: 12).fill(Color.yellow.opacity(0.08)))
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.yellow.opacity(0.3), style: StrokeStyle(lineWidth: 1, dash: [5])))
                }
                .buttonStyle(.plain)
            }
        }
    }

    private var descriptionBlock: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Mô tả").font(.system(size: 16, weight: .bold)).foregroundColor(.white)
            Text(g.description)
                .font(.system(size: 14))
                .foregroundColor(.white.opacity(0.75))
                .lineSpacing(3)
                .textSelection(.enabled)
        }
    }

    private var infoBlock: some View {
        VStack(spacing: 0) {
            infoRow("Nguồn", g.source)
            if let exp = g.expiryDate {
                infoRow("Hết hạn", exp.formatted(date: .abbreviated, time: .shortened))
            }
            if let seen = g.firstSeenDate {
                infoRow("Phát hiện", RelativeTime.text(seen))
            }
            infoRow("Độ tin cậy", "\(g.confidence)%")
        }
        .background(RoundedRectangle(cornerRadius: 14).fill(Theme.card))
    }

    private func infoRow(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label).foregroundColor(.white.opacity(0.55))
            Spacer()
            Text(value).foregroundColor(.white).lineLimit(1)
        }
        .font(.system(size: 14))
        .padding(.horizontal, 14)
        .padding(.vertical, 11)
    }
}
