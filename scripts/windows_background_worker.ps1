# RE Dragon BACKGROUND Unity compatibility probe.
# Never activates the window, moves the physical cursor, or uses global mouse input.
# PrintWindow/PostMessage acceptance NEVER proves Unity processed an interaction.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("probe","capture","click")]
    [string]$Action,
    [ValidatePattern('^[A-Za-z0-9_-]{1,64}$')]
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
public static class REBackground {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
    [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr hwnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll", SetLastError = true)] public static extern bool PrintWindow(IntPtr hwnd, IntPtr hdc, uint flags);
    [DllImport("user32.dll", SetLastError = true)] public static extern bool PostMessage(IntPtr hwnd, uint message, UIntPtr wParam, IntPtr lParam);
}
'@ -ErrorAction Stop | Out-Null

function Get-ClientSize([IntPtr]$handle) {
    $rect = New-Object REBackground+RECT
    if (-not [REBackground]::GetClientRect($handle, [ref]$rect)) {
        throw "CLIENT_RECT_FAILED"
    }
    $w = $rect.Right - $rect.Left
    $h = $rect.Bottom - $rect.Top
    if ($w -lt 100 -or $h -lt 100 -or $w -gt 8192 -or $h -gt 8192) {
        throw "INVALID_CLIENT_BOUNDS: width=$w height=$h"
    }
    return @{ width = $w; height = $h }
}

function Get-BackgroundFrame([IntPtr]$handle, [string]$folder, [string]$stem) {
    $size = Get-ClientSize $handle
    $bitmap = [System.Drawing.Bitmap]::new([int]$size.width, [int]$size.height)
    $ok = $false
    try {
        $g = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $hdc = $g.GetHdc()
            try {
                # 0x1 PW_CLIENTONLY; 0x2 PW_RENDERFULLCONTENT. GPU clients may
                # return blank/stale frames even if PrintWindow returns TRUE.
                $ok = [REBackground]::PrintWindow($handle, $hdc, [uint32]3)
            } finally { $g.ReleaseHdc($hdc) }
        } finally { $g.Dispose() }
        if (-not $ok) { throw "PRINTWINDOW_FAILED: Unity may reject background capture" }
        $colors = New-Object 'System.Collections.Generic.HashSet[int]'
        for ($iy=1; $iy -le 9; $iy++) {
            for ($ix=1; $ix -le 9; $ix++) {
                $px = [int][Math]::Floor($ix * ($size.width-1) / 10)
                $py = [int][Math]::Floor($iy * ($size.height-1) / 10)
                [void]$colors.Add($bitmap.GetPixel($px,$py).ToArgb())
            }
        }
        if ($colors.Count -lt 5) {
            throw "PRINTWINDOW_UNUSABLE_FRAME: low visual diversity; do not send background clicks"
        }
        $file = Join-Path $folder "$stem.png"
        $bitmap.Save($file,[System.Drawing.Imaging.ImageFormat]::Png)
        return @{
            path = $file
            sha256 = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
            width = $size.width
            height = $size.height
            sample_distinct_colors = $colors.Count
            image_quality = "PLAUSIBLE_NOT_VERIFIED"
        }
    } finally { $bitmap.Dispose() }
}

$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ")
if (-not $EvidenceDirectory) {
    $EvidenceDirectory = Join-Path $env:LOCALAPPDATA "REDragon\WindowsBackgroundSurvey"
}
$result = @{
    schema = "re-dragon.windows-background.v1"
    at_utc = [DateTime]::UtcNow.ToString("o")
    action = $Action
    process_name = $ProcessName
    status = "BLOCKED"
    input_dispatched = $false
    gameplay_verified = $false
    method = "Win32.PrintWindow/PostMessage"
    no_global_mouse_input = $true
}
$lock = $null
try {
    if (-not [Environment]::UserInteractive) {
        throw "INTERACTIVE_DESKTOP_REQUIRED"
    }
    New-Item -ItemType Directory -Force -Path $EvidenceDirectory | Out-Null
    $EvidenceDirectory = (Resolve-Path -LiteralPath $EvidenceDirectory).Path
    $lock = [System.IO.File]::Open(
        (Join-Path $EvidenceDirectory "background.lock"),
        [System.IO.FileMode]::OpenOrCreate,
        [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::None)
    $targets = @(Get-Process -Name $ProcessName -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero })
    if ($targets.Count -ne 1) {
        throw "EXPECTED_ONE_GAME_WINDOW: found=$($targets.Count)"
    }
    $proc = $targets[0]
    $handle = $proc.MainWindowHandle
    if (-not [REBackground]::IsWindowVisible($handle)) {
        throw "GAME_WINDOW_NOT_VISIBLE"
    }
    if ([REBackground]::IsIconic($handle)) {
        throw "GAME_MINIMIZED: background capture not reliable"
    }
    $exe = $proc.MainModule.FileName
    if (-not $exe -or [IO.Path]::GetFileNameWithoutExtension($exe) -ine $ProcessName) {
        throw "PROCESS_IMAGE_MISMATCH"
    }
    $size = Get-ClientSize $handle
    $result.pid = $proc.Id
    $result.exe = $exe
    $result.client_width = $size.width
    $result.client_height = $size.height
    $result.game_was_foreground = ([REBackground]::GetForegroundWindow() -eq $handle)
    if ($Action -eq "probe") {
        $result.status = "OBSERVED"
        $result.interpretation = "Background capability NOT yet verified"
    } else {
        $folder = Join-Path $EvidenceDirectory $stamp
        New-Item -ItemType Directory -Path $folder -Force | Out-Null
        $before = Get-BackgroundFrame $handle $folder "before"
        $result.before = $before
        $result.evidence_dir = $folder
        if ($Action -eq "click") {
            if (-not $EnableInput) { throw "INPUT_NOT_AUTHORIZED" }
            if ($X -lt 0 -or $Y -lt 0 -or
                $X -ge $size.width -or $Y -ge $size.height -or
                $X -gt 32767 -or $Y -gt 32767) {
                throw "CLICK_OUTSIDE_GAME_CLIENT"
            }
            $sameSize = Get-ClientSize $handle
            if ($sameSize.width -ne $size.width -or $sameSize.height -ne $size.height) {
                throw "WINDOW_GEOMETRY_CHANGED"
            }
            $param = [IntPtr]([int](($Y -shl 16) -bor $X))
            $result.client_click = @{ x = $X; y = $Y }
            # PostMessage acceptance only means Windows queued a message;
            # many Unity Player builds use native input and ignore it.
            if (-not [REBackground]::PostMessage($handle, [uint32]0x0200,
                                                   [UIntPtr]::Zero, $param)) {
                throw "WM_MOUSEMOVE_NOT_QUEUED"
            }
            if (-not [REBackground]::PostMessage($handle, [uint32]0x0201,
                                                   [UIntPtr]([uint32]1), $param)) {
                throw "WM_LBUTTONDOWN_NOT_QUEUED"
            }
            # A mouse-down message is now queued; retrying could duplicate effects.
            $result.input_dispatched = $true
            Start-Sleep -Milliseconds 65
            if (-not [REBackground]::PostMessage($handle, [uint32]0x0202,
                                                   [UIntPtr]::Zero, $param)) {
                throw "WM_LBUTTONUP_NOT_QUEUED"
            }
            Start-Sleep -Milliseconds 450
            $after = Get-BackgroundFrame $handle $folder "after"
            $result.after = $after
            $result.visual_changed = ($before.sha256 -ne $after.sha256)
            $result.interpretation = "UNVERIFIED: queued input and changed pixels do NOT prove Unity handled click"
        }
        $result.status = "OBSERVED"
    }
} catch {
    $result.error = [string]$_.Exception.Message
    $result.status = "BLOCKED"
} finally {
    if ($lock) { $lock.Dispose() }
}
$line = ConvertTo-Json -InputObject $result -Compress -Depth 8
if (Test-Path -LiteralPath $EvidenceDirectory -PathType Container) {
    try {
        Add-Content -LiteralPath (Join-Path $EvidenceDirectory "events.jsonl") -Value $line -Encoding UTF8
    } catch {
        $result.status = "BLOCKED"
        $result.error = "JOURNAL_WRITE_FAILED: " + [string]$_.Exception.Message
        $line = ConvertTo-Json -InputObject $result -Compress -Depth 8
    }
}
Write-Output $line
if ($result.status -eq "BLOCKED") { exit 2 }
exit 0
