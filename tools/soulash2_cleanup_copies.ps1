param([Parameter(Mandatory=$true)][string]$ExpectedPlanSha256, [switch]$Resume)
$ErrorActionPreference = 'Stop'
$workspaceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')
$cleanupRoot = Join-Path $workspaceRoot 'working_private\SOULASH_2\storage_cleanup_20261031'
$planPath = Join-Path $cleanupRoot 'plan.json'
if ((Get-FileHash -LiteralPath $planPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedPlanSha256) { throw '삭제 계획 지문 불일치' }
$plan = Get-Content -LiteralPath $planPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($plan.workspace -ne $workspaceRoot) { throw '작업 경로 불일치' }
$allowedRoots = @('source_original\SOULASH_2','build_candidate\SOULASH_2','working_private\SOULASH_2') | ForEach-Object { (Join-Path $workspaceRoot $_) + '\' }
$validated = New-Object 'System.Collections.Generic.List[object]'
$deletedRecords = New-Object 'System.Collections.Generic.List[string]'
foreach ($entry in $plan.targets) {
    $absolute = [IO.Path]::GetFullPath($entry.path)
    if ($absolute -ne $entry.path) { throw '절대 경로 불일치' }
    if (-not ($allowedRoots | Where-Object { $absolute.StartsWith($_, [StringComparison]::OrdinalIgnoreCase) })) { throw '삭제 허용 경계 밖' }
    if (-not (Test-Path -LiteralPath $absolute)) {
        if (-not $Resume) { throw '삭제 전 대상 누락' }
        $deletedRecords.Add($entry.relative)
        continue
    }
    $resolved = (Resolve-Path -LiteralPath $entry.path).ProviderPath
    $absolute = [IO.Path]::GetFullPath($resolved)
    if ($absolute -ne $entry.path) { throw '최종 경로 변경' }
    if (-not ($allowedRoots | Where-Object { $absolute.StartsWith($_, [StringComparison]::OrdinalIgnoreCase) })) { throw '삭제 허용 경계 밖' }
    $current = Get-Item -LiteralPath $absolute -Force
    while ($null -ne $current -and $current.FullName -ne $workspaceRoot) {
        if ($current.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw '연결 경로 삭제 거부' }
        if ($current.Attributes -band [IO.FileAttributes]::Directory) { $current = $current.Parent }
        else { $current = $current.Directory }
    }
    if ($entry.is_directory) {
        $links = Get-ChildItem -LiteralPath $absolute -Recurse -Force -Attributes ReparsePoint
        if ($links) { throw '하위 연결 경로 삭제 거부' }
    }
    $validated.Add($entry)
}
# 실행 중인 게임 사본은 제거하지 않는다. 실제 설치된 게임은 허용 경계 밖이다.
foreach ($process in @(Get-Process -Name 'Soulash 2' -ErrorAction SilentlyContinue)) {
    if (-not $process.Path) { throw '실행 중인 게임의 경로를 확인할 수 없음' }
    foreach ($entry in $validated) {
        if ($process.Path.StartsWith($entry.path + '\', [StringComparison]::OrdinalIgnoreCase) -or $process.Path -eq $entry.path) { throw '삭제 대상 게임이 실행 중' }
    }
}
if ((Get-FileHash -LiteralPath $plan.qa_archive.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $plan.qa_archive.sha256) { throw '검수 기록 보존 실패' }
$completed = $deletedRecords.Count
foreach ($entry in $validated) {
    # 삭제 직전에 절대 경로와 연결 상태를 다시 확인한다.
    $resolved = (Resolve-Path -LiteralPath $entry.path).ProviderPath
    if ($resolved -ne $entry.path) { throw '삭제 직전 경로 변경' }
    if ((Get-Item -LiteralPath $resolved -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw '삭제 직전 연결 경로 발견' }
    if ($entry.is_directory) { Remove-Item -LiteralPath $resolved -Recurse -Force }
    else { Remove-Item -LiteralPath $resolved -Force }
    if (Test-Path -LiteralPath $resolved) { throw '삭제 후 경로 잔존' }
    $deletedRecords.Add($entry.relative)
    $completed++
    if ($completed % 2000 -eq 0) { Write-Output "삭제 완료 대상: $completed" }
}
[IO.File]::WriteAllLines((Join-Path $cleanupRoot 'deleted_paths.txt'), $deletedRecords, (New-Object Text.UTF8Encoding($true)))
[ordered]@{ status = 'PASS'; deleted_targets = $completed; deleted_files = $plan.delete_files; deleted_bytes = $plan.delete_bytes; plan_sha256 = $ExpectedPlanSha256; finished_utc = [DateTime]::UtcNow.ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $cleanupRoot 'deletion_result.json') -Encoding UTF8
Write-Output "삭제 완료: $completed 대상"
