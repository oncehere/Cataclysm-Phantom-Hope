# 开发版目标协议与本地核验契约

**现行本地契约与未部署边界：**个人 CDDA fork 和受控 CI/sync 入口现已存在，但本模块仍未成为远端发布器。目标仓库已明确；永久应用身份、四平台包、正式签名和每日公开发布依然需要各自的实际证据。带日期的当前进度见 [status.md](status.md)。

状态为 **IMPLEMENTED_NOT_DEPLOYED**。本模块只读取文件和输出 JSON，没有网络调用、
签名、上传、发布、删除、频道提升或修改 Git 引用的执行路径。所有输出的
`public_release_ready` 均为 false。它没有实现完整发布事务、远端互斥、版本号预留、
最终公开或超时补写；这些仍须后续在明确目标上实现和验证。

真实四平台目标、长期身份和签名 profile 尚未决定，故没有生成虚假的有效 manifest
或包。`project/release-prerequisites.json` 是实际缺口清单，始终明确 BLOCKED。
Linux 仅测试身份不能填成正式发布身份。单元测试只创建写明 MODEL ONLY 的无效包
字节及模拟 API 记录；这些测试不代表游戏、平台、密码学签名或 GitHub 验收。

## 输入和信任边界

`project/release-manifest.schema.json` 是 JSON Schema 2020-12 结构约束。
标准库检查器实现该文件实际使用的有限子集，并另做跨字段、来源和实际文件核验。
未知字段、重复 JSON 键、非有限值、空必需集合、重复目标/产物/检查均拒绝。

`verify` 必须收到由**独立可信控制器**生成的 expected 文件及独立传入的文件 SHA256；
不能从候选包顺手读取 expected 和 pin，也不能执行候选脚本生成审批事实。
expected 的顶层字段是：

| 字段 | 含义 |
|---|---|
| `schema_version`, `configuration_status` | 必须为 1、READY；缺真实配置不能置 READY |
| `decision_reference` | 目标/身份/检查/签名策略的授权决定记录 |
| `inputs` | asset_lock、target_config、check_policy、toolchain_config 的 SHA256，加 `policy_sha` |
| `manifest` | 控制器预期的完整事实；与候选清单逐字段一致 |
| `signing_requirements` | 每个 target 的 `{required, identity}`，不得由上传者自行降为可选 |
| `android_allocation` | 持久控制记录中的 candidate_id、version_code、last_published_version_code |

“可信”是部署时必须建立的权限/执行边界，CLI 不能只凭文件名证明它。
实际部署还必须从受保护版本执行检查器、schema 和策略。当前 local PASS 不声明该
边界已经部署，也不会变成可签名或可发布的令牌。

清单必须有覆盖 Windows/Linux/macOS/Android 四个平台的明确 target，每个至少一件非空包和
非空必需检查集合，所有来源绑定同一 source/tree/inputs 和显式 repository ID。
workflow ID/路径、event、run ID/attempt、架构、格式、build configuration、独立应用
ID、acceptance profile 等必须与 expected 一致。所有检查要求实际执行、PASS、
非空命令；kind=test 还必须有正测试数和正断言数。检查证据文件必须存在、非空且摘要相符。

实际包的大小/SHA256 与清单及控制器预期一致；路径穿越和符号链接被拒绝，不解包或
执行包内容。ABI、包结构、原生启动和签名验证由独立平台探针/固定工具产生可信事实；
本检查器不会通过查看一个文件扩展名推断这些事实。必要签名要求固定身份、独立验证
证据及其摘要，并把签名后的最终包摘要绑定到验证结果。它本身不运行签名工具。
所需可信 collector/平台探针与本契约的绑定尚未部署；本模块不解析包内 ABI/应用 ID、
JUnit 或 apksigner 输出。它只验证声明、独立 expected 与文件摘要的一致性。
Android 分配必须属于同候选、匹配清单且高于已公开最大 versionCode。

## 稳定身份与 CLI

规范化采用 UTF-8 JSON、按 key 排序、无额外空白、禁止 NaN/Infinity。
`inputs_digest` 是可信 inputs 的 SHA256。candidate_id 为 `cph-dev-` 加以下对象的
规范化 SHA256：`{schema_version: 1, source_sha: H, inputs_digest: D}`。
tag 为 `dev-` 加 candidate_id。日期、run、attempt 不进入逻辑候选身份。
这些名称是本地协议选择，不是永久品牌/应用 ID 决定。

```sh
python3 tools/project/release_contract.py prerequisites
python3 tools/project/release_contract.py identify --source-sha H --inputs INPUTS_JSON
python3 tools/project/release_contract.py verify \
  --manifest CANDIDATE_MANIFEST --expected TRUSTED_EXPECTED \
  --expected-sha256 INDEPENDENT_EXPECTED_FILE_SHA256 \
  --artifacts-root PACKAGE_DIRECTORY --evidence-root CHECK_EVIDENCE_DIRECTORY
python3 tools/project/release_contract.py state \
  --pages RECORDED_PAGES --trusted-state TRUSTED_STATE \
  --trusted-state-sha256 INDEPENDENT_STATE_FILE_SHA256
```

上面的参数名是接口说明，不是已存在的真实发布输入。命令只输出结果；退出码
0=本地操作成功，1=拒绝/失败，2=prerequisites 确认 BLOCKED。
`verify` 的 PASS 仅名为 `local_contract_verified`。

## 完整分页的只读状态识别

`state` 读取已记录并规范化的 GET 观察，不自行请求 API，也不保证记录实时性。
每页包含 repository_id、page、http_status、error、next_page、releases。页码从 1
连续递增，最后 next_page 必须为 null；缺页、重排、403/429/404、网络错误均拒绝，
不能变成“暂无版本”。只有完整、可见的 200 空列表才能表示没有记录。

release 条目保留 GitHub 的 id/draft/prerelease/tag_name/published_at，另添加独立
只读 tag 解析的 `tag_source_sha` 和取得 manifest 后算出的 `manifest_sha256`。
不能把 `target_commitish` 字符串当作标签最终解析到 H 的证据。这里的规范化记录
不是声称 GitHub 原生 list 响应自带这两个证明字段。

trusted-state 顶层含 repository_id、requested、verified_receipts、blocked_candidates、
superseded_candidates、draft_visibility_verified、observations_digest。最后一项是可信
只读 collector 所记录完整 pages 数组的规范化 SHA256，防止上传者自行篡改 draft 等观察字段。
requested 含 source_sha、inputs_digest、
candidate_id、tag、android_version_code。每个收据含 release_id、同形状 identity、
manifest_sha256、contract_verified；已公开条目必须有独立核验通过的收据。
草稿预留可以尚未 contract_verified，但不能进入最后有效开发版结果。
权限不足以查看草稿时必须拒绝缺失推论，不能重复预留同一候选。
全部可信收据都必须对应当轮的受控 release 观察；已知草稿删除、改名或记录缺失时
拒绝分类并要求对账，不能因此忘记已预留的 versionCode。

最后有效开发版按可信、单调的 Android versionCode 选择，排除 draft 和封禁/取代项，
不依赖 API 第一项或发布时间先后。所有已公开版本的分配仍计入防倒退检查。
同候选草稿返回 RETRY_SAME_CANDIDATE，已公开返回 ALREADY_PUBLISHED，旧候选或
封禁候选保持 BLOCKED。任何候选/版本分配重复、重试改号或 tag/manifest 不匹配均拒绝。
受控开发 tag 被改成非 prerelease 会失败；manifest 也只允许 development 频道。
这不是声称 GitHub 底层 contents:write 权限禁止修改频道。

2026-09-26 实际复核的官方语义：list releases 提供已公开版本，草稿仅对有 push
权限者可见；支持 page/per_page，latest 排除 prerelease/draft。
[GitHub Releases REST 文档](https://docs.github.com/en/rest/releases/releases)。
必须继续读取 Link 中的下一页，直至没有下一页。
[GitHub 分页文档](https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api)。
403/429 可表示限流；404 也不能一概解释为资源不存在，因为认证/授权可能隐藏私有资源。
[GitHub REST 排错文档](https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api)。
这些官方资料校验了接口语义，不是本项目的远程运行证据。

## 本轮测试与后续

模型测试覆盖 T09/T10 的缺包、空包、声明的 ABI/输入/来源与 expected 不符，T11/T12 的分页及读取失败，
T13 的固定候选重试与已公开去重，T16 的版本号/签名身份/签名后包变化，T21 的 stable
与开发频道提升拒绝。还覆盖零测试、实际证据变化、路径穿越、符号链接及错误可信输入。

恢复顺序：先固定目标和四平台身份/profile，产出真实原生证据与独立签名核验收据；
建立持久候选/versionCode 状态与具备草稿可见性的只读查询，固定 expected 的来源；
然后执行本地 verify/state。最终发布前的重新读取、暂停/封禁复核、串行事务、上传核验、
响应丢失恢复及实际公开验证仍需另一个受控实现。不能据本模块启用每日公开发布。

## 目标发布协议

本节承接执行规格原 E6/§8，是**尚需实现并真实验收的目标协议**；上文 CLI 仍只是本地核验器，不因此获得签名、上传、事务或公开能力。发布必须满足 [§6.2](execution-spec.md#62-发布)，先完成不公开的真实端到端演练，再启用每日开发版；不使用占位包公开演练。每天一次是需求，03:17 UTC 是可逆默认时刻；失败候选可重试，已成功候选不重复公开，稳定版入口保持关闭。

- 身份绑定固定源码 H、规范化输入摘要、稳定 candidate/tag、独立 run/attempt；重试保留候选身份和已预留的 Android versionCode，失败预留不分给另一候选，后续公开版递增。记录实际 runner、工具链和依赖，不以同 SHA 声称字节级可复现。
- 以持久受控状态管理预留、构建、核验、草稿齐备和公开，失败另记 attempt。固定并发组可串行化整个事务，禁止自动取消正在公开的事务，不占用同步/PR CI 的并发组。并发互斥不是幂等证明，不假定 FIFO 或只依赖 runner 临时磁盘。
- 完整分页查询有效开发版和草稿，核验 tag/manifest；不用 `/releases/latest` 查开发版，不把权限、限流或网络失败视为无版本。重试先对账；旧候选晚到不得覆盖新版本或复活封禁候选。
- 四平台使用同一提交及锁定资源，产物不可跨候选补齐。Actions artifacts/草稿可作暂存，但公开仓库 artifacts 不保证保密，单平台暂存包不作为完整开发版公告。
- 构建不携带正式签名或写权限。签名在独立可信环境用固定工具执行，不重跑候选 Gradle/CMake/脚本；先完成必要对齐，签后独立核验并计算最终摘要。签名/发布不复用候选执行环境或可执行缓存。
- 先建草稿，上传并核验全部预期资产、source/tree/inputs、repo/workflow/run/attempt、版本、架构、资源、签名指纹及摘要；公开前重读暂停、封禁、候选状态和远端资产，最后统一公开为 prerelease。公开超时先查同 candidate/tag/manifest：已完成则记成功，否则才补做，不另建候选。公开标签及资产不覆盖，问题版通过受授权的公告和新版本修复。
- immutable releases 只能提供部分保护，不能单独约束 stable 授权；开发入口拒绝 stable/频道提升，不能把 `contents:write` 的底层权限描述成禁止修改频道。运行状态与源码历史分离，见 [控制手册](operator-controls.md)。

可信控制器预期与 manifest 至少表达：schema/candidate/source/ccb_integrated/policy 身份、inputs_digest、tag/version_name/android_version_code；每平台 target/OS/arch/format/build configuration；每产物名称/大小/摘要/repository/workflow/event/run/attempt/tested source/tree/signing；每检查 ID/必需范围/环境/实际执行状态/证据；素材来源、工具链、许可证、已知问题、人工验证及未验证范围。此为数据含义要求，实际结构由 schema 和已审查实现维护，不能让上传者自报 success 即放行。

历史核验来源（随原规格迁移，本次未重新在线核验）：[Android versionCode](https://developer.android.com/studio/publish/versioning)、[并发控制](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)、[apksigner](https://developer.android.com/tools/apksigner)、[immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases)。分页来源见上文本地状态说明。

## 验收场景

以下为保留的规范性场景；是否已通过须查实际证据，不由本表或模型测试推断。

| 编号 | 场景 | 预期 |
| --- | --- | --- |
| T09 | 四平台中一包缺失、为空、错误 ABI、错误 H 或资源摘要 | 不签发完整开发版。 |
| T10 | 同名 artifact 来自别的 repo/run/attempt | 拒绝签名/发布。 |
| T11 | 没有 stable，只有分页后的 prerelease | 正确识别最后有效开发版。 |
| T12 | 读取发布状态时权限/限流/网络错误 | 明确失败或重试，不当作无版本。 |
| T13 | 同候选昨日失败今日无新提交、已成功候选重复触发 | 前者允许重试；后者不重复公开。 |
| T14 | 定时和手动运行重叠，旧候选晚完成 | 无覆盖、重复或版本倒退。 |
| T15 | 最终公开成功但响应丢失 | 查询远端后恢复，不重复发布。 |
| T16 | Android versionCode 回退、签名身份错误、签名后包被改 | 拒绝长期升级发布。 |
| T21 | 试图从开发发布入口传入 stable、或提升 prerelease | 受控开发入口拒绝；不能宣称 contents:write 或 immutable 在底层 API 权限上禁止频道变更。 |
