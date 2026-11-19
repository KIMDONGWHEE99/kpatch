param([string]$GameDirectory = 'D:\steam\steamapps\common\The Loopler')
$ErrorActionPreference = 'Stop'
$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
$workRoot = Join-Path $workspaceRoot 'working_private\THE_LOOPLER'
$packageRoot = Join-Path $workRoot 'package_v2\from_final_zip'
$runtimePath = Join-Path $workRoot 'qa_c04\runtime_validation.json'
$runtime = Get-Content -LiteralPath $runtimePath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($runtime.status -ne 'PASS' -and $runtime.user_requested_qa_stop -ne $true) { throw '실제 화면 검수 또는 사용자 중단 지시 기록이 필요합니다.' }
$tests = Get-Content -LiteralPath (Join-Path $workRoot 'package_v2\installer_tests.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($tests.status -ne 'PASS') { throw '최종 설치기 시험이 완료되지 않았습니다.' }
$zipPath = Join-Path $workRoot 'package_v2\THE_LOOPLER_KOREAN_PATCH_1.0.0.zip'
if ((Get-FileHash -LiteralPath $zipPath).Hash.ToLowerInvariant() -ne $tests.final_zip_sha256) { throw '시험한 ZIP이 변경됐습니다.' }
if ([IO.Path]::GetFullPath($GameDirectory) -ne 'D:\steam\steamapps\common\The Loopler') { throw '허용한 설치 위치가 아닙니다.' }
if (Get-Process -Name 'The Loopler' -ErrorAction SilentlyContinue) { throw '게임을 정상 종료한 뒤 설치해야 합니다.' }
& (Join-Path $PSScriptRoot 'snapshot_user.ps1') -OutputPath (Join-Path $workRoot 'install_user_before.json')
& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $packageRoot 'Patch.ps1') -Mode Install -GameDirectory $GameDirectory
if ($LASTEXITCODE -ne 0) { throw '패치 설치에 실패했습니다. 설치기의 복구 기록을 확인합니다.' }
$manifest = Get-Content -LiteralPath (Join-Path $packageRoot 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$changeMap = @{}
foreach ($change in $manifest.changes) { $changeMap[$change.path] = $change.patched_sha256 }
$verified = @()
foreach ($file in $manifest.baseline) {
    $expected = if ($changeMap.ContainsKey($file.path)) { $changeMap[$file.path] } else { $file.sha256 }
    $actual = (Get-FileHash -LiteralPath (Join-Path $GameDirectory $file.path)).Hash.ToLowerInvariant()
    if ($actual -ne $expected) { throw "설치 후 내용이 다른 파일: $($file.path)" }
    $verified += [ordered]@{ path=$file.path; sha256=$actual }
}
# 기존 설정은 유지하고 언어 코드 한 곳만 한국어로 선택합니다.
$optionsPath = 'C:\Users\PC\AppData\LocalLow\Mheep Dev\The Loopler\Options.json'
$settingsResult = 'NOT_FOUND'
if ([IO.File]::Exists($optionsPath)) {
    $originalBytes = [IO.File]::ReadAllBytes($optionsPath)
    $originalText = [Text.Encoding]::UTF8.GetString($originalBytes)
    $pattern = '"languageCode"\s*:\s*"[^"]*"'
    if ([regex]::Matches($originalText,$pattern).Count -ne 1) { throw '언어 설정 위치가 예상과 다릅니다.' }
    $backupPath = Join-Path $workRoot 'install_options_original.json'
    if ([IO.File]::Exists($backupPath)) { throw '이전 설정 백업이 존재하므로 덮어쓰지 않습니다.' }
    [IO.File]::WriteAllBytes($backupPath,$originalBytes)
    $newText = [regex]::Replace($originalText,$pattern,'"languageCode":"ko"')
    $beforeObject = $originalText.TrimStart([char]0xFEFF) | ConvertFrom-Json
    $afterObject = $newText.TrimStart([char]0xFEFF) | ConvertFrom-Json
    foreach ($property in $beforeObject.PSObject.Properties) {
        if ($property.Name -ne 'languageCode' -and $property.Value -ne $afterObject.($property.Name)) { throw '언어 이외 설정 변경 감지' }
    }
    $optionsTemporary = $optionsPath + '.loopler-ko-new'
    if ([IO.File]::Exists($optionsTemporary)) { throw '이전 언어 설정 임시 파일이 존재합니다.' }
    try {
        [IO.File]::WriteAllBytes($optionsTemporary,[Text.Encoding]::UTF8.GetBytes($newText))
        [IO.File]::Replace($optionsTemporary,$optionsPath,[System.Management.Automation.Language.NullString]::Value,$true)
        if ([IO.File]::ReadAllText($optionsPath) -ne $newText.TrimStart([char]0xFEFF)) { throw '언어 설정 저장 확인 실패' }
    } catch { [IO.File]::WriteAllBytes($optionsPath,$originalBytes); throw }
    finally { if ([IO.File]::Exists($optionsTemporary)) { Remove-Item -LiteralPath $optionsTemporary } }
    $settingsResult = 'PASS: languageCode만 ko로 변경'
}
& (Join-Path $PSScriptRoot 'snapshot_user.ps1') -OutputPath (Join-Path $workRoot 'install_user_after.json')
[ordered]@{status='PASS';game_id='THE_LOOPLER';steam_build='25262314';candidate='ko_1.0.0_c04';game_directory=$GameDirectory;zip_sha256=$tests.final_zip_sha256;verified_files=$verified;language_selection=$settingsResult;completed=(Get-Date).ToUniversalTime().ToString('o')} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $workRoot 'installation.json') -Encoding utf8
Write-Output 'The Loopler 한국어 적용 및 설치 파일 대조 완료'
