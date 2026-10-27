import Foundation
import SwiftUI

// MARK: - Nền tảng

enum Platform: String, CaseIterable, Identifiable, Codable {
    case all, ios, windows, macos, game, android, other

    var id: String { rawValue }

    var title: String {
        switch self {
        case .all: return "Tất cả"
        case .ios: return "iOS"
        case .windows: return "Windows"
        case .macos: return "macOS"
        case .game: return "Game"
        case .android: return "Android"
        case .other: return "Khác"
        }
    }

    var icon: String {
        switch self {
        case .all: return "square.grid.2x2.fill"
        case .ios: return "iphone"
        case .windows: return "pc"
        case .macos: return "laptopcomputer"
        case .game: return "gamecontroller.fill"
        case .android: return "candybarphone"
        case .other: return "shippingbox.fill"
        }
    }

    var color: Color {
        switch self {
        case .all: return .indigo
        case .ios: return .blue
        case .windows: return .cyan
        case .macos: return .gray
        case .game: return .purple
        case .android: return .green
        case .other: return .orange
        }
    }

    static var notifiable: [Platform] { [.ios, .windows, .macos, .game, .android, .other] }
}

enum SortOption: String, CaseIterable, Identifiable {
    case new, ending, worth
    var id: String { rawValue }
    var title: String {
        switch self {
        case .new: return "Mới nhất"
        case .ending: return "Sắp hết hạn"
        case .worth: return "Giá trị cao"
        }
    }
    var icon: String {
        switch self {
        case .new: return "clock.arrow.circlepath"
        case .ending: return "hourglass"
        case .worth: return "dollarsign.circle"
        }
    }
}

// MARK: - Giveaway

struct Giveaway: Identifiable, Codable, Hashable {
    let id: Int
    let title: String
    let source: String
    let url: String
    let claimUrl: String
    let platform: String
    let imageUrl: String
    let worth: String
    let worthValue: Double
    let expiresAt: String?
    let startsAt: String?
    let status: String
    let codes: [String]
    let tags: [String]
    let description: String
    let rating: Double
    let store: String
    let appId: String
    let confidence: Int
    let firstSeenAt: String

    enum CodingKeys: String, CodingKey {
        case id, title, source, url, platform, worth, status, codes, tags, description, rating, store, confidence
        case claimUrl = "claim_url"
        case imageUrl = "image_url"
        case worthValue = "worth_value"
        case expiresAt = "expires_at"
        case startsAt = "starts_at"
        case appId = "app_id"
        case firstSeenAt = "first_seen_at"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(Int.self, forKey: .id)
        title = (try? c.decode(String.self, forKey: .title)) ?? ""
        source = (try? c.decode(String.self, forKey: .source)) ?? ""
        url = (try? c.decode(String.self, forKey: .url)) ?? ""
        claimUrl = (try? c.decode(String.self, forKey: .claimUrl)) ?? url
        platform = (try? c.decode(String.self, forKey: .platform)) ?? "other"
        imageUrl = (try? c.decode(String.self, forKey: .imageUrl)) ?? ""
        worth = (try? c.decode(String.self, forKey: .worth)) ?? ""
        worthValue = (try? c.decode(Double.self, forKey: .worthValue)) ?? 0
        expiresAt = try? c.decodeIfPresent(String.self, forKey: .expiresAt)
        startsAt = try? c.decodeIfPresent(String.self, forKey: .startsAt)
        status = (try? c.decode(String.self, forKey: .status)) ?? "active"
        codes = (try? c.decode([String].self, forKey: .codes)) ?? []
        tags = (try? c.decode([String].self, forKey: .tags)) ?? []
        description = (try? c.decode(String.self, forKey: .description)) ?? ""
        rating = (try? c.decode(Double.self, forKey: .rating)) ?? 0
        store = (try? c.decode(String.self, forKey: .store)) ?? ""
        appId = (try? c.decode(String.self, forKey: .appId)) ?? ""
        confidence = (try? c.decode(Int.self, forKey: .confidence)) ?? 0
        firstSeenAt = (try? c.decode(String.self, forKey: .firstSeenAt)) ?? ""
    }

    var platformEnum: Platform { Platform(rawValue: platform) ?? .other }
    var expiryDate: Date? { DateParser.parse(expiresAt) }
    var startDate: Date? { DateParser.parse(startsAt) }
    var firstSeenDate: Date? { DateParser.parse(firstSeenAt) }
    var isUpcoming: Bool { status == "upcoming" }
    var isExpired: Bool {
        if status == "expired" { return true }
        if let d = expiryDate { return d < Date() }
        return false
    }
    var imageURL: URL? { imageUrl.isEmpty ? nil : URL(string: imageUrl) }
    var claimURL: URL? { URL(string: claimUrl.isEmpty ? url : claimUrl) }
    var postURL: URL? { URL(string: url) }

    var storeLabel: String {
        switch store {
        case "appstore": return "App Store"
        case "steam": return "Steam"
        case "epic": return "Epic Games"
        case "gog": return "GOG"
        case "googleplay": return "Google Play"
        case "itch": return "itch.io"
        case "prime": return "Prime Gaming"
        case "ubisoft": return "Ubisoft"
        case "indiegala": return "IndieGala"
        case "microsoft": return "Microsoft Store"
        case "": return source
        default: return store.capitalized
        }
    }

    var cleanTitle: String {
        var t = title
        for pattern in ["\\s*\\(?(Epic Games|Steam|GOG|IndieGala|itch\\.io)\\)?\\s*Giveaway$", "\\s*Giveaway$"] {
            t = t.replacingOccurrences(of: pattern, with: "", options: [.regularExpression, .caseInsensitive])
        }
        return t.trimmingCharacters(in: .whitespaces)
    }
}

struct GiveawayPage: Codable {
    let status: String
    let page: Int
    let total: Int
    let hasMore: Bool
    let items: [Giveaway]
    let serverTime: String?

    enum CodingKeys: String, CodingKey {
        case status, page, total, items
        case hasMore = "has_more"
        case serverTime = "server_time"
    }
}

struct Stats: Codable {
    let platforms: [String: Int]
    let activeTotal: Int
    let totalWorth: Double
    let endingSoon: Int
    let upcoming: Int
    let lastScanAt: String?

    enum CodingKeys: String, CodingKey {
        case platforms
        case activeTotal = "active_total"
        case totalWorth = "total_worth"
        case endingSoon = "ending_soon"
        case upcoming
        case lastScanAt = "last_scan_at"
    }
}

// MARK: - Ngày giờ

enum DateParser {
    private static let iso: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()
    private static let isoFrac: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    static func parse(_ s: String?) -> Date? {
        guard let s = s, !s.isEmpty else { return nil }
        return iso.date(from: s) ?? isoFrac.date(from: s)
    }

    static func string(_ d: Date) -> String { iso.string(from: d) }
}

enum Countdown {
    static func text(until date: Date, now: Date = Date()) -> String {
        let secs = Int(date.timeIntervalSince(now))
        if secs <= 0 { return "Đã hết hạn" }
        let d = secs / 86400, h = (secs % 86400) / 3600, m = (secs % 3600) / 60, s = secs % 60
        if d > 0 { return "\(d)n \(h)g" }
        if h > 0 { return "\(h)g \(m)p" }
        return String(format: "%02d:%02d", m, s)
    }

    static func isUrgent(_ date: Date?) -> Bool {
        guard let date = date else { return false }
        return date.timeIntervalSinceNow < 24 * 3600
    }
}

enum RelativeTime {
    private static let formatter: RelativeDateTimeFormatter = {
        let f = RelativeDateTimeFormatter()
        f.locale = Locale(identifier: "vi_VN")
        f.unitsStyle = .short
        return f
    }()
    static func text(_ date: Date?) -> String {
        guard let date = date else { return "" }
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}
