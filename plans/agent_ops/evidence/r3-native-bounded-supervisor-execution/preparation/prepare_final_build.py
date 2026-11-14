from pathlib import Path

b=Path(__file__).resolve().parent
s=(b/'build_install.py').read_text()
s=s.replace('ROOT=Path(__file__).resolve().parent',"BUNDLE=Path(__file__).resolve().parent\nROOT=BUNDLE/'final-build'\nROOT.mkdir()")
s=s.replace('PYTHON=ROOT/','PYTHON=BUNDLE/').replace("(ROOT/'environment.json')","(BUNDLE/'environment.json')")
s=s.replace('341a1d12ec1e6db7fe202be14ce1d2ef4c4e1f07','7810f3b9bd2576bca5ccc8286a4c661789bf73a4')
s=s.replace('02a74d6d7e60cba25e1e0e2999d330c302f9e5d2','6714d69563f86e965b7551239a09367982eadbca')
s=s.replace("'install','--no-index','--no-deps'","'install','--force-reinstall','--no-index','--no-deps'")
s=s.replace('installed=ROOT/','installed=BUNDLE/').replace("sha(ROOT/'dependency-manifest.json')","sha(BUNDLE/'dependency-manifest.json')")
with (b/'build_final.py').open('x',encoding='utf-8') as f:f.write(s)
