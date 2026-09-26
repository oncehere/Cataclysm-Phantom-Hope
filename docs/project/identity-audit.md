# E3 身份与四平台构建输入审计

日期：2026-09-26。代码基线为
`bcb85682f3d28ab0f0123b05e45651bb9888b61b`（U）。本次只读检查真实代码、
打包入口及本轮工具探针；没有修改应用身份、执行安装/升级/卸载或运行隔离哨兵。
E1 的 Linux 编译与本审计并行，构建结果由 E1 日志单独报告。

**静态定位：PASS。E3 身份实现与四平台隔离验收：NOT_RUN。**
四平台的正式身份、实际目标清单和发布验收尚未成立。显示名、安装身份、数据路径、
gettext 域及内部文件格式分别处理；不做全仓替换，也不迁移真实 CCB 存档。

## 1. 继承身份与冲突位置

下列行号指向 U 的源码；继承 workflow 已移至 `project/inherited-workflows/`，
内容保持原样且不在 GitHub Actions 活动目录。表中路径是源码事实，不代表已经运行。

| 平台/层面 | 当前身份与路径 | 代码证据和隔离风险 |
|---|---|---|
| 桌面显示名 | SDL 应用名和菜单后备标题为 `Cataclysm: Cleanwater Bomb`；标题还读取 `data/title` | `src/sdltiles.cpp:252–256`、`src/main_menu.cpp:959`。仅换包名不能改变这些显示入口。 |
| Windows 程序 | MSVC 图形目标为 `cataclysm-tiles.exe`；ZIP 为 `cataclysmdda-0.J.zip` | `msvc-full-features/Cataclysm-vcpkg-static.vcxproj:122`、`build-scripts/windist.ps1:13,69`。解压到既有 CCB 目录会发生文件名冲突；本轮没有 MSI/注册产品 GUID 的已验收契约。 |
| Windows 默认数据 | 开启 HOME 模式时使用 `%LOCALAPPDATA%/cataclysm-dda/`；否则采用当前目录。`save/`、通常的 `config/` 位于用户根下 | `src/path_info.cpp:104–107,164–185`、`src/main.cpp:1003–1007`。MSVC 公共编译定义没有设置 HOME/XDG（`Cataclysm-common.props:69–97`）；CMake 的 HOME 默认却为 ON（`CMakeLists.txt:23–24`）。不能把一个构建方式的默认路径套给全部 Windows 包。 |
| Linux 系统安装 | desktop/AppStream/icon ID 共用 `org.cataclysmdda.CataclysmDDA`，执行 `cataclysm-tiles`；系统资源为 `share/cataclysm-dda` | `data/xdg/org.cataclysmdda.CataclysmDDA.desktop:2–7`、同名 `.appdata.xml:3–6`、`Makefile:1494–1519`、`CMakeLists.txt:199`。命令、图标、元数据和数据目录均可能覆盖同前缀内的 CCB/CDDA 安装。 |
| Linux 用户数据 | HOME 模式为 `$HOME/.cataclysm-dda/`；XDG 模式为 `$XDG_DATA_HOME/cataclysm-dda/` 或 `$HOME/.local/share/cataclysm-dda/`；配置另取 `$XDG_CONFIG_HOME/cataclysm-dda/` 或 `$HOME/.config/cataclysm-dda/` | `src/path_info.cpp:111–120,172–185`。**XDG 模式下只传 `--userdir` 仍会共用默认配置目录**，因为 `set_standard_filenames()` 独立求配置路径。 |
| macOS 包与技术 ID | `Cataclysm.app` / `Cataclysm.dmg`，`CFBundleName=Cataclysm`，`CFBundleIdentifier=com.cataclysmdda.en.cataclysm` | `Makefile:1573,1645–1667`、`build-data/osx/Info.plist:5–14`。包路径和 bundle ID 仍属于继承身份；仅改显示名不隔离安装。 |
| macOS 用户数据/启动器 | HOME 模式为 `$HOME/Library/Application Support/Cataclysm/`；`.app` 启动器先进入 `Contents/Resources`，再调用旧二进制 | `src/path_info.cpp:108–110`、`build-data/osx/Cataclysm.sh:4–5,16–21`。该启动器**没有转发 `"$@"`**；不能假定在 `.app` 启动层附加 `--userdir` 就会生效。 |
| Android 显示与安装 ID | `namespace/applicationId=com.crimsoncrossbunker.cataclysmcb`；stable 无后缀，experimental 为 `.experimental`，newUi 为 `.newui`；显示名均为 CCB 系列 | `android/app/build.gradle:298,317–319,375–405`。当前 `experimental` 是 CCB 自己的身份，不是 CPH 独立身份。 |
| Android Java/JNI/组件 | Java 包为 `com.crimsoncrossbunker.cataclysmcb`；manifest 的两个 activity 使用相对类名。JNI 导出显式包含旧 Java 包名 | `android/app/src/main/AndroidManifest.xml:45–66`、`src/sdltiles.cpp:1045–1165`。applicationId 与 Java namespace 可分别审查；不能机械重命名 Java 包而遗漏 JNI。静态搜索所审计 manifest/Java 未发现自定义 provider authorities，但仍需检查实际 merged manifest。 |
| Android 用户数据（最高优先级） | `Use Legacy Storage` 默认 false，此时使用公共 `Documents/cataclysm-ccb`；true 才使用 `getExternalFilesDir(null)` | `android/app/src/main/java/com/crimsoncrossbunker/cataclysmcb/StoragePaths.java:10–28`。**仅改 applicationId 不能隔离默认存档/配置**。C++ 通过 Java `getUserDirectory()` 取得路径（`src/path_info.cpp:88–100`）；桌面的 `--userdir` 逻辑不能直接作为 Android 隔离证明。 |
| Android 私有输入 | APK 资源安装于 `getExternalFilesDir(null)` 的 `data/gfx/lang`，HUD 位于 `getFilesDir()/hud` | `SplashScreen.java:480–497`、`AndroidHudRepository.java:75`（均位于上述 Java 包目录）。这部分与公共 Documents 用户数据是两条不同路径，必须同时核验。 |
| 内部格式与翻译 | gettext 文件名仍为 `cataclysm-dda.mo`；HUD format 标识为 `cataclysm-android-hud` | `src/path_info.cpp:480–482`、`AndroidHudRepository.java:320`。这些不是安装身份；当前 MO 冷启动依赖原域，不应随显示名替换。 |

## 2. 便携、升级与卸载边界

- 桌面没有设置 HOME/XDG 时，以 `.` 为用户目录（`src/main.cpp:1003–1007`）。
  `cataclysm-launcher:9–30,40–48` 切换至程序目录、选择旧二进制并转发参数；
  因此便携模式的“当前目录”可能是包目录，而不是调用者原目录。
- `--basepath`、`--userdir` 先初始化根；`--datadir`、`--savedir`、`--configdir`
  在第二轮参数处理中覆盖具体路径（`src/main.cpp:401–408,466–473,490–530`）。
  E3 测试必须覆盖普通启动和显式参数启动，尤其是 XDG 配置与 macOS 包装器。
- Android 升级先按资源清单删除旧 `data/gfx/lang` 文件，并校验 canonical 路径
  仍位于应用资源根（`SplashScreen.java:511–545`）；没有清单时退回递归保留规则
  （`480–489,605–629`）。**升级还删除当前用户目录下的 `cache`、`config/cache`、
  `memorial/cache`**（`578–585`）。在公共 `Documents/cataclysm-ccb` 未隔离前，
  新 applicationId 仍可能触及 CCB 用户缓存。没有对真实手机执行这些路径。
- Windows 打包脚本会先递归删除当前构建目录的 `bindist`
  （`build-scripts/windist.ps1:8–12`），再覆盖 ZIP；这属于构建暂存清理，
  不是经过验证的用户卸载程序。必须在独立构建目录运行。
- CMake `uninstall` 逐项删除 `install_manifest.txt` 所列路径，前置 `DESTDIR`
  （`cmake_uninstall.cmake.in:1–22`）。它没有项目身份或用户数据归属校验；
  如果此前共享了安装前缀/文件名，就不能以“按清单卸载”证明不会删除 CCB。
- 当前 ZIP/tar.gz/.app/APK 路径没有经过本项目安装、升级、卸载验收。
  本次没有执行系统卸载、扫描用户目录或删除任何 CCB 数据；Android 系统卸载
  对公共目录的实际影响也未验证。

## 3. 四平台继承输入与实际缺口

每个平台最终必须绑定同一项目提交 H 和同一资源锁摘要。下表是已定位的继承入口，
**不是已批准的 CPH 发布目标**；不扩张为必须保留所有继承变体。

| 平台 | 继承 ABI、配置、格式与预期文件 | 签名/运行检查的真实边界 | 本次 E3 状态 |
|---|---|---|---|
| Windows | `release.yml:240–255,821–830` 指定 Windows 2022、MSVC x64、SDL2 Release、图形 ZIP；`windist.ps1` 收集 exe/PDB、资源和 MO。另有 CMake MinGW/MSVC presets，不能当作同一构建结果。 | 未运行原生构建、PE 架构/依赖检查、原生启动或隔离回归；所审计 release/windist 路径没有 Authenticode 验证步骤。不能由 Linux 结果推断 Windows 通过。 | 身份实现/原生验收 **NOT_RUN**；当前已配置环境内未验证 Windows runner，远程运行 **BLOCKED** 于目标与权限。 |
| Linux | `release.yml:267–283,806–813` 指定 Ubuntu 24.04 x64、Make/Clang、SDL2、Release、本地化，输出 tar.gz；`Makefile:1672–1682` 组包。当前本机为 NixOS x86_64，E1 编译另记。 | E3 尚未检验 ELF 依赖、包内容、安装路径、启动/升级/卸载哨兵；NixOS 构建成功不能直接宣称 Ubuntu 包可用。 | 身份实现、E3 安装隔离和发行包验收 **NOT_RUN**；本地后续开发可继续，无需等待远程目标。 |
| macOS | `release.yml:304–316,842–845` 声明 macos-15、SDL2、`USE_HOME_DIR=1 UNIVERSAL_BINARY=1`，`.app` 后装入 DMG。plist 的架构优先级不是 Mach-O 架构证明。 | 未取得实际 runner/二进制，尚未执行 `lipo`、依赖检查、包检查或启动探针。`codesign-macos.sh:2,27,32` 只做 ad-hoc 签名，且 Make 的 SDL2 DMG 路径不调用它（`1661–1667`）；这不能冒充长期身份签名或本项目发行验收。按规格，不另加人工 Mac 游玩的硬门槛。 | 构建/自动验收 **NOT_RUN**；当前 Mac 环境与正式身份未配置验证，相关动作 **BLOCKED**。 |
| Android | `release.yml:326–350` 中名称 `Android x64` 实际参数为 **arm64**；Gradle 将其映射到 **arm64-v8a**，不是 x86_64。默认还启用 armeabi-v7a，按 ABI 分包，无 universal APK（`build.gradle:128–132,321–342`）。非新 UI 入口为 `assembleExperimentalRelease`（`release.yml:889–892`）。现有 SDL3 Android 路径已继承，不是本轮新增桌面 SDL3。 | 配置为 compile/target SDK 35、min SDK 24、NDK 28.1.13356709（`android/gradle.properties:58–70`），只是配置值；实际最低兼容性未验证。正式签名条件式读取 keystore（`build.gradle:414–445`）；本轮未读取密钥或生成临时签名包。未运行 APK ABI/ID/version/签名检查、模拟器或实机回归；用户设备 ABI 和每日运行 profile 未确认。 | 构建/运行/升级隔离 **NOT_RUN**；SDK/NDK/ADB 环境、长期身份/密钥与运行 profile 未配置验证，依赖动作 **BLOCKED**。 |

本轮 `preflight-in-progress.json` 报告 Linux x86_64、未配置
`ANDROID_HOME/ANDROID_SDK_ROOT/ANDROID_NDK_HOME/SDKROOT`，默认 PATH 上没有 Java/ADB。
本次补查 `adb/emulator/sdkmanager/java/wine/pwsh/xcodebuild/codesign` 也未得到 PATH
入口。这只证明当前会话没有配置可直接使用的相应工具，不证明机器或 Nix store
绝不存在这些工具。继承 YAML 声明 hosted runner 也不是本项目已获 runner 运行证据。

还有两个必须先适配的 MO 打包入口：

1. `Makefile:1645–1650` 的 `dmgdistclean` 会删除整个 `lang/mo`，之后才执行
   localization/app；不能直接用于本轮仅 MO 的锁定输入。
2. `android/app/build.gradle:197–220,290–295` 的 `makeLocalization` 默认执行旧翻译
   构建入口。后续须显式接入已校验 MO 资源并核验最终 APK 内容，不通过关闭中文或
   放宽检查绕过。资源锁目前只覆盖翻译/许可/署名，四平台其他依赖和素材仍需各自锁定。

## 4. 下一轮可执行的仅测试身份与验证入口

以下值只是明确、可撤销的**测试参数建议，尚未实现或采用**：显示名
`CPH Isolation Test`，独立桌面命令/数据子目录 `cph-isolation-test`，
Android applicationId 与 macOS bundle ID `org.example.cph.isolationtest`，
Linux desktop/AppStream 测试 ID `org.example.cph.IsolationTest`。
它们不决定永久品牌/技术 ID，也不得用于公开长期开发版。

- 桌面先在独立测试用户的主目录、临时 LOCALAPPDATA/XDG 根和独立安装前缀内放置模拟 CCB 程序、
  配置和存档哨兵，记录哈希，再调用真实构建的测试身份程序与真实打包入口。
  覆盖默认 HOME、XDG、便携、显式 user/config/save 参数，以及路径含空格的入口。
  Windows/macOS 的流程必须在实际相应运行环境验证，不以 Python fixture 替代。
- Android 同时定点隔离 applicationId、公共 Documents 子目录、私有资源根、
  preference/HUD 所在应用数据及升级缓存删除路径。保留或有意识地修改 namespace/JNI，
  以 merged manifest 和实际 APK 作核验对象；不做全包名替换。
- 所有平台执行适用的安装、冷启动、更新、卸载后重新核对哨兵及输出清单；
  任何触及 CCB 路径的行为都应失败。先用模拟目录/测试用户/模拟器，未经明确范围
  不对真实现有安装和存档开展破坏性验证。
- Android 的每日运行策略仍须单独固定：ARM64 实际运行环境是否可用尚未验证。
  兼容架构模拟器只能证明自身产物；不能自动取代 ARM64 包运行或擅自采用替代 profile。

## 5. 本审计的验证与恢复点

执行了定向 `rg`、带行号源码读取、JSON 证据解析和工具 PATH 探针，未运行候选
安装器/包脚本，也未改应用源码。关键文件已与 U 的 Git 对象核对；文档行号通过
本地逐项定位验证。静态结论只适用于审计基线。

恢复 E3 时先读本文件第 1、2 节并按测试身份做独立提交；Linux 可在 E1 固定输入
验收后继续。远程目标只阻塞远程部署，正式 ID/签名只阻塞依赖它们的动作。
Windows/macOS 需要可用原生环境；Android 需要 SDK/NDK/ADB、测试设备/模拟器入口及
确定的运行 profile。永久标识和签名材料由用户在受控配置处提供，不能贴入源码、日志
或聊天。只有实际完成上述包/隔离检查后才能推进 E3 readiness；本审计不是 readiness。
