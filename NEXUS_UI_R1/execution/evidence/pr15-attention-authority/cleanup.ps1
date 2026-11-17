$ErrorActionPreference = 'Stop'
$base = $PSScriptRoot
$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
$files = @('agent/allocation-antecedent.json','agent/allocation.json','home-off/antecedent-server-flag-oracle/allocation.json','home-off/allocation.json')
$records = @()
foreach ($file in $files) {
  $allocation = Get-Content -LiteralPath (Join-Path $base $file) -Raw | ConvertFrom-Json
  $target = [IO.Path]::GetFullPath($allocation.home)
  if ([IO.Path]::GetDirectoryName($target) -ne $tempBase -or -not [IO.Path]::GetFileName($target).StartsWith('nexus-ui-attention-authority-')) { throw 'Outside exact own Temp allocation' }
  if (Test-Path -LiteralPath $target) {
    if ((Get-Item -LiteralPath $target).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse allocation refused' }
    Remove-Item -LiteralPath $target -Recurse -Force
  }
  $records += [pscustomobject]@{path=$target;absent= -not (Test-Path -LiteralPath $target)}
}
$records | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $base 'cleanup.json') -Encoding utf8
foreach ($file in @('agent/stop','home-off/stop','home-off/antecedent-server-flag-oracle/stop')) {
  $target=Join-Path $base $file
  if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target }
}
