# PO Keeper

轻量的本地 gettext 翻译维护工具，面向长期合并上游翻译、同时保留本项目人工修订的维护者。输入本地 POT/PO，输出可审查的完整 PO、来源状态与报告。贡献者可以只改 PO 提交 PR。

当前是 **0.1.0rc1 发布候选**，Linux / Python 3.11+；实际验收和未验证项见 [验证记录](docs/validation.md)。不包含下载平台、Web 编辑器或常驻服务。

## 安装与离线试用

需要 Python 3.11+、[GNU gettext](https://www.gnu.org/software/gettext/) 的 `msgfmt`。推荐使用锁定环境：

```sh
uv sync --frozen --extra test
uv run --frozen pokeeper --help
uv run --frozen pokeeper plan --config examples/demo/project.toml --candidate /tmp/po-review-1
# 审查 /tmp/po-review-1/candidate.po、report.json 和 state.json
uv run --frozen pokeeper apply /tmp/po-review-1
uv run --frozen pokeeper check --config examples/demo/project.toml
uv run --frozen pokeeper compile --config examples/demo/project.toml --output /tmp/example.mo
```

没有 uv 时：`python -m venv .venv`，用 `.venv/bin/pip install --require-hashes -r requirements.lock` 安装锁定运行依赖，再 `.venv/bin/pip install --no-deps .`。`python -m pokeeper` 与 `pokeeper` 使用相同入口。

复制 [示例配置](examples/demo/project.toml) 到自己的翻译项目，调整 `project`、语言、复数规则、PO/POT 路径与有序 `sources`。所有相对输入/输出路径基于配置文件目录；首版拒绝符号链接和输入/输出路径别名。`project` 应是项目及语言唯一标识；不同分支使用各自检出的状态及快照，不能共用全局状态目录。PO 的非空 Language 必须与配置一致（仅规范化 `-` / `_` 分隔符）；不推断其它语言别名。

首次接管已有译文必须选择 `--adopt-existing protect`（全部作为受保护人工译文）或 `--adopt-existing reuse`（允许更高优先级上游替换）。之后不要重复此选项。缺少整份既有 PO、状态损坏或快照缺失时，恢复匹配文件后再继续，不静默重建基线。

## 日常维护

1. 维护者把固定版本上游 PO 和本项目 POT 放入配置指定的位置。
2. `pokeeper plan --config project.toml --candidate review-001` 生成候选，不修改正式 PO/状态。
3. 审查完整 `candidate.po`、`report.json` 中的更新、冲突、缺口、人工改动及忽略原因。无效来源不会复制，低优先级不同译文会报告。
4. `pokeeper apply review-001` 重新校验所有输入摘要，以及配置、PO、状态与来源之间的一致性，再应用候选。过期输入、清单摘要不符、目标与配置不符或未完成事务都会被拒绝。
5. 提交正式 PO、状态 JSON 和 `snapshots/` 中被引用的文件。通常保留全部内容寻址快照，首版不做垃圾回收。

候选应来自本机可信的生成过程。SHA256 清单是完整性检查，不是数字签名；不要应用来历不明的候选。需要修订译文时修改工作 PO 并重新生成候选，不必手改状态或清单。

人工改译文、清空译文都会持续保护；删除仍在 POT 中的条目会恢复为受保护空白，并报告。工具下一次运行自动比较 PO 与上次输出的译文摘要，无需贡献者手改状态。换行排版、注释及单独 fuzzy 标记变化不会被当作人工改译文。已保护译文即便后来恰好与上游一致，也不自动解锁。

解除保护需在计划操作显式传 `--unprotect ENTRY_ID`（可重复），ID 从报告或状态取得，审查后应用。普通 Gemini / 外部工具译文没有保护标记，后续有效上游可替换。上游移除译文时，仍需要的有效当前译文及其原始快照来源保持不变。

身份精确包含 `(msgctxt, msgid, msgid_plural)`，缺省上下文与 `""` 不同。原文改变形成新条目，旧条目成为 obsolete；不自动 fuzzy 迁移。fuzzy、obsolete、空译文、复数规则不兼容及格式错误分别报告。复数规则只做去空白后的精确比较，数学等价但写法不同也会保守报告冲突，绝不补齐/截断。

`check` 和 `compile` 允许合法的未译空白及 fuzzy 条目；GNU gettext 不会把它们当作有效翻译编译。PASS 表示结构/格式检查成功，不表示全覆盖或语言质量已人工认可。百分号和 Python brace 格式、换行形状及配置的 token 正则先保守预检，再由 `msgfmt --check --check-format` 整体检查。复杂占位符的合法重排可能被预检拒绝，应审查报告；项目标签通过配置扩展，不写死在核心。

## 无 API 的外部翻译流程

可以让 Antigravity 或其他编辑器直接编写小批 JSON，由本工具离线校验、合并。没有新的网络翻译后端，不需要 API 密钥。当前 CPH 使用此流程，见 [可直接复制的 Antigravity 提示词](cph-translation/ANTIGRAVITY_HANDOFF.md)。

```sh
pokeeper plan --config project.toml --candidate review-base
# 如需历史 Gemini 完成缓存，用下面命令代替 plan；绝不请求模型、不改缓存：
# pokeeper fill --config project.toml --cache .pokeeper/gemini-cache.json --cache-only --candidate review-base
pokeeper export review-base --output translation-batches --batch-size 12 --max-chars 16000
pokeeper responses translation-batches
# 外部编辑器读 instructions.json 和单个 requests/0001.json，写 responses/0001.json
pokeeper responses translation-batches --batch 0001
# 全部批次通过，再聚合审查：
pokeeper import translation-batches --candidate review-translated
pokeeper apply review-translated
```

导出只包含未保护缺口，保留精确身份、单复数、开发者/译者注释、位置和格式标记；按上下文分组，相关术语及少量例句每批只写一份。现有 `[gemini]` 的 `prompt/terms/examples` 也可用作离线编辑指导，离线流程不读取模型型号、不访问 SDK。无此配置也可导出。字符限制不拆分单条长消息；超长批次在导出结果中单独列出。

响应协议：`{"request_sha256":"请求文件摘要","producer":{"tool":"Antigravity","model":"实际型号或not-reported"},"translations":[{"id":"请求条目ID","values":["译文"]}]}`。原文身份绑定到请求摘要和条目 ID，不要求重复输出长原文。每批 ID 精确覆盖且不重复；复数数量、占位符、项目规则及完整 PO 均需通过原有检查。

`responses` 是只读检查；`INCOMPLETE` 且退出 0 表示已保存部分通过、尚有批次缺失，`FAIL` 退出 2，全部通过才是 `PASS`。`import` 拒绝错误响应，允许缺少整批时形成完整的部分候选。成功响应文件支持跨会话继续；建议全部完成前不 apply，这样原始输入基线保持有效。不自动重跑模型或重写已完成响应。

导入保留 `external` 来源、实际工具/模型、请求/响应摘要和译文 PO 快照，不伪装人工保护或 Gemini API 来源。apply 同时复核配置、原始 PO/state 和导出批次/响应文件，导入后修订了响应则需重新 import 到新候选。输入变更后旧 bundle 过期，不可改摘要强行套用。批次目录与正式项目输入分开，保留到应用完成；后续来源验证依赖项目的 PO 快照，建议另保留响应供审核。

## 按需 Gemini 补空（可选）

只有不带 `--cache-only` 的 `fill` 能调用模型。`plan`、`check`、`compile`、`apply`、`export`、`responses`、`import` 均无需密钥、不访问模型。`fill` 先执行同样的来源合并及人工保护，只请求尚未保护的缺口。

```sh
# 用系统密钥管理器或交互式输入设置 GEMINI_API_KEY；不要写入配置或 shell 历史。
read -r -s GEMINI_API_KEY
export GEMINI_API_KEY
pokeeper fill --config project.toml --cache .pokeeper/gemini-cache.json --candidate review-ai-001
unset GEMINI_API_KEY
# 整体审查 review-ai-001，再 apply；无需逐条点击。
```

配置 `[gemini]` 中的模型、批量大小（1–16）、重试上限（0–5，0 表示仅首请求一次）、超时（1–300 秒）、项目提示、术语字典及 `source` / `translation` 例句表。小批量串行发送完整身份、上下文、两种原文、开发者/译者注释与源码位置；术语按本批筛选，例句最多三条。响应必须保持身份对应、准确复数数量、占位符、换行及项目规则。

2026-09-28 曾按创作及翻译证据选择 `gemini-3.7-flash`，依据和局限见 [历史模型选型](docs/gemini-model.md)。CPH API 实测中，3.7 返回503，3.8也多次503，3.5 Flash-Lite 曾成功生成小批译文，详见[历史探针记录](cph-translation/model-comparison.json)。用户随后确认没有 API 额度，**CPH 当前改用 Antigravity 内置模型与上述离线文件流程**；保留旧配置用于匹配历史完成缓存，不代表要求继续调用该 API 型号。Antigravity 实际可用模型应以其界面为准。API 后端不会自动切换模型，采样使用服务默认值。

完成的结果会保存并在重跑时重新检查、复用。有限重试仅适用于明确可重试错误；超时、连接中断及中途退出留下的请求标为结果未知，默认不自动再次调用。确需重试时显式添加 `--retry-unknown`，**可能再次计费**。同一项目/语言/条目的未解决未知请求在配置变化后仍需这个显式选项。更换配置、模型或条目语境会使已完成缓存失效，也可能产生费用。不提供金额硬上限，不承诺绝不重复收费。缓存包含请求摘要及译文，建议保持私有且排除 Git；密钥仅从环境读取，不存入状态、候选、报告或镜像。

## 中断、分支与文件一致性

维护项目的 `.gitignore` 可排除 `.pokeeper/gemini-cache.json`、`.pokeeper/*.lock`、`.pokeeper/*.pending` 和临时候选目录；不要忽略正式状态 JSON 或 `snapshots/`。排除 journal 不等于可以删除它，恢复前需保留。

一份版本化 `state.json` 保存上次完整 PO 的 SHA256、每条译文摘要、保护位和来源引用；`snapshots/<sha256>.po` 保存实际采用的原始字节，防止把历史翻译误标为最新上游。快照是只增内容寻址文件，不是第二个全局状态数据库。候选目录也记录所有输入摘要。

应用采用持久 journal 和进程锁，**不是跨文件原子事务**。PO 和状态之间中断时，`<state>.pending` 保留旧/新字节，普通命令拒绝继续：

```sh
pokeeper recover --config project.toml --action finish
# 或恢复应用前的两个文件：
pokeeper recover --config project.toml --action rollback
```

恢复仅接受目标仍为已记录的旧/新内容；遇到额外人工修改会拒绝覆盖。先保全修改并解决后再恢复，不要直接删除 journal。锁协调本工具进程，不能阻止不遵守锁的外部编辑器；应用期间应暂停外部写入。生成期间修改会在最终输入复核被发现；文件系统不提供对任意外部写入者的跨文件 CAS 保证。

PO 与状态可以在 PR 中暂时不一致，因为这正是只修改 PO 的工作流；基线快照必须能验证状态。若整个分支的 PO、状态和快照来自另一套历史且内部自洽，仅凭文件内容无法区分操作意图，应由版本控制审查保证同分支交付。Git 冲突不能用随意挑选“最新状态”解决。

## 一次性容器

镜像使用固定 Python 基础镜像摘要、Debian 软件包版本及 Python 哈希锁，原生与容器均运行 `pokeeper`：

```sh
podman build -f Containerfile -t po-keeper:0.1.0rc1 .
podman run --rm --userns=keep-id --network=none \
  -v "$PWD:/work" -w /work po-keeper:0.1.0rc1 \
  plan --config examples/demo/project.toml --candidate /work/review-container
```

后续 `apply` 使用相同 `/work` 挂载路径；候选记录绝对路径，不能直接拿容器候选在不同宿主路径应用。Docker 用同一 Containerfile（`docker build -f Containerfile`），运行可用 `--user "$(id -u):$(id -g)"`。`fill` 需移除 `--network=none` 并传 `-e GEMINI_API_KEY`；不要把密钥放入 build 参数。所有命令执行即退出，没有守护进程。

## 开发与发布候选

```sh
uv run --frozen --extra test pytest -q
uv run --frozen --extra test python -m build
uv run --frozen python scripts/verify_real_project.py --workdir /tmp/pokeeper-wget-validation
bash scripts/audit_lokit.sh
```

设计取舍见 [选型记录](docs/decisions.md)、[固定版 lokit 审查](docs/lokit-audit.md)。[CPH 示例及边界](docs/cph.md) 包括现有编译链和补充 PO 角色；[GNU Wget 实证](docs/real-project.md) 验证同一核心只改配置支持非 Cataclysm 三复数项目。[验证记录](docs/validation.md) 区分 PASS / FAIL / NOT_RUN / BLOCKED。

本任务不创建远程仓库、不发布包或镜像、不联系上游。当前许可证为 MIT；真实 Gemini 两条样例验收已通过。实际发行前确认名称可用性、维护者与许可归属、支持平台和发布凭据，并审校目标项目译文质量。
