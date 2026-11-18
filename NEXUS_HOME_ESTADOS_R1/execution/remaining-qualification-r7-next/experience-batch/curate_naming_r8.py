"""R8 counterpart of the frozen R7 naming curator, without editing its antecedent."""
from pathlib import Path

HERE=Path(__file__).resolve().parent
source=(HERE/'curate_naming.py').read_text()
changes={
    "dest=HERE/'naming-r7'":"dest=HERE/'naming-r8'",
    "result['status']=='PRODUCT_DEFECT_UNNAMED_HEADER_MENU'":"result['status']=='PASS_NAMING_PREFLIGHT'",
    "status='FAIL_PRODUCT_ACCESSIBLE_NAME'":"status='PASS_FOCAL_ACCESSIBLE_NAME_EXPANDED'",
    'Only actual header-menu accessible name, not whole keyboard journey':'Actual header-menu name and expanded toggles only; not whole keyboard journey',
}
for old,new in changes.items():
    assert source.count(old)==1
    source=source.replace(old,new)
exec(compile(source,str(HERE/'curate_naming.py'),'exec'),dict(__name__='__main__',__file__=str(HERE/'curate_naming.py')))
