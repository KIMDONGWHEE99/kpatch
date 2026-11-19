param(
    [Parameter(Mandatory = $true)]
    [int]$ProcessId,

    [Parameter(Mandatory = $true)]
    [ValidateRange(0.0, 1.0)]
    [double]$X,

    [Parameter(Mandatory = $true)]
    [ValidateRange(0.0, 1.0)]
    [double]$Y,

    [int]$WaitMilliseconds = 1000,

    [switch]$MoveOnly
)

Add-Type @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public static class PibcrementalWindowInput
{
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential)]
    public struct Rect { public int Left, Top, Right, Bottom; }

    [StructLayout(LayoutKind.Sequential)]
    public struct Point { public int X, Y; }

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    [DllImport("user32.dll")]
    public static extern bool GetClientRect(IntPtr hWnd, out Rect rect);

    [DllImport("user32.dll")]
    public static extern bool ClientToScreen(IntPtr hWnd, ref Point point);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int command);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool SetCursorPos(int x, int y);

    [DllImport("user32.dll")]
    public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extraInfo);

    public static IntPtr FindLargestWindow(uint targetProcessId)
    {
        IntPtr best = IntPtr.Zero;
        long bestArea = 0;
        EnumWindows((window, _) =>
        {
            GetWindowThreadProcessId(window, out uint processId);
            if (processId != targetProcessId) return true;
            if (!GetClientRect(window, out Rect rect)) return true;
            long area = Math.Max(0, rect.Right - rect.Left) * (long)Math.Max(0, rect.Bottom - rect.Top);
            if (area > bestArea) { bestArea = area; best = window; }
            return true;
        }, IntPtr.Zero);
        return best;
    }
}
'@

$handle = [PibcrementalWindowInput]::FindLargestWindow([uint32]$ProcessId)
if ($handle -eq [IntPtr]::Zero) {
    throw "게임 창을 찾지 못했습니다: PID $ProcessId"
}

[PibcrementalWindowInput]::ShowWindow($handle, 9) | Out-Null
[PibcrementalWindowInput]::SetForegroundWindow($handle) | Out-Null
Start-Sleep -Milliseconds 250

$rect = New-Object PibcrementalWindowInput+Rect
if (-not [PibcrementalWindowInput]::GetClientRect($handle, [ref]$rect)) {
    throw "게임 창의 내부 크기를 읽지 못했습니다."
}
$width = $rect.Right - $rect.Left
$height = $rect.Bottom - $rect.Top
$point = New-Object PibcrementalWindowInput+Point
$point.X = [int][Math]::Round($width * $X)
$point.Y = [int][Math]::Round($height * $Y)
if (-not [PibcrementalWindowInput]::ClientToScreen($handle, [ref]$point)) {
    throw "게임 창 좌표를 화면 좌표로 바꾸지 못했습니다."
}

[PibcrementalWindowInput]::SetCursorPos($point.X, $point.Y) | Out-Null
if (-not $MoveOnly) {
    [PibcrementalWindowInput]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 80
    [PibcrementalWindowInput]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
}
Start-Sleep -Milliseconds $WaitMilliseconds

[pscustomobject]@{
    ProcessId = $ProcessId
    WindowHandle = $handle.ToInt64()
    ClientWidth = $width
    ClientHeight = $height
    ClickX = $point.X
    ClickY = $point.Y
    MoveOnly = [bool]$MoveOnly
} | ConvertTo-Json
