# 安装包与 Beta 2 修复说明

## Beta 1 无法连接服务的原因

收到的诊断显示 iOS 17.1.1 上应用可以运行并读取传感器，但后台连接失败，
权限查询为 false，启动结果持续为 EPERM（1）。Beta 1 的启动函数在查询
`no-sandbox` 失败后直接返回 EPERM；因此这些记录不是一次实际 posix_spawn 的返回结果，
不能用来判定设备是否已经越狱，也尚不能据此判断该设备是否支持电池控制。

Beta 1 为了产出完全未签名 IPA，移除了主程序和辅助程序的签名，也就没有在二进制中
嵌入权限。Release 单独附带的 .entitlements 文件不会被 TrollStore 自动应用。
TrollStore / Lite 从二进制现有签名读取权限并保留；缺失时按普通应用权限处理。
这是旧版打包方案的问题，并非用户未安装巨魔的证据。
上游依据：[TrollStore 权限说明](https://github.com/opa334/TrollStore#features)、
[安装器源码](https://github.com/opa334/TrollStore/blob/main/RootHelper/main.m)。

## 选择安装包

| 文件 | 适用方式 | 签名与权限 |
|---|---|---|
| `MiniWatts-TrollStore.ipa` | TrollStore / TrollStore Lite | 内嵌所需权限的 ad-hoc 签名；没有 Apple 开发者证书或描述文件。不是严格意义的零签名文件。 |
| `MiniWatts-rootless.deb` | Sileo 的标准 `/var/jb` rootless 越狱 | `iphoneos-arm64`，应用和 root launchd 服务；包含同样的 ad-hoc 权限。 |
| `MiniWatts-unsigned.ipa` | 自行处理签名的构建底包 | 完全无签名，也无嵌入权限。直接导入安装器不能依靠它自动补齐限充权限。 |

TrollStore Lite 用户应选 `MiniWatts-TrollStore.ipa`，不要再选 unsigned 底包。
Sileo 用户下载 DEB 后通过分享/打开方式交给 Sileo 安装。标准 rootless 安装路径：

- `/var/jb/Applications/MiniWatts.app`
- `/var/jb/Library/LaunchDaemons/org.zhaohe.MiniWatts.charge.plist`
- 服务名 `org.zhaohe.MiniWatts.charge`，系统域、root 用户，启动失败后间隔至少 30 秒重试。

**IPA 与 DEB 选择一种，不要同时安装运行。** 从 TrollStore 切换到 Sileo 之前，
先关闭自动控制并移除 TrollStore 中的旧 MiniWatts，避免同 bundle ID 注册冲突或旧服务占用端口。
如果需要保留应用内充电历史，先自行备份；ChargeLimiter 后台配置和数据库仍保持原来的独立路径。

应用最低 iOS 17。rootless 包不适用于 rootful，也未实现 RootHide 自定义路径转换。
安装 DEB 不会升级或建立越狱，也不能保证所有私有接口在当前系统可用；需保持越狱环境生效。
这次反馈来自 TrollStore Lite，不能套用普通 TrollStore 到 iOS 17.0 的版本范围，
判断重点是 Lite 所依赖的实际越狱和权限是否生效。

## 本次代码修改

1. **更正打包方式**：保留完全未签名底包，新增可携带权限的 TrollStore IPA 和 rootless DEB；
   Actions 验证三个程序内嵌的实际权限、ad-hoc 签名及小组件权限。主应用保留数据容器。
2. **取消单一权限查询的启动拦截**：`MWHasChargePrivileges` 仅作为诊断；
   IPA 实际尝试启动自身后台，由系统返回结果。支持记录多种无沙盒权限及 persona 权限。
3. **rootless 服务管理**：安装/升级时注册并启动 launchd 服务，移除时先停止服务再复位充电；
   rootless 应用不自行反复启动第二个后台实例。
4. **正常停止恢复**：后台收到 SIGTERM 时通过正常退出路径恢复快充前状态、解除温度模拟、恢复充电；
   卸载还会执行独立 reset 作为补充。进程崩溃或强制 SIGKILL 无法保证执行清理。
5. **诊断 v2**：增加包类型、权限查询详情、辅助程序存在性、实际启动阶段、errno、PID、
   退出状态/信号及最多 64 KiB 的启动输出；DEB 也读取 launchd 启动日志末尾。
6. **后台独立性**：启动输出管道持续读取并限容；后台忽略 SIGPIPE，前台退出不会因为日志管道关闭导致后台意外终止。
7. **明确提示**：不再把权限字段缺失直接表述成“设备未越狱”；区分权限拒绝、进程已启动但接口未就绪、系统管理的服务尚未连接。

没有修改充电阈值、温控优先级或插电/边缘触发策略。

## 验证范围与反馈

GitHub Actions 完成编译与打包；检查 IPA 和 DEB 实际内容及内嵌权限。
这只能验证产物，不等于真机安装/launchd/硬件功能已通过。
安装新版本后，如仍未连接，请导出新 JSON；其 `launcher` 字段能进一步区分
权限、安装包路径、子进程崩溃、动态库加载以及 launchd 启动失败。
不要将个人日志提交到公开仓库；本项目只加入抽象的故障结论。

## Beta 3：服务失联时的恢复与启动崩溃修复

新的诊断已确认 `no-sandbox`、`persona-mgmt` 等权限为真，包类型是 Rootless-DEB，
辅助程序也存在。`launchd_managed / errno=57` 是 Beta 2 代码主动返回的状态，
不是一次真实启动的错误；空的 launchd 日志也不足以确定原进程为何没有提供接口。

这次针对已确认的缺陷修改：

- 移除 DEB 专属的提前返回。接口不可用时，应用也会通过已有 root 启动流程尝试恢复后台，记录实际 spawn、退出码和信号。
- 后台增加 root 拥有的单实例文件锁，启动和恢复并发时只有一个进程能初始化控制；锁随进程退出释放，不用 PID 文件当作运行状态。
- 修复上游 `get_mem_limit` 将字节数当成条目数遍历的问题；目标 PID 缺失或查询失败时安全返回。ASan 测试覆盖这些情况。此缺陷可能导致后台初始化崩溃，但不能仅凭当前空日志断言它就是该设备的崩溃原因。
- 后台启动各阶段写入 stderr；HTTP 服务显式关闭前后台自动暂停，删除未生效的“禁用后台模式”编译宏。蓝牙、低电量等可选私有服务改为按需初始化，避免阻塞启动。通知源不可用时改用 20 秒轮询。
- 安装脚本优先选择存在的 rootless launchctl，记录 enable/bootstrap/kickstart/print 输出，并检查监听端口是否就绪；启动失败会保留说明供应用直接恢复。
- 卸载/升级会额外停止应用直接拉起的后台，再复位状态。停止前检查锁和可执行文件路径，不会仅凭旧 PID 文件结束进程。
- 日志增加安装输出和最近 4 次启动历史，重试不再丢掉上次退出原因；并区分文件缺失、无权限、内容为空及读取失败。界面保留具体启动提示，不再被下一轮普通刷新覆盖。

没有修改充电策略。构建和回归测试不能替代真机安装、越狱环境及硬件功能验证。
