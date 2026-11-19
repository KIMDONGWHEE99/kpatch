[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$SourceGame,
    [Parameter(Mandatory = $true)][string]$CandidateGame,
    [Parameter(Mandatory = $true)][string]$ReleaseDir,
    [Parameter(Mandatory = $true)][string]$PreviousAssembly,
    [Parameter(Mandatory = $true)][string]$PreviousGame,
    [Parameter(Mandatory = $true)][string]$TestRoot,
    [Parameter(Mandatory = $true)][string]$ReportPath
)

$ErrorActionPreference = "Stop"

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToUpperInvariant()
}

function Get-TreeHashes {
    param([string]$Root)
    $resolved = [System.IO.Path]::GetFullPath($Root).TrimEnd('\')
    $result = @{}
    foreach ($file in Get-ChildItem -LiteralPath $resolved -Recurse -File) {
        $relative = $file.FullName.Substring($resolved.Length + 1).Replace('\', '/')
        $result[$relative] = Get-Sha256 $file.FullName
    }
    return $result
}

function Assert-TreeEqual {
    param([string]$ActualRoot, [hashtable]$ExpectedHashes, [string]$Label)
    $actualHashes = Get-TreeHashes $ActualRoot
    $actualKeys = @($actualHashes.Keys | Sort-Object)
    $expectedKeys = @($ExpectedHashes.Keys | Sort-Object)
    if (Compare-Object -ReferenceObject $expectedKeys -DifferenceObject $actualKeys) {
        throw "$Label 파일 구성이 예상과 다릅니다."
    }
    foreach ($relative in $expectedKeys) {
        if ($actualHashes[$relative] -ne $ExpectedHashes[$relative]) {
            throw "$Label SHA-256 불일치: $relative"
        }
    }
}

function Invoke-PatchProcess {
    param([string]$PatchScript, [string]$Mode, [string]$GameDir, [int]$ExpectedExitCode)
    $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PatchScript -Mode $Mode -GameDir $GameDir -NonInteractive 2>&1
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne $ExpectedExitCode) {
        throw "$Mode 종료 코드 불일치: 실제 $exitCode / 예상 $ExpectedExitCode`n$($output -join [Environment]::NewLine)"
    }
    return ($output -join [Environment]::NewLine)
}

$sourceResolved = [System.IO.Path]::GetFullPath($SourceGame)
$candidateResolved = [System.IO.Path]::GetFullPath($CandidateGame)
$releaseResolved = [System.IO.Path]::GetFullPath($ReleaseDir)
$previousGameResolved = [System.IO.Path]::GetFullPath($PreviousGame)
$testRootResolved = [System.IO.Path]::GetFullPath($TestRoot)
$reportResolved = [System.IO.Path]::GetFullPath($ReportPath)
$workspaceTestBase = [System.IO.Path]::GetFullPath("working_private\SUPERREAP_DEMO")
if (-not $testRootResolved.StartsWith($workspaceTestBase, [StringComparison]::OrdinalIgnoreCase)) {
    throw "시험 폴더가 허용된 작업 경로 밖에 있습니다: $testRootResolved"
}
if (Test-Path -LiteralPath $testRootResolved) {
    throw "시험 폴더가 이미 존재합니다: $testRootResolved"
}

$sourceHashes = Get-TreeHashes $sourceResolved
$candidateHashes = Get-TreeHashes $candidateResolved
$manifest = Get-Content -LiteralPath (Join-Path $releaseResolved "manifest.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$patchScript = Join-Path $releaseResolved "Patch.ps1"
$testGame = Join-Path $testRootResolved "SuperReap Demo"
$results = New-Object System.Collections.Generic.List[object]

try {
    New-Item -ItemType Directory -Path $testRootResolved | Out-Null
    Copy-Item -LiteralPath $sourceResolved -Destination $testRootResolved -Recurse
    Assert-TreeEqual -ActualRoot $testGame -ExpectedHashes $sourceHashes -Label "원본 시험 복사본"

    $output = Invoke-PatchProcess -PatchScript $patchScript -Mode "Install" -GameDir $testGame -ExpectedExitCode 0
    Assert-TreeEqual -ActualRoot $testGame -ExpectedHashes $candidateHashes -Label "원본 설치"
    $results.Add([pscustomobject]@{ Test = "original_install"; Passed = $true; Output = $output })

    $output = Invoke-PatchProcess -PatchScript $patchScript -Mode "Install" -GameDir $testGame -ExpectedExitCode 0
    Assert-TreeEqual -ActualRoot $testGame -ExpectedHashes $candidateHashes -Label "중복 설치"
    $results.Add([pscustomobject]@{ Test = "duplicate_install"; Passed = $true; Output = $output })

    $output = Invoke-PatchProcess -PatchScript $patchScript -Mode "Uninstall" -GameDir $testGame -ExpectedExitCode 0
    Assert-TreeEqual -ActualRoot $testGame -ExpectedHashes $sourceHashes -Label "설치 후 제거"
    $results.Add([pscustomobject]@{ Test = "uninstall_current"; Passed = $true; Output = $output })

    $previousReleaseHashes = $sourceHashes.Clone()
    foreach ($file in Get-ChildItem -LiteralPath $previousGameResolved -Recurse -File) {
        $relative = $file.FullName.Substring($previousGameResolved.TrimEnd('\').Length + 1).Replace('\', '/')
        if (-not $sourceHashes.ContainsKey($relative)) {
            continue
        }
        $relativeWindows = $relative.Replace('/', '\')
        Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $testGame $relativeWindows) -Force
        $previousReleaseHashes[$relative] = Get-Sha256 $file.FullName
    }
    Assert-TreeEqual -ActualRoot $testGame -ExpectedHashes $previousReleaseHashes -Label "1.0.0 시험 복사본"
    $output = Invoke-PatchProcess -PatchScript $patchScript -Mode "Install" -GameDir $testGame -ExpectedExitCode 0
    Assert-TreeEqual -ActualRoot $testGame -ExpectedHashes $candidateHashes -Label "1.0.0에서 1.0.1 갱신"
    $results.Add([pscustomobject]@{ Test = "previous_release_1.0.0_upgrade"; Passed = $true; Output = $output })

    $output = Invoke-PatchProcess -PatchScript $patchScript -Mode "Uninstall" -GameDir $testGame -ExpectedExitCode 0
    Assert-TreeEqual -ActualRoot $testGame -ExpectedHashes $sourceHashes -Label "1.0.0 갱신 후 제거"
    $results.Add([pscustomobject]@{ Test = "uninstall_after_1.0.0_upgrade"; Passed = $true; Output = $output })

    foreach ($entry in $manifest.files) {
        $relativeWindows = $entry.path.Replace('/', '\')
        Copy-Item -LiteralPath (Join-Path $candidateResolved $relativeWindows) -Destination (Join-Path $testGame $relativeWindows) -Force
    }
    Copy-Item -LiteralPath ([System.IO.Path]::GetFullPath($PreviousAssembly)) -Destination (Join-Path $testGame "SuperReap_Data\Managed\Assembly-CSharp.dll") -Force
    $output = Invoke-PatchProcess -PatchScript $patchScript -Mode "Install" -GameDir $testGame -ExpectedExitCode 0
    Assert-TreeEqual -ActualRoot $testGame -ExpectedHashes $candidateHashes -Label "0.9.0 패치 갱신"
    $results.Add([pscustomobject]@{ Test = "previous_patch_0.9.0_upgrade"; Passed = $true; Output = $output })

    $output = Invoke-PatchProcess -PatchScript $patchScript -Mode "Uninstall" -GameDir $testGame -ExpectedExitCode 0
    Assert-TreeEqual -ActualRoot $testGame -ExpectedHashes $sourceHashes -Label "0.9.0 갱신 후 제거"
    $results.Add([pscustomobject]@{ Test = "uninstall_after_0.9.0_upgrade"; Passed = $true; Output = $output })

    $partialEntry = $manifest.files[0]
    $partialRelative = $partialEntry.path.Replace('/', '\')
    Copy-Item -LiteralPath (Join-Path $candidateResolved $partialRelative) -Destination (Join-Path $testGame $partialRelative) -Force
    $output = Invoke-PatchProcess -PatchScript $patchScript -Mode "Install" -GameDir $testGame -ExpectedExitCode 0
    Assert-TreeEqual -ActualRoot $testGame -ExpectedHashes $candidateHashes -Label "부분 설치 복구"
    $results.Add([pscustomobject]@{ Test = "partial_install_resume"; Passed = $true; Output = $output })

    $output = Invoke-PatchProcess -PatchScript $patchScript -Mode "Uninstall" -GameDir $testGame -ExpectedExitCode 0
    Assert-TreeEqual -ActualRoot $testGame -ExpectedHashes $sourceHashes -Label "부분 설치 복구 후 제거"
    $results.Add([pscustomobject]@{ Test = "uninstall_after_resume"; Passed = $true; Output = $output })

    $modifiedTarget = Join-Path $testGame $partialRelative
    $bytes = [System.IO.File]::ReadAllBytes($modifiedTarget)
    $modifiedBytes = New-Object byte[] ($bytes.Length + 1)
    [Array]::Copy($bytes, $modifiedBytes, $bytes.Length)
    $modifiedBytes[$modifiedBytes.Length - 1] = 0x5A
    [System.IO.File]::WriteAllBytes($modifiedTarget, $modifiedBytes)
    $beforeRejected = Get-TreeHashes $testGame
    $output = Invoke-PatchProcess -PatchScript $patchScript -Mode "Install" -GameDir $testGame -ExpectedExitCode 1
    Assert-TreeEqual -ActualRoot $testGame -ExpectedHashes $beforeRejected -Label "변조 파일 거부 후 무변경"
    $results.Add([pscustomobject]@{ Test = "modified_file_rejected"; Passed = $true; Output = $output })
    Copy-Item -LiteralPath (Join-Path $sourceResolved $partialRelative) -Destination $modifiedTarget -Force
    Assert-TreeEqual -ActualRoot $testGame -ExpectedHashes $sourceHashes -Label "변조 시험 복원"

    $output = Invoke-PatchProcess -PatchScript $patchScript -Mode "Uninstall" -GameDir $testGame -ExpectedExitCode 0
    Assert-TreeEqual -ActualRoot $testGame -ExpectedHashes $sourceHashes -Label "원본 상태 중복 제거"
    $results.Add([pscustomobject]@{ Test = "duplicate_uninstall"; Passed = $true; Output = $output })

    $sourceHashSet = @{}
    foreach ($hash in $sourceHashes.Values) { $sourceHashSet[$hash] = $true }
    $identicalReleaseFiles = @()
    foreach ($file in Get-ChildItem -LiteralPath $releaseResolved -Recurse -File) {
        if ($sourceHashSet.ContainsKey((Get-Sha256 $file.FullName))) {
            $identicalReleaseFiles += $file.FullName
        }
    }
    if ($identicalReleaseFiles.Count -ne 0) {
        throw "배포본에 원본과 동일한 파일이 포함되어 있습니다: $($identicalReleaseFiles -join ', ')"
    }
    $results.Add([pscustomobject]@{ Test = "no_original_payload"; Passed = $true; Output = "원본 동일 파일 0건" })

    $report = [ordered]@{
        schema_version = 1
        passed = $true
        tests = $results.Count
        source_files = $sourceHashes.Count
        candidate_files = $candidateHashes.Count
        results = $results
    }
    $reportDir = Split-Path -Parent $reportResolved
    if (-not (Test-Path -LiteralPath $reportDir)) { New-Item -ItemType Directory -Path $reportDir -Force | Out-Null }
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportResolved -Encoding utf8
    $report | Select-Object schema_version,passed,tests,source_files,candidate_files | Format-List
}
finally {
    if (Test-Path -LiteralPath $testRootResolved) {
        $verified = [System.IO.Path]::GetFullPath($testRootResolved)
        if (-not $verified.StartsWith($workspaceTestBase, [StringComparison]::OrdinalIgnoreCase)) {
            throw "시험 폴더 삭제 안전 검증에 실패했습니다: $verified"
        }
        Remove-Item -LiteralPath $verified -Recurse -Force
    }
}
