# CPH 文档入口

本目录同时保留继承自 CCB/CDDA 的技术文档和 CPH 自己的项目记录。先按目的选择入口，不要把历史审计或本地工具测试当作当前远端验收。

| 要做的事 | 入口 |
| --- | --- |
| 了解工作区目录、源码仓库和本地证据的边界 | [工作区布局](project/workspace-layout.md) |
| 核对仍有效的用户需求 R01—R18 与阶段目标 | [执行规格](project/execution-spec.md) |
| 查看带日期的进度及已验证范围 | [状态记录](project/status.md) |
| 接着实施或排查阻塞 | [恢复入口](project/resume.md) |
| 操作当前受控同步链 | [远端同步](project/remote-sync.md) |
| 了解本次文档逐篇核验范围 | [文档审阅记录](project/documentation-review.md) |
| 阅读历史来源、初次 fork 上传和阶段回证 | [来源锁定](project/upstreams.md)、[建仓回证](project/fork-deployment.md)、[继承工作流审计](project/inherited-workflows.md) |

`project/` 下的其他页面按主题说明本地工具、平台探针、身份隔离与发布契约；各页开头标明其是现行操作说明、当时的回证还是待部署设计。源码仓库的 `project/` 保存机器可读的锁、策略和清单，与本目录的项目说明用途不同。

仓库根部的 `doc/` 是继承的游戏开发和数据格式技术资料；不要因为它与 `docs/` 名称相近就整体迁移。其具体结论仍须与当前源码和测试核对。
