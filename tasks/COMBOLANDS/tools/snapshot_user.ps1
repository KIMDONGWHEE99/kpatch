param([Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference = 'Stop'
# 게임과 관련된 저장·로그·설정만 읽고 지문을 비공개 작업 폴더에 보관합니다.
$locations = @('C:\Users\PC\AppData\LocalLow\Crux Games\Combolands')
if (Test-Path -LiteralPath 'D:\steam\userdata') {
    foreach ($account in Get-ChildItem -LiteralPath 'D:\steam\userdata' -Directory) {
        $locations += Join-Path $account.FullName '4075620'
    }
}
$rows = @()
foreach ($location in $locations) {
    if (Test-Path -LiteralPath $location) {
        foreach ($file in Get-ChildItem -LiteralPath $location -Recurse -File) {
            $rows += [ordered]@{path=$file.FullName; size=$file.Length; sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash}
        }
    }
}
$reg = 'HKCU:\Software\Crux Games\Combolands'
$settings = if (Test-Path -LiteralPath $reg) { Get-ItemProperty -LiteralPath $reg | Select-Object * -ExcludeProperty PSPath,PSParentPath,PSChildName,PSDrive,PSProvider } else { $null }
[ordered]@{files=$rows; settings=$settings} | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $OutputPath -Encoding utf8
Write-Output ('저장·로그 파일 {0}개 지문 기록' -f $rows.Count)
