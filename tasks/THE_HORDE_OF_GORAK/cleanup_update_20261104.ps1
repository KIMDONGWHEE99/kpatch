param([ValidateSet('Plan','Apply')][string]$Mode='Plan')
$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$taskWork=Join-Path $taskRoot 'working_private\THE_HORDE_OF_GORAK'
$updateRoot=Join-Path $taskWork 'update_20261104'
$packageRoot=Join-Path $taskWork 'package_1.0.1_r1'
if ((Get-Content -LiteralPath (Join-Path $updateRoot 'actual_install_result.json') -Raw -Encoding UTF8 | ConvertFrom-Json).status -ne 'PASS') { throw '실제 설치 확인 필요' }
if ((Get-Content -LiteralPath (Join-Path $updateRoot 'publication_verified.json') -Raw -Encoding UTF8 | ConvertFrom-Json).status -ne 'PASS') { throw '공개 배포 확인 필요' }
$targets=@(
 (Join-Path $taskRoot 'source_original\THE_HORDE_OF_GORAK\steam_26365992'),
 (Join-Path $taskRoot 'build_candidate\THE_HORDE_OF_GORAK\ko_1_0_1_c01\game'),
 (Join-Path $taskRoot 'build_candidate\THE_HORDE_OF_GORAK\ko_1_0_1_c01\THOG.dat'),
 (Join-Path $updateRoot 'previous_original'),
 (Join-Path $packageRoot 'tests\running_game_guard_stub\game'),
 (Join-Path $packageRoot 'tests\추가 Steam 라이브러리\steamapps\common\바뀐 설치 폴더 이름')
)
foreach($run in @('qa_update1104','qa_update_original1104','qa_update_exact1104','qa_update_shop1104','qa_update_shop_direct1104')) {
 foreach($relative in @('game','temp','evidence\smoke_candidate.dat')) { $targets+=Join-Path (Join-Path $taskWork $run) $relative }
}
$targets+=@(Get-ChildItem -LiteralPath $packageRoot -File -Filter '*.rebuilt' | ForEach-Object FullName)
$records=@()
foreach($target in $targets) {
 $absolute=[IO.Path]::GetFullPath($target)
 if (-not $absolute.StartsWith($taskRoot.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw '작업 공간 밖 정리 대상' }
 if (-not (Test-Path -LiteralPath $absolute)) { continue }
 $item=Get-Item -LiteralPath $absolute -Force
 $children=@(if($item.PSIsContainer){Get-ChildItem -LiteralPath $absolute -Recurse -Force}else{$item})
 if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or @($children | Where-Object {$_.Attributes -band [IO.FileAttributes]::ReparsePoint}).Count) { throw '연결 경로 정리 금지' }
 $files=@($children | Where-Object {-not $_.PSIsContainer})
 $records+= [pscustomobject][ordered]@{path=$absolute;files=$files.Count;bytes=[long](($files | Measure-Object -Property Length -Sum).Sum)}
}
$planPath=Join-Path $updateRoot 'cleanup_plan.json'
if($Mode -eq 'Plan') {
 $records | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $planPath -Encoding UTF8
 [ordered]@{targets=$records.Count;files=($records | Measure-Object -Property files -Sum).Sum;bytes=($records | Measure-Object -Property bytes -Sum).Sum;paths=@($records.path)} | ConvertTo-Json -Depth 4
 exit
}
$plan=@(Get-Content -LiteralPath $planPath -Raw -Encoding UTF8 | ConvertFrom-Json)
if($plan.Count -ne $records.Count) { throw '정리 계획이 달라짐' }
for($index=0;$index -lt $records.Count;$index++) {
 foreach($property in @('path','files','bytes')) { if($plan[$index].$property -ne $records[$index].$property){throw '정리 대상 변경'} }
}
foreach($record in $records) { Remove-Item -LiteralPath $record.path -Recurse -Force }
if(@($records | Where-Object {Test-Path -LiteralPath $_.path}).Count){throw '정리 미완료'}
$result=[ordered]@{status='PASS';targets=$records.Count;files=($records | Measure-Object -Property files -Sum).Sum;bytes=($records | Measure-Object -Property bytes -Sum).Sum;preserved='실제 설치본·이전/새 원본 백업·배포 ZIP·설치기·번역·글꼴·도구·검증 기록·검수 저장·화면 캡처'}
$result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $updateRoot 'cleanup_result.json') -Encoding UTF8
$result | ConvertTo-Json -Compress
