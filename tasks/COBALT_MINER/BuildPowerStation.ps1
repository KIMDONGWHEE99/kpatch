# imagegen에서 이미 만든 한글 패널을 잘라 원래의 정확한 영역에 조립합니다.
# 새 글씨나 그림을 코드로 그리지 않습니다.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$SourceRoot = Join-Path $Root 'extracted_private/COBALT_MINER/steam_24347666/nebula_01/images'
$PreviousRoot = Join-Path $Root 'working_private/COBALT_MINER/media_ko_01'
$OutputRoot = Join-Path $Root 'working_private/COBALT_MINER/media_ko_02'
$GeneratedInput = 'C:/Users/PC/.codex/generated_images/01a195f0-6079-7510-af21-63485768d8e8/exec-1c4493a7-9ac7-4d54-b8a9-77ea7e04962d.png'
if (Test-Path -LiteralPath $OutputRoot) { throw '기존 미디어 후보 덮어쓰기 금지' }
New-Item -ItemType Directory -Path $OutputRoot | Out-Null
$PreviousManifest = Join-Path $PreviousRoot 'manifest.json'
$Previous = Get-Content -LiteralPath $PreviousManifest -Raw | ConvertFrom-Json
$Records = @()
foreach ($Row in $Previous.files) {
    $Name = '{0:D5}.png' -f $Row.handle
    Copy-Item -LiteralPath (Join-Path $PreviousRoot $Name) -Destination (Join-Path $OutputRoot $Name)
    if ((Get-FileHash -LiteralPath (Join-Path $OutputRoot $Name) -Algorithm SHA256).Hash.ToLower() -ne $Row.output_sha256) { throw '광고판 복사 지문 불일치' }
    $Records += $Row
}
$GeneratedPath = Join-Path $OutputRoot 'power_station_generated.png'
Copy-Item -LiteralPath $GeneratedInput -Destination $GeneratedPath
$Generated = [System.Drawing.Bitmap]::new($GeneratedPath)
if ($Generated.Width -ne 2170 -or $Generated.Height -ne 725) { throw '확인한 생성 이미지 크기와 다름' }
$Panel = [System.Drawing.Bitmap]::new(140,39,[System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$Graphics = [System.Drawing.Graphics]::FromImage($Panel)
$Graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
$Graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::Half
$Graphics.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceCopy
# 원본 확인에서 위 60행과 아래 63행은 생성 이미지의 검정 띠였습니다.
$Graphics.DrawImage($Generated,[System.Drawing.Rectangle]::new(0,0,140,39),0,60,2170,602,[System.Drawing.GraphicsUnit]::Pixel)
$Graphics.Dispose()
$Generated.Dispose()
$Panel.Save((Join-Path $OutputRoot 'power_station_panel_140x39.png'),[System.Drawing.Imaging.ImageFormat]::Png)
$OriginalPath = Join-Path $SourceRoot '01123.png'
$Original = [System.Drawing.Bitmap]::new($OriginalPath)
$Output = $Original.Clone([System.Drawing.Rectangle]::new(0,0,$Original.Width,$Original.Height),[System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
for ($Y=0; $Y -lt 39; $Y++) {
    for ($X=0; $X -lt 140; $X++) {
        $Color = $Panel.GetPixel($X,$Y)
        $OriginalColor = $Original.GetPixel($X+47,$Y+197)
        # 영역 왼쪽 아래의 원본 투명 마젠타 4픽셀은 그림의 바깥 윤곽이므로 보존합니다.
        if ($OriginalColor.A -eq 0) { continue }
        if ($Color.A -ne $OriginalColor.A) { throw '패널 내부 원본 알파 변경' }
        $Output.SetPixel($X+47,$Y+197,$Color)
    }
}
$Outside=0; $Alpha=0; $Magenta=0
for ($Y=0; $Y -lt $Original.Height; $Y++) {
    for ($X=0; $X -lt $Original.Width; $X++) {
        $A=$Original.GetPixel($X,$Y); $B=$Output.GetPixel($X,$Y)
        if ($A.A -ne $B.A) { $Alpha++ }
        if ($A.R -eq 255 -and $A.G -eq 0 -and $A.B -eq 255 -and $A.ToArgb() -ne $B.ToArgb()) { $Magenta++ }
        if ($X -ge 47 -and $X -lt 187 -and $Y -ge 197 -and $Y -lt 236) { continue }
        if ($A.ToArgb() -ne $B.ToArgb()) { $Outside++ }
    }
}
if ($Outside -or $Alpha -or $Magenta) { throw '영역 밖·알파·투명 마젠타 변경' }
$OutputPath = Join-Path $OutputRoot '01123.png'
$Output.Save($OutputPath,[System.Drawing.Imaging.ImageFormat]::Png)
$Original.Dispose(); $Output.Dispose(); $Panel.Dispose()
$Records += [ordered]@{handle=1123;source_sha256=(Get-FileHash -LiteralPath $OriginalPath -Algorithm SHA256).Hash.ToLower();output_sha256=(Get-FileHash -LiteralPath $OutputPath -Algorithm SHA256).Hash.ToLower();allowed_region=@(47,197,187,236);outside_differences=$Outside;alpha_differences=$Alpha;transparent_magenta_differences=$Magenta;width=256;height=256;method='MEDIA_REPLACE';source_transcription=$null;source_transcription_status='UNKNOWN';text='발전소';reason='원문을 추측 번역하지 않고 객체506·설명514·frame7 event1219/1220으로 확인된 기능명 표지를 제작';generated_sha256=(Get-FileHash -LiteralPath $GeneratedPath -Algorithm SHA256).Hash.ToLower();generated_crop_xyxy=@(0,60,2170,662);resize='NearestNeighbor'}
$Manifest=[ordered]@{generator='image_gen';previous_manifest_sha256=(Get-FileHash -LiteralPath $PreviousManifest -Algorithm SHA256).Hash.ToLower();process='기존 광고판 11장 그대로 복사, imagegen 생성 발전소 간판의 금속 패널 영역만 축소·조립';runtime_qa='NOT_RUN';files=$Records}
$Manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $OutputRoot 'manifest.json') -Encoding utf8
$Records | Select-Object handle,outside_differences,alpha_differences
