# RE Dragon Windows client survey worker. Windows PowerShell 5.1, interactive desktop.
# A screen snapshot or PCAP file alone NEVER proves a gameplay function succeeded.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("probe","capture","click","fingerprint")]
    [string]$Action,
    [ValidatePattern('^[a-zA-Z0-9_-]{1,64}$')]
    [string]$ProcessName = "DragonBall",
    [string]$EvidenceDirectory = "",
    [int]$X = -1,
    [int]$Y = -1,
    [switch]$EnableInput
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class REWindows {
    [StructLayout(LayoutKind.Sequential)]
    public struct POINT { public int X; public int Y; }
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
    [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr hWnd, ref POINT point);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extra);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
'@ -ErrorAction Stop | Out-Null
[void][REWindows]::SetProcessDPIAware()

function New-Frame($handle, $directory, $stem) {
    if ([REWindows]::GetForegroundWindow() -ne $handle) {
        throw "TARGET_NOT_FOREGROUND: capture would not prove the game is visible"
    }
    $rect = New-Object REWindows+RECT
    if (-not [REWindows]::GetClientRect($handle, [ref]$rect)) {
        throw "GetClientRect failed"
    }
    $width = $rect.Right - $rect.Left
    $height = $rect.Bottom - $rect.Top
    if ($width -lt 100 -or $height -lt 100 -or $width -gt 8192 -or $height -gt 8192) {
        throw "Invalid game client dimensions"
    }
    $point = New-Object REWindows+POINT
    if (-not [REWindows]::ClientToScreen($handle, [ref]$point)) {
        throw "ClientToScreen failed"
    }
    $name = "$stem.png"
    $file = Join-Path $directory $name
    $bitmap = [System.Drawing.Bitmap]::new($width, $height)
    try {
        $graphic = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphic.CopyFromScreen(
                $point.X, $point.Y, 0, 0,
                [System.Drawing.Size]::new($width,$height),
                [System.Drawing.CopyPixelOperation]::SourceCopy
            )
        } finally { $graphic.Dispose() }
        $bitmap.Save($file, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally { $bitmap.Dispose() }
    $hash = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
    return @{
        path = $file; sha256 = $hash; width = $width; height = $height
        x_screen = $point.X; y_screen = $point.Y
    }
}

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ")
if (-not $EvidenceDirectory) {
    $EvidenceDirectory = Join-Path $env:LOCALAPPDATA "REDragon\WindowsSurvey"
}
$result = @{
    schema = "re-dragon.windows-worker.v1"
    at_utc = [DateTime]::UtcNow.ToString("o")
    action = $Action
    process_name = $ProcessName
    status = "BLOCKED"
}
$lock = $null
try {
    if (-not [Environment]::UserInteractive) {
        throw "INTERACTIVE_DESKTOP_REQUIRED: Windows worker must run in the user desktop session"
    }
    New-Item -ItemType Directory -Path $EvidenceDirectory -Force | Out-Null
    $EvidenceDirectory = (Resolve-Path -LiteralPath $EvidenceDirectory).Path
    $lockPath = Join-Path $EvidenceDirectory "worker.lock"
    $lock = [System.IO.File]::Open(
        $lockPath, [System.IO.FileMode]::OpenOrCreate,
        [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None
    )
    $found = @(Get-Process -Name $ProcessName -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero })
    if ($found.Count -ne 1) {
        throw "EXPECTED_ONE_VISIBLE_GAME_WINDOW: found $($found.Count)"
    }
    $process = $found[0]
    if (-not [REWindows]::IsWindowVisible($process.MainWindowHandle)) {
        throw "GAME_WINDOW_NOT_VISIBLE"
    }
    $exe = $process.MainModule.FileName
    if (-not $exe -or ([IO.Path]::GetFileNameWithoutExtension($exe) -ine $ProcessName)) {
        throw "PROCESS_IMAGE_MISMATCH"
    }
    $handle = $process.MainWindowHandle
    $bounds = New-Object REWindows+RECT
    if (-not [REWindows]::GetClientRect($handle, [ref]$bounds)) {
        throw "GetClientRect failed"
    }
    $width = $bounds.Right - $bounds.Left
    $height = $bounds.Bottom - $bounds.Top
    $result.pid = $process.Id
    $result.exe = $exe
    $result.client_width = $width
    $result.client_height = $height
    if ($width -lt 100 -or $height -lt 100) {
        throw "INVALID_CLIENT_BOUNDS"
    }

    if ($Action -eq "fingerprint") {
        $dir = Split-Path -Parent $exe
        $targets = @(
            (Join-Path $dir "DragonBall.exe"),
            (Join-Path $dir "GameAssembly.dll"),
            (Join-Path $dir "DragonBall_Data\il2cpp_data\Metadata\global-metadata.dat")
        )
        $artifacts = @()
        foreach($target in $targets) {
            if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
                throw "REQUIRED_BINARY_MISSING: $([IO.Path]::GetFileName($target))"
            }
            $item = Get-Item -LiteralPath $target
            $artifacts += @{
                file = $target; bytes = $item.Length
                sha256 = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        }
        $result.artifacts = $artifacts
        $result.status = "OBSERVED"
    } elseif ($Action -eq "probe") {
        $result.foreground = ([REWindows]::GetForegroundWindow() -eq $handle)
        $result.status = "OBSERVED"
    } else {
        if (-not [REWindows]::SetForegroundWindow($handle)) {
            throw "FOREGROUND_DENIED: Windows refused to focus game"
        }
        Start-Sleep -Milliseconds 300
        if ([REWindows]::GetForegroundWindow() -ne $handle) {
            throw "FOREGROUND_MISMATCH: do not capture or click"
        }
        $folder = Join-Path $EvidenceDirectory $stamp
        New-Item -ItemType Directory -Path $folder -Force | Out-Null
        $before = New-Frame $handle $folder "before"
        $result.before = $before
        if ($Action -eq "click") {
            if (-not $EnableInput) { throw "INPUT_NOT_AUTHORIZED: supply -EnableInput" }
            if ($X -lt 0 -or $Y -lt 0 -or $X -ge $width -or $Y -ge $height) {
                throw "CLICK_OUTSIDE_GAME_CLIENT"
            }
            Start-Sleep -Milliseconds 600
            $baseline = New-Frame $handle $folder "baseline"
            if ([REWindows]::GetForegroundWindow() -ne $handle) {
                throw "FOCUS_CHANGED_BEFORE_INPUT"
            }
            $point = New-Object REWindows+POINT
            $point.X = $X; $point.Y = $Y
            if (-not [REWindows]::ClientToScreen($handle,[ref]$point)) {
                throw "ClientToScreen failed for click"
            }
            if (-not [REWindows]::SetCursorPos($point.X,$point.Y)) {
                throw "SetCursorPos failed"
            }
            [REWindows]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
            Start-Sleep -Milliseconds 70
            [REWindows]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
            Start-Sleep -Milliseconds 750
            $after = New-Frame $handle $folder "after"
            $result.baseline = $baseline
            $result.after = $after
            $result.client_click = @{x = $X; y = $Y}
            $result.visual_changed = ($baseline.sha256 -ne $after.sha256)
            $result.background_animation_possible = ($before.sha256 -ne $baseline.sha256)
            $result.interpretation = "UNVERIFIED: pixel change is not proof of any gameplay function or server state"
        }
        $result.evidence_dir = $folder
        $result.status = "OBSERVED"
    }
} catch {
    $result.status = "BLOCKED"
    $result.error = [string]$_.Exception.Message
} finally {
    if ($lock) { $lock.Dispose() }
}

# Preserve single-output JSON protocol; never turn a failed action into PASS.
if ($result.status -ne "BLOCKED") {
    $line = ConvertTo-Json -InputObject $result -Compress -Depth 8
    Add-Content -LiteralPath (Join-Path $EvidenceDirectory "events.jsonl") -Value $line -Encoding UTF8
} else {
    $line = ConvertTo-Json -InputObject $result -Compress -Depth 8
}
Write-Output $line
if ($result.status -eq "BLOCKED") { exit 2 }
exit 0
