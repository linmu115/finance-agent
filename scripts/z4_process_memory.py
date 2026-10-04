"""Windows process-tree observed working set sampler, using OS APIs only."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import time
from pathlib import Path

class Entry(C.Structure):
    _fields_=[('dwSize',W.DWORD),('cntUsage',W.DWORD),('th32ProcessID',W.DWORD),('th32DefaultHeapID',C.c_size_t),('th32ModuleID',W.DWORD),('cntThreads',W.DWORD),('th32ParentProcessID',W.DWORD),('pcPriClassBase',W.LONG),('dwFlags',W.DWORD),('szExeFile',W.WCHAR*260)]
class Memory(C.Structure):
    _fields_=[('cb',W.DWORD),('PageFaultCount',W.DWORD),('PeakWorkingSetSize',C.c_size_t),('WorkingSetSize',C.c_size_t),('QuotaPeakPagedPoolUsage',C.c_size_t),('QuotaPagedPoolUsage',C.c_size_t),('QuotaPeakNonPagedPoolUsage',C.c_size_t),('QuotaNonPagedPoolUsage',C.c_size_t),('PagefileUsage',C.c_size_t),('PeakPagefileUsage',C.c_size_t)]
kernel=C.WinDLL('kernel32',use_last_error=True);psapi=C.WinDLL('psapi',use_last_error=True)
kernel.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD];kernel.CreateToolhelp32Snapshot.restype=W.HANDLE
kernel.Process32FirstW.argtypes=[W.HANDLE,C.POINTER(Entry)];kernel.Process32NextW.argtypes=[W.HANDLE,C.POINTER(Entry)]
kernel.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];kernel.OpenProcess.restype=W.HANDLE
kernel.CloseHandle.argtypes=[W.HANDLE]
psapi.GetProcessMemoryInfo.argtypes=[W.HANDLE,C.POINTER(Memory),W.DWORD]

def sample(pid):
    handle=kernel.CreateToolhelp32Snapshot(2,0);entry=Entry();entry.dwSize=C.sizeof(entry);processes={}
    try:
        ok=kernel.Process32FirstW(handle,C.byref(entry))
        while ok:
            processes[entry.th32ProcessID]={'pid':entry.th32ProcessID,'parent_pid':entry.th32ParentProcessID,'name':entry.szExeFile}
            ok=kernel.Process32NextW(handle,C.byref(entry))
    finally:kernel.CloseHandle(handle)
    selected={pid};changed=True
    while changed:
        expanded=selected|{p for p,v in processes.items() if v['parent_pid'] in selected};changed=expanded!=selected;selected=expanded
    rows=[]
    for ident in selected:
        if ident not in processes:continue
        process=kernel.OpenProcess(0x0400|0x0010,False,ident);m=Memory();m.cb=C.sizeof(m)
        try:
            if process and psapi.GetProcessMemoryInfo(process,C.byref(m),C.sizeof(m)):
                rows.append(processes[ident]|{'rss_bytes':m.WorkingSetSize,'os_peak_working_set_bytes':m.PeakWorkingSetSize})
        finally:
            if process:kernel.CloseHandle(process)
    return {'unix_seconds':time.time(),'host_pid':pid,'processes':rows,'total_rss_bytes':sum(p['rss_bytes'] for p in rows)}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pid',required=True,type=int);p.add_argument('--output',required=True,type=Path);p.add_argument('--stop-file',required=True,type=Path);a=p.parse_args()
    with a.output.open('x',encoding='utf8') as stream:
        while not a.stop_file.exists():
            stream.write(json.dumps(sample(a.pid))+'\n');stream.flush();time.sleep(1)
