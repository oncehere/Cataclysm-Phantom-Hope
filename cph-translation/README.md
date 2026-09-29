# CPH 中文补译

这是与游戏仓库分开的本地翻译项目。**当前由 Antigravity 自身模型翻译小批 JSON，本地 PO Keeper 校验和合并，不调用 Gemini API。** 不运行旧的 `run_fill.py` 或模型探针。

风格为克制的黑色幽默、一本正经的冷笑话；保留原意和人物身份，不给按钮、数值、操作说明强加笑话。见 [style.md](style.md) 和可直接转交的 [Antigravity 执行提示词](ANTIGRAVITY_HANDOFF.md)。

## 当前状态与修订

Antigravity 已完成266批、3,078条补译并应用 review-09，正式目录117,224条均已填写。独立复核确认原256条人工保护记录完整保留、MO可复编译，同时发现两个条目的语义偏差。

2026-09-29按用户要求修订：0067 的 mid-40s 改为“四十五岁左右”；0188 改为“篷车的车厢后部”，并纠正指向同一个实体的三处复数代词。修订由当前PO的基线比较识别为受保护编辑；review-11已应用，保护数由256变为258，external来源由3,078变为3,076，原316条Gemini及113,574条上游译文保持不变。实际应用与验证以 [修订验收](corrections-validation-20260929.json) 为准，原文/修订/理由见 [修订记录](review-corrections-20260929.json)。

本项目的 [Antigravity 原执行提示](ANTIGRAVITY_HANDOFF.md)、原始 requests/responses 和 review-08/09/10 的摘要清单、报告作为历史审核资料保留。它们引用的旧输入基线已过期，且清单包含原机器绝对路径；**不要在当前工作PO上重放旧 import/apply**，也不能宣称跨路径clone可直接重放历史包。

## 后续维护

从工具项目根目录运行，确保 GNU msgfmt 在 PATH。原生入口示例：

```sh
.venv/bin/pokeeper check --config cph-translation/project.toml
# 生成新的维护候选，先审查 report 和 PO，再应用；每次使用新目录名。
.venv/bin/pokeeper plan --config cph-translation/project.toml --candidate cph-translation/review-next
.venv/bin/pokeeper apply cph-translation/review-next
.venv/bin/pokeeper compile --config cph-translation/project.toml --output cph-translation/zh_CN-reviewed.mo
```

只有新POT/上游更新产生缺口后才从新的候选 `export` 批次，让 Antigravity 翻译并通过 `responses`、`import` 校验。无需API，现有有效译文及保护位仍按既定优先级处理。旧未知/失败API记录保持历史状态，不能视为成功或自动重试。

直接修改工作PO会被下一次plan识别并保护；改注释/排版不会被误判。未改写的普通external译文可被后续有效上游替换。工具的check/compile PASS不代表全量语义精校，游戏内加载仍未验证。

PO/state及被引用的全部 `.pokeeper/snapshots/` 和当前本地PO/POT输入需要一并提交。历史完整候选、API缓存、备用MO恢复PO和编译产物留在本地，不纳入Git；历史manifest/report可供审核，但不构成可重放的完整候选。来源许可证及署名保存在inputs/notices。PO/state应用使用journal恢复，不是跨文件原子事务。

## 输入与来源

- CPH `main@a43a8f2f270994dad716ab067c48aad7c2eeaee3`：从只读Git归档复制源码，在临时目录运行已有提取器，得到117,224条模板；251条原CPH补充译文保留并保护，后来另有5条人工修订。[提取记录](inputs/source-manifest.json)
- CDDA：官方翻译构建 [run 36497683966](https://github.com/CleverRaven/Cataclysm-DDA/actions/runs/36497683966)，artifact `11003869087`。
- CCB：官方翻译构建 [run 35769923993](https://github.com/CrimsonCrossBunker/Cataclysm-Cleanwater-Bomb/actions/runs/35769923993)，artifact `10715293685`；编译消息与CPH锁定MO一致。
- 摘要、构建提交及署名见 [upstream-sources.json](inputs/upstream-sources.json)。PO-Revision-Date 不充当快照时间；恢复自MO的备用PO仅作证据，不加入优先级。

优先级为受保护人工 → 当前有效CDDA → 当前有效CCB → 当前有效译文 → 显式补空。过去 Gemini SDK、探针和中断记录保留为历史证据，不代表当前应继续API调用。

## 范围与许可

提取覆盖项目提取器标记的消息。16个实际Lua文件提取得到0个标记消息，不能据此宣称未标记或动态文本全部覆盖。

游戏文本/翻译沿用上游 CC BY-SA 3.0 等权利和署名，见 [来源许可](inputs/notices/ccb-bcb85682/LICENSE.txt) 及来源credits，不属于工具MIT许可。本目录排除在工具wheel/sdist和容器构建上下文外。

游戏源码工作树只读，未安装MO、访问真实obj-lua/或存档，未恢复同步。完整PO大于现有CPH补充PO，安装位置、加载优先级和游戏内显示仍待接入验证。
