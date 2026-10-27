import Foundation

enum APIError: LocalizedError {
    case badURL, badStatus(Int), decoding(String), network(String)

    var errorDescription: String? {
        switch self {
        case .badURL: return "Địa chỉ máy chủ không hợp lệ."
        case .badStatus(let code): return "Máy chủ trả về lỗi \(code)."
        case .decoding(let msg): return "Dữ liệu không hợp lệ: \(msg)"
        case .network(let msg): return "Không kết nối được máy chủ: \(msg)"
        }
    }
}

struct APIClient {
    static let defaultServer = "https://giveaway.buongloi.live"

    static var serverURL: String {
        let saved = UserDefaults.standard.string(forKey: "serverURL")?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return saved.isEmpty ? defaultServer : saved
    }

    private static let session: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 20
        config.timeoutIntervalForResource = 40
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        config.waitsForConnectivity = false
        return URLSession(configuration: config)
    }()

    private static func makeURL(_ path: String, _ query: [String: String]) throws -> URL {
        let base = serverURL.hasSuffix("/") ? String(serverURL.dropLast()) : serverURL
        guard var comps = URLComponents(string: base + path) else { throw APIError.badURL }
        comps.queryItems = query.filter { !$0.value.isEmpty }.map { URLQueryItem(name: $0.key, value: $0.value) }
        guard let url = comps.url else { throw APIError.badURL }
        return url
    }

    private static func get<T: Decodable>(_ path: String, _ query: [String: String] = [:]) async throws -> T {
        let url = try makeURL(path, query)
        var request = URLRequest(url: url)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("GiveawayHunter-iOS/3.0", forHTTPHeaderField: "User-Agent")
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.network(error.localizedDescription)
        }
        if let http = response as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
            throw APIError.badStatus(http.statusCode)
        }
        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw APIError.decoding(error.localizedDescription)
        }
    }

    static func giveaways(platform: Platform = .all, status: String = "active", sort: SortOption = .new,
                          query: String = "", page: Int = 1, perPage: Int = 40, since: String = "") async throws -> GiveawayPage {
        try await get("/api/v2/giveaways", [
            "platform": platform == .all ? "" : platform.rawValue,
            "status": status,
            "sort": sort.rawValue,
            "q": query,
            "page": String(page),
            "per_page": String(perPage),
            "since": since,
        ])
    }

    static func giveaways(ids: [Int]) async throws -> [Giveaway] {
        guard !ids.isEmpty else { return [] }
        let page: GiveawayPage = try await get("/api/v2/giveaways", [
            "ids": ids.prefix(200).map(String.init).joined(separator: ","),
            "per_page": "100",
        ])
        return page.items
    }

    static func stats() async throws -> Stats {
        try await get("/api/v2/stats")
    }

    static func triggerScan() async -> String {
        guard let url = try? makeURL("/action/scan", [:]) else { return "URL không hợp lệ" }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("XMLHttpRequest", forHTTPHeaderField: "X-Requested-With")
        do {
            let (data, _) = try await session.data(for: request)
            if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let msg = obj["message"] as? String {
                return msg
            }
            return "Đã gửi yêu cầu quét."
        } catch {
            return "Không gửi được yêu cầu quét: \(error.localizedDescription)"
        }
    }
}

// MARK: - Cache offline

enum DiskCache {
    private static var dir: URL {
        FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
    }

    static func save<T: Encodable>(_ value: T, as name: String) {
        guard let data = try? JSONEncoder().encode(value) else { return }
        try? data.write(to: dir.appendingPathComponent(name), options: .atomic)
    }

    static func load<T: Decodable>(_ type: T.Type, from name: String) -> T? {
        guard let data = try? Data(contentsOf: dir.appendingPathComponent(name)) else { return nil }
        return try? JSONDecoder().decode(type, from: data)
    }
}
