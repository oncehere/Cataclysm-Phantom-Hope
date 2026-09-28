#requires -Version 7.0
<#
Native Windows E1 probe. Run in a disposable checkout from a VS 2022 x64
Developer PowerShell with dependencies already installed. No publishing,
signing, global vcpkg integration, package installation or downloads occur here.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SourceDir,
    [Parameter(Mandatory)][string]$BuildDir,
    [Parameter(Mandatory)][string]$EvidenceDir,
    [Parameter(Mandatory)][string]$ResourcesDir,
    [Parameter(Mandatory)][string]$VcpkgRoot,
    [Parameter(Mandatory)][string]$VcpkgInstalled,
    [ValidateRange(1, 64)][int]$Parallel = 2,
    [string]$Python = 'python'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
if (-not $IsWindows) {
    @{ status = 'BLOCKED'; reason = 'Native Windows is required';
       platform = [Environment]::OSVersion.VersionString } |
        ConvertTo-Json -Compress
    exit 3
}

function Full-Path([string]$Path) {
    return [IO.Path]::GetFullPath($Path).TrimEnd([char[]]'\/')
}

function Is-Nested([string]$Child, [string]$Parent) {
    return $Child.Equals($Parent, [StringComparison]::OrdinalIgnoreCase) -or
        $Child.StartsWith($Parent + [IO.Path]::DirectorySeparatorChar,
                          [StringComparison]::OrdinalIgnoreCase)
}

function Assert-Prerequisite([bool]$Condition, [string]$Reason) {
    if (-not $Condition) {
        $script:Outcome = 'BLOCKED'
        $script:ResultExit = 3
        throw $Reason
    }
}

function Invoke-Logged([string]$Name, [string]$Executable,
                       [string[]]$Arguments) {
    $log = Join-Path $EvidenceDir ($Name + '.log')
    if (Test-Path -LiteralPath $log) { throw "Log exists: $log" }
    $started = [DateTime]::UtcNow
    & $Executable @Arguments 2>&1 | Out-File -LiteralPath $log -Encoding utf8
    $code = $LASTEXITCODE
    $record = @{
        argv = @($Executable) + $Arguments; cwd = $SourceDir
        platform = [Environment]::OSVersion.VersionString; exit_code = $code
        status = $(if ($code -eq 0) { 'PASS' } else { 'FAIL' })
        elapsed_seconds = ([DateTime]::UtcNow - $started).TotalSeconds
        log = $log; log_sha256 = (Get-FileHash $log -Algorithm SHA256).Hash
    }
    $record | ConvertTo-Json -Depth 8 -Compress |
        Add-Content -LiteralPath (Join-Path $EvidenceDir 'commands.jsonl')
    $record | ConvertTo-Json -Depth 8 -Compress | Write-Output
    if ($code -ne 0) {
        $script:ResultExit = $code
        throw "$Name failed; see $log"
    }
}

function Check-JUnit([string]$Path) {
    $settings = [Xml.XmlReaderSettings]::new()
    $settings.DtdProcessing = [Xml.DtdProcessing]::Prohibit
    $settings.XmlResolver = $null
    $reader = [Xml.XmlReader]::Create($Path, $settings)
    try {
        $document = [Xml.XmlDocument]::new()
        $document.XmlResolver = $null
        $document.Load($reader)
    } finally { $reader.Dispose() }
    if ($document.DocumentElement.Name -notin @('testsuite', 'testsuites')) {
        throw 'Not a JUnit report'
    }
    $cases = $document.SelectNodes('//testcase')
    $suites = $document.SelectNodes('//testsuite')
    if ($cases.Count -eq 0 -or $suites.Count -eq 0) {
        throw 'Zero executed test cases'
    }
    if ($document.SelectNodes('//failure|//error|//skipped').Count -ne 0) {
        throw 'JUnit contains failed or skipped tests'
    }
    foreach ($suite in $document.SelectNodes('//testsuite|//testsuites')) {
        foreach ($field in @('failures', 'errors', 'skipped', 'disabled')) {
            if ($suite.HasAttribute($field) -and
                [int]$suite.GetAttribute($field) -ne 0) {
                throw "JUnit has nonzero $field"
            }
        }
    }
    $assertions = 0
    $containedCases = 0
    foreach ($suite in $suites) {
        $directCases = $suite.SelectNodes('./testcase').Count
        if (-not $suite.HasAttribute('tests') -or
            [int]$suite.GetAttribute('tests') -le 0 -or $directCases -eq 0) {
            throw 'Missing or zero executed cases/assertions in JUnit suite'
        }
        # This repository's Catch2 JUnit tests count means assertions.
        $assertions += [int]$suite.GetAttribute('tests')
        $containedCases += $directCases
    }
    if ($containedCases -ne $cases.Count) {
        throw 'Test case outside an assertion-bearing suite'
    }
    $root = $document.DocumentElement
    if ($root.Name -eq 'testsuites' -and $root.HasAttribute('tests') -and
        [int]$root.GetAttribute('tests') -ne $assertions) {
        throw 'Inconsistent aggregate assertion count'
    }
    return @{ test_cases = $cases.Count; assertions = $assertions }
}

$script:Outcome = 'FAIL'
$script:ResultExit = 1
$savedEnvironment = @{}
$locationPushed = $false
$evidenceCreated = $false
$testResults = @()
$binaryInputs = @{}
try {
    $SourceDir = Full-Path $SourceDir
    $BuildDir = Full-Path $BuildDir
    $EvidenceDir = Full-Path $EvidenceDir
    $ResourcesDir = Full-Path $ResourcesDir
    $VcpkgRoot = Full-Path $VcpkgRoot
    $VcpkgInstalled = Full-Path $VcpkgInstalled
    # Resolve policy beside the running script, independently of SourceDir/cwd.
    $policyPath = Join-Path $PSScriptRoot '../../project/check-policy.json'
    $policy = Get-Content -Raw -LiteralPath $policyPath | ConvertFrom-Json -AsHashtable
    $target = $policy.targets.windows
    if ($target.tests -isnot [Collections.IDictionary] -or $target.tests.Count -eq 0) {
        throw 'Policy requires a nonempty tests mapping'
    }
    foreach ($test in $target.tests.GetEnumerator()) {
        if ($test.Key -isnot [string] -or [string]::IsNullOrWhiteSpace($test.Key) -or
            $test.Value -isnot [string] -or [string]::IsNullOrWhiteSpace($test.Value)) {
            throw 'Policy requires nonempty test names and selectors'
        }
    }
    foreach ($pair in @(@($SourceDir, $BuildDir),
                       @($SourceDir, $EvidenceDir),
                       @($BuildDir, $EvidenceDir))) {
        Assert-Prerequisite (-not (Is-Nested $pair[0] $pair[1]) -and
                             -not (Is-Nested $pair[1] $pair[0])) `
            'Source, build and evidence directories must be disjoint'
    }
    Assert-Prerequisite (-not (Test-Path -LiteralPath $EvidenceDir)) `
        'Evidence must be a new directory; previous attempts are preserved'
    New-Item -ItemType Directory -Path $EvidenceDir | Out-Null
    $evidenceCreated = $true
    foreach ($tool in @('git', 'cmake', 'cl', 'msbuild', 'msgfmt', $Python)) {
        Assert-Prerequisite ($null -ne (Get-Command $tool -ErrorAction SilentlyContinue)) `
            "Missing $tool; use an already prepared VS 2022 x64 developer shell"
    }
    Assert-Prerequisite ([Environment]::Is64BitProcess) 'Use a 64-bit PowerShell process'
    Assert-Prerequisite (Test-Path -LiteralPath (Join-Path $SourceDir 'CMakePresets.json')) `
        'Source must be the isolated CPH checkout'
    Assert-Prerequisite (Test-Path -LiteralPath (Join-Path $VcpkgRoot 'scripts/buildsystems/vcpkg.cmake')) `
        'VcpkgRoot must be the existing pinned vcpkg checkout'
    Assert-Prerequisite (Test-Path -LiteralPath (Join-Path $VcpkgInstalled "$($target.vcpkg_triplet)/include/SDL2/SDL.h")) `
        'Preinstall manifest SDL2/static x64 dependencies; this probe does not install them'

    # These changes apply only to this process and are restored on every exit.
    foreach ($item in Get-ChildItem Env:) {
        if ($item.Name -match 'TOKEN|SECRET|PASSWORD|PRIVATE_KEY|KEYSTORE') {
            $savedEnvironment[$item.Name] = $item.Value
            [Environment]::SetEnvironmentVariable($item.Name, $null, 'Process')
        }
    }
    $overrides = @{
        VCPKG_ROOT = $VcpkgRoot; VCPKG_INSTALLATION_ROOT = $VcpkgRoot
        GIT_OPTIONAL_LOCKS = '0'; GIT_NO_LAZY_FETCH = '1'
        PYTHONUTF8 = '1'; PYTHONIOENCODING = 'utf-8'
    }
    foreach ($kind in @('DATA', 'CONFIG', 'CACHE')) {
        $xdg = Join-Path $EvidenceDir ('xdg-' + $kind.ToLowerInvariant())
        New-Item -ItemType Directory -Path $xdg | Out-Null
        $overrides['XDG_' + $kind + '_HOME'] = $xdg
    }
    foreach ($key in $overrides.Keys) {
        $savedEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
        [Environment]::SetEnvironmentVariable($key, $overrides[$key], 'Process')
    }
    Push-Location -LiteralPath $SourceDir
    $locationPushed = $true
    Invoke-Logged 'preflight' $Python @('tools/project/preflight.py', '--repo', $SourceDir)
    Invoke-Logged 'resources' $Python @('tools/project/bootstrap_translations.py',
        '--output', $ResourcesDir, '--check')
    $lockPath = Join-Path $SourceDir 'project/assets.lock.json'
    $assetLock = Get-Content -Raw -LiteralPath $lockPath | ConvertFrom-Json
    foreach ($entry in $assetLock.files | Where-Object kind -eq 'gettext-mo') {
        $catalog = Join-Path $SourceDir $entry.path
        if (-not (Test-Path -LiteralPath $catalog -PathType Leaf) -or
            (Get-Item -LiteralPath $catalog).Length -ne $entry.bytes -or
            (Get-FileHash -LiteralPath $catalog -Algorithm SHA256).Hash -ne $entry.sha256) {
            throw "Missing or unverified source MO: $($entry.path)"
        }
    }
    Invoke-Logged 'vcpkg-head' 'git' @('--no-replace-objects', '-C', $VcpkgRoot,
                                     'rev-parse', 'HEAD')
    Invoke-Logged 'vcpkg-tracked-clean' 'git' @('--no-replace-objects', '-c',
        'core.fsmonitor=false', '-C', $VcpkgRoot, 'diff', '--quiet',
        '--no-ext-diff', '--no-textconv', 'HEAD', '--')
    $manifestPath = Join-Path $SourceDir 'msvc-full-features/vcpkg.json'
    $manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
    $vcpkgHead = (Get-Content -Raw (Join-Path $EvidenceDir 'vcpkg-head.log')).Trim()
    Assert-Prerequisite ($vcpkgHead -eq $manifest.'builtin-baseline' -and
                         $vcpkgHead -eq $target.vcpkg_commit) `
        'vcpkg checkout differs from policy/manifest baseline; no automatic checkout'
    $cachePath = Join-Path $BuildDir 'CMakeCache.txt'
    if (Test-Path -LiteralPath $cachePath) {
        $cacheSource = @(Get-Content -LiteralPath $cachePath |
            Where-Object { $_ -like 'CMAKE_HOME_DIRECTORY:INTERNAL=*' })
        Assert-Prerequisite ($cacheSource.Count -eq 1 -and
            (Full-Path ($cacheSource[0].Split('=', 2)[1])) -eq $SourceDir) `
            'Existing CMake cache belongs to another source; use a new build directory'
    } elseif ((Test-Path -LiteralPath $BuildDir) -and
              @(Get-ChildItem -LiteralPath $BuildDir -Force).Count -gt 0) {
        Assert-Prerequisite $false 'Nonempty build directory has no recognizable CMake cache'
    }
    New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null
    $state = Get-Content -Raw (Join-Path $EvidenceDir 'preflight.log') | ConvertFrom-Json
    @{
        source_sha = $state.head; branch = $state.branch
        source = $SourceDir; build = $BuildDir; resources = $ResourcesDir
        preset = $target.preset; configuration = $target.configuration
        policy_sha256 = (Get-FileHash $policyPath -Algorithm SHA256).Hash
        vcpkg_commit = $vcpkgHead; vcpkg_installed = $VcpkgInstalled
        assets_lock_sha256 = (Get-FileHash $lockPath -Algorithm SHA256).Hash
        manifest_sha256 = (Get-FileHash $manifestPath -Algorithm SHA256).Hash
        sdk_version_from_developer_shell = $env:WindowsSDKVersion
        msvc_tools_version_from_developer_shell = $env:VCToolsVersion
        public_release = $false; signing = $false
    } | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $EvidenceDir 'inputs.json')
    Invoke-Logged 'cmake-version' 'cmake' @('--version')
    Invoke-Logged 'msbuild-version' 'msbuild' @('-version', '-nologo')
    Invoke-Logged 'msgfmt-version' 'msgfmt' @('--version')
    $fixtureDir = Join-Path $SourceDir 'data/mods/TEST_DATA/lang/mo/ru/LC_MESSAGES'
    New-Item -ItemType Directory -Path $fixtureDir -Force | Out-Null
    $binaryDir = Join-Path $BuildDir 'bin'
    $msgfmt = (Get-Command 'msgfmt').Source
    $configurationKey = 'CMAKE_RUNTIME_OUTPUT_DIRECTORY_' + $target.configuration.ToUpperInvariant()
    $configureArguments = @('--preset', $target.preset,
        '-S', $SourceDir, '-B', $BuildDir, '-G', $target.generator,
        '-A', $target.generator_platform, '-DVCPKG_MANIFEST_FEATURES=sdl2',
        "-DVCPKG_ROOT=$VcpkgRoot", "-DVCPKG_INSTALLED_DIR=$VcpkgInstalled",
        "-DGETTEXT_MSGFMT_BINARY=$msgfmt",
        "-DGETTEXT_MSGFMT_EXECUTABLE=$msgfmt",
        "-D$configurationKey=$binaryDir")
    foreach ($option in $target.options.GetEnumerator()) {
        $value = if ($option.Value) { 'ON' } else { 'OFF' }
        $configureArguments += "-D$($option.Key)=$value"
    }
    Invoke-Logged 'configure' 'cmake' $configureArguments
    $configured = @{}
    foreach ($line in Get-Content -LiteralPath $cachePath) {
        if ($line -match '^([^#/:][^:]*):[^=]+=(.*)$') {
            $configured[$Matches[1]] = $Matches[2]
        }
    }
    $expectedOptions = $target.options
    foreach ($key in $expectedOptions.Keys) {
        $validValues = if ($expectedOptions[$key]) { @('ON', 'TRUE', '1', 'YES') }
                       else { @('OFF', 'FALSE', '0', 'NO') }
        if (-not $configured.ContainsKey($key) -or $configured[$key] -notin $validValues) {
            throw "Configured $key differs from the required probe setting"
        }
    }
    $expectedPaths = @{
        CMAKE_HOME_DIRECTORY = $SourceDir; VCPKG_ROOT = $VcpkgRoot
        VCPKG_INSTALLED_DIR = $VcpkgInstalled
    }
    $expectedPaths[$configurationKey] = $binaryDir
    foreach ($key in $expectedPaths.Keys) {
        if (-not $configured.ContainsKey($key) -or
            (Full-Path $configured[$key]) -ne (Full-Path $expectedPaths[$key])) {
            throw "Configured $key differs from the explicit input"
        }
    }
    if ($configured['CMAKE_GENERATOR'] -ne $target.generator -or
        $configured['CMAKE_GENERATOR_PLATFORM'] -ne $target.generator_platform -or
        $configured['VCPKG_MANIFEST_FEATURES'] -ne 'sdl2') {
        throw 'Configured generator/platform/dependency feature differs from the probe'
    }
    $cacheHash = (Get-FileHash -LiteralPath $cachePath -Algorithm SHA256).Hash
    @{ options = $expectedOptions; paths = $expectedPaths; cache_sha256 = $cacheHash
       generator = $configured['CMAKE_GENERATOR']; platform = $target.generator_platform; features = 'sdl2'
    } | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $EvidenceDir 'configured-cache.json')
    Invoke-Logged 'build' 'cmake' @('--build', $BuildDir, '--config', $target.configuration,
        '--parallel', "$Parallel", '--target', 'cataclysm-tiles', 'cata_test-tiles')
    foreach ($relative in $target.binaries) {
        $binary = Join-Path $BuildDir $relative
        $name = [IO.Path]::GetFileName($binary)
        $binaryInputs[$name] = @{
            path = $binary; bytes = (Get-Item -LiteralPath $binary).Length
            sha256 = (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash
        }
    }
    $versionUser = Join-Path $EvidenceDir 'version-user'
    New-Item -ItemType Directory -Path $versionUser | Out-Null
    Invoke-Logged 'game-version' (Join-Path $BuildDir $target.binaries[0]) @(
        '--userdir', $versionUser, '--version')
    foreach ($test in $target.tests.GetEnumerator()) {
        $userDir = Join-Path $EvidenceDir ($test.Key + '-user')
        New-Item -ItemType Directory -Path $userDir | Out-Null
        $xml = Join-Path $EvidenceDir ($test.Key + '.xml')
        Invoke-Logged $test.Key (Join-Path $BuildDir $target.binaries[1]) @(
            $test.Value, '--rng-seed', '4902', '--order', 'lex', '--user-dir', $userDir,
            '--reporter', 'junit', '--out', $xml)
        $counts = Check-JUnit $xml
        $testResults += @{
            name = $test.Key; test_cases = $counts.test_cases
            assertions = $counts.assertions; status = 'PASS'; report = $xml
            report_sha256 = (Get-FileHash -LiteralPath $xml -Algorithm SHA256).Hash
        }
    }
    Invoke-Logged 'preflight-after' $Python @('tools/project/preflight.py', '--repo', $SourceDir)
    $after = Get-Content -Raw (Join-Path $EvidenceDir 'preflight-after.log') | ConvertFrom-Json
    if ($after.local_status -ne 'PASS' -or $after.head -ne $state.head -or
        $after.branch -ne $state.branch) {
        throw 'Source checkout changed during the probe'
    }
    foreach ($entry in $assetLock.files | Where-Object kind -eq 'gettext-mo') {
        $catalog = Join-Path $SourceDir $entry.path
        if ((Get-FileHash -LiteralPath $catalog -Algorithm SHA256).Hash -ne $entry.sha256) {
            throw "Source MO changed during the probe: $($entry.path)"
        }
    }
    foreach ($binary in $binaryInputs.Values) {
        if ((Get-FileHash -LiteralPath $binary.path -Algorithm SHA256).Hash -ne $binary.sha256) {
            throw 'Built executable changed during test execution'
        }
    }
    if ((Get-FileHash -LiteralPath $cachePath -Algorithm SHA256).Hash -ne $cacheHash) {
        throw 'CMake cache changed after configuration verification'
    }
    $script:Outcome = 'PASS'
    $script:ResultExit = 0
} catch {
    $failure = $_.Exception.Message
    Write-Error -Message $failure -ErrorAction Continue
} finally {
    if ($locationPushed) { Pop-Location }
    foreach ($key in $savedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($key, $savedEnvironment[$key], 'Process')
    }
    if ($evidenceCreated) {
        @{ status = $script:Outcome; exit_code = $script:ResultExit
           tests = $testResults; binaries = $binaryInputs
           error = $(if (Test-Path variable:failure) { $failure } else { $null })
           platform = [Environment]::OSVersion.VersionString
           scope = 'Native Windows build and focused tests only; no GUI/package/isolation/release acceptance'
        } | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $EvidenceDir 'result.json')
    }
}
exit $script:ResultExit
