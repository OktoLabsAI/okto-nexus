$ErrorActionPreference = 'Stop'
$base = $PSScriptRoot
$ready1 = Get-Content -LiteralPath (Join-Path $base 'ready.json') -Raw | ConvertFrom-Json
$ready2 = Get-Content -LiteralPath (Join-Path $base 'artifacts-only/ready.json') -Raw | ConvertFrom-Json
$allocation = Get-Content -LiteralPath (Join-Path $base 'allocation.json') -Raw | ConvertFrom-Json
$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
$records = @()
$items = @(
 @{path=$ready1.home;prefix='nexus-ui04-human-live-'},
 @{path=$ready2.home;prefix='nexus-ui04-human-live-'},
 @{path=$allocation.runner_root;prefix='nexus-ui-nav-arrival-runner-'},
 @{path='C:/Users/jpamb/AppData/Local/Temp/nexus-ui-nav-arrival-runner-kazww5_n';prefix='nexus-ui-nav-arrival-runner-'}
)
foreach ($item in $items) {
  $target = [IO.Path]::GetFullPath($item.path)
  if ([IO.Path]::GetDirectoryName($target) -ne $tempBase -or -not [IO.Path]::GetFileName($target).StartsWith($item.prefix)) { throw 'Outside exact own Temp allocation' }
  if (Test-Path -LiteralPath $target) {
    if ((Get-Item -LiteralPath $target).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse allocation refused' }
    Remove-Item -LiteralPath $target -Recurse -Force
  }
  $records += [pscustomobject]@{path=$target;absent= -not (Test-Path -LiteralPath $target)}
}
$records | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $base 'cleanup.json') -Encoding utf8
foreach ($file in @('stop','trigger-Graph','trigger-Artifacts','artifacts-only/stop','artifacts-only/trigger-Graph','artifacts-only/trigger-Artifacts')) {
  $target = Join-Path $base $file
  if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target }
}
