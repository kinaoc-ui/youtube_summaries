# Martin Luk is chained AFTER 9edge First Screen (daily_fs_scheduled.bat).
# This script only bootstraps known stream ids — it does NOT create a separate schedule.

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Py = Get-Command py -ErrorAction SilentlyContinue
if (-not $Py) { $Py = Get-Command python -ErrorAction SilentlyContinue }
if (-not $Py) { throw 'Python not found' }

Write-Host '[..] Bootstrap known Martin Luk stream ids...'
& $Py.Source (Join-Path $Root 'scripts\martin_daily.py') --bootstrap
if ($LASTEXITCODE -ne 0) { throw "bootstrap failed: $LASTEXITCODE" }

# Remove legacy standalone task if present
schtasks /Delete /TN '9edge-Daily-MartinLuk' /F 2>$null | Out-Null

Write-Host ''
Write-Host '[OK] Martin Luk runs after screening via:'
Write-Host '     screening\daily_fs_scheduled.bat'
Write-Host '       -> First Screen'
Write-Host '       -> new CSV'
Write-Host '       -> youtube\daily_martin_scheduled.bat'
Write-Host '       -> youtube\push_summaries_git.bat  (github.com/kinaoc-ui/youtube_summaries)'
Write-Host ''
Write-Host 'Schedule is still: 9edge-Daily-FirstScreen (Tue-Sat 04:30)'
Write-Host 'Manual: run_martin_daily.bat   then   push_summaries_git.bat'
Write-Host ''
