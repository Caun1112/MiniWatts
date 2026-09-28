import SwiftUI

struct ChargeControlView: View {
    @State private var client = ChargeControlClient.shared

    var body: some View {
        PageScaffold("充电控制", glow: .mwBattery) {
            statusPanel
            controlsPanel
            thresholdsPanel
            Panel("完整功能", systemImage: "slider.horizontal.3") {
                VStack(spacing: 16) {
                    NavigationLink { ChargeControlWebPage(page: "index.html", title: "充电设置") } label: {
                        Label("温控 / 快充 / 高级控制 / 悬浮窗", systemImage: "slider.horizontal.3")
                    }
                    NavigationLink { ChargeControlWebPage(page: "history.html", title: "电池统计") } label: {
                        Label("5 分钟 / 小时 / 天 / 月统计", systemImage: "chart.xyaxis.line")
                    }
                    Text("包含 SmartBattery、智能停充、禁流、自动限流、Powercuff、峰值性能、通知、SBC / UPS 信息和全部电池数据。")
                        .font(.caption).foregroundStyle(Color.mwMuted)
                }.frame(maxWidth: .infinity, alignment: .leading)
            }.disabled(!client.connected)
            Panel("诊断与帮助", systemImage: "stethoscope") {
                VStack(alignment: .leading, spacing: 14) {
                    NavigationLink { DiagnosticsView() } label: { Label("导出 Bug 日志", systemImage: "square.and.arrow.up") }
                    Text("服务独立于界面运行；系统重启或终止服务后，需要重新打开 MiniWatts。不要同时启用其他限充工具。部分设备的状态变化可能延迟 120 秒；高温模拟在锁屏时可能失效。")
                        .font(.caption).foregroundStyle(Color.mwMuted)
                    Text("快捷指令 URL：miniwatts:///charge、miniwatts:///nocharge、miniwatts:///enable、miniwatts:///disable；兼容 cl:///charge/exit。HTTP 接口只监听本机 127.0.0.1:1231。")
                        .font(.caption).foregroundStyle(Color.mwMuted)
                    Link("ChargeLimiter 开源项目 · GPLv3", destination: URL(string: "https://github.com/lich4/ChargeLimiter")!)
                        .font(.caption)
                }
            }
        }
    }

    private var statusPanel: some View {
        Panel("服务状态", systemImage: "bolt.shield") {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Image(systemName: client.connected ? "checkmark.circle.fill" : "lock.circle")
                        .foregroundStyle(client.connected ? Color.mwBattery : Color.mwLoss)
                    Text(client.connected ? "ChargeLimiter 已连接" : "控制服务不可用").font(.headline)
                    Spacer()
                    if client.busy { ProgressView() }
                }
                Text(client.message).font(.caption).foregroundStyle(Color.mwMuted)
                if client.connected {
                    HStack {
                        value("电量", key: "CurrentCapacity", suffix: "%")
                        Spacer()
                        VStack(alignment: .trailing) {
                            Text("硬件充电状态").mwCaption()
                            Text((client.battery["IsCharging"] as? Bool).map { $0 ? "正在充电" : "未充电" } ?? "未知")
                                .font(.headline).foregroundStyle(Color.mwBattery)
                        }
                    }
                } else {
                    Button("重新连接") { Task { await client.refresh() } }.tint(.mwAccent)
                }
            }
        }
    }

    private var controlsPanel: some View {
        Panel("充电策略", systemImage: "battery.100.bolt") {
            VStack(alignment: .leading, spacing: 14) {
                Toggle("启用自动充电控制", isOn: Binding(get: { client.bool("enable") }, set: { v in Task { await client.set("enable", v) } }))
                    .tint(.mwBattery)
                Picker("模式", selection: Binding(get: { client.string("mode", fallback: "charge_on_plug") }, set: { v in Task { await client.set("mode", v) } })) {
                    Text("插电即充").tag("charge_on_plug")
                    Text("边缘触发").tag("edge_trigger")
                }.pickerStyle(.segmented)
                Text(client.string("mode") == "edge_trigger" ? "低于下限开始充电，高于上限停止；区间内保持状态，重新插电会按上游策略停充。" : "接入电源且满足阈值条件时充电；达到电量或温度上限时停止。")
                    .font(.caption).foregroundStyle(Color.mwMuted)
                HStack {
                    Button("立即充电") { Task { await client.command(["api": "set_charge_status", "flag": true]) } }
                    Spacer()
                    Button("停止充电") { Task { await client.command(["api": "set_charge_status", "flag": false]) } }
                }.buttonStyle(.bordered).tint(.mwAccent)
                Text("手动控制后，启用中的自动策略仍可能在下一次电池事件时改变状态。关闭自动控制会恢复充电。")
                    .font(.caption).foregroundStyle(Color.mwMuted)
            }
        }.disabled(!client.canControl)
    }

    private var thresholdsPanel: some View {
        Panel("电量阈值", systemImage: "dial.low") {
            VStack(spacing: 16) {
                threshold("恢复充电", key: "charge_below", fallback: 20, range: 5...max(5, client.number("charge_above", fallback: 80) - 1))
                threshold("停止充电", key: "charge_above", fallback: 80, range: min(100, client.number("charge_below", fallback: 20) + 1)...100)
            }
        }.disabled(!client.canControl)
    }
    private func threshold(_ title: String, key: String, fallback: Double, range: ClosedRange<Double>) -> some View {
        HStack {
            VStack(alignment: .leading) {
                Text(title).mwCaption()
                Text("\(Int(client.number(key, fallback: fallback)))%").mwReadout(size: 30).foregroundStyle(Color.mwBattery)
            }
            Spacer()
            Stepper(title, value: Binding(get: { client.number(key, fallback: fallback) }, set: { v in Task { await client.set(key, v) } }), in: range, step: 1).labelsHidden()
        }
    }
    private func value(_ title: String, key: String, suffix: String) -> some View {
        VStack(alignment: .leading) {
            Text(title).mwCaption()
            Text((client.battery[key] as? NSNumber).map { "\($0)\(suffix)" } ?? "—").mwReadout(size: 34).foregroundStyle(Color.mwBattery)
        }
    }
}

struct ChargeControlWebPage: View {
    let page: String
    let title: String
    @State private var revision = 0
    var body: some View {
        ChargeWebSurface(page: page).id(revision)
            .background(Color.mwCanvas)
            .navigationTitle(title).navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button { revision += 1 } label: { Image(systemName: "arrow.clockwise") }
                    NavigationLink { DiagnosticsView() } label: { Image(systemName: "doc.text.magnifyingglass") }
                }
            }
    }
}
private struct ChargeWebSurface: UIViewRepresentable {
    let page: String
    func makeUIView(context: Context) -> MWChargeWebView {
        let view = MWChargeWebView(frame: .zero)
        view.eventHandler = { message in
            Task { @MainActor in DiagnosticLog.shared.record("web", message) }
        }
        view.loadPage(page)
        return view
    }
    func updateUIView(_ uiView: MWChargeWebView, context: Context) {}
    static func dismantleUIView(_ uiView: MWChargeWebView, coordinator: ()) { uiView.stop() }
}
