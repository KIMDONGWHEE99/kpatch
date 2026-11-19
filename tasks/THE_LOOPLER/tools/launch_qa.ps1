param([string]$RunName = 'run01')
$ErrorActionPreference = 'Stop'
$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
$qaRoot = (Resolve-Path -LiteralPath (Join-Path $workspaceRoot 'working_private\THE_LOOPLER\qa_c04\game')).Path
if ($RunName -notmatch '^run[0-9]{2}$') { throw '검수 실행 이름 오류' }
$qaLog = Join-Path (Split-Path $qaRoot) ($RunName + '.log')
$executable = Join-Path $qaRoot 'The Loopler.exe'
if (-not $qaRoot.StartsWith((Join-Path $workspaceRoot 'working_private\THE_LOOPLER\'), [StringComparison]::OrdinalIgnoreCase)) { throw '검수 경로 범위 오류' }
if (Get-Process 'The Loopler' -ErrorAction SilentlyContinue) { throw '게임이 이미 실행 중입니다' }
& (Join-Path $PSScriptRoot 'snapshot_user.ps1') -OutputPath (Join-Path (Split-Path $qaRoot) ($RunName + '_user_before.json'))
$qaProcess = Start-Process -FilePath $executable -ArgumentList @('-screen-fullscreen','0','-screen-width','1280','-screen-height','720','-logFile',('"'+$qaLog+'"')) -WorkingDirectory $qaRoot -WindowStyle Normal -PassThru
Start-Sleep -Seconds 2
$observed = Get-Process -Id $qaProcess.Id
if ($observed.Path -ne $executable) { throw '검수 프로세스 실제 경로 불일치' }
[ordered]@{ id=$observed.Id; path=$observed.Path; started=$observed.StartTime.ToUniversalTime().ToString('o'); exe_sha256=(Get-FileHash -LiteralPath $executable).Hash; assembly_sha256=(Get-FileHash -LiteralPath (Join-Path $qaRoot 'GameAssembly.dll')).Hash; metadata_sha256=(Get-FileHash -LiteralPath (Join-Path $qaRoot 'The Loopler_Data\il2cpp_data\Metadata\global-metadata.dat')).Hash; data_sha256=(Get-FileHash -LiteralPath (Join-Path $qaRoot 'The Loopler_Data\data.unity3d')).Hash; log=$qaLog } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path (Split-Path $qaRoot) ($RunName + '_launch.json')) -Encoding utf8
Write-Output "검수 후보 실행: $($observed.Id)"
