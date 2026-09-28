import SwiftUI

struct DiagnosticsView: View {
    @Environment(PowerMonitor.self) private var monitor
    @State private var note = ""
    @State private var exportURL: URL?
    @State private var exporting = false
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                Panel("问题描述", systemImage: "text.bubble") {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("请填写操作步骤、预期结果、实际结果，以及问题发生的大致时间。")
                            .font(.caption).foregroundStyle(Color.mwMuted)
                        TextEditor(text: $note).frame(minHeight: 120).scrollContentBackground(.hidden)
                    }
                }
                Panel("诊断日志", systemImage: "doc.text.magnifyingglass") {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("包含版本、机型、iOS、传感器快照、服务状态、控制请求及错误记录。日志只保存在本机，按大小滚动；导出时过滤常见序列号和设备标识字段。")
                            .font(.caption).foregroundStyle(Color.mwMuted)
                        Button {
                            exporting = true
                            exportURL = nil
                            error = nil
                            Task {
                                do { exportURL = try await DiagnosticLog.shared.export(snapshot: monitor.snapshot, model: monitor.deviceModelIdentifier, note: note) }
                                catch { self.error = error.localizedDescription }
                                exporting = false
                            }
                        } label: { Label(exporting ? "正在生成…" : "生成诊断报告", systemImage: "doc.badge.gearshape") }
                            .buttonStyle(.borderedProminent).tint(.mwAccent).disabled(exporting)
                        if let exportURL {
                            ShareLink(item: exportURL) { Label("导出 / 分享 Bug 日志", systemImage: "square.and.arrow.up") }
                            Text(exportURL.lastPathComponent).mwMono(size: 11).foregroundStyle(Color.mwMuted)
                        }
                        if let error { Text(error).font(.caption).foregroundStyle(Color.mwDanger) }
                    }
                }
                Panel("闪退问题", systemImage: "exclamationmark.bubble") {
                    Text("如果出现闪退，重新打开后先导出本页日志。也可附上系统设置 → 隐私与安全性 → 分析与改进 → 分析数据中的 MiniWatts 或 MiniWattsChargeDaemon .ips 文件；系统崩溃报告无法由普通应用自动读取。")
                        .font(.caption).foregroundStyle(Color.mwMuted)
                }
            }.padding(16)
        }
        .background { Backdrop(glow: .mwAccent) }
        .navigationTitle("Bug 日志").navigationBarTitleDisplayMode(.inline)
    }
}
