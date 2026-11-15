"""Finish metadata only after successful wheel builds/install; no rebuild."""
from pathlib import Path
import hashlib,json,subprocess,tarfile
HERE=Path(__file__).resolve().parent
def pin(p): return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
versions=json.loads(subprocess.check_output(['rtk','proxy','python','-c',
    "import importlib.metadata,json; print(json.dumps({n:importlib.metadata.version(n) for n in ('build','setuptools','wheel')}))"],text=True))
sources={}
for name in ('core','connector','nexus'):
    archive=HERE/(name+'-source.tar')
    with tarfile.open(archive) as t: commit=t.pax_headers['comment']
    sources[name]={'commit':commit,'archive':pin(archive)}
record={'format':1,'sources':sources,'build_python':'C:/Python313/python.exe',
 'build_versions':versions,'build_isolation':False,'source_date_epoch':'1767225600',
 'core_normalization':'archived tools/build_artifacts.py _normalize_wheel',
 'wheels':[pin(p) for p in sorted((HERE/'wheels').glob('*.whl'))],
 'dependency_origin':'C:/Users/jpamb/AppData/Local/Temp/sonnet-canonical-recovery-proposal-7oq808_t/package/venv',
 'dependency_copy_only':True,'campaign_environment_modified':False,
 'initial_metadata_failure':'After successful build/install, isolated build script could not discover user-site build distribution metadata. Finalizer queried same nonisolated Python invocation used by the build children; no rebuild or test rerun.',
 'nexus_ui':'Committed assets from archive only; concurrent UI changes not included or qualified'}
(HERE/'build-provenance.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'sources':sources,'wheels':record['wheels']}))
