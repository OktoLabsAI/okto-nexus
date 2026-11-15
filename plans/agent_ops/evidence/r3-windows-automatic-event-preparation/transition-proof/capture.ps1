param([Parameter(Mandatory=$true)][string]$StartUtc,
      [Parameter(Mandatory=$true)][string]$OutputFile,
      [long]$AnchorRecordId=0)
$ErrorActionPreference='Stop'
$provider='Microsoft-Windows-Kernel-Power'
$names=@{42='PreSleepNotification';107='PostSleepNotification';506='CsEnterReason';507='CsExitReason'}
$began=[DateTimeOffset]::UtcNow
$result=[ordered]@{schema=1;status='UNCONFIRMED';started_utc=$began.ToString('o');events=@();manifest=@();anchor=$null;latest=$null;truncated=$false;event_generated=$false}
function Project($event) {
  # Deliberately never access Message, Properties or runtime XML.
  [ordered]@{provider=$event.ProviderName;event_id=[int]$event.Id;version=[int]$event.Version;record_id=[long]$event.RecordId;utc=$event.TimeCreated.ToUniversalTime().ToString('o');transition=$names[[int]$event.Id]}
}
function ReadEvents($filter,$maximum) {
  try { @(Get-WinEvent -FilterHashtable $filter -MaxEvents $maximum -ErrorAction Stop) }
  catch { if($_.FullyQualifiedErrorId -like 'NoMatchingEventsFound*'){return @()}; throw }
}
try {
  if($StartUtc -notmatch '(Z|[+-][0-9]{2}:[0-9]{2})$'){throw 'AWARE_TIME_REQUIRED'}
  $start=[DateTimeOffset]::Parse($StartUtc)
  if($start -gt $began -or ($began-$start).TotalHours -gt 24){throw 'WINDOW_INVALID'}
  $result.query_start_utc=$start.ToUniversalTime().ToString('o')
  $result.query_end_utc=$began.ToString('o')
  $result.boot_utc=(Get-CimInstance Win32_OperatingSystem -Property LastBootUpTime).LastBootUpTime.ToUniversalTime().ToString('o')
  $meta=Get-WinEvent -ListProvider $provider
  $result.manifest=@($meta.Events | Where-Object {$names.ContainsKey([int]$_.Id) -and $_.LogLink.LogName -eq 'System'} | ForEach-Object {
    [ordered]@{provider=$provider;event_id=[int]$_.Id;version=[int]$_.Version;log='System';transition=$_.Task.Name;description=$_.Description}
  })
  $latest=@(ReadEvents @{LogName='System';ProviderName=$provider;Id=@(42,107,506,507);EndTime=$began.UtcDateTime} 1)
  if($latest.Count -eq 1){$result.latest=Project $latest[0]}
  if($AnchorRecordId -gt 0){
    try {$anchors=@(Get-WinEvent -LogName System -FilterXPath "*[System[Provider[@Name='$provider'] and EventRecordID=$AnchorRecordId and (EventID=42 or EventID=107 or EventID=506 or EventID=507)]]" -MaxEvents 1 -ErrorAction Stop)}
    catch {if($_.FullyQualifiedErrorId -like 'NoMatchingEventsFound*'){$anchors=@()}else{throw}}
    if($anchors.Count -eq 1){$result.anchor=Project $anchors[0]}
  }
  $rows=@(ReadEvents @{LogName='System';ProviderName=$provider;Id=@(42,107,506,507);StartTime=$start.UtcDateTime;EndTime=$began.UtcDateTime} 129)
  $result.truncated=$rows.Count -gt 128
  $result.events=@($rows | Select-Object -First 128 | Sort-Object RecordId | ForEach-Object {Project $_})
  $result.status='READ_ONLY_CAPTURED'
} catch {
  $result.error_class=$_.Exception.GetType().Name
  # No exception message, event payload, username, wake source or device data.
}
$result.finished_utc=[DateTimeOffset]::UtcNow.ToString('o')
$bytes=[Text.UTF8Encoding]::new($false).GetBytes(($result | ConvertTo-Json -Depth 8))
$stream=[IO.File]::Open($OutputFile,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try{$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
Write-Output ($result.status)
