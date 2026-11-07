import json, pathlib, subprocess, sys, datetime

root = pathlib.Path(r'D:/Projetos/Techridy/okto_labs_okto_nexus')
out = root / 'output/playwright/dx04-participant-guide'
out.mkdir(parents=True, exist_ok=True)
commands = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
for item in commands:
    command = ['rtk', 'proxy', r'C:\Program Files\Git\bin\bash.exe',
               'C:/Users/jpamb/.codex/skills/playwright/scripts/playwright_cli.sh',
               '--session=dx04-guide', *item['args']]
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding='utf-8')
    record = dict(item, started=started, ended=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
    (out / (item['name'] + '.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(name=item['name'], exit_code=result.returncode), ensure_ascii=False), flush=True)
    print(result.stdout if not item.get('quiet') else '(Full output saved to artifact.)', flush=True)
    if result.returncode:
        print(result.stderr, flush=True)
        sys.exit(result.returncode)
