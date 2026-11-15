from pathlib import Path
OLD=Path('C:/Users/jpamb/AppData/Local/Temp/r3-codex0157-restore-sqmdsq70')
HERE=Path(__file__).resolve().parent
s=(OLD/'restore.py').read_text(encoding='utf-8')
s=s.replace("ROOT.name=='r3-codex0157-restore-sqmdsq70'","ROOT.name=='r3-codex0157-restore-attempt2-60na9ol4'")
start=s.index("    archive=ROOT/'codex-x86_64-pc-windows-msvc.exe.zip'")
end=s.index("    paths();STAGED.mkdir",start)
s=s[:start]+"""    archive=Path('C:/Users/jpamb/AppData/Local/Temp/r3-codex0157-restore-sqmdsq70/codex-x86_64-pc-windows-msvc.exe.zip')
    no_reparse(archive)
    require(archive.stat().st_size==ZIP_SIZE and hashfile(archive)==ZIP_SHA,'REUSED_ARCHIVE_CHANGED')
    save('archive-proof.json',{'url':URL,'path':str(archive),'bytes':ZIP_SIZE,'sha256':ZIP_SHA,
        'reused_exact_download':True,'download_calls_this_attempt':0,'native_executions':0})
    checkpoint('EXISTING_ARCHIVE_REVERIFIED',bytes=ZIP_SIZE,sha256=ZIP_SHA)
"""+s[end:]
old="if item.is_dir():require(clean in valid_dirs and item.file_size==0,'UNEXPECTED_ARCHIVE_DIRECTORY');continue"
new="if item.is_dir():require((clean in valid_dirs or clean=='bin') and item.file_size==0 and item.compress_size==0,'UNEXPECTED_ARCHIVE_DIRECTORY');continue"
assert old in s
s=s.replace(old,new)
(HERE/'restore.py').write_text(s,encoding='utf-8')
