import SwiftUI

struct UIEvent: Codable {
    let kind: String
    let title: String
    let at: Date
}

// Same journaling contract as GoldenNotes: every UI-driven mutation is
// recorded, and verifiers require the matching journal entry.
final class LabStore: ObservableObject {
    @Published var savedTemperature: Int? = nil
    @Published var revealedCode: String? = nil
    @Published var submittedCode: String? = nil
    @Published var tappedColors: [String] = []

    private var docs: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    }

    func saveTemperature(_ value: Int) {
        savedTemperature = value
        write(["temperature": value], to: "settings.json")
        journal(kind: "save-temperature-ui", title: String(value))
    }

    func codeRevealed(_ code: String) {
        revealedCode = code
        journal(kind: "code-revealed", title: code)
    }

    func revealRestarted() {
        journal(kind: "reveal-restarted", title: "")
    }

    func submitCode(_ code: String) {
        submittedCode = code
        write(["submitted": code], to: "submission.json")
        journal(kind: "code-submitted-ui", title: code)
    }

    func tappedSquare(color: String, row: Int, column: Int) {
        tappedColors.append(color)
        write(tappedColors, to: "grid-taps.json")
        journal(kind: "grid-tapped-ui", title: "\(color)@\(row),\(column)")
    }

    private func journal(kind: String, title: String) {
        var events: [UIEvent] = []
        if let data = try? Data(contentsOf: docs.appendingPathComponent("events.json")),
           let loaded = try? JSONDecoder().decode([UIEvent].self, from: data) {
            events = loaded
        }
        events.append(UIEvent(kind: kind, title: title, at: Date()))
        write(events, to: "events.json")
    }

    private func write<T: Encodable>(_ value: T, to name: String) {
        if let data = try? JSONEncoder().encode(value) {
            try? data.write(to: docs.appendingPathComponent(name))
        }
    }
}

@main
struct GoldenLabApp: App {
    var body: some Scene {
        WindowGroup { LabContentView() }
    }
}

struct LabContentView: View {
    @StateObject private var store = LabStore()

    var body: some View {
        TabView {
            DialView(store: store)
                .tabItem { Label("Dial", systemImage: "dial.medium") }
            RevealView(store: store)
                .tabItem { Label("Reveal", systemImage: "timer") }
            GridView(store: store)
                .tabItem { Label("Grid", systemImage: "square.grid.3x3") }
        }
    }
}

struct DialView: View {
    @ObservedObject var store: LabStore
    @State private var temperature: Double = 20

    var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                Text("\(Int(temperature))")
                    .font(.system(size: 56, weight: .semibold))
                    .accessibilityIdentifier("dial-value")
                HStack(spacing: 12) {
                    Button("−") { temperature = max(0, temperature - 1) }
                        .buttonStyle(.bordered)
                        .accessibilityIdentifier("dial-minus")
                    Slider(value: $temperature, in: 0...100, step: 1)
                        .accessibilityIdentifier("dial-slider")
                    Button("+") { temperature = min(100, temperature + 1) }
                        .buttonStyle(.bordered)
                        .accessibilityIdentifier("dial-plus")
                }
                .padding(.horizontal, 24)
                Button("Save temperature") {
                    store.saveTemperature(Int(temperature))
                }
                .buttonStyle(.borderedProminent)
                .accessibilityIdentifier("save-temperature-button")
                if let saved = store.savedTemperature {
                    Text("Saved: \(saved)").foregroundStyle(.secondary)
                }
                Spacer()
            }
            .padding(.top, 32)
            .navigationTitle("Dial")
        }
    }
}

struct RevealView: View {
    @ObservedObject var store: LabStore
    @State private var revealing = false
    @State private var code: String? = nil
    @State private var entry = ""
    @State private var attempt = 0

    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                // Tapping Reveal while the spinner runs restarts the wait —
                // impatience is journaled and costs another five seconds.
                Button(revealing ? "Revealing…" : "Reveal code") {
                    if revealing {
                        store.revealRestarted()
                    }
                    startReveal()
                }
                .buttonStyle(.borderedProminent)
                .accessibilityIdentifier("reveal-button")

                if revealing {
                    ProgressView().accessibilityIdentifier("reveal-spinner")
                }
                if let code {
                    Text(code)
                        .font(.system(.title, design: .monospaced))
                        .accessibilityIdentifier("revealed-code")
                }

                TextField("Enter code", text: $entry)
                    .textFieldStyle(.roundedBorder)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                    .padding(.horizontal, 24)
                    .accessibilityIdentifier("code-entry-field")
                Button("Submit code") {
                    store.submitCode(entry.trimmingCharacters(in: .whitespaces))
                }
                .buttonStyle(.bordered)
                .accessibilityIdentifier("submit-code-button")
                if store.submittedCode != nil {
                    Text("Submitted").foregroundStyle(.secondary)
                }
                Spacer()
            }
            .padding(.top, 32)
            .navigationTitle("Reveal")
        }
    }

    private func startReveal() {
        attempt += 1
        let current = attempt
        revealing = true
        code = nil
        DispatchQueue.main.asyncAfter(deadline: .now() + 5) {
            guard current == attempt else { return }
            let fresh = String(format: "KX-%04d", Int.random(in: 1000...9999))
            revealing = false
            code = fresh
            store.codeRevealed(fresh)
        }
    }
}

struct GridView: View {
    @ObservedObject var store: LabStore

    // Fixed arrangement; exactly one red cell (row 3, column 1, zero-based).
    // Cells are hidden from the accessibility tree — only pixels identify
    // them.
    private static let palette: [String: Color] = [
        "navy": Color(red: 0.16, green: 0.22, blue: 0.55),
        "teal": Color(red: 0.11, green: 0.55, blue: 0.55),
        "olive": Color(red: 0.45, green: 0.50, blue: 0.14),
        "plum": Color(red: 0.48, green: 0.19, blue: 0.46),
        "slate": Color(red: 0.35, green: 0.40, blue: 0.46),
        "red": Color(red: 0.86, green: 0.14, blue: 0.13),
    ]
    private static let layout: [[String]] = [
        ["navy", "teal", "olive", "plum", "slate"],
        ["olive", "slate", "navy", "teal", "plum"],
        ["teal", "plum", "slate", "olive", "navy"],
        ["slate", "red", "plum", "navy", "teal"],
        ["plum", "navy", "teal", "slate", "olive"],
    ]

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                Grid(horizontalSpacing: 8, verticalSpacing: 8) {
                    ForEach(0..<5, id: \.self) { row in
                        GridRow {
                            ForEach(0..<5, id: \.self) { column in
                                let name = Self.layout[row][column]
                                Rectangle()
                                    .fill(Self.palette[name] ?? .black)
                                    .frame(width: 58, height: 58)
                                    .cornerRadius(6)
                                    .onTapGesture {
                                        store.tappedSquare(
                                            color: name, row: row, column: column
                                        )
                                    }
                            }
                        }
                    }
                }
                .accessibilityElement(children: .ignore)
                .accessibilityIdentifier("grid-canvas")
                if let last = store.tappedColors.last {
                    Text("Tapped: \(last)").foregroundStyle(.secondary)
                }
                Spacer()
            }
            .padding(.top, 24)
            .navigationTitle("Grid")
        }
    }
}
