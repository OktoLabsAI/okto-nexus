$ErrorActionPreference = 'Stop'
$evidence = $PSScriptRoot
$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
$records = @()
foreach ($name in @('allocation.json', 'allocation-antecedent.json')) {
  $allocation = Get-Content -LiteralPath (Join-Path $evidence $name) -Raw | ConvertFrom-Json
  $target = [IO.Path]::GetFullPath($allocation.own_root)
  if ([IO.Path]::GetDirectoryName($target) -ne $tempBase -or [IO.Path]::GetFileName($target) -notlike 'nexus-ui-cli12-*') { throw 'Outside exact owned Temp allocation' }
  if (Test-Path -LiteralPath $target) {
    if ((Get-Item -LiteralPath $target).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse allocation refused' }
    Remove-Item -LiteralPath $target -Recurse -Force
  }
  $records += [pscustomobject]@{path=$target;absent= -not (Test-Path -LiteralPath $target)}
}
$records | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence 'cleanup.json') -Encoding utf8
