param(
    [Parameter(Mandatory = $true)][int]$ProcessId,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [int]$TimeoutSeconds = 20
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Text;
using System.Runtime.InteropServices;
using System.Collections.Generic;

public static class TFC2WindowNative
{
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [StructLayout(LayoutKind.Sequential)]
    public struct Rect { public int Left; public int Top; public int Right; public int Bottom; }

    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out Rect rect);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int maxCount);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr hWnd, StringBuilder text, int maxCount);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdc, uint flags);

    public static List<IntPtr> WindowsForProcess(uint wanted)
    {
        var result = new List<IntPtr>();
        EnumWindows((window, parameter) => {
            uint actual;
            GetWindowThreadProcessId(window, out actual);
            if (actual == wanted) result.Add(window);
            return true;
        }, IntPtr.Zero);
        return result;
    }
}
'@

$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$chosen = $null
while ([DateTime]::UtcNow -lt $deadline) {
    $process = Get-Process -Id $ProcessId -ErrorAction Stop
    $candidates = New-Object System.Collections.Generic.List[object]
    foreach ($handle in [TFC2WindowNative]::WindowsForProcess([uint32]$ProcessId)) {
        $rect = New-Object TFC2WindowNative+Rect
        if (-not [TFC2WindowNative]::GetWindowRect($handle, [ref]$rect)) { continue }
        $width = $rect.Right - $rect.Left
        $height = $rect.Bottom - $rect.Top
        if ($width -le 0 -or $height -le 0) { continue }
        $titleBuffer = New-Object System.Text.StringBuilder 512
        $classBuffer = New-Object System.Text.StringBuilder 256
        [void][TFC2WindowNative]::GetWindowText($handle, $titleBuffer, $titleBuffer.Capacity)
        [void][TFC2WindowNative]::GetClassName($handle, $classBuffer, $classBuffer.Capacity)
        $candidates.Add([pscustomobject]@{
            Handle = $handle
            Visible = [TFC2WindowNative]::IsWindowVisible($handle)
            Width = $width
            Height = $height
            Area = $width * $height
            Title = $titleBuffer.ToString()
            Class = $classBuffer.ToString()
        })
    }
    $chosen = $candidates | Sort-Object @{Expression='Visible';Descending=$true}, @{Expression='Area';Descending=$true} | Select-Object -First 1
    if ($chosen) { break }
    Start-Sleep -Milliseconds 250
}

if (-not $chosen) { throw "게임 프로세스에 속한 창을 찾지 못했습니다." }
$bitmap = New-Object System.Drawing.Bitmap($chosen.Width, $chosen.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$hdc = $graphics.GetHdc()
try {
    if (-not [TFC2WindowNative]::PrintWindow($chosen.Handle, $hdc, 2)) {
        throw "게임 창 캡처에 실패했습니다."
    }
}
finally {
    $graphics.ReleaseHdc($hdc)
    $graphics.Dispose()
}

$absoluteOutput = [System.IO.Path]::GetFullPath($OutputPath)
[System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($absoluteOutput)) | Out-Null
try { $bitmap.Save($absoluteOutput, [System.Drawing.Imaging.ImageFormat]::Png) }
finally { $bitmap.Dispose() }

[pscustomobject]@{
    Output = $absoluteOutput
    ProcessId = $ProcessId
    Handle = $chosen.Handle.ToInt64()
    Visible = $chosen.Visible
    Width = $chosen.Width
    Height = $chosen.Height
    Title = $chosen.Title
    Class = $chosen.Class
} | ConvertTo-Json
