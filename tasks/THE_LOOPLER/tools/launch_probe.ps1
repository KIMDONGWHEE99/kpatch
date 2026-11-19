$ErrorActionPreference = 'Stop'
$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
$qaRoot = (Resolve-Path -LiteralPath (Join-Path $workspaceRoot 'working_private\THE_LOOPLER\risk_probe\game')).Path
$qaLog = Join-Path (Split-Path $qaRoot) 'Player3.log'
$executable = Join-Path $qaRoot 'The Loopler.exe'
if (-not $qaRoot.StartsWith((Join-Path $workspaceRoot 'working_private\THE_LOOPLER\'), [StringComparison]::OrdinalIgnoreCase)) { throw '검수 경로 범위 오류' }
# 직접 경로로 실행하여 Steam 설치본으로 연결되는 앱 탐색을 피합니다.
$qaProcess = Start-Process -FilePath $executable -ArgumentList @('-screen-fullscreen','0','-screen-width','1280','-screen-height','720','-logFile',('"'+$qaLog+'"')) -WorkingDirectory $qaRoot -WindowStyle Normal -PassThru
Start-Sleep -Seconds 2
$observed = Get-Process -Id $qaProcess.Id
if ($observed.Path -ne $executable) { throw '검수 프로세스 실제 경로 불일치' }
[ordered]@{ id=$observed.Id; path=$observed.Path; started=$observed.StartTime.ToUniversalTime().ToString('o'); exe_sha256=(Get-FileHash -LiteralPath $executable).Hash; assembly_sha256=(Get-FileHash -LiteralPath (Join-Path $qaRoot 'GameAssembly.dll')).Hash; log=$qaLog } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path (Split-Path $qaRoot) 'launch3.json') -Encoding utf8
Write-Output "검수 사본 직접 실행: $($observed.Id)"
