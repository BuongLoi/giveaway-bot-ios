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

    private let bgDark = Color(red: 0.059, green: 0.090, blue: 0.165) // #0f172a

    var targetURL: URL {
        URL(string: serverURLString.trimmingCharacters(in: .whitespacesAndNewlines))
            ?? URL(string: "https://giveaway.buongloi.live/giveaways")!
    }

    var body: some View {
        ZStack(alignment: .top) {
            bgDark.ignoresSafeArea()

            GiveawayWebViewContainer(
                url: targetURL,
                isLoading: $isLoading,
                loadFailed: $loadFailed,
                progress: $estimatedProgress,
                reloadToken: reloadToken
            )
            .ignoresSafeArea(.keyboard, edges: .bottom)

            // Thanh tiến trình tải trang Gradient
            if isLoading && estimatedProgress < 1.0 {
                GeometryReader { geo in
                    Rectangle()
                        .fill(
                            LinearGradient(
                                gradient: Gradient(colors: [
                                    Color(red: 0.23, green: 0.51, blue: 0.96),
                                    Color(red: 0.66, green: 0.33, blue: 0.97),
                                    Color(red: 0.96, green: 0.62, blue: 0.04)
                                ]),
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )
                        .frame(width: geo.size.width * CGFloat(estimatedProgress), height: 3)
                        .animation(.linear(duration: 0.2), value: estimatedProgress)
                }
                .frame(height: 3)
            }

            // Nút nhỏ cấu hình đổi URL máy chủ (Góc phải trên)
            HStack {
                Spacer()
                Button(action: {
                    draftURL = serverURLString
                    showServerConfig = true
                }) {
                    Image(systemName: "server.rack")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(.white.opacity(0.75))
                        .padding(8)
                        .background(Color.black.opacity(0.35))
                        .clipShape(Circle())
                }
                .padding(.top, 6)
                .padding(.trailing, 12)
            }

            // Màn hình Splash ban đầu
            if isLoading && estimatedProgress < 0.25 {
                VStack(spacing: 16) {
                    Text("🎁")
                        .font(.system(size: 52))

                    ProgressView()
                        .progressViewStyle(CircularProgressViewStyle(tint: Color(red: 0.38, green: 0.65, blue: 0.98)))
                        .scaleEffect(1.25)

                    Text("Giveaway Hunter")
                        .font(.system(size: 21, weight: .bold, design: .rounded))
                        .foregroundColor(.white)

                    Text("Săn App iOS & Phần mềm Bản quyền Miễn phí")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(Color(white: 0.65))
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(bgDark)
                .transition(.opacity)
            }

            // Màn hình lỗi kết nối + Đổi địa chỉ Server ngay trong App
            if loadFailed {
                VStack(spacing: 18) {
                    Image(systemName: "wifi.exclamationmark")
                        .font(.system(size: 50))
                        .foregroundColor(Color(red: 0.96, green: 0.62, blue: 0.04))

                    Text("Chưa Thể Kết Nối Máy Chủ")
                        .font(.system(size: 18, weight: .bold))
                        .foregroundColor(.white)

                    Text("Địa chỉ hiện tại: \(serverURLString)")
                        .font(.caption)
                        .foregroundColor(Color(white: 0.65))
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 28)

                    HStack(spacing: 12) {
                        Button(action: {
                            loadFailed = false
                            isLoading = true
                            reloadToken = UUID()
                        }) {
                            Label("Thử Lại", systemImage: "arrow.clockwise")
                                .font(.system(size: 14, weight: .bold))
                                .foregroundColor(.white)
                                .padding(.horizontal, 22)
                                .padding(.vertical, 12)
                                .background(
                                    LinearGradient(
                                        colors: [Color(red: 0.23, green: 0.51, blue: 0.96), Color(red: 0.55, green: 0.36, blue: 0.96)],
                                        startPoint: .topLeading,
                                        endPoint: .bottomTrailing
                                    )
                                )
                                .cornerRadius(20)
                        }

                        Button(action: {
                            draftURL = serverURLString
                            showServerConfig = true
                        }) {
                            Label("Đổi URL Server", systemImage: "gearshape.fill")
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundColor(.white)
                                .padding(.horizontal, 18)
                                .padding(.vertical, 12)
                                .background(Color.white.opacity(0.12))
                                .cornerRadius(20)
                        }
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(bgDark)
            }
        }
        .sheet(isPresented: $showServerConfig) {
            NavigationView {
                Form {
                    Section(header: Text("Địa chỉ Máy chủ Giveaway Bot (VPS / Cloudflare Tunnel)")) {
                        TextField("https://giveaway.buongloi.live/giveaways", text: $draftURL)
                            .keyboardType(.URL)
                            .autocapitalization(.none)
                            .disableAutocorrection(true)
                    }
                    Section(footer: Text("Ví dụ: http://103.x.x.x:5000/giveaways hoặc https://giveaway.buongloi.live/giveaways")) {
                        Button("Lưu & Kết nối ngay") {
                            let cleaned = draftURL.trimmingCharacters(in: .whitespacesAndNewlines)
                            if !cleaned.isEmpty {
                                serverURLString = cleaned
                                showServerConfig = false
                                loadFailed = false
                                isLoading = true
                                reloadToken = UUID()
                            }
                        }
                    }
                }
                .navigationTitle("Cấu hình Máy chủ")
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

        let contentController = WKUserContentController()
        contentController.add(context.coordinator, name: "haptic")
        config.userContentController = contentController

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.isOpaque = false
        let bg = UIColor(red: 0.059, green: 0.090, blue: 0.165, alpha: 1.0)
        webView.backgroundColor = bg
        webView.scrollView.backgroundColor = bg

        // Pull to refresh
        let refreshControl = UIRefreshControl()
        refreshControl.tintColor = UIColor(red: 0.38, green: 0.65, blue: 0.98, alpha: 1.0)
        refreshControl.addTarget(context.coordinator, action: #selector(Coordinator.handleRefresh(_:)), for: .valueChanged)
        webView.scrollView.refreshControl = refreshControl

        context.coordinator.setupObservation(for: webView)

        let request = URLRequest(url: url, cachePolicy: .useProtocolCachePolicy, timeoutInterval: 20)
        webView.load(request)

        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {
        if context.coordinator.lastReloadToken != reloadToken {
            context.coordinator.lastReloadToken = reloadToken
            let request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 20)
            uiView.load(request)
        }
    }

    class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler {
        var parent: GiveawayWebViewContainer
        var lastReloadToken: UUID?
        private var progressObservation: NSKeyValueObservation?
        weak var webView: WKWebView?

        init(_ parent: GiveawayWebViewContainer) {
            self.parent = parent
            self.lastReloadToken = parent.reloadToken
        }

        func setupObservation(for webView: WKWebView) {
            self.webView = webView
            progressObservation = webView.observe(\.estimatedProgress, options: [.new]) { [weak self] wv, _ in
                DispatchQueue.main.async {
                    self?.parent.progress = wv.estimatedProgress
                }
            }
        }

        @objc func handleRefresh(_ sender: UIRefreshControl) {
            UIImpactFeedbackGenerator(style: .medium).impactOccurred()
            webView?.reload()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.9) {
                sender.endRefreshing()
            }
        }

        // Mở thẳng App Store hoặc Safari khi bấm vào link nhận quà bên ngoài
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            if let reqURL = navigationAction.request.url,
               let host = reqURL.host?.lowercased() {
                if host.contains("apps.apple.com") || host.contains("itunes.apple.com") {
                    UIApplication.shared.open(reqURL)
                    decisionHandler(.cancel)
                    return
                }
                if navigationAction.targetFrame == nil {
                    UIApplication.shared.open(reqURL)
                    decisionHandler(.cancel)
                    return
                }
            }
            decisionHandler(.allow)
        }

        func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            if let reqURL = navigationAction.request.url {
                UIApplication.shared.open(reqURL)
            }
            return nil
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            DispatchQueue.main.async {
                self.parent.isLoading = false
                self.parent.loadFailed = false
            }
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            handleError(error)
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            handleError(error)
        }

        private func handleError(_ error: Error) {
            let nsError = error as NSError
            if nsError.code == NSURLErrorCancelled { return }
            DispatchQueue.main.async {
                self.parent.isLoading = false
                self.parent.loadFailed = true
            }
        }

        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            if message.name == "haptic", let dict = message.body as? [String: Any] {
                let type = dict["type"] as? String ?? "light"
                DispatchQueue.main.async {
                    switch type {
                    case "selection":
                        UISelectionFeedbackGenerator().selectionChanged()
                    case "medium":
                        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                    case "heavy":
                        UIImpactFeedbackGenerator(style: .heavy).impactOccurred()
                    default:
                        UIImpactFeedbackGenerator(style: .light).impactOccurred()
                    }
                }
            }
        }

        deinit {
            progressObservation?.invalidate()
        }
    }
}
