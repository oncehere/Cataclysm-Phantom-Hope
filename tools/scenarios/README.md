# Windows 小场景验收入口

这个标准库 Python 工具只做场景清单、隔离目录、启动与重跑。Lua/JSON 仍是游戏内容；
不引入场景框架，不导入 AI 同伴包，不读取真实存档、配置或密钥。
现有 `TEST_DATA` 继续仅用于原生测试，玩家世界不用启用它。

在源码根目录的 PowerShell 中运行（需要 Python 3.10+；`py -3` 可换成实际 Python 路径）：

```powershell
py -3 tools/scenarios/run.py list
py -3 tools/scenarios/run.py prepare story-delivery --game E:/CPH-test/app/cataclysm-tiles.exe --basepath E:/CPH-test/app --run-dir E:/CPH-test/runs/story-001
py -3 tools/scenarios/run.py check-mods --run-dir E:/CPH-test/runs/story-001
py -3 tools/scenarios/run.py run --run-dir E:/CPH-test/runs/story-001
# 在游戏中保存并退出后，使用同一目录重进：
py -3 tools/scenarios/run.py rerun --run-dir E:/CPH-test/runs/story-001
```

`--game` 必须是与这份数据匹配、支持 Lua 的游戏程序；`--basepath` 是游戏资源根，
源码内运行可省略它。`--source-root` 默认本工具所在源码树。
新目录内只有 `userdata/`、`config/`、尝试记录和 `CHECKLIST.md`；工具总是显式传入
隔离 `--userdir` 和 `--configdir`，不复制现有配置和世界。
GUI 依照 `--basepath` 查找 `data/` 与 `gfx/`，不额外指定会改变图形目录的 `--datadir`；
只有加载检查把 `--source-root` 下的 `data/` 用作 `--datadir`。资源目录必须已有与 source-root 相同的场景文件，缺少时准备会拒绝；
可直接用源码根作为 `--basepath`，或先更新独立测试 app 的数据。
准备时在这个新隔离 `config/user-default-mods.json` 写入清单的默认 Mod，
使用本体已有配置契约。创建新世界时在 GUI 核对清单即可，不用重复添加 Mod；
它不影响已有世界，也不伪造世界存档或自动完成剧情。
旧版本工具准备的运行目录仍可重跑，不会自动补写或改动它的配置。

`run` 和 `rerun` 是相同操作，都复用这个目录，便于存读档验证。
从干净状态再来一次时，用新的 `--run-dir` 执行 `prepare`。
工具拒绝覆盖既有目录；不提供清空真实存档的命令。
二进制、场景文件或准备时的 manifest 变化后，要准备新的运行目录。
运行中的 `launch.lock` 防止重复启动同一份隔离存档；崩溃遗留锁时，先确认该游戏已退出，
再手工删除这个运行目录里的 `launch.lock`。
`--dry-run` 可用于 `run`、`rerun`、`check-mods`，只显示 argv，不启动进程。

三个清单分别是：

| ID | 内容 | 当前自动化边界 |
| --- | --- | --- |
| `story-delivery` | 非 AI 终端交付、分支、取消缺货、存读档 | 提供独立 Lua 素材；菜单与游玩结果人工观察 |
| `companion-actions` | follow / move / gather / craft | 复用现有原生任务能力与小物料；不自动授权或请求模型 |
| `interruption-recovery` | 优先接管、模型断开、活动中存读档 | 人工步骤；不把离线候选重放冒充在线通过 |

两个 AI 清单明确启用并检查 `ccb`、`cph_ai_companion`；非 AI 的 `story-delivery`
仍只依赖 `ccb` 与独立场景 Mod。

使用已经内置 `data/mods/cph_ai_companion` 的 Windows 测试包时，将 source-root 和 basepath
都指向同一份 `app/`，让加载检查和 GUI 使用包内相同的数据。保持隔离 userdata 中没有
第二份 AI wrapper；重复的 Mod ID 会使加载被拒绝。

```powershell
py -3 tools/scenarios/run.py prepare companion-actions --game E:/CPH-test/app/cataclysm-tiles.exe --source-root E:/CPH-test/app --basepath E:/CPH-test/app --run-dir E:/CPH-test/runs/actions-001
py -3 tools/scenarios/run.py check-mods --run-dir E:/CPH-test/runs/actions-001
py -3 tools/scenarios/run.py prepare interruption-recovery --game E:/CPH-test/app/cataclysm-tiles.exe --source-root E:/CPH-test/app --basepath E:/CPH-test/app --run-dir E:/CPH-test/runs/interruption-001
py -3 tools/scenarios/run.py check-mods --run-dir E:/CPH-test/runs/interruption-001
```

使用独立同伴包且游戏数据中尚无 `cph_ai_companion` 时，按
[同伴安装说明](../../companion/docs/install.md) 将 wrapper 部署到这份隔离 userdata 的 Mod 目录。
工具不自动安装运行时或读取密钥。`check-mods` 缺少该 Mod 时应失败，不能将只加载核心
视为同伴场景通过。使用旧 AI 清单准备的目录保留原数据；重新 `prepare` 一个新目录
才能预设与加载检查更新后的 Mod 列表。

`attempts/*.json` 只记录启动时间、命令、进程退出码；`gameplay` 始终是 `NOT_RUN`。
在 `CHECKLIST.md` 填实际观察与 PASS/FAIL。加载检查通过、程序正常退出或台词表示成功，
都不能代替物品、位置、活动和重进后的实际结果。AI 场景的模型调用另按当轮授权执行。

新增场景时复制一个 `manifests/*.json`：稳定 `id`、明确 `mods`、仅列本场景输入的
`fixture_files`、准备步骤和可观察的 `checks`。不要填写自动通过的结果。
首个示例实现见 [Scenario_Story_Smoke](../../data/mods/Scenario_Story_Smoke/README.md)，
接口示例源于 [Lua_First_Example](../../data/mods/Lua_First_Example/README.md)。

```powershell
py -3 -m unittest discover -s tools/scenarios -p 'test_*.py'
py -3 -m unittest discover -s tools/lua_api -p 'test_*.py'
```

纯 Lua 内容还要用匹配的 Lua-enabled native binary 跑 `check-mods`；
Python 测试验证隔离、重跑、锁和输入变化拒绝，不能证明游戏内分支或存读档已通过。
`test_story.lua` 还可用本机现有 Lua 解释器从源码根目录运行，使用实际 `main.lua`
和小型 `ccb` 替身验证取消、缺货、单次提交及再次进入；它同样不代替原生存档验收。
