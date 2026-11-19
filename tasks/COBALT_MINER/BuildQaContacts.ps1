param(
    [Parameter(Mandatory=$true)][string]$InputFolder,
    [Parameter(Mandatory=$true)][string]$OutputFolder,
    [int]$X=940,[int]$Y=352,[int]$Width=224,[int]$Height=101,[int]$Padding=12,
    [switch]$WhitePanel
)
# 실제 캡처를 내용 변경 없이 원래 크기로 잘라 비교판을 만듭니다.
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Drawing
$privateRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../working_private/COBALT_MINER')).TrimEnd('\')+'\'
$inputRoot=[IO.Path]::GetFullPath($InputFolder)
$outputRoot=[IO.Path]::GetFullPath($OutputFolder)
if (-not $inputRoot.StartsWith($privateRoot,[StringComparison]::OrdinalIgnoreCase) -or -not $outputRoot.StartsWith($privateRoot,[StringComparison]::OrdinalIgnoreCase)) {throw '비공개 Cobalt 경로만 허용'}
if (Test-Path -LiteralPath $outputRoot) {throw '기존 비교판을 덮어쓰지 않음'}
[IO.Directory]::CreateDirectory($outputRoot)|Out-Null
$records=[Collections.Generic.List[object]]::new()
$unique=[Collections.Generic.List[object]]::new()
$seen=@{}
$rect=[Drawing.Rectangle]::new($X,$Y,$Width,$Height)
$displayRect=[Drawing.Rectangle]::new($X-$Padding,$Y-$Padding,$Width+2*$Padding,$Height+2*$Padding)
$hash=[Security.Cryptography.SHA256]::Create()
foreach($file in Get-ChildItem -LiteralPath $inputRoot -Filter 'cycle_*.bmp' | Sort-Object Name) {
    if($file.Length -ne 8294454) {continue}
    $source=[Drawing.Bitmap]::new($file.FullName)
    try {
        if($source.Width -ne 1920 -or $source.Height -ne 1080){throw '캡처 해상도 불일치'}
        if($WhitePanel) {
            $corners=@($source.GetPixel($X+2,$Y+2),$source.GetPixel($X+$Width-3,$Y+2),$source.GetPixel($X+2,$Y+$Height-3),$source.GetPixel($X+$Width-3,$Y+$Height-3))
            if(@($corners|Where-Object {$_.R -lt 245 -or $_.G -lt 245 -or $_.B -lt 245}).Count -gt 0){continue}
        }
        $crop=$source.Clone($rect,[Drawing.Imaging.PixelFormat]::Format24bppRgb)
        $stream=[IO.MemoryStream]::new()
        try {
            $crop.Save($stream,[Drawing.Imaging.ImageFormat]::Png)
            $bytes=$stream.ToArray()
            $digest=([BitConverter]::ToString($hash.ComputeHash($bytes))).Replace('-','').ToLowerInvariant()
            if(-not $seen.ContainsKey($digest)) {
                $number=$unique.Count
                $name=('panel_{0:D3}.png' -f $number)
                $display=$source.Clone($displayRect,[Drawing.Imaging.PixelFormat]::Format24bppRgb)
                try {$display.Save((Join-Path $outputRoot $name),[Drawing.Imaging.ImageFormat]::Png)} finally {$display.Dispose()}
                $row=[pscustomobject]@{panel=$number;file=$name;roi_sha256=$digest;display_sha256=(Get-FileHash -LiteralPath (Join-Path $outputRoot $name) -Algorithm SHA256).Hash.ToLowerInvariant();first_capture=$file.Name;source_sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant();rect=@($X,$Y,$Width,$Height);display_rect=@($displayRect.X,$displayRect.Y,$displayRect.Width,$displayRect.Height);graphics_review='NOT_RUN';paragraph='UNKNOWN'}
                $unique.Add($row);$seen[$digest]=$number
            }
            $records.Add([pscustomobject]@{capture=$file.Name;panel=$seen[$digest];roi_sha256=$digest})
        } finally {$stream.Dispose();$crop.Dispose()}
    } finally {$source.Dispose()}
}
if($unique.Count -eq 0){throw '비교할 화면 영역 없음'}
$tileWidth=$displayRect.Width+12;$tileHeight=$displayRect.Height+28;$columns=4;$perPage=12
$font=[Drawing.Font]::new('Segoe UI',10)
for($page=0;$page -lt [Math]::Ceiling($unique.Count/$perPage);$page++) {
    $count=[Math]::Min($perPage,$unique.Count-$page*$perPage)
    $board=[Drawing.Bitmap]::new($columns*$tileWidth,[int]([Math]::Ceiling($count/$columns)*$tileHeight))
    $graphics=[Drawing.Graphics]::FromImage($board)
    try {
        $graphics.Clear([Drawing.Color]::FromArgb(210,210,210))
        for($slot=0;$slot -lt $count;$slot++) {
            $row=$unique[$page*$perPage+$slot];$left=($slot%$columns)*$tileWidth+6;$top=[int]([Math]::Floor($slot/$columns)*$tileHeight)
            $graphics.DrawString(('P{0:D3}  {1}' -f $row.panel,$row.first_capture),$font,[Drawing.Brushes]::Black,$left,$top+3)
            $panel=[Drawing.Bitmap]::new((Join-Path $outputRoot $row.file))
            try {$graphics.DrawImageUnscaled($panel,$left,$top+24)} finally {$panel.Dispose()}
        }
        $board.Save((Join-Path $outputRoot ('contact_{0:D2}.png' -f $page)),[Drawing.Imaging.ImageFormat]::Png)
    } finally {$graphics.Dispose();$board.Dispose()}
}
$font.Dispose();$hash.Dispose()
$report=[pscustomobject]@{source=$inputRoot;rect=@($X,$Y,$Width,$Height);unique_panels=$unique.Count;captures=$records.Count;panels=$unique;mapping=$records;graphics_review='NOT_RUN';paragraph_alignment='NOT_RUN';scope='원래 크기의 캡처 영역 비교판. 그림·텍스트를 합성하거나 수정하지 않음. 각 문단과 실제 판독을 연결해야 함.'}
$report|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $outputRoot 'contacts.json') -Encoding utf8
[pscustomobject]@{unique=$unique.Count;captures=$records.Count;output=$outputRoot}|ConvertTo-Json -Compress
