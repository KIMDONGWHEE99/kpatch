param([Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference = 'Stop'
# 이 게임의 저장 영역만 읽고 크기와 내용 지문을 기록합니다.
$savePaths = @('C:\Users\PC\AppData\LocalLow\Mheep Dev\The Loopler')
$steamRoot = 'D:\steam\userdata'
if (Test-Path -LiteralPath $steamRoot) {
    foreach ($account in Get-ChildItem -LiteralPath $steamRoot -Directory) {
        $savePaths += Join-Path $account.FullName '4150860'
    }
}
$files = @()
foreach ($path in $savePaths) {
    if (Test-Path -LiteralPath $path) {
        foreach ($file in Get-ChildItem -LiteralPath $path -Recurse -File) {
            $files += [ordered]@{ path=$file.FullName; size=$file.Length; sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash }
        }
    }
}
$registryPath = 'HKCU:\Software\Mheep Dev\The Loopler'
$registry = if (Test-Path -LiteralPath $registryPath) { (Get-ItemProperty -LiteralPath $registryPath | Select-Object * -ExcludeProperty PS*) } else { $null }
[ordered]@{ files=$files; registry=$registry } | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $OutputPath -Encoding utf8
Write-Output "저장 파일 $($files.Count)개, 설정 존재 $($null -ne $registry)"
