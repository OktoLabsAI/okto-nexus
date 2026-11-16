$ErrorActionPreference='Stop'
$uiNavTargets=@('C:\Users\jpamb\AppData\Local\Temp\nexus-ui07-navigation-pt709ie0','C:\Users\jpamb\AppData\Local\Temp\nexus-ui07-navigation-e44lk_l6')
foreach($uiNavTarget in $uiNavTargets){
  $uiNavResolved=[System.IO.Path]::GetFullPath($uiNavTarget).TrimEnd('\')
  if([System.IO.Path]::GetDirectoryName($uiNavResolved) -ne 'C:\Users\jpamb\AppData\Local\Temp' -or -not [System.IO.Path]::GetFileName($uiNavResolved).StartsWith('nexus-ui07-navigation-')){throw 'Unsafe target'}
  if(Test-Path -LiteralPath $uiNavResolved){if((Get-Item -LiteralPath $uiNavResolved -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint){throw 'Redirected target'}}
}
$uiNavRemaining=@(Get-CimInstance Win32_Process|Where-Object{ $_.Name -in @('python.exe','pythonw.exe') -and $_.CommandLine -like '*tests/ui_simplification/browser_navigation_fixture.py*' }|Select-Object ProcessId,Name)
if($uiNavRemaining.Count -ne 0){throw 'Own fixture process remains'}
foreach($uiNavTarget in $uiNavTargets){if(Test-Path -LiteralPath $uiNavTarget){Remove-Item -LiteralPath $uiNavTarget -Recurse -Force}}
$uiNavRecord=[pscustomobject]@{remaining_fixture_processes=$uiNavRemaining;targets=@($uiNavTargets|ForEach-Object{[pscustomobject]@{path=$_;absent=(-not(Test-Path -LiteralPath $_))}})}
$uiNavRecord|ConvertTo-Json -Depth 5|Set-Content -LiteralPath 'D:\Projetos\Techridy\okto_labs_okto_nexus\NEXUS_UI_R1\execution\evidence\pr07-navigation\cleanup.json' -Encoding UTF8
$uiNavRecord|ConvertTo-Json -Depth 5
Remove-Item -LiteralPath 'D:\Projetos\Techridy\okto_labs_okto_nexus\NEXUS_UI_R1\execution\evidence\pr07-navigation\stop' -ErrorAction SilentlyContinue
