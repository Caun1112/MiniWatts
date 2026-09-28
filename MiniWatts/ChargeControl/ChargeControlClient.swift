import Foundation
import Observation
import UIKit

@MainActor @Observable
final class ChargeControlClient {
    static let shared = ChargeControlClient()
    private(set) var config: [String: Any] = [:]
    private(set) var battery: [String: Any] = [:]
    private(set) var connected = false
    private(set) var busy = false
    private(set) var message = "尚未连接充电服务"
    private var lastLaunch = Date.distantPast
    private let session: URLSession = {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 3
        configuration.timeoutIntervalForResource = 5
        return URLSession(configuration: configuration)
    }()

    var sensorAvailable: Bool { config["sensor_available"] as? Bool == true }
    var canControl: Bool { connected && sensorAvailable && !busy }
    func bool(_ key: String) -> Bool { config[key] as? Bool ?? false }
    func number(_ key: String, fallback: Double) -> Double { (config[key] as? NSNumber)?.doubleValue ?? fallback }
    func string(_ key: String, fallback: String = "") -> String { config[key] as? String ?? fallback }

    func request(_ payload: [String: Any]) async throws -> [String: Any] {
        var request = URLRequest(url: URL(string: "http://127.0.0.1:1231/bridge")!)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        let (data, response) = try await session.data(for: request)
        guard (response as? HTTPURLResponse)?.statusCode == 200,
              let result = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let status = result["status"] as? Int else { throw ControlError.invalidResponse }
        guard status == 0 else { throw ControlError.backend(status) }
        return result
    }

    func refresh(startIfNeeded: Bool = true) async {
        do {
            let reply = try await request(["api": "get_conf"])
            guard let values = reply["data"] as? [String: Any],
                  values["backend"] as? String == "MiniWatts.ChargeLimiter",
                  values["protocol"] as? Int == 1 else { throw ControlError.invalidResponse }
            let reading = try await request(["api": "get_bat_info"])
            guard !Task.isCancelled else { return }
            config = values
            battery = reading["data"] as? [String: Any] ?? [:]
            if !connected { DiagnosticLog.shared.record("charge", "Service connected; sensor=\(sensorAvailable)") }
            connected = true
            message = sensorAvailable ? "后台服务已连接 · 实际状态以电池读数为准" : "服务已连接，但系统未提供电池控制接口"
        } catch {
            guard !Task.isCancelled else { return }
            let wasConnected = connected
            connected = false
            config = [:]
            battery = [:]
            message = MWHasChargePrivileges() ? "充电服务未连接，正在等待后台响应" : "当前安装未检测到后台所需权限。巨魔 / 越狱用户请安装 Release 中的 TrollStore 版；这不代表设备没有越狱。"
            if wasConnected { DiagnosticLog.shared.record("charge", "Service disconnected: \(error.localizedDescription)") }
            if startIfNeeded && Date().timeIntervalSince(lastLaunch) > 10 {
                lastLaunch = Date()
                let code = MWStartChargeService()
                let launch = MWChargeLaunchDiagnostics()
                DiagnosticLog.shared.record("charge", "Service launch errno=\(code); details=\(launch)")
                if code == EPERM || code == EACCES {
                    message = "系统拒绝启动后台（\(code)）。请使用内嵌权限的 TrollStore 版，并确认越狱环境已生效。"
                } else if code == ENOTCONN {
                    message = "DEB 后台由系统服务管理，尚未连接。请等待约 30 秒重试，或导出日志检查服务输出。"
                } else if code == EALREADY {
                    message = "后台进程已启动，但接口尚未就绪；请稍候或导出日志检查启动输出。"
                } else if code != 0 {
                    message = "服务启动失败（\(code)），请导出诊断日志查看具体阶段。"
                }
            }
        }
    }

    func command(_ payload: [String: Any]) async {
        guard canControl else { return }
        busy = true
        defer { busy = false }
        do {
            _ = try await request(payload)
            DiagnosticLog.shared.record("command", "\(payload) accepted; awaiting hardware readback")
            await refresh(startIfNeeded: false)
            message = "请求已接受，硬件状态最多可能延迟 120 秒更新"
        } catch {
            message = "操作失败：\(error.localizedDescription)"
            DiagnosticLog.shared.record("command", "\(payload) failed: \(error.localizedDescription)")
        }
    }
    func set(_ key: String, _ value: Any) async { await command(["api": "set_conf", "key": key, "val": value]) }

    func handle(_ url: URL) async {
        guard ["miniwatts", "cl"].contains(url.scheme?.lowercased() ?? "") else { return }
        let parts = ([url.host ?? ""] + url.pathComponents).filter { !$0.isEmpty && $0 != "/" }
        let allowed = ["charge", "nocharge", "enable", "disable", "exit"]
        guard parts.allSatisfy({ allowed.contains($0) }) else {
            DiagnosticLog.shared.record("url", "Rejected unknown command")
            return
        }
        for _ in 0..<4 {
            await refresh()
            if connected { break }
            try? await Task.sleep(for: .seconds(1))
        }
        guard canControl else { return }
        for part in parts {
            switch part {
            case "charge", "nocharge": await command(["api": "set_charge_status", "flag": part == "charge"])
            case "enable", "disable": await set("enable", part == "enable")
            case "exit":
                DiagnosticLog.shared.record("url", "Shortcut completed; closing foreground app, service remains running")
                // Compatibility with upstream cl:///charge/exit shortcuts.
                try? await Task.sleep(for: .seconds(1))
                Darwin.exit(0)
            default: break
            }
        }
    }

    enum ControlError: LocalizedError {
        case invalidResponse, backend(Int)
        var errorDescription: String? {
            switch self {
            case .invalidResponse: "服务响应格式或版本不匹配"
            case .backend(let code): "后台返回 \(code)（权限、参数或硬件写入失败）"
            }
        }
    }
}
