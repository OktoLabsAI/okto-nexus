$ErrorActionPreference = 'Stop'
$base = $PSScriptRoot
$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
$names = @('nexus-ui-results-browser-1pcwglv6','nexus-ui-results-browser-b6m4ia72','nexus-ui-results-browser-bfcs8vxf','nexus-ui-results-browser-fs_ljf_1','nexus-ui-results-browser-jzl3mfta')
$records = @()
foreach ($name in $names) {
  $target = [IO.Path]::GetFullPath((Join-Path $tempBase $name))
  if ([IO.Path]::GetDirectoryName($target) -ne $tempBase -or -not [IO.Path]::GetFileName($target).StartsWith('nexus-ui-results-browser-')) { throw 'Outside exact own Temp allocation' }
  if (Test-Path -LiteralPath $target) {
    if ((Get-Item -LiteralPath $target).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse allocation refused' }
    Remove-Item -LiteralPath $target -Recurse -Force
  }
  $records += [pscustomobject]@{path=$target;absent= -not (Test-Path -LiteralPath $target)}
}
$records | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $base 'cleanup.json') -Encoding utf8
foreach ($file in @('antecedent-before-fix/stop','final/stop','final/capture-after-read','final/capture-after-seen','final-relation/stop','final-relation/capture-after-read','final-relation/capture-after-seen')) {
  $target=Join-Path $base $file
  if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target }
}
