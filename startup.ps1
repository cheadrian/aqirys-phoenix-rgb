<#
.SYNOPSIS
    Run the Dynamic Lighting bridge automatically at logon (or remove it).

.DESCRIPTION
    Creates a shortcut "AQIRYS Dynamic Lighting" in the current user's Startup
    folder. It starts aqirys_dynamic_lighting.py hidden with pythonw.exe.
    No administrator rights needed.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\startup.ps1            # install
    powershell -ExecutionPolicy Bypass -File .\startup.ps1 -Uninstall # remove
#>
param([switch]$Uninstall)

$ErrorActionPreference = 'Stop'
$startup  = [Environment]::GetFolderPath('Startup')
$shortcut = Join-Path $startup 'AQIRYS Dynamic Lighting.lnk'
$script   = Join-Path $PSScriptRoot 'aqirys_dynamic_lighting.py'

if ($Uninstall) {
    if (Test-Path $shortcut) { Remove-Item $shortcut -Confirm:$false; "Removed: $shortcut" }
    else { "Nothing to remove." }
    # Stop a running instance, if any.
    Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
        Where-Object { $_.CommandLine -match 'aqirys_dynamic_lighting' } |
        ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; "Stopped PID $($_.ProcessId)" } catch {} }
    return
}

if (-not (Test-Path $script)) { throw "aqirys_dynamic_lighting.py not found next to this script." }

# Resolve the real interpreter (not the WindowsApps alias) and use pythonw.exe next to it.
$python = (& python -c "import sys; print(sys.executable)").Trim()
if (-not $python) { throw "Python not found in PATH. Install Python 3 first." }
$pythonw = Join-Path (Split-Path $python) 'pythonw.exe'
if (-not (Test-Path $pythonw)) { $pythonw = (Get-Command pythonw -ErrorAction Stop).Source }

$wsh = New-Object -ComObject WScript.Shell
$lnk = $wsh.CreateShortcut($shortcut)
$lnk.TargetPath       = $pythonw
$lnk.Arguments        = "`"$script`" --quiet"
$lnk.WorkingDirectory = $PSScriptRoot
$lnk.Description      = 'AQIRYS Phoenix - follow Windows Dynamic Lighting'
$lnk.Save()

"Created: $shortcut"
"  -> $pythonw `"$script`" --quiet"
"It will start at next logon. To start it now:"
"  Start-Process '$pythonw' -ArgumentList '`"$script`" --quiet'"
