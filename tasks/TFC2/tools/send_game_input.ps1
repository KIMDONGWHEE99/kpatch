param(
    [Parameter(Mandatory = $true)][int]$ProcessId,
    [ValidateSet("Click", "Key")][string]$Action,
    [int]$X = 0,
    [int]$Y = 0,
    [int]$VirtualKey = 0
)

$ErrorActionPreference = "Stop"
Add-Type @'
using System;
using System.Runtime.InteropServices;
using System.Collections.Generic;

public static class TFC2InputNative
{
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [StructLayout(LayoutKind.Sequential)]
    public struct Rect { public int Left; public int Top; public int Right; public int Bottom; }
    [StructLayout(LayoutKind.Sequential)]
    public struct Point { public int X; public int Y; }
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out Rect rect);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int command);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hWnd, uint message, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr hWnd, ref Point point);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extraInfo);

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

$windows = foreach ($handle in [TFC2InputNative]::WindowsForProcess([uint32]$ProcessId)) {
    $rect = New-Object TFC2InputNative+Rect
    if ([TFC2InputNative]::GetWindowRect($handle, [ref]$rect)) {
        $width = $rect.Right - $rect.Left
        $height = $rect.Bottom - $rect.Top
        if ($width -gt 0 -and $height -gt 0) {
            [pscustomobject]@{ Handle=$handle; Visible=[TFC2InputNative]::IsWindowVisible($handle); Area=$width*$height }
        }
    }
}
$window = $windows | Sort-Object @{Expression='Visible';Descending=$true}, @{Expression='Area';Descending=$true} | Select-Object -First 1
if (-not $window) { throw "입력을 보낼 게임 창을 찾지 못했습니다." }
[void][TFC2InputNative]::ShowWindow($window.Handle, 5)
[void][TFC2InputNative]::SetForegroundWindow($window.Handle)
Start-Sleep -Milliseconds 150

if ($Action -eq "Click") {
    $point = New-Object TFC2InputNative+Point
    $point.X = $X
    $point.Y = $Y
    if (-not [TFC2InputNative]::ClientToScreen($window.Handle, [ref]$point)) {
        throw "클라이언트 좌표를 화면 좌표로 바꾸지 못했습니다."
    }
    [void][TFC2InputNative]::SetCursorPos($point.X, $point.Y)
    Start-Sleep -Milliseconds 80
    [TFC2InputNative]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 80
    [TFC2InputNative]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
}
else {
    [void][TFC2InputNative]::PostMessage($window.Handle, 0x0100, [IntPtr]$VirtualKey, [IntPtr]::Zero)
    Start-Sleep -Milliseconds 80
    [void][TFC2InputNative]::PostMessage($window.Handle, 0x0101, [IntPtr]$VirtualKey, [IntPtr]::Zero)
}
[pscustomobject]@{ ProcessId=$ProcessId; Handle=$window.Handle.ToInt64(); Action=$Action; X=$X; Y=$Y; VirtualKey=$VirtualKey } | ConvertTo-Json
