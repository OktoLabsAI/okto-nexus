"""Restore exact previously qualified public payload. Never execute native code."""
from pathlib import Path,PurePosixPath
import hashlib,json,os,shutil,stat,time,urllib.request,urllib.parse,zipfile

ROOT=Path(__file__).resolve().parent
TEMP=Path('C:/Users/jpamb/AppData/Local/Temp')
TARGET=TEMP/'m1-native-discovery-iyoo0rs3/codex-0.157.0'
STAGED=ROOT/'staged/codex-0.157.0'
CONTEXT=TEMP/'m1-v12-bundle-bldo9qy7/campaign/nexus-home/service-context.json'
E=Path('D:/Projetos/Techridy/okto_labs_okto_nexus/plans/agent_ops/evidence')
ARTIFACT=E/'r3-campaign-proposals/prepared-v1/codex-0.157.0-artifact-proof.json'
DISCOVERY=E/'r3-m1-execution-context/discovery.json'
URL='https://github.com/openai/codex/releases/download/rust-v0.157.0/codex-x86_64-pc-windows-msvc.exe.zip'
ZIP_SIZE=160862984
ZIP_SHA='6c74e2019583cc16e55f79161ef795c8ff712709ad9ed832b3a5b87a7eacdef6'
MAX_UNCOMPRESSED=472021001

def require(ok,reason):
    if not ok:raise RuntimeError(reason)

def hashfile(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(65536),b''):h.update(block)
    return h.hexdigest()

def save(name,value):
    path=ROOT/name
    with path.open('x',encoding='utf-8') as f:
        json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())

def checkpoint(stage,**value):
    print(json.dumps({'stage':stage,**value}),flush=True)

def no_reparse(path):
    path=Path(path).absolute()
    for item in (path,*path.parents):
        try:s=item.lstat()
        except FileNotFoundError:continue
        require(not getattr(s,'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT
                and not stat.S_ISLNK(s.st_mode),'REPARSE_PATH_REFUSED')
    require(path.resolve(strict=False)==path,'RESOLVED_PATH_CHANGED')

def paths():
    require(os.name=='nt','WINDOWS_ATOMIC_RENAME_REQUIRED')
    require(ROOT.name=='r3-codex0157-restore-attempt2-60na9ol4' and ROOT.parent==TEMP,'OWN_RESTORE_ROOT_REQUIRED')
    require(TARGET==TEMP/'m1-native-discovery-iyoo0rs3/codex-0.157.0'
            and STAGED==ROOT/'staged/codex-0.157.0','LITERAL_TARGET_SOURCE_REQUIRED')
    for p in (ROOT,STAGED,TARGET):no_reparse(p)
    require(ROOT.resolve().is_relative_to(TEMP.resolve()) and TARGET.resolve().is_relative_to(TEMP.resolve()),
            'TEMP_CONTAINMENT_REQUIRED')
    require(not TARGET.exists(),'TARGET_EXISTS_NO_OVERWRITE')
    require(STAGED.drive.casefold()==TARGET.drive.casefold()==TEMP.drive.casefold(),'SAME_VOLUME_REQUIRED')
    require(os.stat(ROOT).st_dev==os.stat(TEMP).st_dev,'SAME_FILESYSTEM_REQUIRED')

class ExactRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        u=urllib.parse.urlsplit(newurl)
        require(u.scheme=='https' and u.hostname in {'github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'}
                and not u.username and not u.password,'UNEXPECTED_DOWNLOAD_REDIRECT')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def inventory(folder):
    result={}
    for p in sorted(folder.rglob('*')):
        no_reparse(p)
        if p.is_file():result[p.relative_to(folder).as_posix()]=hashfile(p)
        else:require(p.is_dir(),'NONREGULAR_PAYLOAD_REFUSED')
    return result

def main():
    paths()
    require(hashfile(ARTIFACT)=='1c9fe1a29850f30c21dd2a717c5e015f1b24f4c525f93eaf65625c71de686516','ARTIFACT_MANIFEST_CHANGED')
    require(hashfile(DISCOVERY)=='dd576135300847231eb9fd523526d75d3624a281c9b42bb4e8b13458d417f7c3','DISCOVERY_MANIFEST_CHANGED')
    a=json.loads(ARTIFACT.read_bytes());d=json.loads(DISCOVERY.read_bytes())
    expected=d['source_payload_sha256'];final=d['copied_payload_sha256']
    require(len(expected)==47 and len(final)==48 and final==dict(expected,**{'codex.exe':expected['codex-x86_64-pc-windows-msvc.exe']}),
            'EXACT_MANIFEST_AND_ALIAS_REQUIRED')
    sizes={item['path']:item['size'] for item in a['inventory']}
    require(set(sizes)==set(expected) and sum(sizes.values())==MAX_UNCOMPRESSED
            and {item['path']:item['sha256'] for item in a['inventory']}==expected,'SOURCE_MANIFESTS_DISAGREE')
    require(a['asset']['browser_download_url']==URL and a['asset']['size']==ZIP_SIZE
            and a['asset']['digest']=='sha256:'+ZIP_SHA,'EXACT_OFFICIAL_ARCHIVE_REQUIRED')
    require(Path(d['package_root'])==TARGET,'ORIGINAL_DISCOVERY_PATH_CHANGED')
    no_reparse(CONTEXT);context_before=hashfile(CONTEXT)
    save('source-manifest.json',{'artifact_reference':{'path':str(ARTIFACT),'sha256':hashfile(ARTIFACT)},
        'discovery_reference':{'path':str(DISCOVERY),'sha256':hashfile(DISCOVERY)},
        'url':URL,'archive_sha256':ZIP_SHA,'archive_bytes':ZIP_SIZE,'source_payload':expected,'destination_payload':final,
        'service_context_path':str(CONTEXT),'service_context_file_sha256_before':context_before})
    save('restoration-reserved.json',{'target':str(TARGET),'staged':str(STAGED),'status':'EXACT_ARTIFACT_RESTORE_RESERVED',
        'target_absent':True,'overwrite':False,'native_executions':0,'service_calls':0,'provider_calls':0})
    checkpoint('SOURCE_AND_PATH_GUARDS_CONFIRMED',files=47,alias_files=1)
    archive=Path('C:/Users/jpamb/AppData/Local/Temp/r3-codex0157-restore-sqmdsq70/codex-x86_64-pc-windows-msvc.exe.zip')
    no_reparse(archive)
    require(archive.stat().st_size==ZIP_SIZE and hashfile(archive)==ZIP_SHA,'REUSED_ARCHIVE_CHANGED')
    save('archive-proof.json',{'url':URL,'path':str(archive),'bytes':ZIP_SIZE,'sha256':ZIP_SHA,
        'reused_exact_download':True,'download_calls_this_attempt':0,'native_executions':0})
    checkpoint('EXISTING_ARCHIVE_REVERIFIED',bytes=ZIP_SIZE,sha256=ZIP_SHA)
    paths();STAGED.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(archive) as z:
        entries=z.infolist();require(len(entries)<=128,'ARCHIVE_ENTRY_BOUND')
        names=[];seen=set();valid_dirs={str(p) for name in expected for p in PurePosixPath(name).parents if str(p)!='.'}
        for item in entries:
            name=item.filename;clean=name[:-1] if item.is_dir() else name;p=PurePosixPath(clean)
            require(clean and not p.is_absolute() and all(x not in ('','..','.') for x in p.parts)
                    and '\\' not in clean and ':' not in clean and str(p)==clean,'UNSAFE_ARCHIVE_PATH')
            require(clean.casefold() not in seen,'DUPLICATE_ARCHIVE_PATH');seen.add(clean.casefold())
            kind=stat.S_IFMT(item.external_attr>>16)
            require(kind in (0,stat.S_IFREG,stat.S_IFDIR) and not item.flag_bits&1,'NONREGULAR_OR_ENCRYPTED_ARCHIVE_ENTRY')
            if item.is_dir():require((clean in valid_dirs or clean=='bin') and item.file_size==0 and item.compress_size==0,'UNEXPECTED_ARCHIVE_DIRECTORY');continue
            require(clean in expected and item.file_size==sizes[clean],'UNEXPECTED_FILE_OR_SIZE')
            names.append(clean)
        require(set(names)==set(expected) and len(names)==47,'ARCHIVE_FILE_SET_CHANGED')
        for name in names:
            dest=STAGED/Path(*PurePosixPath(name).parts)
            require(dest.resolve().is_relative_to(STAGED.resolve()),'EXTRACTION_OUTSIDE_STAGING')
            dest.parent.mkdir(parents=True,exist_ok=True);no_reparse(dest)
            h=hashlib.sha256();n=0
            with z.open(name) as source,dest.open('xb') as out:
                while block:=source.read(65536):
                    n+=len(block);require(n<=sizes[name],'EXTRACTED_FILE_BOUND_EXCEEDED');out.write(block);h.update(block)
                out.flush();os.fsync(out.fileno())
            require(n==sizes[name] and h.hexdigest()==expected[name],'EXTRACTED_PAYLOAD_CHANGED')
    require(inventory(STAGED)==expected,'SOURCE_PAYLOAD_MANIFEST_CHANGED')
    with (STAGED/'codex-x86_64-pc-windows-msvc.exe').open('rb') as source,(STAGED/'codex.exe').open('xb') as out:
        shutil.copyfileobj(source,out,length=65536);out.flush();os.fsync(out.fileno())
    require(inventory(STAGED)==final,'STAGED_FINAL_MANIFEST_CHANGED')
    checkpoint('STAGED_PAYLOAD_VERIFIED',files=48)
    paths();require(hashfile(CONTEXT)==context_before,'SERVICE_CONTEXT_CHANGED_BEFORE_PUBLICATION')
    if not TARGET.parent.exists():TARGET.parent.mkdir(exist_ok=False)
    no_reparse(TARGET.parent);require(os.stat(TARGET.parent).st_dev==os.stat(STAGED).st_dev,'RENAME_VOLUME_CHANGED')
    paths()
    os.rename(STAGED,TARGET)  # Same filesystem, directory absent, Windows fails if target exists; no replacement.
    no_reparse(TARGET);actual=inventory(TARGET)
    require(actual==final,'PUBLISHED_MANIFEST_CHANGED')
    require(hashfile(CONTEXT)==context_before,'SERVICE_CONTEXT_CHANGED_AFTER_PUBLICATION')
    save('destination-manifest.json',{'target':str(TARGET),'files':actual,'file_count':48,'matched_original_discovery':True})
    save('result.json',{'status':'EXACT_CODEX_0157_PAYLOAD_RESTORED','target':str(TARGET),'archive_sha256':ZIP_SHA,
        'original_discovery_manifest_sha256':hashfile(DISCOVERY),'files':48,'atomic_directory_rename':True,
        'overwrite':False,'service_context_file_sha256_before':context_before,'service_context_file_sha256_after':hashfile(CONTEXT),
        'service_context_unchanged':True,'native_executions':0,'provider_calls':0,'service_calls':0,'auth_or_personal_config_read':False})
    checkpoint('RESTORATION_CONFIRMED',target=str(TARGET),files=48,service_context_unchanged=True)

if __name__=='__main__':
    try:main()
    except Exception as error:
        save('failure.json',{'status':'RESTORATION_FAILED_NO_FALLBACK','error_type':type(error).__name__,
            'safe_reason':str(error) if type(error) is RuntimeError else None,'target_exists':TARGET.exists(),
            'native_executions':0,'provider_calls':0,'service_calls':0})
        checkpoint('RESTORATION_FAILED',error_type=type(error).__name__)
        raise SystemExit(1)
