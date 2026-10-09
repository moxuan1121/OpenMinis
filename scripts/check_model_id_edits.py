"""Run the actual model update/reference-remapping code with in-memory persistence."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
store = (root / "src/ios/Providers/ProviderConfigStore.swift").read_text(encoding="utf-8")
update = re.search(r"    @discardableResult\n    func updateEntry\(.*?\n    }", store, re.S).group()
normalize = re.search(r"    @discardableResult\n    func normalizeReferences\(.*?\n    }", store, re.S).group()
ui = (root / "src/ios/Views/Providers/ProviderInstanceDetailView.swift").read_text(encoding="utf-8")
assert "store.updateEntry(updatedEntry, replacing: entry.id)" in ui
source = '''import Foundation
struct Log { func info(_ text: String) {} }
let logger = Log()
struct ModelEntry: Codable, Equatable {
    let uuid: String
    let providerInstanceId: String
    var modelId: String
    var displayName: String
    var userModifiedAt: Date?
    var id: String { "\\(providerInstanceId)/\\(modelId)" }
}
struct Group: Codable, Equatable {
    var memberEntryIds: [String]
    var addedMembers: [String: Date]
    var removedMembers: [String: Date]
}
enum SessionModelSource: Codable, Equatable {
    case directEntry(modelEntryId: String, compositeKey: String?)
    case group(groupId: String, resolvedEntryId: String)
}
struct Binding: Codable, Equatable {
    var primarySource: SessionModelSource
    var subModelSource: SessionModelSource?
}
struct Tombstone: Codable, Equatable { let id: String }
struct Config: Codable, Equatable {
    var modelEntries: [ModelEntry]
    var modelGroups: [Group]
    var agentLoopModelEntryIds: [String]
    var sessionBindings: [String: Binding]
    var deletedModelEntries: [Tombstone] = []
}
actor ChatStore {
    static let shared = ChatStore()
    func markDirty(recordType: String, recordId: String, operation: String) {}
}
final class Store {
    var config: Config
    var legacyUuidToCompositeKey: [String: String] = [:]
    var saved = Data()
    var writes = 0
    init(_ config: Config) { self.config = config }
    func save() { saved = try! JSONEncoder().encode(config); writes += 1 }
    func persistLegacyUuidMap() {}
    static func recordTombstone(in records: inout [Tombstone], ids: [String]) {
        records += ids.map { Tombstone(id: $0) }
    }
''' + update + '\n' + normalize + '''
}
let original = ModelEntry(uuid: "stable-uuid", providerInstanceId: "provider", modelId: "model-a", displayName: "My model")
let other = ModelEntry(uuid: "other-uuid", providerInstanceId: "provider", modelId: "existing", displayName: "Other")
let config = Config(modelEntries: [original, other],
    modelGroups: [Group(memberEntryIds: [original.id], addedMembers: [original.id: Date()], removedMembers: [:])],
    agentLoopModelEntryIds: [original.id],
    sessionBindings: ["chat": Binding(primarySource: .directEntry(modelEntryId: original.uuid, compositeKey: original.id),
        subModelSource: .group(groupId: "group", resolvedEntryId: original.id))])
let s = Store(config)
var current = original
for id in ["model-b", "model-c"] {
    var edited = current
    edited.modelId = id
    edited.displayName = "Edited \\(id)"
    precondition(s.updateEntry(edited, replacing: current.id), "Rename was silently ignored")
    let reloaded = try! JSONDecoder().decode(Config.self, from: s.saved)
    precondition(reloaded.modelEntries[0].modelId == id)
    precondition(reloaded.modelEntries[0].displayName == edited.displayName)
    precondition(reloaded.modelEntries[0].uuid == original.uuid)
    precondition(reloaded.modelGroups[0].memberEntryIds == [edited.id])
    precondition(reloaded.modelGroups[0].addedMembers[edited.id] != nil)
    precondition(reloaded.agentLoopModelEntryIds == [edited.id])
    precondition(reloaded.sessionBindings["chat"]?.primarySource == .directEntry(modelEntryId: original.uuid, compositeKey: edited.id))
    precondition(reloaded.sessionBindings["chat"]?.subModelSource == .group(groupId: "group", resolvedEntryId: edited.id))
    precondition(s.legacyUuidToCompositeKey[original.uuid] == edited.id)
    precondition(s.legacyUuidToCompositeKey[original.id] == edited.id)
    current = edited
}
let before = s.config
let writes = s.writes
var duplicate = current
duplicate.modelId = other.modelId
precondition(!s.updateEntry(duplicate, replacing: current.id), "Duplicate overwrote another model")
precondition(s.config == before && s.writes == writes)
precondition(!s.updateEntry(current, replacing: "removed-model"))
current.displayName = "Name-only edit"
precondition(s.updateEntry(current))
precondition(s.config.modelEntries[0].displayName == "Name-only edit")
precondition(s.config.deletedModelEntries.map(\\.id) == [original.id, "provider/model-b"])
print("PASS: repeated model ID saves, persisted references, duplicate/missing rejection and name-only edits")
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "check.swift"
    path.write_text(source, encoding="utf-8")
    subprocess.run(["swift", str(path)], check=True)
