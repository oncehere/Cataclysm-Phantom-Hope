# E3 Linux 仅测试身份

此改动已在 E1 固定基线验收后从独立工作树以 merge commit 移入主实现分支。
Linux HOME 编译模式、显式隔离 user/config/save 目录的实际安装、路径检查、
73 项资源校验、核心数据加载和卸载已 **PASS**，CCB 模拟哨兵保持不变。
测试提交为 `6cd76598a44`，完整命令及退出码见工作区外
`../evidence/e3-linux-build-attempt4/commands.jsonl`，运行结果见
`../evidence/e3-linux-main-identity-run4/result.json`。配置、编译和探针均退出 0。
远端部署仍为 **IMPLEMENTED_NOT_DEPLOYED**，下述 GUI/升级/默认 HOME 启动边界不变。
永久名称、应用 ID、Android 运行 profile 均未决定；公开发布继续关闭。

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

## E1 完成后的主力模式验证入口

先保留 E1 结果和原构建配置，再将这个独立补丁移入 E1 源树。复用其原生 Linux
构建缓存与依赖环境，不创建另一套完整构建。下面参数追加到原有 configure，
其余选项维持原值；`USE_HOME_DIR/USE_XDG_DIR` 此轮不切换。

```sh
cmake -S /tmp/cph-e1-20260926-bkx10cn5/source \
  -B /tmp/cph-e1-20260926-bkx10cn5/build \
  -DCPH_TEST_IDENTITY=ON -DUSE_PREFIX_DATA_DIR=ON \
  -DCPH_TEST_TRANSLATION_ROOT=/home/oncehere/文档/ChatGPT/CPH/inputs/translations-baseline \
  -DCMAKE_INSTALL_PREFIX=/home/oncehere/文档/ChatGPT/CPH/evidence/e3-linux-main-identity-run/prefix
cmake --build /tmp/cph-e1-20260926-bkx10cn5/build --target cataclysm-tiles
```

若 E1 选用的是 curses/headless，则目标为 `cataclysm`，不为本任务改变其渲染路线。
以上模式已实际运行；失败尝试原样保留，成功目录后缀为 `run4`。重试时使用新
work-dir 并同步更改 CMAKE_INSTALL_PREFIX。具体构建目录须由主任务保留的
`linux-build-location.json` 核对；原有 Nix 编译环境和 ASCII 源目录映射继续使用。

运行工具时使用**源构建所对应 checkout 中的工具**，且
`e3-linux-main-identity-run` 必须尚不存在；其父目录已存在。

```sh
python3 tools/project/linux_identity_probe.py \
  --build-dir /tmp/cph-e1-20260926-bkx10cn5/build \
  --work-dir /home/oncehere/文档/ChatGPT/CPH/evidence/e3-linux-main-identity-run
```

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

修改范围限于 CMake 的 Linux 测试选项、身份/路径入口、专用 metadata、检查器与文档。
没有 SDL3/UI 迁移、永久身份选择、存档迁移或系统安装。E1 验收完成前不要将本补丁
覆盖正在编译的源树；完成后由主任务 review、独立提交并增量验证。
