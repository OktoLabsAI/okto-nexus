$prefix = 'C:\Users\jpamb\AppData\Local\Temp\nexus-ui-r1-packages-wry3ter9\venv\Scripts\python.exe'
$owned = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
    $_.CommandLine -and $_.CommandLine.Contains($prefix) -and (
        $_.CommandLine.Contains('pytest') -or $_.CommandLine.Contains('live_client.py') -or
        $_.CommandLine.Contains('okto_nexus.adapters.inbound.mcp.server'))
} | Select-Object ProcessId,ParentProcessId,Name)
@{checked_at=(Get-Date).ToUniversalTime().ToString('o');remaining_owned_runtime_processes=$owned;count=$owned.Count} |
    ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 (Join-Path $PSScriptRoot 'cleanup.json')
Get-Content (Join-Path $PSScriptRoot 'cleanup.json')
