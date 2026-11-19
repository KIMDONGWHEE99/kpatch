param([Parameter(Mandatory=$true)][string]$PackageDirectory, [Parameter(Mandatory=$true)][string]$WorkDirectory)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$null = New-Item -ItemType Directory -Path $WorkDirectory -Force
$tokens = $null; $errors = $null
foreach ($name in @('Patch.ps1', 'ChooseGame.ps1')) {
    $null = [Management.Automation.Language.Parser]::ParseFile((Join-Path $PackageDirectory $name), [ref]$tokens, [ref]$errors)
    if ($errors.Count -ne 0) { throw ($errors | Out-String) }
}
. (Join-Path $PackageDirectory 'ChooseGame.ps1')
$steam = Join-Path $WorkDirectory 'Steam 기본'
$modern = Join-Path $WorkDirectory '추가 라이브러리 [한글] (공백)'
$legacy = Join-Path $WorkDirectory '이전 형식 라이브러리'
$games = @((Join-Path $modern 'steamapps\common\Combolands 다른 이름'), (Join-Path $legacy 'steamapps\common\Combolands'))
foreach ($game in $games) {
    $null = New-Item -ItemType Directory -Path (Join-Path $game 'Combolands_Data') -Force
    [IO.File]::WriteAllBytes((Join-Path $game 'Combolands.exe'), [byte[]]@())
}
$null = New-Item -ItemType Directory -Path (Join-Path $steam 'steamapps') -Force
$vdf = '"libraryfolders"' + "`n{`n" + '"1"' + "`n{`n" + '"path" "' + $modern.Replace('\','\\') + '"' + "`n}`n" + '"2" "' + $legacy.Replace('\','\\') + '"' + "`n}"
[IO.File]::WriteAllText((Join-Path $steam 'steamapps\libraryfolders.vdf'), $vdf, [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $modern 'steamapps\appmanifest_4075620.acf'), '"AppState" { "installdir" "Combolands 다른 이름" }', [Text.UTF8Encoding]::new($false))
$found = @(Get-GameLocations -SteamRoots @($steam, $steam) -NearbyPaths @() -ReceiptRoot '')
if ($found.Count -ne 2 -or @($found | Where-Object { $_ -notin $games }).Count -ne 0) { throw '추가·구형 라이브러리 탐색 실패' }
if ((Resolve-GameLocation ('"' + (Join-Path $games[0] 'Combolands.exe') + '"')) -ne $games[0]) { throw '실행 파일 경로 처리 실패' }
if ($null -ne (Resolve-GameLocation $steam)) { throw '잘못된 게임 폴더 허용' }
if (@(Get-GameLocations -SteamRoots @() -NearbyPaths @() -ReceiptRoot '').Count -ne 0) { throw '빈 탐색 결과 처리 실패' }
$receiptRoot = Join-Path $WorkDirectory 'receipts'
$null = New-Item -ItemType Directory -Path (Join-Path $receiptRoot 'test') -Force
[IO.File]::WriteAllText((Join-Path $receiptRoot 'test\receipt.json'), (@{game_directory=$games[0]} | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
if (@(Get-GameLocations -SteamRoots @() -NearbyPaths @() -ReceiptRoot $receiptRoot)[0] -ne $games[0]) { throw '이전 설치 위치 탐색 실패' }

# 제작한 창을 화면에 띄우지 않고 그려서 배치와 실제 확인 버튼 동작을 점검합니다.
$form = New-GameLocationForm 'Install' $found
try {
    $form.TopLevel = $false
    $form.Show()
    $form.CreateControl()
    $form.PerformLayout()
    $bitmap = [Drawing.Bitmap]::new($form.Width, $form.Height)
    try {
        $form.DrawToBitmap($bitmap, [Drawing.Rectangle]::new(0, 0, $form.Width, $form.Height))
        $bitmap.Save((Join-Path $WorkDirectory 'installer_form.png'), [Drawing.Imaging.ImageFormat]::Png)
    } finally { $bitmap.Dispose() }
    $button = $form.Controls.Find('Confirm', $true)[0]
    $pathBox = $form.Controls.Find('GameDirectory', $true)[0]
    $pathBox.Text = $games[0]
    $method = $button.GetType().GetMethod('OnClick', [Reflection.BindingFlags]'Instance,NonPublic')
    $null = $method.Invoke($button, @([EventArgs]::Empty))
    if ($form.Tag -ne $games[0] -or $form.DialogResult -ne [Windows.Forms.DialogResult]::OK) { throw '선택한 폴더 전달 실패' }
} finally { $form.Dispose() }
$removeForm = New-GameLocationForm 'Uninstall' @()
try {
    if ($removeForm.Controls.Find('Confirm', $true)[0].Text -ne '제거') { throw '제거 창 동작 표시 오류' }
} finally { $removeForm.Dispose() }
$result = [ordered]@{status='PASS';checks=@('Windows PowerShell 5.1 문법', 'Steam 추가·구형 라이브러리', '앱 설치 폴더 이름', '한글·공백·대괄호 경로', '중복 제거', '실행 파일 경로', '게임 폴더 오선택 거부', '탐색 결과 없음', '이전 설치 기록', '창 생성·그리기', '확인 버튼의 선택 경로 전달', '제거 창 표시');powershell=$PSVersionTable.PSVersion.ToString();ui_source_sha256=(Get-FileHash -LiteralPath (Join-Path $PackageDirectory 'ChooseGame.ps1') -Algorithm SHA256).Hash.ToLowerInvariant();real_detected_count=@(Get-GameLocations).Count}
[IO.File]::WriteAllText((Join-Path $WorkDirectory 'path_validation.json'), ($result | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
$result | ConvertTo-Json -Depth 5
