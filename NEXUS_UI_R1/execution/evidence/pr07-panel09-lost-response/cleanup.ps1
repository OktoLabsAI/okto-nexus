$ErrorActionPreference = 'Stop'
$evidence = $PSScriptRoot
$allocation = Get-Content -LiteralPath (Join-Path $evidence 'allocation.json') -Raw | ConvertFrom-Json
$ready = Get-Content -LiteralPath (Join-Path $evidence 'ready.json') -Raw | ConvertFrom-Json
$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
$records = @()
foreach ($item in @(@{path=$allocation.runner_root;prefix='nexus-ui-panel09-runner-'},@{path=$ready.home;prefix='nexus-ui04-human-live-'})) {
  $target = [IO.Path]::GetFullPath($item.path)
  if ([IO.Path]::GetDirectoryName($target) -ne $tempBase -or -not [IO.Path]::GetFileName($target).StartsWith($item.prefix)) { throw 'Outside exact own Temp allocation' }
  if (Test-Path -LiteralPath $target) {
    if ((Get-Item -LiteralPath $target).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse allocation refused' }
    Remove-Item -LiteralPath $target -Recurse -Force
  }
  $records += [pscustomobject]@{path=$target;absent= -not (Test-Path -LiteralPath $target)}
}
$records | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence 'cleanup.json') -Encoding utf8
Remove-Item -LiteralPath (Join-Path $evidence 'stop')
