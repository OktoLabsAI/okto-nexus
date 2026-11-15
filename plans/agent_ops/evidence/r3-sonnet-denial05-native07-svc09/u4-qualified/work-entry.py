"""Explicit paid-work entry; requires reviewed plan and completed remote setup."""
from pathlib import Path
import sys
import json
sys.path.insert(0,str(Path(__file__).resolve().parent))
from work_context import load
from remote_work import run

def main():
    context,action=load()
    try:
        if action=='prepare':value=context.prepare()
        else:context.activate(action);value=run(context,action)
        print(json.dumps(value,ensure_ascii=False));return 0
    finally:context.close()

if __name__=='__main__':raise SystemExit(main())
