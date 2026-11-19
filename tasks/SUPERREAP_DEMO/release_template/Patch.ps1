[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Install", "Uninstall")]
    [string]$Mode,
    [string]$GameDir = "",
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToUpperInvariant()
}

function Resolve-GameDirectory {
    param([string]$RequestedPath, [string]$ExecutableName, [switch]$NoPrompt)

    $candidates = New-Object System.Collections.Generic.List[string]
    if (-not [string]::IsNullOrWhiteSpace($RequestedPath)) {
        $candidates.Add($RequestedPath)
    }
    $candidates.Add($PSScriptRoot)
    $candidates.Add((Split-Path -Parent $PSScriptRoot))
    $candidates.Add("D:\steam\steamapps\common\SuperReap Demo")
    $candidates.Add("C:\Program Files (x86)\Steam\steamapps\common\SuperReap Demo")

    foreach ($candidate in $candidates) {
        if ([string]::IsNullOrWhiteSpace($candidate)) {
            continue
        }
        $fullPath = [System.IO.Path]::GetFullPath($candidate)
        if (Test-Path -LiteralPath (Join-Path $fullPath $ExecutableName) -PathType Leaf) {
            return $fullPath
        }
    }

    if ($NoPrompt) {
        throw "SuperReap.exe가 있는 게임 폴더를 찾지 못했습니다. -GameDir 인수로 정확한 경로를 지정해 주세요."
    }
    $entered = Read-Host "SuperReap.exe가 있는 게임 폴더를 입력하세요"
    if ([string]::IsNullOrWhiteSpace($entered)) {
        throw "게임 폴더가 입력되지 않았습니다."
    }
    $resolved = [System.IO.Path]::GetFullPath($entered.Trim('"'))
    if (-not (Test-Path -LiteralPath (Join-Path $resolved $ExecutableName) -PathType Leaf)) {
        throw "선택한 폴더에서 SuperReap.exe를 찾지 못했습니다: $resolved"
    }
    return $resolved
}

function Invoke-Xdelta {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Delta,
        [Parameter(Mandatory = $true)][string]$Output
    )
    $messages = & $Executable -d -f -s $Source $Delta $Output 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "차이 패치 적용에 실패했습니다: $Delta`n$($messages -join [Environment]::NewLine)"
    }
}

function Confirm-Operation {
    param([string]$OperationName, [string]$TargetPath, [switch]$NoPrompt)
    if ($NoPrompt) {
        return
    }
    Write-Host ""
    Write-Host "작업: $OperationName"
    Write-Host "대상: $TargetPath"
    $answer = Read-Host "계속하려면 Y를 입력하세요"
    if ($answer -notmatch '^(?i:y|yes|예|네)$') {
        throw "사용자가 작업을 취소했습니다."
    }
}

try {
    $manifestPath = Join-Path $PSScriptRoot "manifest.json"
    $xdeltaPath = Join-Path $PSScriptRoot "tools\xdelta3.exe"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "manifest.json이 없습니다. 패치 압축을 다시 풀어 주세요."
    }
    if (-not (Test-Path -LiteralPath $xdeltaPath -PathType Leaf)) {
        throw "tools\xdelta3.exe가 없습니다. 패치 압축을 다시 풀어 주세요."
    }

    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ((Get-Sha256 $xdeltaPath) -ne $manifest.patch.xdelta_sha256.ToUpperInvariant()) {
        throw "xdelta3.exe의 SHA-256이 일치하지 않습니다. 손상되지 않은 패치 파일을 사용해 주세요."
    }
    $resolvedGameDir = Resolve-GameDirectory -RequestedPath $GameDir -ExecutableName $manifest.patch.game_executable -NoPrompt:$NonInteractive
    if (Get-Process -Name "SuperReap" -ErrorAction SilentlyContinue) {
        throw "SuperReap Demo가 실행 중입니다. 게임을 완전히 종료한 뒤 다시 시도해 주세요."
    }

    $operationName = if ($Mode -eq "Install") { "한국어 패치 설치" } else { "한국어 패치 제거" }
    Confirm-Operation -OperationName $operationName -TargetPath $resolvedGameDir -NoPrompt:$NonInteractive

    $actions = New-Object System.Collections.Generic.List[object]
    foreach ($entry in $manifest.files) {
        $relativeWindows = $entry.path.Replace('/', '\')
        $targetPath = Join-Path $resolvedGameDir $relativeWindows
        if (-not (Test-Path -LiteralPath $targetPath -PathType Leaf)) {
            throw "필수 게임 파일이 없습니다: $relativeWindows"
        }
        $currentHash = Get-Sha256 $targetPath

        if ($Mode -eq "Install") {
            if ($currentHash -eq $entry.patched_sha256.ToUpperInvariant()) {
                $actions.Add([pscustomobject]@{ Entry = $entry; Target = $targetPath; Kind = "KeepPatched"; Source = $null })
                continue
            }
            $accepted = @($entry.accepted_sources | Where-Object { $_.sha256.ToUpperInvariant() -eq $currentHash })
            if ($accepted.Count -ne 1) {
                throw "지원하지 않는 파일 버전이거나 파일이 변조되었습니다: $relativeWindows`n현재 SHA-256: $currentHash"
            }
            $actions.Add([pscustomobject]@{ Entry = $entry; Target = $targetPath; Kind = "Install"; Source = $accepted[0] })
        }
        else {
            if ($currentHash -eq $entry.original_sha256.ToUpperInvariant()) {
                $actions.Add([pscustomobject]@{ Entry = $entry; Target = $targetPath; Kind = "KeepOriginal"; Source = $null })
                continue
            }
            if ($currentHash -eq $entry.patched_sha256.ToUpperInvariant()) {
                $actions.Add([pscustomobject]@{ Entry = $entry; Target = $targetPath; Kind = "Uninstall"; Source = $null })
                continue
            }
            $previous = @($entry.accepted_sources | Where-Object { $_.kind -ne "original" -and $_.sha256.ToUpperInvariant() -eq $currentHash })
            if ($previous.Count -eq 1) {
                $actions.Add([pscustomobject]@{ Entry = $entry; Target = $targetPath; Kind = "UninstallPrevious"; Source = $previous[0] })
                continue
            }
            throw "지원하지 않는 파일 버전이거나 파일이 변조되었습니다: $relativeWindows`n현재 SHA-256: $currentHash"
        }
    }

    $changeActions = @($actions | Where-Object { $_.Kind -notlike "Keep*" })
    if ($changeActions.Count -eq 0) {
        if ($Mode -eq "Install") {
            Write-Host "이미 최신 한국어 패치가 설치되어 있습니다."
        }
        else {
            Write-Host "이미 원본 상태입니다. 제거할 한국어 패치가 없습니다."
        }
        exit 0
    }

    $workRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("SuperReapKoreanPatch_" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $workRoot | Out-Null
    try {
        $prepared = New-Object System.Collections.Generic.List[object]
        $counter = 0
        foreach ($action in $changeActions) {
            $counter++
            $entry = $action.Entry
            $preparedPath = Join-Path $workRoot ("prepared_" + $counter.ToString("000") + ".bin")

            if ($action.Kind -eq "Install") {
                $patchPath = Join-Path $PSScriptRoot $action.Source.patch.Replace('/', '\')
                if ((Get-Sha256 $patchPath) -ne $action.Source.patch_sha256.ToUpperInvariant()) {
                    throw "설치 차이 파일이 손상되었습니다: $($action.Source.patch)"
                }
                Invoke-Xdelta -Executable $xdeltaPath -Source $action.Target -Delta $patchPath -Output $preparedPath
            }
            elseif ($action.Kind -eq "Uninstall") {
                $patchPath = Join-Path $PSScriptRoot $entry.reverse_patch.Replace('/', '\')
                if ((Get-Sha256 $patchPath) -ne $entry.reverse_patch_sha256.ToUpperInvariant()) {
                    throw "제거 차이 파일이 손상되었습니다: $($entry.reverse_patch)"
                }
                Invoke-Xdelta -Executable $xdeltaPath -Source $action.Target -Delta $patchPath -Output $preparedPath
            }
            elseif ($action.Kind -eq "UninstallPrevious") {
                $forwardPath = Join-Path $PSScriptRoot $action.Source.patch.Replace('/', '\')
                $reversePath = Join-Path $PSScriptRoot $entry.reverse_patch.Replace('/', '\')
                if ((Get-Sha256 $forwardPath) -ne $action.Source.patch_sha256.ToUpperInvariant()) {
                    throw "이전 버전 변환 파일이 손상되었습니다: $($action.Source.patch)"
                }
                if ((Get-Sha256 $reversePath) -ne $entry.reverse_patch_sha256.ToUpperInvariant()) {
                    throw "제거 차이 파일이 손상되었습니다: $($entry.reverse_patch)"
                }
                $currentPrepared = Join-Path $workRoot ("current_" + $counter.ToString("000") + ".bin")
                Invoke-Xdelta -Executable $xdeltaPath -Source $action.Target -Delta $forwardPath -Output $currentPrepared
                if ((Get-Sha256 $currentPrepared) -ne $entry.patched_sha256.ToUpperInvariant()) {
                    throw "이전 패치 변환 결과의 SHA-256이 일치하지 않습니다: $($entry.path)"
                }
                Invoke-Xdelta -Executable $xdeltaPath -Source $currentPrepared -Delta $reversePath -Output $preparedPath
            }

            $expectedHash = if ($Mode -eq "Install") { $entry.patched_sha256 } else { $entry.original_sha256 }
            if ((Get-Sha256 $preparedPath) -ne $expectedHash.ToUpperInvariant()) {
                throw "준비된 파일의 SHA-256이 일치하지 않습니다: $($entry.path)"
            }
            $prepared.Add([pscustomobject]@{ Action = $action; Prepared = $preparedPath })
        }

        foreach ($item in $prepared) {
            $temporaryTarget = $item.Action.Target + ".korean_patch_tmp"
            Copy-Item -LiteralPath $item.Prepared -Destination $temporaryTarget -Force
            Move-Item -LiteralPath $temporaryTarget -Destination $item.Action.Target -Force
        }
    }
    finally {
        if (Test-Path -LiteralPath $workRoot) {
            Remove-Item -LiteralPath $workRoot -Recurse -Force
        }
    }

    foreach ($entry in $manifest.files) {
        $targetPath = Join-Path $resolvedGameDir $entry.path.Replace('/', '\')
        $expectedHash = if ($Mode -eq "Install") { $entry.patched_sha256 } else { $entry.original_sha256 }
        if ((Get-Sha256 $targetPath) -ne $expectedHash.ToUpperInvariant()) {
            throw "최종 검사에서 SHA-256이 일치하지 않습니다: $($entry.path)"
        }
    }

    if ($Mode -eq "Install") {
        Write-Host "한국어 패치 설치와 최종 SHA-256 검사가 완료되었습니다."
    }
    else {
        Write-Host "한국어 패치 제거와 원본 SHA-256 복원이 완료되었습니다."
    }
    exit 0
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
