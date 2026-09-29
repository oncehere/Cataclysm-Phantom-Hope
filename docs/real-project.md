# 独立 gettext 项目验证

固定样本为 GNU Wget **1.25.0** 的完整 `po/wget.pot` 和 `po/pl.po`、`po/ru.po`。两种语言均包含真实三复数译文，与 Cataclysm 无关。来源为 [GNU 官方发布目录](https://ftp.gnu.org/gnu/wget/)，[官方 Wget 分发说明](https://www.gnu.org/software/wget/manual/html_node/Distribution.html) 指向同一版本的发布归档。只读取翻译及许可，不构建或运行上游代码。

固定归档：`https://ftp.gnu.org/gnu/wget/wget-1.25.0.tar.gz`

| 文件 | SHA256 |
| --- | --- |
| `wget-1.25.0.tar.gz` | `766e48423e79359ea31e41db9e5c289675947a7fcf2efdcedb726ac9d0da3784` |
| `po/wget.pot` | `1eec698763439e0680995ac1a4ee3c8d404bc9e3a7c51e4d11801609d78f63f4` |
| `po/pl.po` | `9d8c07a9f974247a2f1b0001242b29567ec7b5db87cbaa27aca9e71d30b56143` |
| `po/ru.po` | `86748d0ec7b0b33298efb4c2fd2ce94c9cbea36610b097f066e75e2fc38f5621` |
| `COPYING` | `f7dc7522e7e1be9227f3dc8de8b39a4d1d2471968c893af15f00c1a2076a0eec` |

哈希固定此次实际下载内容；本次未独立核验归档的签名。上游翻译和 GPLv3 COPYING 保留在验收临时目录，不复制为本工具的代码或测试许可。脚本只从归档读取指定的普通文件，校验逐文件哈希，不执行归档代码。

在已安装依赖且 `msgfmt` 位于 PATH 的环境运行：

```sh
python scripts/verify_real_project.py --workdir /tmp/pokeeper-wget-validation
```

离线复跑同一归档：

```sh
python scripts/verify_real_project.py --workdir /tmp/pokeeper-wget-validation-rerun \
  --archive /tmp/pokeeper-real-project/wget-1.25.0.tar.gz
```

`--workdir` 必须是新目录；脚本保存每条实际 CLI 命令、退出码、报告和摘要到 `evidence.json`。脚本为 pl/ru 只改变配置中的语言、复数规则及文件路径，用同一核心依次运行 `plan → apply → check → compile → plan → apply`。核对完整 POT 身份集合、所有有效译文精确复用、两个真实复数条目各三个译文的逐字相等，以及第二次更新 PO 字节一致；运行前后比较核心 Python 文件哈希。模型密钥从子进程环境移除，全部操作离线；可选下载只用于准备已固定验收样本。

实际生成配置保留为 [examples/wget-pl.toml](../examples/wget-pl.toml) 和 [examples/wget-ru.toml](../examples/wget-ru.toml)，复制到脚本准备的工作目录即可使用；核心不含 Wget 分支。Wget 的长帮助文本在翻译时会重新折行，所以仅在配置中设 `preserve_newlines = false`，仍由 GNU gettext 检查必须一致的开头/结尾换行和格式约束。首轮使用严格换行数量规则时，pl 的 31 条、ru 的 62 条被明确报告为 `newlines` 冲突；未静默导入。调整这一项目规则后，全部有效译文精确复用。

## 实际结果

2026-09-28 Linux、Python 3.13.15、polib 1.2.0、GNU gettext 1.0：

```sh
PATH=/nix/store/db8cwzsgxv3lijvf18kqvjjbylm5hrpi-gettext-1.0/bin:$PATH \
PYTHONPATH=src .venv/bin/python scripts/verify_real_project.py \
  --workdir /tmp/pokeeper-wget-validation-final-2 \
  --archive /tmp/pokeeper-real-project/wget-1.25.0.tar.gz
```

**PASS，退出 0**。原始命令、逐项退出码、核心哈希及输出哈希见 [real-project-results.json](real-project-results.json)。

| 语言 | POT/输出有效条目 | 精确复用 | 真实复数 | 冲突/缺口 | 二轮更新 | MO 编译 |
| --- | --- | --- | --- | --- | --- | --- |
| 波兰语 pl | 599/599 | 599 | 2 条，每条 3 形式 | 0/0 | 字节一致 | PASS |
| 俄语 ru | 599/599 | 599 | 2 条，每条 3 形式 | 0/0 | 字节一致 | PASS |

俄语源 PO 的另外 74 条 obsolete 被单独报告并排除，没有恢复成有效译文。两个语言均只用本地输入和不同 TOML 配置运行相同核心，无模型密钥，也未请求 Gemini。

本验收脚本不调用 Gemini，Wget 构建和运行、其他操作系统均 **NOT_RUN**；真实 API 的独立验收以 [验证记录](validation.md) 为准。这组验证不替代语言质量审校或所有 gettext 项目的兼容性承诺。
