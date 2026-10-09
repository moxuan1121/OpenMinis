import Foundation

/// Reads and writes PendingShare data to the App Group shared container.
/// Compiled into both the main app target and the Share Extension target.
enum SharedContainerStore {
    static let appGroupID = "group.com.openminis.app"

    /// Main-app storage remains usable when a signing tool omits App Groups.
    /// Cross-process transfers still require the real shared container below.
    static let appStorageContainer: URL = {
        if let container = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroupID) {
            return container
        }
        NSLog("[AppGroup] Shared container unavailable; using persistent app-local storage")
        return FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("MinisLocalContainer", isDirectory: true)
    }()

    private static let pendingShareKey = "pendingShare"

    static var sharedDefaults: UserDefaults? {
        UserDefaults(suiteName: appGroupID)
    }

    /// Directory in the shared container for transferring attachment files.
    static var sharedFileDirectory: URL? {
        FileManager.default
            .containerURL(forSecurityApplicationGroupIdentifier: appGroupID)?
            .appendingPathComponent("ShareExtension", isDirectory: true)
    }

    // MARK: - Write (called by Share Extension)

    static func savePendingShare(_ share: PendingShare) {
        guard let defaults = sharedDefaults else { return }
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        if let data = try? encoder.encode(share) {
            defaults.set(data, forKey: pendingShareKey)
            defaults.synchronize()
        }
    }

    // MARK: - Read & Consume (called by main app)

    static func loadPendingShare() -> PendingShare? {
        guard let defaults = sharedDefaults,
              let data = defaults.data(forKey: pendingShareKey) else { return nil }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try? decoder.decode(PendingShare.self, from: data)
    }

    static func clearPendingShare() {
        sharedDefaults?.removeObject(forKey: pendingShareKey)
        sharedDefaults?.synchronize()
    }

    /// Remove all files from the shared transfer directory.
    static func cleanSharedFiles() {
        guard let dir = sharedFileDirectory else { return }
        let fm = FileManager.default
        if let files = try? fm.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil) {
            for file in files {
                try? fm.removeItem(at: file)
            }
        }
    }
}
