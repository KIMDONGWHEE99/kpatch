param(
    [ValidateSet('Install', 'Remove')][string]$Mode = 'Install',
    [string]$Path = ''
)

$ErrorActionPreference = 'Stop'
$expectedDeltaHash = '__DELTA_SHA256__'
$pendingPath = $null
$ownsPending = $false

function Get-BytesHash([byte[]]$Data) {
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($hasher.ComputeHash($Data))).Replace('-', '').ToLowerInvariant() }
    finally { $hasher.Dispose() }
}

function Read-Bytes([string]$FilePath) {
    return ,([System.IO.File]::ReadAllBytes($FilePath))
}

function Convert-Patch([byte[]]$InputBytes, $Delta, [bool]$Reverse) {
    $buffer = New-Object System.IO.MemoryStream
    [long]$cursor = 0
    [long]$shift = 0
    try {
        foreach ($change in $Delta.changes) {
            [byte[]]$oldBytes = [Convert]::FromBase64String([string]$change.oldBase64)
            [byte[]]$newBytes = [System.Text.Encoding]::UTF8.GetBytes([string]$change.newText)
            [long]$position = $change.offset
            if ($Reverse) {
                $position += $shift
                $take = $newBytes
                $put = $oldBytes
            } else {
                $take = $oldBytes
                $put = $newBytes
            }
            if ($position -lt $cursor -or $position + $take.Length -gt $InputBytes.Length) {
                throw '패치의 변경 위치가 올바르지 않습니다.'
            }
            for ($i = 0; $i -lt $take.Length; $i++) {
                if ($InputBytes[$position + $i] -ne $take[$i]) { throw '원본 내용이 패치와 일치하지 않습니다.' }
            }
            $buffer.Write($InputBytes, [int]$cursor, [int]($position - $cursor))
            $buffer.Write($put, 0, $put.Length)
            $cursor = $position + $take.Length
            $shift += $newBytes.Length - $oldBytes.Length
        }
        $buffer.Write($InputBytes, [int]$cursor, [int]($InputBytes.Length - $cursor))
        return ,($buffer.ToArray())
    } finally { $buffer.Dispose() }
}

try {
    $deltaPath = Join-Path $PSScriptRoot 'korean.delta.json'
    $deltaBytes = Read-Bytes $deltaPath
    if ((Get-BytesHash $deltaBytes) -ne $expectedDeltaHash) { throw '패치 자료가 손상되었습니다. ZIP을 다시 풀어 주세요.' }
    $delta = [System.Text.Encoding]::UTF8.GetString($deltaBytes) | ConvertFrom-Json
    if ($delta.schema -ne 1 -or $delta.changes.Count -ne 4235) { throw '지원하지 않는 패치 자료입니다.' }

    if ([string]::IsNullOrWhiteSpace($Path)) {
        Add-Type -AssemblyName System.Windows.Forms
        $dialog = New-Object System.Windows.Forms.OpenFileDialog
        $dialog.Title = 'VanillaPlus 모드의 Config 폴더에서 Localization.csv를 선택하세요'
        $dialog.Filter = '번역표 (Localization.csv)|Localization.csv'
        $dialog.CheckFileExists = $true
        try {
            if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { exit 2 }
            $Path = $dialog.FileName
        } finally { $dialog.Dispose() }
    }

    $targetPath = [System.IO.Path]::GetFullPath($Path)
    if (-not [System.IO.File]::Exists($targetPath)) { throw '선택한 파일을 찾을 수 없습니다.' }
    if ([System.IO.Path]::GetFileName($targetPath) -ne 'Localization.csv') { throw 'Localization.csv를 선택해 주세요.' }
    $configPath = [System.IO.Path]::GetDirectoryName($targetPath)
    $modPath = [System.IO.Path]::GetDirectoryName($configPath)
    if ([System.IO.Path]::GetFileName($configPath) -ne 'Config') { throw '모드의 Config 폴더 안에 있는 파일을 선택해 주세요.' }
    $infoPath = Join-Path $modPath 'ModInfo.xml'
    if (-not [System.IO.File]::Exists($infoPath)) { throw 'ModInfo.xml이 없습니다. 기본 게임이 아닌 VanillaPlus 모드의 파일을 선택해 주세요.' }
    [xml]$info = [System.IO.File]::ReadAllText($infoPath)
    if ($info.xml.Name.value -ne 'VanillaPlus' -or $info.xml.Version.value -ne '1.6.0') {
        throw '이 번역본은 VanillaPlus 1.6.0 전용입니다.'
    }
    $running = @(Get-Process -Name '7DaysToDie', '7DaysToDie_EAC', '7DaysToDieServer' -ErrorAction SilentlyContinue)
    if ($running.Count -gt 0) { throw '게임과 전용 서버를 완전히 종료한 뒤 실행해 주세요.' }

    $inputBytes = Read-Bytes $targetPath
    $inputHash = Get-BytesHash $inputBytes
    $sourceHash = [string]$delta.sourceSha256
    $targetHash = [string]$delta.targetSha256
    if ($inputHash -ne $sourceHash -and $inputHash -ne $targetHash) {
        throw '원본 또는 이 번역본과 내용이 다릅니다. 다른 버전이나 이미 수정한 파일에는 강제로 적용하지 않습니다.'
    }
    $pendingPath = $targetPath + '.vanillaplus-ko.pending'
    if ([System.IO.File]::Exists($pendingPath)) {
        $pendingHash = Get-BytesHash (Read-Bytes $pendingPath)
        if ($pendingHash -ne $sourceHash -and $pendingHash -ne $targetHash) {
            # 쓰기 도중 중단된 자료도 삭제하지 않고 같은 폴더에 보관한다.
            $recoveredPath = $pendingPath + '.recovered.' + [Guid]::NewGuid().ToString('N')
            [System.IO.File]::Move($pendingPath, $recoveredPath)
        } else {
            Remove-Item -LiteralPath $pendingPath
        }
    }
    if (($Mode -eq 'Install' -and $inputHash -eq $targetHash) -or ($Mode -eq 'Remove' -and $inputHash -eq $sourceHash)) {
        Write-Host '이미 요청한 상태입니다. 파일을 변경하지 않았습니다.'
        exit 0
    }

    $reverse = $Mode -eq 'Remove'
    $outputBytes = Convert-Patch $inputBytes $delta $reverse
    $expectedHash = if ($reverse) { $sourceHash } else { $targetHash }
    if ((Get-BytesHash $outputBytes) -ne $expectedHash) { throw '변환 결과 검증에 실패했습니다. 원본은 변경하지 않았습니다.' }

    if (-not $reverse) {
        $backupPath = $targetPath + '.vanillaplus-ko.original'
        if ([System.IO.File]::Exists($backupPath)) {
            $backupBytes = Read-Bytes $backupPath
            if ((Get-BytesHash $backupBytes) -ne $sourceHash) {
                $partialBackup = $backupBytes.Length -lt $inputBytes.Length
                for ($i = 0; $partialBackup -and $i -lt $backupBytes.Length; $i++) {
                    if ($backupBytes[$i] -ne $inputBytes[$i]) { $partialBackup = $false }
                }
                if (-not $partialBackup) { throw '기존 백업의 내용이 다릅니다. 덮어쓰지 않습니다.' }
                $recoveredBackup = $backupPath + '.recovered.' + [Guid]::NewGuid().ToString('N')
                [System.IO.File]::Move($backupPath, $recoveredBackup)
            }
        }
        if (-not [System.IO.File]::Exists($backupPath)) {
            $backupStream = [System.IO.File]::Open($backupPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
            try { $backupStream.Write($inputBytes, 0, $inputBytes.Length); $backupStream.Flush($true) }
            finally { $backupStream.Dispose() }
        }
    }

    # 모든 결과를 완성한 뒤 파일 하나를 원자적으로 교체한다. 중단되어도 원본 또는 검증된 번역본이 남는다.
    $pendingStream = [System.IO.File]::Open($pendingPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
    $ownsPending = $true
    try { $pendingStream.Write($outputBytes, 0, $outputBytes.Length); $pendingStream.Flush($true) }
    finally { $pendingStream.Dispose() }
    if ((Get-BytesHash (Read-Bytes $pendingPath)) -ne $expectedHash) { throw '임시 파일 검증에 실패했습니다.' }
    if ((Get-BytesHash (Read-Bytes $targetPath)) -ne $inputHash) { throw '작업 도중 대상 파일이 바뀌었습니다. 적용을 중단했습니다.' }
    [System.IO.File]::Replace($pendingPath, $targetPath, [NullString]::Value)
    $ownsPending = $false
    if ((Get-BytesHash (Read-Bytes $targetPath)) -ne $expectedHash) { throw '최종 파일 검증에 실패했습니다.' }
    if ($reverse) { Write-Host '원문 복구 완료. 게임의 한국어 설정은 그대로 사용할 수 있습니다.' }
    else { Write-Host '한국어 번역 적용 완료. 게임 언어를 한국어로 설정한 뒤 플레이하세요.' }
    Write-Host $targetPath
    exit 0
} catch {
    if ($ownsPending -and $pendingPath -and [System.IO.File]::Exists($pendingPath)) {
        try { Remove-Item -LiteralPath $pendingPath } catch { }
    }
    Write-Host ('처리하지 못했습니다: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
