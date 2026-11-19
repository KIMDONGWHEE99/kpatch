$ErrorActionPreference = 'Stop'
$patchPython = (Get-Command python -ErrorAction Stop).Source
& $patchPython (Join-Path $PSScriptRoot 'tools/install_personal.py') restore
if ($LASTEXITCODE -ne 0) { throw '원본 복원을 완료하지 못했습니다. 표시된 내용을 확인해 주세요.' }
Write-Host '원래 한국어 번역으로 복원했습니다.'
