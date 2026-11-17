from pathlib import Path
import subprocess, json
root=Path(__file__).resolve().parent
escaped=str(root/'venv').replace("'","''")
script="$items=@(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -like '"+escaped+"\\*' } | Select-Object ProcessId,ParentProcessId,ExecutablePath); ConvertTo-Json -InputObject $items -Compress"
result=subprocess.run(['rtk','proxy','powershell','-NoProfile','-Command',script],capture_output=True,text=True,check=True,timeout=30)
items=json.loads(result.stdout)
assert items==[],items
report={'own_prefix':str(root/'venv'),'remaining_processes':items,'scope':'Read-only executable-path fence to this new prefix only; no stop/kill issued.'}
(root/'cleanup-snapshot.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report))
