# CPH 文档入口

本目录同时保留继承自 CCB/CDDA 的技术文档和 CPH 自己的项目记录。先按目的选择入口，不要把历史审计或本地工具测试当作当前远端验收。

| 要做的事 | 入口 |
| --- | --- |
| 了解工作区目录、源码仓库和本地证据的边界 | [工作区布局](project/workspace-layout.md) |
| 了解文档逐篇核验范围 | [文档审阅记录](project/documentation-review.md) |
| 必读现行需求 R01—R18、授权和验收边界 | [执行规格](project/execution-spec.md) |
| 查看带日期的进度及已验证范围 | [状态记录](project/status.md)；当前远端状态须重新回读 |
| 查阅阶段恢复清单 | [恢复入口](project/resume.md)；执行前核对记录日期 |
| 按任务选择手册与 T01—T22 验收场景 | [任务路由](project/execution-spec.md#7-按任务读取主题手册)、[场景索引](project/execution-spec.md#10-验收场景索引) |
| 了解受控同步链 | [远端同步](project/remote-sync.md) |
| 查看世界生成高级规则、逐项影响和 MOD 兼容边界 | [世界高级规则](project/world-advanced-options.md) |
| 使用双人联机、睡眠与实验性 Magiclysm | [联机操作和限制](project/multiplayer.md) |
| 查阅四平台发布目标及本地实现边界 | [发布契约](project/release-contract.md#目标发布协议) |
| 完成任务并处理工作树/输出 | [任务收尾与清理](project/workspace-layout.md#任务收尾与清理) |
| 阅读历史来源、初次 fork 上传和阶段回证 | [来源锁定](project/upstreams.md)、[建仓回证](project/fork-deployment.md)、[继承工作流审计](project/inherited-workflows.md) |

`project/` 下的其他页面按主题说明本地工具、平台探针、身份隔离与发布契约；其中可能包含历史快照，当前远端状态应另行回读。源码仓库的 `project/` 保存机器可读的锁、策略和清单，与本目录的项目说明用途不同。

仓库根部的 `doc/` 是继承的游戏开发和数据格式技术资料；不要因为它与 `docs/` 名称相近就整体迁移。其具体结论仍须与当前源码和测试核对。
