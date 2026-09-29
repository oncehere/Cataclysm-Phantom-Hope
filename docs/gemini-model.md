# Gemini 模型选择

核查日期：2026-09-28。面向游戏 PO 的英译中、人物语气与原意保留，选择 **`gemini-3.7-flash`**，写入通用演示及 CPH 示例。核心仍要求配置显式指定模型，不硬编码默认型号，不引入第二套后端或自动切换模型。

这是结合现有证据的工程选择，并非已经证明它在所有语言或角色扮演任务上最强。更重视忠实翻译和保留角色口吻，不把自由续写能力直接当成翻译准确率。

## 依据

| 证据 | 观察 | 适用边界 |
| --- | --- | --- |
| [Synthorai 作者翻译实验](https://synthorai.io/blog/llm-translation-quality/)，2026-08-29 | 英译简中时，3.7 Flash 对固定 GPT-5.6 Sol 基准的非平局胜率 26%，3.1 Pro 为 17%；3.7 的文学文本分组为 60% | 52 段英语、9 种目标语言、LLM 裁判，厂商自评；这些百分比不是正确率，也不是两款 Gemini 的直接对战结果。没有 3.8，不能证明 3.7 翻译优于 3.8 |
| [Arena 创意写作类别](https://arena.ai/leaderboard/text/creative-writing)，页面日期 2026-09-25 | 3.7 Flash high：1492±10；3.8 Flash high：1482±10；3.1 Pro Preview：1480±6 | 区间重叠，Flash 两项标为 preliminary，不能声称显著胜出；创意写作并非中文多轮角色扮演 |
| [EQ-Bench Creative Writing v3 固定数据](https://github.com/EQ-bench/EQ-bench-site/blob/108382e3f5017dce6f90c643e6bb4842825f62df/creative_writing.js)，提交日期 2026-09-24 | Elo：3.7 Flash 1723.2、3.8 Flash 1747.9、3.1 Pro Preview 1491.3、3.5 Flash-Lite 1559.1 | 英语创作、LLM 评分；支持 3.7/3.8 的文体表达能力，不能解释为中译质量或角色一致性的直接胜率 |
| [Last Translation Benchmark v1 论文](https://arxiv.org/pdf/2609.04173)，2026-09-03，表 2 | 3.1 Pro 在困难翻译规则验收中明显强于 3.5 Flash-Lite | 该表没有 3.7/3.8，不能据此排它们的名次；也提醒我们不能用文字流畅代替准确性 |

3.8 Flash 是接近的备选，其 EQ 英语创作成绩更好；但本次找到的英译中实证对 3.7 更直接，故优先选 3.7。[EQ 长篇写作](https://eqbench.com/creative_writing_longform.html)固定数据中没有 3.7，不能推断长篇能力与 3.8 相同。目前未找到能覆盖上述型号的同一中文多轮角色扮演横评。没有采用 Reddit 轶事或通用编程榜作为主要选型依据。

## 运行设置与代价

Google 将 [3.7 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.7-flash)列为 stable，支持结构化输出及 low/medium/high thinking。示例每批 4 条、串行、有限重试，CPH 请求超时为 120 秒。保留模型的服务端默认采样和推理设置；这不等同于复现 Arena 的 high 配置或 EQ 的测试参数。

移除旧后端固定的 `temperature=0`：Google 的 [Gemini 3 指南](https://ai.google.dev/gemini-api/docs/gemini-3#temperature)推荐默认采样，最新[迁移说明](https://ai.google.dev/gemini-api/docs/latest-model#migration-checklist)也要求移除 temperature/top_p/top_k。生成策略协议升到 2，记录 `server-default-sampling`；旧完成缓存不会冒充新策略结果，旧的结果未知请求仍需显式允许重试，可能再次计费。

[官方标准 API 价格](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.7-flash)：截至 2026-12-31 每百万输入/输出 token 为 $0.75/$3.75；2027-01-01 起为 $1.50/$7.50，输出包含思考 token。小批串行不是折价的 Batch API。按质量选型，没有宣称可以精确硬封顶费用。

## 本地验证与尚缺证据

选型阶段没有发起付费模型请求。随后实际 CPH 补译发现 3.7 返回 503，3.8 的单条探针与少数实际批次虽成功，但大批次多次返回 503；3.1 Pro 返回 429。3.5 Flash-Lite 用同一条生存 RPG 俚语样例快速返回，措辞也更自然地保留了“catch these hands”的冷面威胁。因此 CPH 当前选择 3.5 Flash-Lite 以完成大规模工作。这只是小样本的可用性与译文观察，不能视为盲测或型号总体质量排名。[实际逐型号记录](../cph-translation/model-comparison.json)及[补译进度](../cph-translation/README.md)给出边界。

此前 `gemini-3.5-flash-lite` 的两条真实 API 样例是历史连通性/格式验证，不是这些型号的盲评，也不是本次新采样策略的实测。

- **PASS**：离线 SDK 假客户端确认不发送采样覆盖；旧完成缓存失效、旧未知请求保护仍有效。
- **FAIL**：`gemini-3.7-flash` 本次生成接口验收；没有合格译文，见 [失败记录](../cph-translation/api-diagnostic.json)。CPH 3.5 Flash-Lite 的 API/格式批量验收以补译结果为准，风格仅以单样例探针观察，见[翻译交付记录](../cph-translation/README.md)。
- **NOT_RUN**：CPH 代表性术语、讽刺/口语/人物身份、含标签对白的人工盲评。

模型建议可投入候选生成配置，但语言质量应由维护者审查完整 PO。未来对比时保持同一批真实条目、完整语境、术语、参数与判据，再据结果更新型号；无需改变来源合并和人工保护核心。
