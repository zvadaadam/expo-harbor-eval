import AuthenticationServices
import CryptoKit
import Network
import SwiftUI
import WebKit

// GoldenGate: a fixed OAuth sign-in surface for the simulator-use benchmark.
//
// The app embeds its own identity provider ("HarborID") as a loopback HTTP
// server inside the process, so the flow needs no network and no external
// service, yet the driver-facing surfaces are the real ones apps ship with:
//   - system:   ASWebAuthenticationSession (what expo-web-browser's
//               openAuthSessionAsync / expo-auth-session use on iOS) — the
//               "Wants to Use ... to Sign In" consent alert, an out-of-process
//               web sheet, and an automatic return on the custom-scheme
//               callback;
//   - embedded: an in-app WKWebView sheet whose navigation delegate catches
//               the callback;
//   - browser:  a hand-off to Safari, with the callback arriving through the
//               registered URL scheme (onOpenURL) and Safari's "Open in
//               GoldenGate?" prompt in between.
// Every UI-driven step and every provider-side step lands in events.json,
// and the provider binds each authorization to a per-attempt state + PKCE
// challenge, so a callback that did not come out of the provider's own login
// and consent pages cannot complete a sign-in.

struct UIEvent: Codable {
    let kind: String
    let title: String
    let at: Date
}

struct Session: Codable {
    var username: String
    var displayName: String
    var accessToken: String
    var pairingCode: String
    var mode: String
}

/// Serial writer for the app container. Verifiers require matching journal
/// entries for every state change they credit, so writing the data files
/// directly into the container does not score.
final class Store {
    static let shared = Store()
    private let queue = DispatchQueue(label: "com.expo.simbench.goldengate.store")

    private var docs: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    }

    func journal(kind: String, title: String) {
        queue.sync {
            var events: [UIEvent] = loadLocked("events.json") ?? []
            events.append(UIEvent(kind: kind, title: title, at: Date()))
            writeLocked(events, to: "events.json")
        }
    }

    func write<T: Encodable>(_ value: T, to name: String) {
        queue.sync { writeLocked(value, to: name) }
    }

    func load<T: Decodable>(_ name: String) -> T? {
        queue.sync { loadLocked(name) }
    }

    private func loadLocked<T: Decodable>(_ name: String) -> T? {
        guard let data = try? Data(contentsOf: docs.appendingPathComponent(name)) else { return nil }
        return try? JSONDecoder().decode(T.self, from: data)
    }

    private func writeLocked<T: Encodable>(_ value: T, to name: String) {
        if let data = try? JSONEncoder().encode(value) {
            try? data.write(to: docs.appendingPathComponent(name))
        }
    }
}

// MARK: - Loopback identity provider

struct AuthorizationRecord: Codable {
    var state: String
    var codeChallenge: String
    var redirectURI: String
    var userAgent: String
    var loginAttempts: Int
    var username: String?
    var consent: String?
    var code: String?
    var accessToken: String?
    var pairingCode: String?
}

struct ProviderState: Codable {
    var port: Int
    var requests: [String: AuthorizationRecord]
}

struct HTTPRequest {
    let method: String
    let path: String
    let query: [String: String]
    let headers: [String: String]
    let body: Data

    var form: [String: String] {
        Provider.parseForm(String(decoding: body, as: UTF8.self))
    }
}

struct HTTPResponse {
    var status: Int
    var reason: String
    var headers: [String: String]
    var body: Data

    static func html(_ text: String) -> HTTPResponse {
        HTTPResponse(status: 200, reason: "OK",
                     headers: ["Content-Type": "text/html; charset=utf-8"], body: Data(text.utf8))
    }

    static func json(_ object: [String: Any]) -> HTTPResponse {
        let data = (try? JSONSerialization.data(withJSONObject: object)) ?? Data("{}".utf8)
        return HTTPResponse(status: 200, reason: "OK",
                            headers: ["Content-Type": "application/json"], body: data)
    }

    static func redirect(_ location: String) -> HTTPResponse {
        HTTPResponse(status: 302, reason: "Found", headers: ["Location": location], body: Data())
    }

    static func error(_ status: Int, _ message: String) -> HTTPResponse {
        HTTPResponse(status: status, reason: "Error",
                     headers: ["Content-Type": "application/json"],
                     body: Data("{\"error\":\"\(message)\"}".utf8))
    }

    func serialized() -> Data {
        var head = "HTTP/1.1 \(status) \(reason)\r\n"
        var all = headers
        all["Content-Length"] = String(body.count)
        all["Connection"] = "close"
        all["Cache-Control"] = "no-store"
        for (key, value) in all.sorted(by: { $0.key < $1.key }) {
            head += "\(key): \(value)\r\n"
        }
        head += "\r\n"
        return Data(head.utf8) + body
    }
}

final class Provider {
    static let clientID = "goldengate-ios"
    static let redirectURI = "goldengate://callback"
    static let users: [String: (accessCode: String, displayName: String)] = [
        "riley.chen": ("harbor-2026", "Riley Chen"),
        "ada.lovelace": ("engine-1843", "Ada Lovelace"),
        "grace.hopper": ("cobol-1959", "Grace Hopper"),
        "marina.silva": ("tide-4471", "Marina Silva"),
    ]
    /// Simulated identity-provider latency on the login POST.
    static let loginDelay: TimeInterval = 2

    private let queue = DispatchQueue(label: "com.expo.simbench.goldengate.provider")
    private var listener: NWListener?
    private var state: ProviderState
    private(set) var port: UInt16 = 0

    init() {
        state = Store.shared.load("provider.json") ?? ProviderState(port: 0, requests: [:])
    }

    var baseURL: URL { URL(string: "http://127.0.0.1:\(port)")! }

    func authorizeURL(state: String, challenge: String) -> URL {
        var components = URLComponents(url: baseURL.appendingPathComponent("authorize"),
                                       resolvingAgainstBaseURL: false)!
        components.queryItems = [
            URLQueryItem(name: "response_type", value: "code"),
            URLQueryItem(name: "client_id", value: Self.clientID),
            URLQueryItem(name: "redirect_uri", value: Self.redirectURI),
            URLQueryItem(name: "scope", value: "profile"),
            URLQueryItem(name: "state", value: state),
            URLQueryItem(name: "code_challenge", value: challenge),
            URLQueryItem(name: "code_challenge_method", value: "S256"),
        ]
        return components.url!
    }

    func start() {
        let parameters = NWParameters.tcp
        parameters.allowLocalEndpointReuse = true
        parameters.requiredLocalEndpoint = NWEndpoint.hostPort(host: "127.0.0.1", port: .any)
        guard let listener = try? NWListener(using: parameters) else { return }
        self.listener = listener
        listener.stateUpdateHandler = { [weak self] update in
            guard let self, case .ready = update, let port = listener.port?.rawValue else { return }
            self.port = port
            self.state.port = Int(port)
            self.persist()
        }
        listener.newConnectionHandler = { [weak self] connection in
            self?.accept(connection)
        }
        listener.start(queue: queue)
    }

    // MARK: HTTP plumbing

    private func accept(_ connection: NWConnection) {
        connection.start(queue: queue)
        receive(connection, buffer: Data())
    }

    private func receive(_ connection: NWConnection, buffer: Data) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, _, isComplete, error in
            guard let self else { return }
            var buffer = buffer
            if let data { buffer.append(data) }
            if let request = Self.parse(buffer) {
                self.route(request) { response in
                    connection.send(content: response.serialized(), completion: .contentProcessed { _ in
                        connection.cancel()
                    })
                }
                return
            }
            if isComplete || error != nil || buffer.count > 1_000_000 {
                connection.cancel()
                return
            }
            self.receive(connection, buffer: buffer)
        }
    }

    static func parse(_ data: Data) -> HTTPRequest? {
        guard let headerEnd = data.range(of: Data("\r\n\r\n".utf8)) else { return nil }
        let head = String(decoding: data[data.startIndex..<headerEnd.lowerBound], as: UTF8.self)
        var lines = head.components(separatedBy: "\r\n")
        let requestLine = lines.removeFirst().split(separator: " ")
        guard requestLine.count >= 2 else { return nil }
        var headers: [String: String] = [:]
        for line in lines {
            guard let colon = line.firstIndex(of: ":") else { continue }
            let key = line[..<colon].lowercased()
            headers[key] = line[line.index(after: colon)...].trimmingCharacters(in: .whitespaces)
        }
        let length = Int(headers["content-length"] ?? "0") ?? 0
        let body = data[headerEnd.upperBound...]
        guard body.count >= length else { return nil }
        let target = String(requestLine[1])
        let components = URLComponents(string: "http://127.0.0.1" + target)
        var query: [String: String] = [:]
        for item in components?.queryItems ?? [] {
            query[item.name] = item.value ?? ""
        }
        return HTTPRequest(method: String(requestLine[0]), path: components?.path ?? target,
                           query: query, headers: headers, body: Data(body.prefix(length)))
    }

    static func parseForm(_ text: String) -> [String: String] {
        var result: [String: String] = [:]
        for pair in text.split(separator: "&") {
            let parts = pair.split(separator: "=", maxSplits: 1).map(String.init)
            let key = decode(parts[0])
            result[key] = parts.count > 1 ? decode(parts[1]) : ""
        }
        return result
    }

    private static func decode(_ text: String) -> String {
        let spaced = text.replacingOccurrences(of: "+", with: " ")
        return spaced.removingPercentEncoding ?? spaced
    }

    static func random(_ length: Int) -> String {
        let alphabet = Array("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
        return String((0..<length).map { _ in alphabet.randomElement()! })
    }

    static func base64url(_ digest: SHA256Digest) -> String {
        Data(digest).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

    private func persist() {
        Store.shared.write(state, to: "provider.json")
    }

    // MARK: Routes

    private func route(_ request: HTTPRequest, completion: @escaping (HTTPResponse) -> Void) {
        switch (request.method, request.path) {
        case ("GET", "/authorize"):
            completion(authorize(request))
        case ("POST", "/login"):
            let response = login(request)
            queue.asyncAfter(deadline: .now() + Self.loginDelay) { completion(response) }
        case ("POST", "/consent"):
            completion(consent(request))
        case ("POST", "/token"):
            completion(token(request))
        case ("GET", "/userinfo"):
            completion(userinfo(request))
        case ("GET", "/health"):
            completion(.json(["ok": true]))
        default:
            completion(.error(404, "not_found"))
        }
    }

    private func authorize(_ request: HTTPRequest) -> HTTPResponse {
        let query = request.query
        guard query["client_id"] == Self.clientID, query["response_type"] == "code",
              let state = query["state"], !state.isEmpty,
              let challenge = query["code_challenge"], !challenge.isEmpty,
              query["code_challenge_method"] == "S256",
              query["redirect_uri"] == Self.redirectURI
        else {
            return .error(400, "invalid_request")
        }
        let id = Self.random(8)
        self.state.requests[id] = AuthorizationRecord(
            state: state, codeChallenge: challenge, redirectURI: Self.redirectURI,
            userAgent: request.headers["user-agent"] ?? "", loginAttempts: 0
        )
        persist()
        Store.shared.journal(kind: "provider-authorize", title: id)
        return .html(Self.loginPage(requestID: id, error: nil))
    }

    private func login(_ request: HTTPRequest) -> HTTPResponse {
        let form = request.form
        guard let id = form["request_id"], var record = state.requests[id] else {
            return .error(400, "unknown_request")
        }
        let username = (form["username"] ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let accessCode = form["access_code"] ?? ""
        record.loginAttempts += 1
        guard let user = Self.users[username], user.accessCode == accessCode else {
            state.requests[id] = record
            persist()
            Store.shared.journal(kind: "provider-login-rejected", title: "\(id)|\(username)")
            return .html(Self.loginPage(requestID: id, error: "Wrong username or access code. Try again."))
        }
        record.username = username
        state.requests[id] = record
        persist()
        Store.shared.journal(kind: "provider-login-accepted", title: "\(id)|\(username)")
        return .html(Self.consentPage(requestID: id, displayName: user.displayName))
    }

    private func consent(_ request: HTTPRequest) -> HTTPResponse {
        let form = request.form
        guard let id = form["request_id"], var record = state.requests[id],
              let username = record.username
        else {
            return .error(400, "unknown_request")
        }
        if form["action"] == "allow" {
            let code = Self.random(24)
            record.consent = "allow"
            record.code = code
            state.requests[id] = record
            persist()
            Store.shared.journal(kind: "provider-consent-granted", title: "\(id)|\(username)")
            return .redirect("\(record.redirectURI)?code=\(code)&state=\(record.state)")
        }
        record.consent = "deny"
        state.requests[id] = record
        persist()
        Store.shared.journal(kind: "provider-consent-denied", title: "\(id)|\(username)")
        return .redirect("\(record.redirectURI)?error=access_denied&state=\(record.state)")
    }

    private func token(_ request: HTTPRequest) -> HTTPResponse {
        let form = request.form
        guard form["grant_type"] == "authorization_code",
              let code = form["code"], let verifier = form["code_verifier"],
              let entry = state.requests.first(where: { $0.value.code == code }),
              let username = entry.value.username
        else {
            return .error(400, "invalid_grant")
        }
        var record = entry.value
        let challenge = Self.base64url(SHA256.hash(data: Data(verifier.utf8)))
        guard record.accessToken == nil, challenge == record.codeChallenge,
              form["redirect_uri"] == record.redirectURI, form["client_id"] == Self.clientID
        else {
            return .error(400, "invalid_grant")
        }
        record.accessToken = Self.random(40)
        record.pairingCode = String(format: "PAIR-%04d", Int.random(in: 1000...9999))
        state.requests[entry.key] = record
        persist()
        Store.shared.journal(kind: "provider-token-issued", title: "\(entry.key)|\(username)")
        return .json(["access_token": record.accessToken!, "token_type": "Bearer", "expires_in": 3600])
    }

    private func userinfo(_ request: HTTPRequest) -> HTTPResponse {
        let authorization = request.headers["authorization"] ?? ""
        guard authorization.hasPrefix("Bearer ") else { return .error(401, "invalid_token") }
        let token = String(authorization.dropFirst("Bearer ".count))
        guard let entry = state.requests.first(where: { $0.value.accessToken == token }),
              let username = entry.value.username, let user = Self.users[username],
              let pairingCode = entry.value.pairingCode
        else {
            return .error(401, "invalid_token")
        }
        Store.shared.journal(kind: "provider-userinfo", title: "\(entry.key)|\(username)")
        return .json(["username": username, "display_name": user.displayName,
                      "pairing_code": pairingCode])
    }

    // MARK: Pages

    private static let style = """
    <style>
    body{font-family:-apple-system,system-ui,sans-serif;margin:0;padding:24px;background:#f4f6fb;color:#0d1b2a}
    .brand{font-weight:700;color:#1f5fbf;letter-spacing:.02em}
    h1{font-size:22px;margin:16px 0}p{font-size:15px;line-height:1.4}
    label{display:block;font-size:14px;margin:14px 0 6px}
    input{width:100%;box-sizing:border-box;font-size:17px;padding:12px;border:1px solid #b8c2d1;border-radius:8px;background:#fff}
    button{width:100%;font-size:17px;padding:16px;margin-top:16px;border:0;border-radius:8px;background:#1f5fbf;color:#fff}
    button.secondary{background:#e4e8f0;color:#0d1b2a}
    .error{color:#b3261e;font-size:14px}
    </style>
    """

    // The credential is a plain "Access code" text field, not a password
    // field: Safari's password manager offers to save every submitted
    // password-like field (type="password" and CSS-masked inputs alike), which
    // would put an unrelated "Save Password?" prompt in front of the consent
    // page on every fresh simulator. The OAuth surfaces themselves are
    // unchanged.
    static func loginPage(requestID: String, error: String?) -> String {
        let alert = error.map { "<p class=\"error\" role=\"alert\" id=\"login-error\">\($0)</p>" } ?? ""
        return """
        <!doctype html><html lang="en"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>HarborID – Sign in</title>\(style)</head>
        <body><div class="brand">HarborID</div>
        <h1>Sign in to continue to GoldenGate</h1>\(alert)
        <form method="post" action="/login" autocomplete="off">
        <input type="hidden" name="request_id" value="\(requestID)">
        <label for="username">Username</label>
        <input id="username" name="username" type="text" autocapitalize="none" autocorrect="off" spellcheck="false" placeholder="Username">
        <label for="access-code">Access code</label>
        <input id="access-code" name="access_code" type="text" autocapitalize="none" autocorrect="off" spellcheck="false" placeholder="Access code">
        <button id="sign-in" type="submit">Sign in</button>
        </form></body></html>
        """
    }

    static func consentPage(requestID: String, displayName: String) -> String {
        """
        <!doctype html><html lang="en"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>HarborID – Allow access</title>\(style)</head>
        <body><div class="brand">HarborID</div>
        <h1>Allow GoldenGate to access your HarborID account?</h1>
        <p>You are signed in as <strong>\(displayName)</strong>. GoldenGate will be able to read your profile and your device pairing code.</p>
        <form method="post" action="/consent">
        <input type="hidden" name="request_id" value="\(requestID)">
        <button id="deny" class="secondary" type="submit" name="action" value="deny">Deny</button>
        <button id="allow" type="submit" name="action" value="allow">Allow</button>
        </form></body></html>
        """
    }
}

// MARK: - App-side OAuth client

struct EmbeddedLogin: Identifiable {
    let id = UUID()
    let url: URL
}

final class AuthCoordinator: NSObject, ObservableObject, ASWebAuthenticationPresentationContextProviding {
    @Published var session: Session?
    @Published var status = "Not signed in"
    @Published var embeddedLogin: EmbeddedLogin?

    let provider = Provider()
    private var pending: (state: String, verifier: String, mode: String)?
    private var webSession: ASWebAuthenticationSession?

    override init() {
        super.init()
        session = Store.shared.load("session.json")
        if session != nil { status = "Signed in" }
        provider.start()
    }

    func startSignIn(mode: String) {
        guard provider.port != 0 else {
            status = "HarborID is still starting; try again"
            return
        }
        let state = Provider.random(16)
        let verifier = Provider.random(48)
        let challenge = Provider.base64url(SHA256.hash(data: Data(verifier.utf8)))
        pending = (state, verifier, mode)
        status = "Waiting for HarborID…"
        Store.shared.journal(kind: "sign-in-started-ui", title: mode)
        let url = provider.authorizeURL(state: state, challenge: challenge)
        switch mode {
        case "system":
            let session = ASWebAuthenticationSession(url: url, callbackURLScheme: "goldengate") { [weak self] url, error in
                self?.finish(mode: mode, url: url, error: error)
            }
            session.presentationContextProvider = self
            session.prefersEphemeralWebBrowserSession = false
            webSession = session
            session.start()
        case "embedded":
            embeddedLogin = EmbeddedLogin(url: url)
        case "browser":
            UIApplication.shared.open(url)
        default:
            break
        }
    }

    /// Custom-scheme URLs delivered to the app (Safari hand-off). Only a
    /// pending browser-mode attempt accepts them; anything else is journaled
    /// and ignored, so an injected callback never completes a sign-in.
    func handleIncomingURL(_ url: URL) {
        guard let pending, pending.mode == "browser" else {
            Store.shared.journal(kind: "callback-ignored", title: url.absoluteString)
            return
        }
        finish(mode: "browser", url: url, error: nil)
    }

    func embeddedCallback(_ url: URL) {
        embeddedLogin = nil
        finish(mode: "embedded", url: url, error: nil)
    }

    func embeddedCancelled() {
        embeddedLogin = nil
        finish(mode: "embedded", url: nil,
               error: NSError(domain: "GoldenGate", code: 1,
                              userInfo: [NSLocalizedDescriptionKey: "cancelled"]))
    }

    func signOut() {
        guard let session else { return }
        Store.shared.journal(kind: "sign-out-ui", title: session.username)
        self.session = nil
        Store.shared.write([String: String](), to: "session.json")
        status = "Signed out"
    }

    func pair(code: String) {
        Store.shared.write(["code": code], to: "pairing.json")
        Store.shared.journal(kind: "pair-submitted-ui", title: code)
    }

    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        let windows = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .flatMap { $0.windows }
        return windows.first { $0.isKeyWindow } ?? windows.first ?? ASPresentationAnchor()
    }

    private func finish(mode: String, url: URL?, error: Error?) {
        DispatchQueue.main.async { self.finishOnMain(mode: mode, url: url, error: error) }
    }

    private func finishOnMain(mode: String, url: URL?, error: Error?) {
        guard let pending, pending.mode == mode else {
            Store.shared.journal(kind: "callback-ignored", title: "\(mode)|\(url?.absoluteString ?? "")")
            return
        }
        func fail(_ reason: String) {
            Store.shared.journal(kind: "callback-received", title: "\(mode)|error=\(reason)")
            status = "Sign-in failed: \(reason)"
            self.pending = nil
        }
        if let error {
            let cancelled = (error as? ASWebAuthenticationSessionError)?.code == .canceledLogin
                || error.localizedDescription == "cancelled"
            fail(cancelled ? "cancelled" : error.localizedDescription)
            return
        }
        guard let url, let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems else {
            fail("missing_callback")
            return
        }
        let params = Dictionary(items.map { ($0.name, $0.value ?? "") }, uniquingKeysWith: { first, _ in first })
        guard params["state"] == pending.state else {
            fail("state_mismatch")
            return
        }
        if let providerError = params["error"] {
            fail(providerError)
            return
        }
        guard let code = params["code"], !code.isEmpty else {
            fail("missing_code")
            return
        }
        Store.shared.journal(kind: "callback-received", title: "\(mode)|ok")
        status = "Exchanging code…"
        self.pending = nil
        exchange(code: code, verifier: pending.verifier, mode: mode)
    }

    private func exchange(code: String, verifier: String, mode: String) {
        var request = URLRequest(url: provider.baseURL.appendingPathComponent("token"))
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        let fields = [
            "grant_type": "authorization_code", "code": code, "code_verifier": verifier,
            "redirect_uri": Provider.redirectURI, "client_id": Provider.clientID,
        ]
        request.httpBody = Data(fields.map { key, value in
            "\(key)=\(value.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? value)"
        }.joined(separator: "&").utf8)
        URLSession.shared.dataTask(with: request) { [weak self] data, _, _ in
            guard let data,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let token = json["access_token"] as? String
            else {
                DispatchQueue.main.async {
                    Store.shared.journal(kind: "token-exchange-failed", title: mode)
                    self?.status = "Sign-in failed: token_exchange_failed"
                }
                return
            }
            self?.fetchUserInfo(token: token, mode: mode)
        }.resume()
    }

    private func fetchUserInfo(token: String, mode: String) {
        var request = URLRequest(url: provider.baseURL.appendingPathComponent("userinfo"))
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        URLSession.shared.dataTask(with: request) { [weak self] data, _, _ in
            guard let data,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let username = json["username"] as? String,
                  let displayName = json["display_name"] as? String,
                  let pairingCode = json["pairing_code"] as? String
            else {
                DispatchQueue.main.async {
                    Store.shared.journal(kind: "userinfo-failed", title: mode)
                    self?.status = "Sign-in failed: userinfo_failed"
                }
                return
            }
            let session = Session(username: username, displayName: displayName,
                                  accessToken: token, pairingCode: pairingCode, mode: mode)
            DispatchQueue.main.async {
                self?.session = session
                Store.shared.write(session, to: "session.json")
                Store.shared.journal(kind: "signed-in", title: "\(username)|\(mode)")
                self?.status = "Signed in"
            }
        }.resume()
    }
}

// MARK: - Views

@main
struct GoldenGateApp: App {
    @StateObject private var auth = AuthCoordinator()

    var body: some Scene {
        WindowGroup {
            GateContentView(auth: auth)
                .onOpenURL { url in auth.handleIncomingURL(url) }
        }
    }
}

struct GateContentView: View {
    @ObservedObject var auth: AuthCoordinator

    var body: some View {
        TabView {
            AccountView(auth: auth)
                .tabItem { Label("Account", systemImage: "person.crop.circle") }
            PairView(auth: auth)
                .tabItem { Label("Pair", systemImage: "link") }
        }
        .sheet(item: $auth.embeddedLogin) { login in
            EmbeddedLoginView(url: login.url,
                              onCallback: auth.embeddedCallback,
                              onCancel: auth.embeddedCancelled)
        }
    }
}

struct AccountView: View {
    @ObservedObject var auth: AuthCoordinator

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                Text(auth.status)
                    .foregroundStyle(.secondary)
                    .accessibilityIdentifier("auth-status")
                if let session = auth.session {
                    Text("Signed in as \(session.displayName)")
                        .font(.headline)
                        .accessibilityIdentifier("signed-in-user")
                    Text("Device pairing code")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(session.pairingCode)
                        .font(.system(.title, design: .monospaced))
                        .accessibilityIdentifier("pairing-code")
                    Button("Sign out") { auth.signOut() }
                        .buttonStyle(.bordered)
                        .accessibilityIdentifier("sign-out-button")
                } else {
                    Button("Continue with HarborID") { auth.startSignIn(mode: "system") }
                        .buttonStyle(.borderedProminent)
                        .accessibilityIdentifier("sign-in-system-button")
                    Button("Sign in inside the app") { auth.startSignIn(mode: "embedded") }
                        .buttonStyle(.bordered)
                        .accessibilityIdentifier("sign-in-embedded-button")
                    Button("Sign in with Safari") { auth.startSignIn(mode: "browser") }
                        .buttonStyle(.bordered)
                        .accessibilityIdentifier("sign-in-browser-button")
                }
                Spacer()
            }
            .padding()
            .padding(.top, 24)
            .navigationTitle("Account")
        }
    }
}

struct PairView: View {
    @ObservedObject var auth: AuthCoordinator
    @State private var code = ""
    @State private var submitted: String?

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                Text("Enter the device pairing code shown on your Account screen.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                TextField("Pairing code", text: $code)
                    .textFieldStyle(.roundedBorder)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.characters)
                    .accessibilityIdentifier("pairing-code-field")
                Button("Pair device") {
                    let trimmed = code.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !trimmed.isEmpty else { return }
                    auth.pair(code: trimmed)
                    submitted = trimmed
                }
                .buttonStyle(.borderedProminent)
                .accessibilityIdentifier("pair-button")
                if let submitted {
                    Text("Submitted \(submitted)")
                        .foregroundStyle(.secondary)
                        .accessibilityIdentifier("pair-result")
                }
                Spacer()
            }
            .padding()
            .padding(.top, 24)
            .navigationTitle("Pair")
        }
    }
}

struct EmbeddedLoginView: View {
    let url: URL
    let onCallback: (URL) -> Void
    let onCancel: () -> Void

    var body: some View {
        NavigationStack {
            WebView(url: url, onCallback: onCallback)
                .ignoresSafeArea(edges: .bottom)
                .navigationTitle("HarborID")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Cancel", action: onCancel)
                            .accessibilityIdentifier("embedded-cancel-button")
                    }
                }
        }
        .interactiveDismissDisabled()
    }
}

struct WebView: UIViewRepresentable {
    let url: URL
    let onCallback: (URL) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(onCallback: onCallback) }

    func makeUIView(context: Context) -> WKWebView {
        let view = WKWebView()
        view.navigationDelegate = context.coordinator
        view.accessibilityIdentifier = "embedded-web-view"
        view.load(URLRequest(url: url))
        return view
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKNavigationDelegate {
        let onCallback: (URL) -> Void

        init(onCallback: @escaping (URL) -> Void) { self.onCallback = onCallback }

        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            if let url = navigationAction.request.url, url.scheme == "goldengate" {
                decisionHandler(.cancel)
                onCallback(url)
                return
            }
            decisionHandler(.allow)
        }
    }
}
