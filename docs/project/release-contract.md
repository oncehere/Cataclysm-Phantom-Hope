# E6 本地开发版契约

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
