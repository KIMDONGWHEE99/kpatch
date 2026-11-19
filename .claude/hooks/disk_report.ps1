# SessionStart hook: tell Claude how much free space the project drive has.
# Keep this file ASCII-only. Windows PowerShell 5.1 reads BOM-less scripts as ANSI.
# The hook must never block a session, so every failure path exits 0.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try {
    $root = [System.IO.Path]::GetPathRoot($PSScriptRoot)
    $drive = New-Object System.IO.DriveInfo($root)
    $freeGB = [math]::Round($drive.AvailableFreeSpace / 1GB, 1)
    $totalGB = [math]::Round($drive.TotalSize / 1GB, 1)
    $thresholdGB = 50
    $msg = "Disk report: project drive $root has $freeGB GB free of $totalGB GB."
    if ($freeGB -lt $thresholdGB) {
        $msg += " WARNING: free space is below $thresholdGB GB. Do not create game copies. Tell the user and run the kpatch-cleanup skill first."
    } else {
        $msg += " Before copying game files, confirm the copies fit with 20 GB to spare (see CLAUDE.md)."
    }
    $payload = @{ hookSpecificOutput = @{ hookEventName = 'SessionStart'; additionalContext = $msg } }
    $payload | ConvertTo-Json -Compress -Depth 4
} catch { }
exit 0
