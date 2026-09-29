# lokit 固定版本兼容性审查

审查日期：2026-09-28。审查版本为 [minios-linux/lokit `a28493ba832ffc5506d4e45f4ddfdc5623931aa9`](https://github.com/minios-linux/lokit/tree/a28493ba832ffc5506d4e45f4ddfdc5623931aa9)，该次检出的 master HEAD。结论仅适用于此 SHA；不把早期审查结果当作现在的事实。

本工具选择 **GNU gettext + polib + 单一官方 Google GenAI SDK 补译后端**。lokit 的 Google provider 确实直接调用 Gemini API，不依赖 Gemini CLI。未采用 lokit 的原因是当前候选输出流程会丢失严格验收需要的原始返回信息，不是缺少模型接口。

## 方法和共同样例

`tests/fixtures/compatibility.json` 同时用于本工具和 lokit 审查，包含同文不同上下文、缺省及显式空上下文、波兰语三个复数、占位符、换行、注释与来源位置。`scripts/audit/lokit_probe_test.go` 是本项目原创的特征测试；脚本把它临时加入固定版 lokit 的 `translate` 测试包，调用未经修改的实际解析、提示词和 Google provider 实现。HTTP 只连 `httptest` 本机假服务器，假密钥为固定 `fake-key`。未调用真实 Gemini。

复跑（Go >= 1.23.6、Git 和网络下载 Go 依赖）：

```sh
scripts/audit_lokit.sh
# Nix 环境也可运行：
nix shell nixpkgs#go --command bash scripts/audit_lokit.sh
```

脚本创建临时目录、按完整 SHA 检出源码、验证 SHA、运行 `go test ./translate -run '^TestAudit' -count=1 -v`，退出后清理该目录。Go 模块版本来自上游的 `go.mod` / `go.sum`；本次 Go 版本为 1.26.7 linux/amd64，关闭 CGO。这里的 PASS 表示**成功重现并断言所述行为**，不能读作 lokit 符合全部产品需求。完整实际输出见 `docs/lokit-audit-results.txt`。

## 重新核实的结果

| 要求/探针 | 实测结果 | 影响 |
| --- | --- | --- |
| Google provider | PASS：请求 `/v1beta/models/fake-model:generateContent`，认证在 `x-goog-api-key` header；有效共同样例通过 | 可直接使用 Gemini API；历史上对 CLI 的担心不成立 |
| 条目对应 | PASS：固定版使用不透明 ID，响应可重排；缺项、未知或重复 ID 被拒绝 | 不能继续沿用“仅靠返回位置”的旧结论 |
| 上下文和注释 | 已重现：默认逐条提示词包含 source references，不包含 `msgctxt`、译者注释或开发者注释 | 需要外层补充语境 |
| 提示词薄封装 | PASS：通过现有自定义 system prompt 携带共享样例的上下文和开发者注释；无需修改 lokit | 按上下文分组、附元数据可以解决提示词缺失 |
| 缺省 / 空上下文 | 已重现：`msgctxt ""` 经过其 PO 解析/写出后被省略 | 完整 PO 必须在外层保存；侧表还需保存原身份 |
| 三复数：返回 scalar | 已重现：一个字符串被复制成三个译文并验收通过 | 无法事后知道三个相同译文是模型原样返回还是补齐 |
| 三复数：只返回两个 | 已重现：末项补成第三项并验收通过 | 候选 PO 的复数数量检查无法发现原始返回数量错误 |
| 三复数：返回四个 | 已重现：第四项丢弃并验收通过 | 候选 PO 不再保留原始错误信息 |
| `retries=0` | 已重现：无效响应对应关系产生 4 次请求，即首请求 + 3 次重试 | 显式 0 不是禁用重试；外层不能精确控制每个模型请求 |

源码定位均绑定固定版本：

- [Google dispatch 与原生 HTTP](https://github.com/minios-linux/lokit/blob/a28493ba832ffc5506d4e45f4ddfdc5623931aa9/translate/translate.go#L854-L864)、[endpoint/header](https://github.com/minios-linux/lokit/blob/a28493ba832ffc5506d4e45f4ddfdc5623931aa9/translate/translate.go#L1169-L1176)。
- [ID 生成和匹配](https://github.com/minios-linux/lokit/blob/a28493ba832ffc5506d4e45f4ddfdc5623931aa9/translate/translate.go#L1817-L1878)。
- [复数逐条提示词](https://github.com/minios-linux/lokit/blob/a28493ba832ffc5506d4e45f4ddfdc5623931aa9/translate/translate.go#L1918-L1936)、[单数逐条提示词](https://github.com/minios-linux/lokit/blob/a28493ba832ffc5506d4e45f4ddfdc5623931aa9/translate/translate.go#L2577-L2592)。
- [PO context 字段是非可空 string](https://github.com/minios-linux/lokit/blob/a28493ba832ffc5506d4e45f4ddfdc5623931aa9/internal/format/po/po.go#L20-L40)、[空值不写出](https://github.com/minios-linux/lokit/blob/a28493ba832ffc5506d4e45f4ddfdc5623931aa9/internal/format/po/po.go#L477-L480)。
- [复数补齐/截断](https://github.com/minios-linux/lokit/blob/a28493ba832ffc5506d4e45f4ddfdc5623931aa9/translate/translate.go#L2009-L2054)、[重试缺省值](https://github.com/minios-linux/lokit/blob/a28493ba832ffc5506d4e45f4ddfdc5623931aa9/translate/translate.go#L395-L400)。

## 为何不继续做薄封装

已实际验证最有希望的组合：外层持有完整 PO / 身份，向临时缺口 PO 注入分组的语境提示，lokit 只提供候选。上下文和空上下文往返问题可以隔离。然而，上表三个非法复数响应在翻译函数内已经变为合法数量，外层再对候选 PO 执行 `msgfmt` 和数量检查也无法判定原始错误。这是一种信息丢失，不是再加一条提示词或格式检查可以可靠补救。

若继续采用 lokit，至少需要维护其内部复数 parser 的严格模式、显式 0 重试语义、原始响应/请求状态出口，或者把每个复数拆成伪单数再重组并绕开其原来的身份和复数逻辑。后者会重复实现大部分本项目必须掌握的请求协议、验收和持久化。这超出“本工具只管来源和保护，lokit 只做候选”的薄封装范围，也给 Python 工具增加 Go 二进制和私有 patch 生命周期。

因此直接复用官方 Google GenAI SDK 的传输、认证和类型支持，由一层小而明确的代码生成结构化批次、校验原始结果、记录完成/未知请求；不重新实现 PO parser、模型 HTTP 客户端或通用翻译平台。不保留第二套 lokit 补译后端。后续独立的 SDK 真实 API 验收见 [验证记录](validation.md)；本节 lokit 探针始终仅用假响应。

## 可独立向上游提出的通用修复

这里只整理建议和可复现特征测试，**没有联系、发 issue 或提交 PR**。这些不依赖 CPH：

1. PO Entry 区分不存在的 context 和显式空 context，并让序列化与身份生成保真。将当前 empty-context 特征断言改为保真回归断言。
2. 明确的严格响应模式：对单复数类型、精确复数数量拒绝不一致，不自动 scalar 复制、数组补齐或截断。保持现有宽松模式可另行兼容。
3. 区分重试参数未设置与显式 0；分别测试 API 错误重试和解析错误重试的请求总次数。
4. 逐条提示词携带 `msgctxt`、开发者注释和译者注释，结构化隔离元数据，避免将注释当指令。保持来源 references。
5. 提供结构化原始响应、最终接受结果及请求是否确定失败的事件出口，让外层能可靠实现审计/恢复；不要把网络断开等不确定失败自动表达为确定未计费。

本工具的 audit 测试故意绑定旧 SHA；上游修复后，应换新 SHA、调整预期并重新运行共同样例，不能静默移动审查版本。
