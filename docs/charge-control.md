# MiniWatts + ChargeLimiter

集成上游 ChargeLimiter 1.7（27d42eb1789744eee8e68cf69a806d2465bd2cd4）。
MiniWatts 的功率、温度、配件、历史、小组件和画中画保留；新增「控制」标签。
首次启动默认简体中文，手动选择的语言会保存。
完整控制页沿用上游行为，按 MiniWatts 的圆角卡片、青色/绿色和浅深色主题显示。

## 功能入口

| 功能 | 入口 |
|---|---|
| 全局启用、插电即充、边缘触发、电量阈值、手动充停 | 控制主页 |
| 温度阈值、摄氏/华氏、通知、刷新频率、多语言 | 控制 → 完整功能 → 充电设置 |
| 快充：飞行模式、Wi-Fi、蓝牙、亮度、低电量模式 | 充电设置 → 快速充电 |
| SmartBattery、智能停充、禁流、自动限流 | 充电设置 → 高级 |
| Powercuff、模拟等级与锁定、峰值性能 | 充电设置 → 高级 |
| 原生系统悬浮窗、拖动、单击启停、自动隐藏 | 充电设置 → 悬浮窗 |
| 电池健康、周期、硬件电量、电流、充电器、SBC / UPS | 充电设置 → 电池 / 电源信息 |
| 五分钟、小时、天、月图，时移及指标切换 | 控制 → 电池统计 |
| 快捷方式、HTTP API | 见下文 |
| 问题说明、日志导出和系统分享 | 控制 / 设置 → Bug 日志 |

## 安装和权限

发布的 **MiniWatts-unsigned.ipa 是完全未签名的文件**，包括两个后台辅助程序。
项目仍要求 iOS 17+。常规 Apple ID 签名只能提供原有监测能力，不能赋予充电控制权限。
ChargeLimiter 原上游支持的巨魔版本范围到 iOS 17.0；本应用的最低版本是 17.0，
因此可用系统范围是两者的交集，不能因为本应用在新系统能启动就认为限充可用。

要使用控制功能，需支持这些权限的 TrollStore / 越狱安装环境，并给主程序、
`MiniWattsChargeDaemon`、`MiniWattsChargeHUD` 都应用发布附件
`ChargeControl.entitlements` 中的特权签名。安装工具必须支持嵌套辅助程序；
普通自签工具可能移除这些权限。未签名 IPA 本身不包含有效权限签名，不能保证
直接导入某个安装工具即可工作。本次没有制作越狱 deb，也没有修改系统自启动项目。

有相应设备环境的用户可在 **解包后的副本** 中用 ldid 为这三个 Mach-O 添加
侧载特权签名，再重新打包交给兼容的安装工具。小组件仍用原来的权限配置。
这一步会生成新的签名文件，不应把它称为原始未签名发行物。

服务与上游 ChargeLimiter 使用独立端口和文件：

- `127.0.0.1:1231`，仅本机访问，不监听局域网。
- `/var/root/miniwatts-charge.conf`：设置。
- `/var/root/miniwatts-charge.db`：统计。
- `/var/root/miniwatts-charge.log`：滚动日志。

不要同时运行两个限充工具，它们会写入相同的硬件状态。控制默认关闭。
服务失联时，MiniWatts 会禁止原生控制并显示状态，不把 UI 开关作为硬件成功的证据。
服务启动、系统私有 API、通知、SBC 和系统悬浮窗仍需真机验证。
系统重启/强杀可能终止服务；重新打开应用会尝试恢复。

## 快捷方式与 API

支持 `miniwatts:///charge`、`miniwatts:///nocharge`、`miniwatts:///enable`、
`miniwatts:///disable`；兼容 `cl:///charge/exit`、`cl:///nocharge/exit`、`cl:///exit`。
`exit` 在请求完成后关闭前台应用，后台服务继续运行。避免同时安装另一个注册 `cl` 的应用。

向 `http://127.0.0.1:1231/bridge` POST JSON，保留上游 API：
`get_conf`、`set_conf`、`reset_conf`、`get_bat_info`、`get_statistics`、
`set_charge_status`、`set_inflow_status`；新增 `get_diagnostics`。
例如 `{"api":"set_charge_status","flag":false}`。
返回 `status:0` 仅代表请求执行未报错，硬件读数仍可能延迟最多约 120 秒。
参数校验错误返回 -20。请求在主线程串行处理，避免统计数据库和配置并发修改。

## 真机验证及反馈

1. 先确认原有功率、温度、小组件正常；打开控制页检查是否连接到服务。
2. 保持自动控制关闭，在有电源时手动停充/恢复，观察电流和硬件充电状态。
3. 再开启自动控制，验证上下限、重新插拔、温度阈值与后台/锁屏行为。
4. 根据设备能力逐项测试高级选项、通知、悬浮窗、SBC；切勿把开关成功当成硬件成功。
5. 出现问题后到「Bug 日志」填写时间和重现步骤，生成并分享 JSON。
   报告含提交版本、环境、传感器快照、本机滚动日志、服务日志及请求返回码。
   常见序列号/设备标识字段会被过滤；请在分享前检查自己填写的问题描述。
6. 若闪退，同时提供系统「分析数据」中的 MiniWatts / MiniWattsChargeDaemon `.ips`；
   普通应用无权自动读取系统崩溃报告。

## 构建与许可

所有 IPA 均由 GitHub Actions 编译。源码包含完整依赖，不需要第三方预编译框架、
Theos 或私有 SDK。GitHub Release 提供未签名 IPA、权限配置和对应源码。
构建检查不能替代真机测试；无法在本机 macOS 验证特权 iOS API。

组合发行版使用 GPLv3。原 MiniWatts 源码保留 Apache-2.0 声明；上游和依赖许可见
`LICENSE`、`NOTICE`、`LICENSES/`。上游帮助文档保留为参考，其中电池保养建议不是本项目新增保证。
