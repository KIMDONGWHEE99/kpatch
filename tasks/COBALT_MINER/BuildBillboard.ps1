# 이미지 편집 도구가 만든 한글 영역을 원래 게임 텍스처에 조립합니다.
# 원본의 다른 영역과 각 프레임의 글자 점멸 방향은 유지합니다.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$InputRoot = Join-Path $Root 'extracted_private/COBALT_MINER/steam_24347666/nebula_01/images'
$OutputRoot = Join-Path $Root 'working_private/COBALT_MINER/media_ko_01'
$GeneratedPath = Join-Path $OutputRoot 'billboard_generated.png'
$Panel = [System.Drawing.Bitmap]::new(141, 67, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$Generated = [System.Drawing.Bitmap]::new($GeneratedPath)
$Graphics = [System.Drawing.Graphics]::FromImage($Panel)
$Graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
$Graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::Half
$Graphics.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceCopy
$Graphics.DrawImage($Generated, [System.Drawing.Rectangle]::new(0,0,141,67))
$Graphics.Dispose()
$Generated.Dispose()
$Panel.Save((Join-Path $OutputRoot 'billboard_panel_141x67.png'), [System.Drawing.Imaging.ImageFormat]::Png)
$Base = [System.Drawing.Bitmap]::new((Join-Path $InputRoot '01374.png'))
$Records = @()
foreach ($Handle in @(1374,1486,1491,1492,1498,1499,1500,1501,1503,1504,1513)) {
    $Name = '{0:D5}.png' -f $Handle
    $Source = [System.Drawing.Bitmap]::new((Join-Path $InputRoot $Name))
    $Output = $Source.Clone([System.Drawing.Rectangle]::new(0,0,$Source.Width,$Source.Height),[System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $WarmPixels = 0
    for ($X = 0; $X -lt 141; $X++) {
        $WhiteCount = 0
        $WarmCount = 0
        # 각 열에서 원문이 점멸하는 비율을 해당 한글 열에 연결합니다.
        for ($Y = 0; $Y -lt 67; $Y++) {
            $A = $Base.GetPixel($X + 234, $Y + 99)
            $B = $Source.GetPixel($X + 234, $Y + 99)
            if ($A.R -eq 255 -and $A.G -eq 255 -and $A.B -eq 255) {
                $WhiteCount++
                if ($B.R -eq 255 -and $B.G -eq 219 -and $B.B -eq 187) { $WarmCount++ }
            }
        }
        $Flicker = $WhiteCount -gt 0 -and ($WarmCount / $WhiteCount) -ge 0.5
        for ($Y = 0; $Y -lt 67; $Y++) {
            $Color = $Panel.GetPixel($X,$Y)
            if ($Flicker -and $Color.R -gt 230 -and $Color.G -gt 230 -and $Color.B -gt 230) {
                $Color = [System.Drawing.Color]::FromArgb($Color.A,255,219,187)
                $WarmPixels++
            }
            $Output.SetPixel($X+234,$Y+99,$Color)
        }
    }
    $OutsideDifferences = 0
    for ($Y=0; $Y -lt $Source.Height; $Y++) {
        for ($X=0; $X -lt $Source.Width; $X++) {
            if ($X -ge 234 -and $X -lt 375 -and $Y -ge 99 -and $Y -lt 166) { continue }
            if ($Source.GetPixel($X,$Y).ToArgb() -ne $Output.GetPixel($X,$Y).ToArgb()) { $OutsideDifferences++ }
        }
    }
    if ($OutsideDifferences -ne 0) { throw '허용 영역 밖 변경' }
    $Path = Join-Path $OutputRoot $Name
    $Output.Save($Path,[System.Drawing.Imaging.ImageFormat]::Png)
    $Records += [ordered]@{handle=$Handle; source_sha256=(Get-FileHash -LiteralPath (Join-Path $InputRoot $Name) -Algorithm SHA256).Hash.ToLower(); output_sha256=(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLower(); allowed_region=@(234,99,375,166); outside_differences=$OutsideDifferences; warm_pixels=$WarmPixels; width=$Source.Width; height=$Source.Height}
    $Source.Dispose()
    $Output.Dispose()
}
$Base.Dispose()
$Panel.Dispose()
$Report = [ordered]@{generator='image_gen'; generated_sha256=(Get-FileHash -LiteralPath $GeneratedPath -Algorithm SHA256).Hash.ToLower(); text="아름다움과`n평온"; process='생성된 편집 영역 축소와 원본 프레임별 글자 점멸 조립'; runtime_qa='NOT_RUN'; files=$Records}
$Report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputRoot 'manifest.json') -Encoding utf8
$Records | Select-Object handle,warm_pixels,outside_differences
