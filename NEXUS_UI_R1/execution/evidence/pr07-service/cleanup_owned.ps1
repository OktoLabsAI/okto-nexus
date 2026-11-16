$ErrorActionPreference='Stop'
$uiServiceTemp='C:\Users\jpamb\AppData\Local\Temp'
$uiServiceTargets=@(
  'C:\Users\jpamb\AppData\Local\Temp\nexus-ui-r1-service-nexus-y93fv5kn',
  'C:\Users\jpamb\AppData\Local\Temp\nexus-ui-r1-service-connector-7z43wd43',
  'C:\Users\jpamb\AppData\Local\Temp\nexus-ui-r1-service-connector-controls-cl9kihg_',
  'C:\Users\jpamb\AppData\Local\Temp\nexus-ui-r1-service-nexus-passive-bzh6dg_z'
)
foreach($uiServiceTarget in $uiServiceTargets){
  $uiServiceAbsolute=[System.IO.Path]::GetFullPath($uiServiceTarget).TrimEnd('\')
  if([System.IO.Path]::GetDirectoryName($uiServiceAbsolute) -ne $uiServiceTemp -or -not [System.IO.Path]::GetFileName($uiServiceAbsolute).StartsWith('nexus-ui-r1-service-')){throw 'Unsafe target'}
  if(Test-Path -LiteralPath $uiServiceAbsolute){
    $uiServiceItem=Get-Item -LiteralPath $uiServiceAbsolute -Force
    if($uiServiceItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint){throw 'Refuse redirected target'}
  }
}
$uiServiceOwned=@(Get-CimInstance Win32_Process | Where-Object {
  $uiServiceCommand=$_.CommandLine
  $uiServiceMatch=$false
  if($_.Name -in @('python.exe','pythonw.exe') -and $uiServiceCommand){
    foreach($uiServiceTarget in $uiServiceTargets){
      if($uiServiceCommand.IndexOf($uiServiceTarget,[System.StringComparison]::OrdinalIgnoreCase) -ge 0){$uiServiceMatch=$true}
    }
  }
  $uiServiceMatch
} | Select-Object ProcessId,Name)
if($uiServiceOwned.Count -ne 0){throw 'Owned process remains; preserve temporary data'}
foreach($uiServiceTarget in $uiServiceTargets){if(Test-Path -LiteralPath $uiServiceTarget){Remove-Item -LiteralPath $uiServiceTarget -Recurse -Force}}
$uiServiceResult=[pscustomobject]@{remaining_owned_processes=$uiServiceOwned;targets=@($uiServiceTargets|ForEach-Object{[pscustomobject]@{path=$_;absent=(-not(Test-Path -LiteralPath $_))}})}
$uiServiceResult|ConvertTo-Json -Depth 6|Set-Content -LiteralPath 'D:\Projetos\Techridy\okto_labs_okto_nexus\NEXUS_UI_R1\execution\evidence\pr07-service\cleanup.json' -Encoding UTF8
$uiServiceResult|ConvertTo-Json -Depth 6
