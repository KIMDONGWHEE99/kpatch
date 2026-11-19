param([Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
$patchLocations=@(Join-Path $env:APPDATA 'Godot\app_userdata\Spellbound & Shelved')
if (Test-Path -LiteralPath 'D:\steam\userdata') {
    foreach ($account in Get-ChildItem -LiteralPath 'D:\steam\userdata' -Directory) {
        $patchLocations+=Join-Path $account.FullName '5097840'
    }
}
$patchRows=@()
foreach ($location in $patchLocations) {
    if (Test-Path -LiteralPath $location) {
        foreach ($file in Get-ChildItem -LiteralPath $location -Recurse -File) {
            $patchRows += [ordered]@{path=$file.FullName;size=$file.Length;sha256=(Get-FileHash -LiteralPath $file.FullName).Hash}
        }
    }
}
[ordered]@{locations=$patchLocations;files=$patchRows} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
Write-Output ('원래 게임 저장 파일 {0}개' -f $patchRows.Count)
