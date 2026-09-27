# E3 Linux 仅测试身份

**已完成的 Linux 局部回证与后续操作说明：**以下 PASS 绑定 2026-09-26 的测试提交和 `run4`，不表示永久应用身份或其他平台已验收。`run`、`run2`、`run3` 是保留的失败证据目录，不得把它们当作新输出。工作区外证据的相对路径说明见 [workspace-layout.md](workspace-layout.md)。

测试提交 `6cd76598a44` 在 Linux HOME 模式、显式隔离 user/config/save 目录下
通过安装、路径、73 项资源、核心数据加载和卸载检查，CCB 哨兵不变。
配置、编译和探针均退出 0；完整命令见工作区外
`../evidence/e3-linux-build-attempt4/commands.jsonl`，结果见
`../evidence/e3-linux-main-identity-run4/result.json`。当前阶段状态集中在
[status.md](status.md)，永久身份及平台条件见 [resume.md](resume.md)。

## 行为与接口

- 新 CMake 选项 `CPH_TEST_IDENTITY` 默认 OFF，仅允许原生 Linux，拒绝交叉构建及
  Android。只给 `project_identity.cpp` 设置该编译宏；前缀宏也局限于实际消费它们的
  main/path_info 单元。没有给整个目标新增身份宏。
- ON 时程序名为 `cph-isolation-test` 或 `cph-isolation-test-tiles`；菜单直接显示
  `CPH Isolation Test`，不再被继承 title 文件盖住；窗口标题、SDL 应用名和版本输出
  也使用测试名。安装的 desktop/AppStream/icon ID 为
  `org.example.cph.IsolationTest`，这些 ID 不能用于长期公开发布。
- HOME 用户目录为 `.cph-isolation-test`；XDG 数据/配置各自使用
  `cph-isolation-test` 子目录，测试身份下空 XDG 变量按未设置处理；默认便携目录为
  `./cph-isolation-test`。显式 `--userdir/--configdir/--savedir` 继续尊重原参数语义。
  XDG 模式仅改 userdir 不覆盖独立的 XDG config；需要时必须显式传 configdir。
- 系统资源目录为 `share/cph-isolation-test`，文档为 `share/doc/cph-isolation-test`。
  全部安装目的地使用相对前缀路径，不会把配置时前缀固化成无法暂存的绝对安装规则。
  内部 gettext 域 `cataclysm-dda.mo` 和数据格式不变。
- 本地化仍启用，测试构建必须传 `CPH_TEST_TRANSLATION_ROOT`，该目录先由现有
  bootstrap 的只读 `--check` 校验；安装包含真实 MO 和锁定许可/署名文件。
  安装探针另对已安装资源逐项复核锁定大小与 SHA256。
- 新开发诊断参数 `--dump-test-paths` 仅在测试身份中可用，输出 JSON 后立即退出，
  位置在创建用户目录、读取配置、初始化游戏之前。其他构建调用该参数失败。
  它证明真实程序的路径解析，不代表 GUI 或游戏启动。

## 构建与运行

原成功运行沿用当时已验收 E1 的源码、原生 Linux 构建缓存与依赖环境，
`USE_HOME_DIR/USE_XDG_DIR` 没有切换；精确历史 argv 在上述 evidence 中。
后续重试须先选定与目标源码对应的隔离构建，并新建**尚不存在**的证据路径。
下面展示路径之间的必要绑定，不能把占位源码/构建位置当作已经验收的缓存：

```sh
CPH_WORKSPACE="$(dirname "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")")"
SOURCE_DIR=/absolute/isolated/source
BUILD_DIR=/absolute/isolated/build
RUN_DIR="$CPH_WORKSPACE/evidence/e3-linux-main-identity-$(date -u +%Y%m%dT%H%M%SZ)-$$"
test ! -e "$RUN_DIR" || exit 1
cmake -S "$SOURCE_DIR" \
  -B "$BUILD_DIR" \
  -DCPH_TEST_IDENTITY=ON -DUSE_PREFIX_DATA_DIR=ON \
  -DCPH_TEST_TRANSLATION_ROOT="$CPH_WORKSPACE/inputs/translations-baseline" \
  -DCMAKE_INSTALL_PREFIX="$RUN_DIR/prefix"
cmake --build "$BUILD_DIR" --target cataclysm-tiles
python3 "$SOURCE_DIR/tools/project/linux_identity_probe.py" \
  --build-dir "$BUILD_DIR" --work-dir "$RUN_DIR"
```

若 E1 选用的是 curses/headless，则目标为 `cataclysm`，不为本任务改变其渲染路线。
上面是重试模板，不是本轮实际执行命令；历史失败尝试原样保留，成功目录后缀为 `run4`。
重试时 `work-dir` 和 `CMAKE_INSTALL_PREFIX` 必须同步变化。历史构建目录可从主任务保留的
`linux-build-location.json` 核对；原有 Nix 编译环境和 ASCII 源目录映射继续使用。

运行工具时使用**源构建所对应 checkout 中的工具**，确认资源目录已按
[translation-inputs.md](translation-inputs.md) 校验；不能复用任一已存在的失败或成功目录。

在原构建环境中运行，使 `cmake` 及运行库可用；也可以 `--cmake` 指定已核验的完整路径。
probe 要求 cache 的 `CMAKE_INSTALL_PREFIX` 精确等于 `work-dir/prefix`，使用真实
`cmake --install`，随后不传 `--basepath` 检查系统资源定位，避免掩盖 desktop 普通启动
所需的前缀契约。实际核心数据启动使用真实程序 `--check-mods ccb`，且该参数放最后。
用户/config/save 路径始终显式指向新 work-dir，HOME 原样保留。

该入口会记录每条命令、退出码、日志、程序/cache/资源锁摘要及阶段结果；验证安装
metadata、MO/通知材料、真实程序路径和核心数据启动，并在卸载前重新核验清单范围、
清单哈希及生成的卸载脚本。卸载脚本必须与 checkout 内模板生成结果一致。
安装/运行/卸载前后比较临时目录中的 CCB 程序、XDG 数据/config、便携 save/config
以及系统资源哨兵，不接触真实 CCB 安装或存档。

## 验收边界与恢复

- 不改写 HOME，不创建或扫描真实 HOME 中的哨兵。HOME 默认映射、XDG 未设置/空值
  退回 HOME 时只做只读路径诊断；缺少独立测试用户时
  `default_home_startup=NOT_RUN`，不得声称真实 HOME 生命周期隔离已通过。
- 当前编译模式的真实路径检查覆盖默认值、XDG 未设置/空值、显式 userdir 和
  user/config/save 同时覆盖。HOME、XDG、便携三种**编译模式**不能由一个二进制全部
  证明；未实际构建的模式保持 NOT_RUN。其预期路径/拒绝规则单元测试只是检查器测试。
- 若以后提供 `--previous-build-dir`，才安装实际的另一个测试身份构建后升级；要求
  可执行文件摘要不同。同一 HEAD 的不同编译结果不能证明跨版本，所以即使该检查
  成功也只报告 `distinct_build_upgrade`，`cross_version_upgrade` 仍为 NOT_RUN。
  本轮没有此前测试身份版本，升级不得冒充通过。
- 单独诊断既有二进制可用 `--paths-only --binary <实际程序> --base-dir <真实资源根>`；
  此模式不执行安装/启动/卸载，结果中 lifecycle 为 NOT_RUN。
- 生成的 CMake 安装链必须来自已审查的本地构建；脚本记录并核对安装链哈希、源目录
  绑定和卸载模板，但它不是用于敌对候选代码的操作系统沙箱。可信 CI 隔离属于 E4。
- 图形交互、新建世界/保存读取、默认 HOME 启动、真正跨版本升级及其他三个平台都
  需要独立实际证据。不得以本工具或 fixture 结果启用公开发布。
