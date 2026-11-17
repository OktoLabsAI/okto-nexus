$ErrorActionPreference = 'Stop'
# The malformed diagnostic observer already completed naturally. A subsequent
# identity check refused to stop PID60592 because it no longer matched; no
# process was stopped. Only read the bounded owned-root namespace now.
$readers = Get-CimInstance Win32_Process -Filter "(Name='python.exe' OR Name='git.exe') AND CommandLine LIKE '%nexus-qc21-review-privacy-%'"
@{own_candidate_readers=@($readers | Select-Object ProcessId,ParentProcessId,CreationDate,ExecutablePath,CommandLine)} |
    ConvertTo-Json -Depth 4
