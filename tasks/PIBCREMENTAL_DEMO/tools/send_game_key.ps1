param(
    [Parameter(Mandatory = $true)]
    [long]$WindowHandle,

    [Parameter(Mandatory = $true)]
    [ValidateSet("Escape", "Enter", "Space")]
    [string]$Key,

    [int]$WaitMilliseconds = 1000
)

Add-Type @'
using System;
using System.Runtime.InteropServices;

public static class PibcrementalKeyboardInput
{
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int command);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern void keybd_event(byte virtualKey, byte scanCode, uint flags, UIntPtr extraInfo);
}
'@

$virtualKeys = @{ Escape = 0x1B; Enter = 0x0D; Space = 0x20 }
$handle = [IntPtr]::new($WindowHandle)
[PibcrementalKeyboardInput]::ShowWindow($handle, 9) | Out-Null
[PibcrementalKeyboardInput]::SetForegroundWindow($handle) | Out-Null
Start-Sleep -Milliseconds 250
$virtualKey = [byte]$virtualKeys[$Key]
[PibcrementalKeyboardInput]::keybd_event($virtualKey, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 80
[PibcrementalKeyboardInput]::keybd_event($virtualKey, 0, 2, [UIntPtr]::Zero)
Start-Sleep -Milliseconds $WaitMilliseconds

[pscustomobject]@{ WindowHandle = $WindowHandle; Key = $Key } | ConvertTo-Json
