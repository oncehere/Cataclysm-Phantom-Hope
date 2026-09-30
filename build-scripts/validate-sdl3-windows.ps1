# Run only in a disposable Windows checkout. This creates candidate evidence,
# not a trusted-gate result, installed application or release.
param(
    [Parameter(Mandatory = $true)][string]$WorkDir,
    [ValidateRange(1, 64)][int]$Parallel = 15
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
Set-StrictMode -Version Latest
$source = (Resolve-Path "$PSScriptRoot/..").Path
if (Test-Path -LiteralPath $WorkDir) { throw 'Use a new work directory for each attempt.' }
$work = (New-Item -ItemType Directory -Path $WorkDir).FullName
$evidence = (New-Item -ItemType Directory -Path "$work/evidence").FullName
Set-Location -LiteralPath $source

function Invoke-Recorded([string]$Id, [string]$Exe, [string[]]$Arguments) {
    $log = Join-Path $evidence "$Id.log"
    # Tee-Object never creates a file when a successful native command is silent.
    # Record a real empty log before running it so hashing also covers that case.
    [System.IO.File]::WriteAllText($log, '')
    & $Exe @Arguments 2>&1 | Tee-Object -FilePath $log | Write-Host
    $code = $LASTEXITCODE
    [ordered]@{ id = $Id; cwd = (Get-Location).Path; argv = @($Exe) + $Arguments;
        exit_code = $code; log = "$Id.log";
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $log).Hash.ToLower() } |
        ConvertTo-Json -Compress -Depth 8 | Add-Content -LiteralPath "$evidence/commands.jsonl"
    if ($code -ne 0) { throw "$Id failed with exit code $code" }
}
function Assert-Junit([string]$Path) {
    [xml]$report = Get-Content -Raw -LiteralPath $Path
    $cases = @($report.SelectNodes('//testcase'))
    $suites = @($report.SelectNodes('//testsuite'))
    if ($cases.Count -eq 0 -or $suites.Count -eq 0) { throw "Empty test report: $Path" }
    foreach ($suite in $suites) {
        if ([int]$suite.tests -le 0 -or [int]$suite.failures -ne 0 -or [int]$suite.errors -ne 0 -or
            [int]$suite.GetAttribute('skipped') -ne 0 -or [int]$suite.GetAttribute('disabled') -ne 0) {
            throw "Failed or empty test suite: $Path"
        }
    }
    if (@($report.SelectNodes('//failure|//error|//skipped')).Count -ne 0) {
        throw "Failed or skipped test cases: $Path"
    }
}
$result = [ordered]@{ status = 'FAIL'; platform = 'windows-x64'; parallel = $Parallel;
    trusted_gate = $false; publication = $false;
    not_run = @('interactive GUI/IME/window/font/gamepad', 'audible sound device',
        'GPU shader runtime', 'full gameplay', 'macOS', 'Android') }
try {
    $vswhere = "${env:ProgramFiles(x86)}/Microsoft Visual Studio/Installer/vswhere.exe"
    $vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if ($LASTEXITCODE -ne 0 -or -not $vs) { throw 'Visual Studio C++ tools were not found.' }
    Import-Module "$vs/Common7/Tools/Microsoft.VisualStudio.DevShell.dll"
    Enter-VsDevShell -VsInstallPath $vs -SkipAutomaticLocation -DevCmdArguments '-arch=x64 -host_arch=x64'
    $env:PATH = "$env:PATH;$env:CPH_MSYS_ROOT/usr/bin"
    $env:SDL_VIDEODRIVER = 'dummy'
    $env:SDL_AUDIODRIVER = 'dummy'
    $env:CDDA_RELEASE_BUILD = '1'
    $env:VCPKG_MAX_CONCURRENCY = "$Parallel"
    $sha = (& git rev-parse HEAD).Trim()
    $tree = (& git rev-parse 'HEAD^{tree}').Trim()
    $baseline = (Get-Content -Raw msvc-full-features/vcpkg.json | ConvertFrom-Json).'builtin-baseline'
    [ordered]@{ commit = $sha; tree = $tree; base = $env:CPH_PR_BASE; head = $env:CPH_PR_HEAD;
        vcpkg_commit = $baseline; visual_studio = $vs; os = [Environment]::OSVersion.VersionString;
        solution_header = @(Get-Content msvc-full-features/Cataclysm-vcpkg-static.sln -TotalCount 5);
        VCToolsVersion = $env:VCToolsVersion; WindowsSDKVersion = $env:WindowsSDKVersion } |
        ConvertTo-Json -Depth 8 | Set-Content "$evidence/inputs.json"
    Invoke-Recorded 'msbuild-version' 'msbuild' @('-version')
    Invoke-Recorded 'cmake-version' 'cmake' @('--version')
    Invoke-Recorded 'msgfmt-version' 'msgfmt' @('--version')

    Invoke-Recorded 'translations-bootstrap' 'python' @('tools/project/bootstrap_translations.py', '--output', "$work/resources")
    $lock = Get-Content -Raw project/assets.lock.json | ConvertFrom-Json
    foreach ($entry in $lock.files) {
        if ($entry.kind -ne 'gettext-mo') { continue }
        $destination = Join-Path $source $entry.path
        if (Test-Path -LiteralPath $destination) { throw "Generated translation already exists: $destination" }
        New-Item -ItemType Directory -Force -Path (Split-Path $destination) | Out-Null
        Copy-Item -LiteralPath (Join-Path "$work/resources" $entry.path) -Destination $destination
    }
    New-Item -ItemType Directory -Force -Path 'lang/mo/cph/zh_CN/LC_MESSAGES', 'data/mods/TEST_DATA/lang/mo/ru/LC_MESSAGES' | Out-Null
    Invoke-Recorded 'cph-translation' 'msgfmt' @('-c', '-o', 'lang/mo/cph/zh_CN/LC_MESSAGES/cataclysm-dda.mo', 'lang/cph/zh_CN.po')
    Invoke-Recorded 'test-translation' 'msgfmt' @('-f', '-o', 'data/mods/TEST_DATA/lang/mo/ru/LC_MESSAGES/TEST_DATA.mo', 'data/mods/TEST_DATA/lang/po/ru.po')

    $vcpkg = "$work/vcpkg"
    Invoke-Recorded 'vcpkg-clone' 'git' @('clone', '--no-checkout', 'https://github.com/microsoft/vcpkg.git', $vcpkg)
    Invoke-Recorded 'vcpkg-checkout' 'git' @('-C', $vcpkg, 'checkout', '--detach', $baseline)
    Invoke-Recorded 'vcpkg-bootstrap' 'cmd' @('/c', "$vcpkg/bootstrap-vcpkg.bat", '-disableMetrics')
    $env:VCPKG_ROOT = $vcpkg
    $env:VCPKG_INSTALLATION_ROOT = $vcpkg
    # Preserve the nested layout expected by the inherited MSBuild shader rule.
    $installed = "$source/msvc-full-features/vcpkg_installed/x64-windows-static"
    Invoke-Recorded 'vcpkg-install' "$vcpkg/vcpkg.exe" @('install', '--triplet=x64-windows-static', '--x-feature=sdl3',
        "--x-manifest-root=$source/msvc-full-features", "--overlay-triplets=$source/.github/vcpkg_triplets",
        "--x-install-root=$installed", '--clean-after-build')
    Invoke-Recorded 'vcpkg-integrate' "$vcpkg/vcpkg.exe" @('integrate', 'install')
    $env:PATH = "$installed/x64-windows-static/bin;$env:PATH"
    $common = @("-m:$Parallel", '-p:Platform=x64', '-p:MultiProcessorCompilation=false',
        '-p:VcpkgManifestInstall=false', "-p:VcpkgInstalledDir=$installed/",
        'msvc-full-features/Cataclysm-vcpkg-static.sln')
    # -m limits projects, while /MP would multiply that budget inside each
    # compiler. Check actual ClCompile metadata before starting the build.
    Invoke-Recorded 'compile-parallel-evaluation' 'msbuild' @('-nologo', '-getItem:ClCompile',
        '-p:Platform=x64', '-p:Configuration=Release', '-p:MultiProcessorCompilation=false',
        '-p:VcpkgManifestInstall=false', "-p:VcpkgInstalledDir=$installed/",
        'msvc-full-features/Cataclysm-libAL-vcpkg-static.vcxproj')
    $evaluation = Get-Content -Raw "$evidence/compile-parallel-evaluation.log" | ConvertFrom-Json
    $compileItems = @($evaluation.Items.ClCompile)
    if ($compileItems.Count -eq 0 -or @($compileItems | Where-Object {
        $_.MultiProcessorCompilation -ne 'false'
    }).Count -ne 0) {
        throw 'ClCompile metadata did not disable /MP; the requested parallel budget is not enforced.'
    }
    Invoke-Recorded 'build-tiles-sound' 'msbuild' ($common + @('-p:Configuration=Release',
        '-target:Cataclysm-vcpkg-static;Cataclysm-test-vcpkg-static;JsonFormatter-vcpkg-static;zzip'))
    if (Get-Content -Raw "$evidence/build-tiles-sound.log" | Select-String '(?im)CL\.exe[^\r\n]*\s/MP(?:\d+)?(?:\s|$)') {
        throw 'A compiler command enabled /MP despite the explicit parallel budget.'
    }
    Invoke-Recorded 'tiles-version' './cataclysm-tiles.exe' @('--version')
    $selections = [ordered]@{ sound = '[sound_backend]'; shader = '[tiles][gpu]';
        gamepad = '[gamepad]'; renderer = '[renderer_recovery]'; options = '[option][sdl3]';
        dialogue = '[lua][platform][dialogue]'; translations = '[translations]~[.]';
        chinese = 'TranslationPluralRulesEvaluatorPerformance' }
    foreach ($id in $selections.Keys) {
        $junit = "$evidence/$id.xml"
        Invoke-Recorded "test-$id" './Cataclysm-test-vcpkg-static-Release-x64.exe' @($selections[$id],
            '--user-dir', "$work/user-$id", '--rng-seed', '4902', '--order', 'lex', '-r', 'junit', '-o', $junit)
        Assert-Junit $junit
    }

    # Packaging runs in this disposable checkout; no archive is published.
    "Candidate $sha; tested tree $tree" | Set-Content 'VERSION.txt'
    Invoke-Recorded 'windist' 'pwsh' @('-NoProfile', '-Command', '$ErrorActionPreference = "Stop"; & ./build-scripts/windist.ps1')
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead("$source/cataclysmdda-0.J.zip")
    try {
        $entries = @($zip.Entries | ForEach-Object { $_.FullName.Replace('\', '/') })
        foreach ($required in @('cataclysm-tiles.exe', 'LICENSE-mpg123.txt', 'lang/mo/cph/zh_CN/LC_MESSAGES/cataclysm-dda.mo')) {
            if ($required -notin $entries) { throw "Package is missing $required" }
        }
        if (-not ($entries -match '(^|/)(lib)?mpg123[^/]*\.dll$')) { throw 'Package has no replaceable mpg123 DLL.' }
        if ($entries -match '(?i)sdl2[^/]*\.dll$') { throw 'Package contains an SDL2 DLL.' }
        foreach ($shader in Get-ChildItem 'data/shaders/*.frag') {
            foreach ($extension in @('spv', 'dxil')) {
                if ("data/shaders/$($shader.Name).$extension" -notin $entries) { throw "Missing shader: $($shader.Name).$extension" }
            }
        }
        $entries | Set-Content "$evidence/package-entries.txt"
    } finally { $zip.Dispose() }
    Get-FileHash -Algorithm SHA256 'cataclysmdda-0.J.zip', 'cataclysm-tiles.exe' |
        Select-Object Path, Hash | ConvertTo-Json | Set-Content "$evidence/package-hashes.json"

    Invoke-Recorded 'build-headless' 'msbuild' ($common + @('-p:Configuration=Release-NoTilesHeadless',
        '-target:Cataclysm-vcpkg-static;Cataclysm-test-vcpkg-static'))
    if (Get-Content -Raw "$evidence/build-headless.log" | Select-String '(?im)CL\.exe[^\r\n]*\s/MP(?:\d+)?(?:\s|$)') {
        throw 'A headless compiler command enabled /MP despite the explicit parallel budget.'
    }
    Invoke-Recorded 'headless-version' './cataclysm-headless.exe' @('--version')
    Invoke-Recorded 'headless-dependencies' 'dumpbin' @('/DEPENDENTS', 'cataclysm-headless.exe')
    if (Get-Content -Raw "$evidence/headless-dependencies.log" | Select-String '(?i)SDL[23]|pdcurses') {
        throw 'Headless executable depends on an SDL or curses DLL.'
    }
    Invoke-Recorded 'test-headless-lua' './Cataclysm-test-vcpkg-static-Release-NoTilesHeadless-x64.exe' @(
        'lua_platform_exposes_one_runtime_contract', '--user-dir', "$work/user-headless",
        '--rng-seed', '4902', '-r', 'junit', '-o', "$evidence/headless.xml")
    Assert-Junit "$evidence/headless.xml"
    $result.status = 'PASS'
} catch {
    $result['error'] = $_.Exception.Message
    throw
} finally {
    $result | ConvertTo-Json -Depth 8 | Set-Content "$evidence/result.json"
}
