# 发布候选验收

日期：2026-09-28。本目录最初只有既有 `.git/`、`.agents/`、`.codex/`，Git 为 `master` 尚无提交；未发现适用 AGENTS.md。原有元数据保留，没有提交、创建远程仓库或发布包/镜像。

## CPH 定点修订（2026-09-29）

Antigravity 全量补译后，经只读复核发现两条语义偏差：年龄段、车厢内位置及单数代词。本轮按用户要求只修订这两个条目，保留旧批次和原始来源证据，基于当前PO生成新状态。执行 `PATH=/nix/store/518bcx82g8m9cyji47sprx9ajmadjk8s-gettext-1.0/bin:$PATH env -u GEMINI_API_KEY .venv/bin/python -m pytest -q`：**PASS，161 passed，退出0**（14.26秒，已有SDK弃用warning一条）。具体PO/state、MO及幂等检查见[修订验收](../cph-translation/corrections-validation-20260929.json)。本轮没有API请求、游戏安装或发布。

## 实际 CPH 补译后的增量验证

真实大目录暴露了 `c-format` 参数编号重排及普通叙述百分号的预检误报，已复用 GNU gettext 修正。供应商故障达到有限重试上限后停止后续批次，保存完整部分候选；429/503 状态及最多60秒等待建议可安全记录，SDK 原始错误正文不进入报告。此阶段曾运行140项回归通过；原先引用的增量构建JSON未实际生成，已删除失效链接，不把被中断的构建说成完成。

用户确认没有 API 额度后，新增离线文件导出/响应验证/导入和只复用缓存模式。当前回归 **PASS：161 passed，退出0**，另有一条既有 SDK Pydantic 弃用 warning；CPH 额外 QA 的13个回归检查通过。与 lokit/Gemini 使用同一组 null/空/不同上下文及三复数样例验证外部文件流程，补充错误响应、占位符/换行/标签、人工空白、API缓存不发请求、并发修改、导出中断及来源替换测试。具体命令和源码摘要见 [离线交接验收](offline-handoff-validation.json)。本轮 Gemini API **NOT_RUN**，Antigravity 实际模型运行、整体译文质量与更新后的容器验证 **NOT_RUN**；不把旧容器PASS挪作新增入口的证明。

实际 CPH 已完成隔离源码提取、固定官方原始 PO 核验及合并；3.7 生成接口请求失败（一次诊断明确 HTTP 503），3.8 产生实际补译结果。当前覆盖率与完整命令见 [CPH 翻译记录](../cph-translation/README.md)，不能把部分翻译或自动格式检查称为完整语言质量验收。游戏仓库保持只读，MO 安装/游戏加载/CI 资源验证仍 **NOT_RUN**。下列两个阶段的数字和旧型号结果保留为历史证据。

## 模型选型后的增量验证（历史）

同日按[网络翻译与创作证据](gemini-model.md)将示例模型设为 `gemini-3.7-flash`，移除后端固定采样参数，升级缓存策略。运行 `PATH=/nix/store/518bcx82g8m9cyji47sprx9ajmadjk8s-gettext-1.0/bin:$PATH .venv/bin/python -m pytest -q --tb=short`：**PASS，99 passed，退出 0**，仍有一条已知 SDK Pydantic 弃用 warning。其中 Gemini 专项 **32 passed**，包含旧策略缓存与未知请求保护。

下表及原始 JSON 是此前 97 项基线的历史验收；其源码摘要没有被改写为新版本。容器/外部项目的离线流程未发生改变，未重复运行。`gemini-3.7-flash` 的真实请求及新参数下的人工语言质量验收为 **NOT_RUN**；不能将此前 Flash-Lite 的 PASS 转记到新模型。新增记录见 [model-selection-results.json](model-selection-results.json)。

## 实际结果

| 项目 | 结果 | 证据与范围 |
| --- | --- | --- |
| 原生回归 | **PASS** | 97 tests，退出 0；Python 3.13.15、polib 1.2.0、Google GenAI 1.43.0、GNU gettext 1.0 |
| lokit 固定版适配审查 | **PASS** | 4 个主探针含 3 个复数子项；成功重现行为不表示 lokit 满足产品约束，见 [原始记录](lokit-audit-results.txt) |
| 非 Cataclysm 真实项目 | **PASS** | Wget 1.25.0 pl/ru 各 599/599 精确复用，两种语言各 2 条三复数、MO 编译、重复 PO 字节一致；只改配置，见 [逐命令记录](real-project-results.json) |
| 容器 | **PASS** | Podman 构建完成；禁网的一次性 plan/apply/check/compile/二轮幂等全部退出 0，见 [记录](container-results.json) |
| Python wheel / sdist 构建 | **PASS** | `python -m build --outdir dist` 退出 0，检查 wheel 含全部核心模块、sdist 不含环境/缓存/密钥文件 |
| wheel 独立安装 | **PASS** | 全新虚拟环境按哈希锁安装依赖及 wheel，离开源码目录运行全部离线命令；[记录](wheel-install-results.json) |
| CPH 当前补充 PO 格式检查 | **PASS** | 只读输入、MO 写入 /tmp；251 条通过 gettext。具体源码快照及缺失完整 POT 的边界见 [CPH 接入](cph.md) |
| Gemini 真实补译 | **PASS** | `gemini-3.5-flash-lite` 一次串行请求，单数 + 波兰语三复数共 2 条均通过身份/格式检查、完整候选应用及 MO 编译；[脱敏记录](gemini-live-results.json)、[实际 PO](gemini-live-candidate.po) |
| 人工语言质量验收 | **NOT_RUN** | 自动格式/结构检查不能证明语义正确 |
| CPH 完整提取、实际上游合并、MO 安装、游戏加载、CI 资源验证 | **NOT_RUN** | 本任务保持只读参考边界 |
| Docker、Windows、macOS、容器 ARM64、Python 3.11/3.12 | **NOT_RUN** | 原生实现依赖 POSIX flock，首版支持目标是 Linux；Windows 原生尚未支持 |
| 远程 CI、包/镜像发布 | **NOT_RUN** | 本任务没有发布授权，未创建远程资源 |

原始基线的原生测试命令、退出码、输出、源码及构建摘要在 [validation-results.json](validation-results.json)。当前 SDK 对新 Pydantic 有一条弃用 warning，测试没有失败；已固定依赖，后续升级要重跑相同验收。

## 可复跑命令

安装锁定依赖，并使 GNU gettext 的 `msgfmt` 位于 PATH：

```sh
uv sync --frozen --extra test
uv run --frozen --extra test pytest -q --tb=short
uv run --frozen --extra test python -m build --outdir dist
uv run --frozen python scripts/verify_real_project.py --workdir /tmp/new-wget-validation
bash scripts/audit_lokit.sh
podman build -f Containerfile -t localhost/po-keeper:0.1.0rc1 .
uv run --frozen python scripts/verify_container.py --evidence /tmp/container-results.json
```

本机 gettext 在 `/nix/store/518bcx82g8m9cyji47sprx9ajmadjk8s-gettext-1.0/bin`；实际原生命令在 PATH 前加该目录，用 `.venv/bin/python` 运行。构建镜像使用独立的 `/tmp/pokeeper-container-storage` 与 `/tmp/pokeeper-container-run`，避免改动已有容器。沙箱最初阻止 rootless 用户命名空间，随后在自动批准的隔离执行中完成构建及验收；这已解决，不列为未完成 BLOCKED。

## 覆盖与失败边界

最初 `gemini-2.5-flash` 两条补译批次被明确拒绝；随后单条诊断定位为 HTTP 404 `NOT_FOUND`。模型元数据查询仍然成功，不能据此声称生成接口可用。Google [当前访问说明](https://ai.google.dev/gemini-api/docs/deprecations) 限制 2.5 系列的新用户访问，此现象与说明一致，但没有把账户权限原因当作已独立证实的事实。

根据实际模型列表改用 `gemini-3.5-flash-lite` 后，同一生产 SDK 后端和完整 PO 流程成功。共尝试 3 个生成请求（旧模型两次明确拒绝，新模型一次成功），每次重试均设 0；另有只读模型查询。未宣称旧请求绝不会计费。用户密钥只经隐藏终端输入临时进程，未写入项目、报告、镜像或普通日志。SDK 对该模型返回的 `thought_signature` 发出非文本提示，文字结果通过校验；未保存签名或原始 API 错误体。

后续可显式运行下面的最小真实验收；它会产生模型请求，未配置环境变量时从终端隐藏读取密钥：

```sh
uv run --frozen python scripts/verify_gemini.py \
  --model gemini-3.5-flash-lite --workdir /tmp/new-gemini-validation
```

本次真实验收只证明所选模型对这两条代表性样例的连通性和完整工作流，不能代替大规模翻译质量评估、其它模型/权限/地区验证或真实网络中断计费核对。

- `test_core.py`：精确身份、None/空上下文、多复数、来源顺序、fuzzy/obsolete/空白/错误格式、源文变化、人工改写/清空/删除/obsolete、持续保护与解除、恢复已保护旧身份、AI 被上游替换、原始来源保留、幂等、语言与复数规则变化、并发输入、MO 路径与保留文件防护。
- `test_transaction.py`：候选完整性、并发输入、symlink/hardlink、应用中断、finish/rollback、未知第三种内容拒绝覆盖、历史快照损坏时拒绝完成恢复。
- `test_candidate.py`：目标必须符合受保护配置、完整 POT 身份集合、PO/状态/来源关系、重算清单仍不能绕过一致性校验、最终 gettext 检查。
- `test_gemini.py`：与 lokit 同一组样例，原始数量/身份/占位符/换行/标签校验、完成缓存、失败续跑、retries=0 和有限重试、超时/中断未知状态、配置变化不能绕过未知请求保护、脱敏错误、请求前路径/输入检查。
- `test_cli.py` / `test_parser_limits.py`：公开离线命令、不导入 SDK、不需要密钥，以及 polib 无法保真写回显式空复数原文时明确拒绝，避免静默改变身份。

实现期间发现并修复了候选目标重定向、状态语义缺检、MO/缓存保留路径碰撞、obsolete 保护重引入等问题。相应回归已进入最终 97 项；早期失败不是最终通过的替代证据。

## 独立发布就绪情况

已有安装入口、版本元数据、MIT 许可、精确依赖/哈希锁、完整使用文档、容器与外部多复数项目实证，可作为本地审查候选。源码和输入以摘要绑定，可复跑，未把当前候选称为所有平台正式发行。

正式发布仍需维护者语言质量审校、选择支持平台、确认包名/维护者/许可归属及发布凭据。非 Cataclysm 真实 gettext 项目和小批量真实 Gemini 生成接口这两个前置条件已经完成。首版没有 snapshot GC、金额硬封顶或跨文件原子性承诺；完整限制见 [选型记录](decisions.md)。
