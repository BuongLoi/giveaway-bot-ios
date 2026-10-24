import SwiftUI
import WebKit
import UIKit

struct ContentView: View {
    @AppStorage("giveaway_server_url") private var serverURLString: String = "https://giveaway.buongloi.live/giveaways"
    @State private var isLoading = true
    @State private var loadFailed = false
    @State private var reloadToken = UUID()
    @State private var estimatedProgress: Double = 0.0
    @State private var showServerConfig = false
    @State private var draftURL: String = ""

    private let bgDark = Color(red: 0.059, green: 0.090, blue: 0.165)     // #0f172a
    private let blueAccent = Color(red: 0.231, green: 0.510, blue: 0.965) // #3b82f6
    private let purpleAccent = Color(red: 0.659, green: 0.333, blue: 0.969) // #a855f7

    var targetURL: URL {
        let cleaned = serverURLString.trimmingCharacters(in: .whitespacesAndNewlines)
        return URL(string: cleaned) ?? URL(string: "https://giveaway.buongloi.live/giveaways")!
    }

    var body: some View {
        ZStack(alignment: .top) {
            bgDark
                .ignoresSafeArea(.all)

            GiveawayWebViewContainer(
                url: targetURL,
                isLoading: $isLoading,
                loadFailed: $loadFailed,
                progress: $estimatedProgress,
                reloadToken: reloadToken
            )
            .ignoresSafeArea(.keyboard, edges: .bottom)

            // Top loading progress bar
            if isLoading && estimatedProgress < 1.0 {
                GeometryReader { geo in
                    Rectangle()
                        .fill(
                            LinearGradient(
                                gradient: Gradient(colors: [blueAccent, purpleAccent]),
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )
                        .frame(width: geo.size.width * CGFloat(estimatedProgress), height: 3)
                        .animation(.linear(duration: 0.2), value: estimatedProgress)
                }
                .frame(height: 3)
            }

            // Initial Splash Screen
            if isLoading && estimatedProgress < 0.28 {
                VStack(spacing: 16) {
                    ZStack {
                        RoundedRectangle(cornerRadius: 20, style: .continuous)
                            .fill(
                                LinearGradient(
                                    colors: [blueAccent, purpleAccent],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                )
                            )
                            .frame(width: 68, height: 68)
                            .shadow(color: blueAccent.opacity(0.35), radius: 14, x: 0, y: 6)

                        Text("🎁")
                            .font(.system(size: 34))
                    }

                    Text("Giveaway Hunter")
                        .font(.system(size: 20, weight: .bold, design: .rounded))
                        .foregroundColor(.white)

                    Text("iOS Freebies • Windows License • Deals")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(Color(white: 0.62))

                    ProgressView()
                        .progressViewStyle(CircularProgressViewStyle(tint: blueAccent))
                        .scaleEffect(1.2)
                        .padding(.top, 6)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(bgDark)
                .ignoresSafeArea(.all)
                .transition(.opacity)
            }

            // Offline / Connection Error View
            if loadFailed {
                VStack(spacing: 20) {
                    Image(systemName: "wifi.exclamationmark")
                        .font(.system(size: 52))
                        .foregroundColor(blueAccent)

                    Text("Không thể kết nối máy chủ")
                        .font(.system(size: 18, weight: .bold, design: .rounded))
                        .foregroundColor(.white)

                    Text("Vui lòng kiểm tra lại kết nối Internet hoặc trạng thái máy chủ giveaway.buongloi.live.")
                        .font(.subheadline)
                        .foregroundColor(Color(white: 0.68))
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 32)

                    HStack(spacing: 12) {
                        Button(action: {
                            let impact = UIImpactFeedbackGenerator(style: .medium)
                            impact.impactOccurred()
                            loadFailed = false
                            isLoading = true
                            reloadToken = UUID()
                        }) {
                            Label("Thử lại ngay", systemImage: "arrow.clockwise")
                                .font(.system(size: 15, weight: .bold))
                                .foregroundColor(.white)
                                .padding(.horizontal, 24)
                                .padding(.vertical, 12)
                                .background(
                                    LinearGradient(
                                        colors: [blueAccent, purpleAccent],
                                        startPoint: .topLeading,
                                        endPoint: .bottomTrailing
                                    )
                                )
                                .cornerRadius(24)
                        }

                        Button(action: {
                            draftURL = serverURLString
                            showServerConfig = true
                        }) {
                            Label("Đổi URL", systemImage: "gearshape.fill")
                                .font(.system(size: 15, weight: .semibold))
                                .foregroundColor(.white)
                                .padding(.horizontal, 18)
                                .padding(.vertical, 12)
                                .background(Color.white.opacity(0.12))
                                .cornerRadius(24)
                        }
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(bgDark)
                .ignoresSafeArea(.all)
                .transition(.opacity)
            }
        }
        .animation(.easeInOut(duration: 0.25), value: isLoading)
        .sheet(isPresented: $showServerConfig) {
            NavigationView {
                Form {
                    Section(header: Text("Địa chỉ Máy chủ Giveaway Bot")) {
                        TextField("https://giveaway.buongloi.live/giveaways", text: $draftURL)
                            .keyboardType(.URL)
                            .autocapitalization(.none)
                            .disableAutocorrection(true)
                    }
                    Section {
                        Button("Lưu & Kết nối lại") {
                            let cleaned = draftURL.trimmingCharacters(in: .whitespacesAndNewlines)
                            if !cleaned.isEmpty {
                                serverURLString = cleaned
                                showServerConfig = false
                                loadFailed = false
                                isLoading = true
                                reloadToken = UUID()
                            }
                        }
                        Button("Khôi phục mặc định (giveaway.buongloi.live)") {
                            serverURLString = "https://giveaway.buongloi.live/giveaways"
                            showServerConfig = false
                            loadFailed = false
                            isLoading = true
                            reloadToken = UUID()
                        }
                    }
                }
                .navigationTitle("Cài đặt Máy chủ")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Đóng") { showServerConfig = false }
                    }
                }
            }
            .preferredColorScheme(.dark)
        }
    }
}

// MARK: - WKWebView Wrapper
struct GiveawayWebViewContainer: UIViewRepresentable {
    let url: URL
    @Binding var isLoading: Bool
    @Binding var loadFailed: Bool
    @Binding var progress: Double
    let reloadToken: UUID

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.allowsInlineMediaPlayback = true
        config.defaultWebpagePreferences.allowsContentJavaScript = true
        config.websiteDataStore = WKWebsiteDataStore.default()
        config.applicationNameForUserAgent = "GiveawayHunterApp/2.1 (iOS)"

        let userContentController = WKUserContentController()
        userContentController.add(context.coordinator, name: "haptic")
        config.userContentController = userContentController

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = true
        webView.scrollView.bounces = true

        let darkColor = UIColor(red: 0.059, green: 0.090, blue: 0.165, alpha: 1.0)
        webView.backgroundColor = darkColor
        webView.isOpaque = false
        webView.scrollView.backgroundColor = darkColor
        webView.scrollView.contentInsetAdjustmentBehavior = .always

        // Pull-to-Refresh
        let refreshControl = UIRefreshControl()
        refreshControl.tintColor = UIColor(red: 0.231, green: 0.510, blue: 0.965, alpha: 0.95)
        refreshControl.addTarget(context.coordinator, action: #selector(Coordinator.handleRefresh(_:)), for: .valueChanged)
        webView.scrollView.refreshControl = refreshControl

        // Observe loading progress
        context.coordinator.observation = webView.observe(\.estimatedProgress, options: [.new]) { wv, _ in
            DispatchQueue.main.async {
                self.progress = wv.estimatedProgress
            }
        }

        context.coordinator.webView = webView
        let request = URLRequest(url: url, cachePolicy: .useProtocolCachePolicy, timeoutInterval: 25)
        webView.load(request)
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        if context.coordinator.lastReloadToken != reloadToken {
            context.coordinator.lastReloadToken = reloadToken
            let request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 25)
            webView.load(request)
        }
    }

    class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler {
        var parent: GiveawayWebViewContainer
        weak var webView: WKWebView?
        var observation: NSKeyValueObservation?
        var lastReloadToken: UUID?

        init(_ parent: GiveawayWebViewContainer) {
            self.parent = parent
            self.lastReloadToken = parent.reloadToken
        }

        deinit {
            observation?.invalidate()
        }

        @objc func handleRefresh(_ sender: UIRefreshControl) {
            let impact = UIImpactFeedbackGenerator(style: .light)
            impact.impactOccurred()
            webView?.reload()
        }

        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            if message.name == "haptic" {
                let impact = UIImpactFeedbackGenerator(style: .light)
                impact.impactOccurred()
            }
        }

        func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
            DispatchQueue.main.async {
                self.parent.isLoading = true
                self.parent.loadFailed = false
            }
        }

        func webView(_ webView: WKWebView, didCommit navigation: WKNavigation!) {
            DispatchQueue.main.async {
                self.parent.isLoading = false
                self.parent.loadFailed = false
            }
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            DispatchQueue.main.async {
                self.parent.isLoading = false
                self.parent.loadFailed = false
                webView.scrollView.refreshControl?.endRefreshing()
            }
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            let nsError = error as NSError
            if nsError.code == NSURLErrorCancelled || (nsError.domain == "WebKitErrorDomain" && nsError.code == 102) {
                return
            }
            DispatchQueue.main.async {
                self.parent.isLoading = false
                webView.scrollView.refreshControl?.endRefreshing()
            }
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            let nsError = error as NSError
            if nsError.code == NSURLErrorCancelled || (nsError.domain == "WebKitErrorDomain" && nsError.code == 102) {
                return
            }
            DispatchQueue.main.async {
                self.parent.isLoading = false
                self.parent.loadFailed = true
                webView.scrollView.refreshControl?.endRefreshing()
            }
        }

        func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
            webView.reload()
        }

        // Mở các link target="_blank" (App Store, trang nhận bản quyền ngoài) bằng Safari / App Store của iOS
        func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            guard let targetURL = navigationAction.request.url else { return nil }
            if let host = targetURL.host?.lowercased(), host.contains("buongloi.live") {
                webView.load(navigationAction.request)
            } else {
                UIApplication.shared.open(targetURL, options: [:], completionHandler: nil)
            }
            return nil
        }
    }
}
