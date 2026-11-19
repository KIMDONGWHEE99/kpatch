param(
    [Parameter(Mandatory = $true)]
    [int]$ProcessId,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [int]$TimeoutSeconds = 20
)

Add-Type -AssemblyName System.Drawing

Add-Type @'
using System;
using System.Runtime.InteropServices;

public static class GameWindowCaptureNative
{
    [StructLayout(LayoutKind.Sequential)]
    public struct Rect
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out Rect rect);

    [DllImport("user32.dll")]
    public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdc, uint flags);
}
'@

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$handle = [IntPtr]::Zero
while ([DateTime]::UtcNow -lt $deadline) {
    $process = Get-Process -Id $ProcessId -ErrorAction Stop
    $process.Refresh()
    $handle = $process.MainWindowHandle
    if ($handle -ne [IntPtr]::Zero) {
        break
    }
    Start-Sleep -Milliseconds 250
}

if ($handle -eq [IntPtr]::Zero) {
    throw "게임 창을 찾지 못했습니다."
}

$rect = New-Object GameWindowCaptureNative+Rect
if (-not [GameWindowCaptureNative]::GetWindowRect($handle, [ref]$rect)) {
    throw "게임 창 크기를 읽지 못했습니다."
}

$width = $rect.Right - $rect.Left
$height = $rect.Bottom - $rect.Top
if ($width -le 0 -or $height -le 0) {
    throw "게임 창 크기가 올바르지 않습니다: ${width}x${height}"
}

$bitmap = New-Object System.Drawing.Bitmap($width, $height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$hdc = $graphics.GetHdc()
try {
    # PW_RENDERFULLCONTENT(2): 가려진 창도 해당 창 내용만 렌더링한다.
    if (-not [GameWindowCaptureNative]::PrintWindow($handle, $hdc, 2)) {
        throw "게임 창 캡처에 실패했습니다."
    }
}
finally {
    $graphics.ReleaseHdc($hdc)
    $graphics.Dispose()
}

$absoluteOutput = [System.IO.Path]::GetFullPath($OutputPath)
$parent = [System.IO.Path]::GetDirectoryName($absoluteOutput)
[System.IO.Directory]::CreateDirectory($parent) | Out-Null
try {
    $bitmap.Save($absoluteOutput, [System.Drawing.Imaging.ImageFormat]::Png)
}
finally {
    $bitmap.Dispose()
}

Write-Output $absoluteOutput
