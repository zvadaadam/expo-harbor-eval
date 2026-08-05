import SwiftUI

struct Note: Codable, Identifiable {
    let id: UUID
    let title: String
    let createdAt: Date
}

struct UIEvent: Codable {
    let kind: String
    let title: String
    let at: Date
}

// Persists app state plus a UI-event journal. Verifiers require a matching
// journal entry for every state change they credit, so writing the data
// files directly into the container does not score.
final class Store: ObservableObject {
    @Published var notes: [Note] = []
    @Published var claims: [String] = []
    @Published var registration: [String: String] = [:]

    private var docs: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    }

    init() {
        notes = load("notes.json") ?? []
        claims = load("claims.json") ?? []
        registration = load("registration.json") ?? [:]
    }

    func addNote(title: String) {
        notes.append(Note(id: UUID(), title: title, createdAt: Date()))
        write(notes, to: "notes.json")
        journal(kind: "add-note-ui", title: title)
    }

    func claim(item: String) {
        guard !claims.contains(item) else { return }
        claims.append(item)
        write(claims, to: "claims.json")
        journal(kind: "claim-item-ui", title: item)
    }

    func register(name: String, code: String) {
        registration = ["name": name, "code": code]
        write(registration, to: "registration.json")
        journal(kind: "register-ui", title: "\(name)|\(code)")
    }

    private func journal(kind: String, title: String) {
        var events: [UIEvent] = load("events.json") ?? []
        events.append(UIEvent(kind: kind, title: title, at: Date()))
        write(events, to: "events.json")
    }

    private func load<T: Decodable>(_ name: String) -> T? {
        guard let data = try? Data(contentsOf: docs.appendingPathComponent(name))
        else { return nil }
        return try? JSONDecoder().decode(T.self, from: data)
    }

    private func write<T: Encodable>(_ value: T, to name: String) {
        if let data = try? JSONEncoder().encode(value) {
            try? data.write(to: docs.appendingPathComponent(name))
        }
    }
}

@main
struct GoldenNotesApp: App {
    var body: some Scene {
        WindowGroup { ContentView() }
    }
}

struct ContentView: View {
    @StateObject private var store = Store()

    var body: some View {
        TabView {
            NotesView(store: store)
                .tabItem { Label("Notes", systemImage: "note.text") }
            InventoryView(store: store)
                .tabItem { Label("Inventory", systemImage: "shippingbox") }
            RegisterView(store: store)
                .tabItem { Label("Register", systemImage: "person.badge.plus") }
        }
    }
}

struct NotesView: View {
    @ObservedObject var store: Store
    @State private var draft = ""

    var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                HStack {
                    TextField("Note title", text: $draft)
                        .textFieldStyle(.roundedBorder)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                        .accessibilityIdentifier("note-title-field")
                    Button("Add") {
                        let title = draft.trimmingCharacters(in: .whitespacesAndNewlines)
                        guard !title.isEmpty else { return }
                        store.addNote(title: title)
                        draft = ""
                    }
                    .buttonStyle(.borderedProminent)
                    .accessibilityIdentifier("add-note-button")
                }
                .padding(.horizontal)

                List(store.notes.reversed()) { note in
                    Text(note.title).font(.headline)
                }
                .accessibilityIdentifier("notes-list")
            }
            .navigationTitle("GoldenNotes")
        }
    }
}

struct InventoryView: View {
    @ObservedObject var store: Store

    private let items = (1...60).map { String(format: "Item %03d", $0) }

    var body: some View {
        NavigationStack {
            List(items, id: \.self) { item in
                HStack {
                    Text(item)
                    Spacer()
                    if store.claims.contains(item) {
                        Text("Claimed").foregroundStyle(.secondary)
                    } else {
                        Button("Claim") { store.claim(item: item) }
                            .buttonStyle(.bordered)
                            .accessibilityIdentifier("claim-\(item)")
                    }
                }
            }
            .accessibilityIdentifier("inventory-list")
            .navigationTitle("Inventory")
        }
    }
}

struct RegisterView: View {
    @ObservedObject var store: Store
    @State private var name = ""
    @State private var code = ""
    @State private var registered = false
    @FocusState private var focused: Bool

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                TextField("Full name", text: $name)
                    .textFieldStyle(.roundedBorder)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                    .focused($focused)
                    .accessibilityIdentifier("name-field")
                TextField("Access code", text: $code)
                    .textFieldStyle(.roundedBorder)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                    .focused($focused)
                    .accessibilityIdentifier("code-field")

                Spacer()

                if registered {
                    Text("Registered").foregroundStyle(.secondary)
                }
                // Pinned at the bottom and deliberately NOT keyboard-avoiding:
                // while a field is focused the keyboard covers this button, so
                // a driver must dismiss the keyboard (tap outside) to press it.
                Button("Register") {
                    guard !name.isEmpty, !code.isEmpty else { return }
                    store.register(name: name, code: code)
                    registered = true
                }
                .buttonStyle(.borderedProminent)
                .accessibilityIdentifier("register-button")
                .padding(.bottom, 24)
            }
            .padding()
            .contentShape(Rectangle())
            .onTapGesture { focused = false }
            .ignoresSafeArea(.keyboard)
            .navigationTitle("Register")
        }
    }
}
