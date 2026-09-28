# 未完成事项与恢复入口

当前快照统一见 [status.md](status.md)。本页只列仍需执行的动作；不重建仓库、不重做已合入 PR、不默认恢复同步。原始阶段恢复记录可从 [整理前版本](https://github.com/oncehere/Cataclysm-Phantom-Hope/blob/abd9222e01b77ac9e187f53cd6cfe85275453a69/docs/project/resume.md) 查阅。

| 动作 | 前置条件 | 执行与验收 |
| --- | --- | --- |
| 用户授权的个人维护 | 固定范围及候选，相关本机证据充分 | 按 [执行规格 §6.1](execution-spec.md#61-合入)；复用证据须核对输入不变，必要失败先修复；GitHub 阻止合入时按 [设置流程](../../REPOSITORY_SETTINGS.md#personal-maintenance-under-the-existing-rule) 办理 |
| 新 tooling 远端验收 | 已审阅控制代码、精确 Actions 白名单，自动合入保持暂停 | 用固定普通候选验证工具结果齐全时可发布 trusted；缺失/失败/零用例/旧 base-policy 必须拒绝；记录实际 run/attempt/tree |
| 恢复 CCB 自动同步/合入 | **用户后续明确要求**，新门槛及规则锁已验收 | 刷新 state revision、main、上游与在途任务；按 [同步手册](remote-sync.md#operator-controls) 分别处理 workflow 与状态开关；不复用旧恢复记录 |
| macOS 发布验收 | 可用原生 runner、实际架构及依赖 | 构建、打包、自动探针；清理夹具通过不等于真实 macOS 包通过；不额外要求每日人工实机验收 |
| Android 发布验收 | SDK/NDK/JDK、身份/签名和明确运行 profile | 实际 APK ABI/资源/签名与选定运行环境核验；兼容架构模拟器不能冒充 ARM64 实测 |
| 长期独立身份与签名 | 用户明确的永久应用身份及受控签名环境 | 与 CCB 并行安装、数据目录及升级/卸载隔离；不使用真实存档破坏性测试，不索取聊天中的密钥 |
| 四平台每日开发版 | 同提交、同锁定输入的四套合格产物，公开前验证与恢复演练完成 | 按 [发布契约](release-contract.md) 和执行规格第 8 节；稳定版需要独立决定 |
| 完整 PO 维护链 | 可核验来源与许可 | 当前外来 MO 作为锁定输入保留；缺 PO 不伪造源码、空资源或自主重建能力 |

文档影响仍为显式本地/人工检查，不能称为 GitHub 自动强制门槛。外部条件只阻塞依赖动作；不购买资源，不降低 required checks，不自动启用 AI。

每次交接记录固定提交、实际命令/退出码、证据位置与 NOT_RUN 范围。工作树结束后按 [维护生命周期](workspace-layout.md#维护生命周期) 判断退役，避免永久保留可重建的源码副本。
