import Foundation
import UIKit

/// Bounded on-device diagnostics. No upload, device identifiers or account details.
@MainActor
final class DiagnosticLog {
    static let shared = DiagnosticLog()
    private let folder: URL
    private let logURL: URL
    private var lastSample = Date.distantPast
    private(set) var writeError: String?

    private init() {
        folder = URL.applicationSupportDirectory.appendingPathComponent("MiniWattsDiagnostics", isDirectory: true)
        logURL = folder.appendingPathComponent("events.jsonl")
        do { try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true) }
        catch { writeError = error.localizedDescription }
        record("app", "Launch version=\(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") ?? "?") build=\(Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") ?? "?") iOS=\(UIDevice.current.systemVersion)")
    }

    func record(_ category: String, _ message: String) {
        let entry = ["time": ISO8601DateFormatter().string(from: .now), "category": category, "message": message]
        do {
            if let size = try? logURL.resourceValues(forKeys: [.fileSizeKey]).fileSize, size > 524288 {
                let previous = folder.appendingPathComponent("previous.jsonl")
                if FileManager.default.fileExists(atPath: previous.path) { try FileManager.default.removeItem(at: previous) }
                try FileManager.default.moveItem(at: logURL, to: previous)
            }
            if !FileManager.default.fileExists(atPath: logURL.path) { try Data().write(to: logURL) }
            let handle = try FileHandle(forWritingTo: logURL)
            defer { try? handle.close() }
            try handle.seekToEnd()
            var data = try JSONSerialization.data(withJSONObject: entry, options: [.sortedKeys])
            data.append(10)
            try handle.write(contentsOf: data)
            writeError = nil
        } catch { writeError = error.localizedDescription }
    }

    func sample(_ snapshot: PowerSnapshot) {
        guard Date().timeIntervalSince(lastSample) >= 60 else { return }
        lastSample = .now
        record("sensor", "external=\(snapshot.externalConnected) inputW=\(snapshot.inputWatts.map(String.init(describing:)) ?? "unavailable") batteryW=\(snapshot.batteryWatts.map(String.init(describing:)) ?? "unavailable") sensors=\(snapshot.sensors.count)")
    }

    func export(snapshot: PowerSnapshot, model: String, note: String) async throws -> URL {
        record("diagnostics", "Export requested")
        let service: Any
        do { service = try await ChargeControlClient.shared.request(["api": "get_diagnostics"])["data"] ?? [:] }
        catch { service = ["unavailable": error.localizedDescription] }
        let events = ["previous.jsonl", "events.jsonl"].map {
            (try? String(contentsOf: folder.appendingPathComponent($0), encoding: .utf8)) ?? ""
        }.joined()
        let buildCommit = Bundle.main.url(forResource: "BuildCommit", withExtension: "txt")
            .flatMap { try? String(contentsOf: $0, encoding: .utf8) } ?? "unavailable"
        let report: [String: Any] = [
            "format": "MiniWatts diagnostics v2", "exportedAt": ISO8601DateFormatter().string(from: .now),
            "appVersion": Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") ?? "?",
            "build": Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") ?? "?", "commit": buildCommit.trimmingCharacters(in: .whitespacesAndNewlines),
            "model": model, "iOS": UIDevice.current.systemVersion,
            "privileged": MWHasChargePrivileges(), "launcher": MWChargeLaunchDiagnostics(), "userDescription": note,
            "thermalState": ProcessInfo.processInfo.thermalState.rawValue,
            "logWriteError": writeError ?? "none",
            "registry": snapshot.registry, "powerSource": snapshot.powerSource ?? [:],
            "adapter": snapshot.adapterDetails ?? [:], "chargeStatus": snapshot.chargeStatus ?? [:],
            "sensors": snapshot.sensors.map { ["name": $0.name, "value": $0.value] as [String: Any] },
            "chargeService": service, "events": events,
            "limitations": "Not an iOS crash dump. For a crash before export, also share the MiniWatts .ips from Settings > Privacy & Security > Analytics & Improvements > Analytics Data."
        ]
        // Keep only the most recent export; a fresh name gives ShareLink a new identity.
        let exportFolder = folder.appendingPathComponent("Exports", isDirectory: true)
        try FileManager.default.createDirectory(at: exportFolder, withIntermediateDirectories: true)
        for old in try FileManager.default.contentsOfDirectory(at: exportFolder, includingPropertiesForKeys: nil) { try? FileManager.default.removeItem(at: old) }
        let url = exportFolder.appendingPathComponent("MiniWatts-bug-\(Int(Date().timeIntervalSince1970)).json")
        try JSONSerialization.data(withJSONObject: Self.redacted(report), options: [.prettyPrinted, .sortedKeys]).write(to: url, options: .atomic)
        return url
    }

    static func redacted(_ value: Any) -> Any {
        if let dictionary = value as? [String: Any] {
            return dictionary.mapValues { $0 }.reduce(into: [String: Any]()) { result, pair in
                let key = pair.key.lowercased()
                if ["serial", "udid", "uniquechip", "uniqueidentifier", "imei", "meid", "macaddress", "devicename", "bluetoothaddress", "wifiaddress", "account", "token", "password"].contains(where: key.contains) {
                    result[pair.key] = "[redacted]"
                } else { result[pair.key] = redacted(pair.value) }
            }
        }
        if let array = value as? [Any] { return array.map { redacted($0) } }
        if let number = value as? NSNumber { return number.doubleValue.isFinite ? number : NSNull() }
        if let string = value as? String {
            return string.replacingOccurrences(of: NSHomeDirectory(), with: "[app-container]")
                .replacingOccurrences(of: #"(?i)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"#, with: "[uuid]", options: .regularExpression)
        }
        if value is NSNull { return value }
        if let date = value as? Date { return ISO8601DateFormatter().string(from: date) }
        return "[unsupported value]"
    }
}
