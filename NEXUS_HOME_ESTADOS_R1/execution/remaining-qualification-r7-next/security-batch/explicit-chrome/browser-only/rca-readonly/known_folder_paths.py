"""Path-only Win32 metadata query; no profile/config file is opened."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import uuid

shell=ctypes.WinDLL('shell32',use_last_error=True)
ole=ctypes.WinDLL('ole32',use_last_error=True)
shell.SHGetKnownFolderPath.argtypes=[ctypes.c_void_p,wintypes.DWORD,wintypes.HANDLE,ctypes.POINTER(ctypes.c_void_p)]
shell.SHGetKnownFolderPath.restype=wintypes.LONG
ole.CoTaskMemFree.argtypes=[ctypes.c_void_p]
identifier=ctypes.create_string_buffer(uuid.UUID('F1B32785-6FBA-4FCF-9D55-7B8E7F157091').bytes_le)


def local_app_data():
    target=ctypes.c_void_p()
    # KF_FLAG_DONT_VERIFY: do not test/create the actual directory.
    result=shell.SHGetKnownFolderPath(identifier,0x4000,None,ctypes.byref(target))
    assert result==0, result
    try:
        return ctypes.wstring_at(target)
    finally:
        ole.CoTaskMemFree(target)


normal=local_app_data()
own=Path('C:/Users/jpamb/AppData/Local/Temp/nexus-hst-browser-diagnostic-829flnmp')
previous=os.environ.get('LOCALAPPDATA')
os.environ['LOCALAPPDATA']=str(own/'localappdata')
try:
    overridden=local_app_data()
finally:
    if previous is None:
        os.environ.pop('LOCALAPPDATA',None)
    else:
        os.environ['LOCALAPPDATA']=previous
actual=own/'browser-profile'
standard=Path(normal)/'Google/Chrome/User Data'
own_environment_default=own/'localappdata/Google/Chrome/User Data'
print(json.dumps({'metadata_only':True,'api':'SHGetKnownFolderPath(FOLDERID_LocalAppData,KF_FLAG_DONT_VERIFY)',
    'known_folder':normal,'after_current_process_LOCALAPPDATA_override':overridden,
    'override_is_current_metadata_process_only':True,
    'standard_chrome_default_derived_not_read':str(standard),
    'own_environment_chrome_default_derived_not_read':str(own_environment_default),
    'actual_cli_user_data_dir_argument':str(actual),
    'actual_argument_equals_known_folder_default':actual.resolve()==standard.resolve(),
    'actual_argument_equals_own_environment_default':actual.resolve()==own_environment_default.resolve(),
    'personal_profile_or_config_file_contents_read':False},indent=2))
