#!/usr/bin/env python3
"""win-kernel-leak - find out WHY every program on a Windows box starts slowly.

Written after a session that blamed Python, then the hooks, then Defender, then a
runaway dllhost, before measuring the one number that mattered.

THE HEADLINE FINDING IT ENCODES
-------------------------------
Every hook timed out. `whoami.exe` took 470 ms, `cmd /c exit` 0.6-2.7 s, and all of
it was spent inside CreateProcess. CPU was at 46% of 32 cores and file opens took
under 25 ms. Four days of uptime had grown the kernel pool to:

    Pool Nonpaged  10.6 GB          (healthy: a few hundred MB)
    Pool Paged     19.8 GB
    Commit         169 / 187 GB
    tag Toke       6.8 GB, 3.27M live tokens, growing 3-15/s
    tag File       4.8 GB nonpaged, 12.7M file objects

No user process held handles to them (311k handles system-wide), so the references
were held inside the kernel. Task Manager shows none of this, and "free RAM" was
23 GB. Measure the pool FIRST when spawns are slow.

USAGE
-----
    win-kernel-leak.py pool [--max-gb N]   # pool totals + top tags; exit 1 over N GB (default 4)
    win-kernel-leak.py rate [SECS]         # which tags GROW (live-object delta per second)
    win-kernel-leak.py spawn [N]           # CreateProcess latency, the user-visible symptom
    win-kernel-leak.py trace TAG [SECS]    # ADMIN: WPR pool trace filtered to one tag -> CSV
    win-kernel-leak.py attribute CSV       # un-freed allocations by process + symbolized stacks
    win-kernel-leak.py hunt TAG [SECS]     # ADMIN: objects that OUTLIVED their creator, read live
    win-kernel-leak.py debug status|on|off # kernel debug mode (Secure Boot blocks `on`)
    win-kernel-leak.py --self-test         # offline regression test of parsers and exit codes

`pool`, `rate` and `spawn` need no admin rights: the tag table comes from
NtQuerySystemInformation(SystemPoolTagInformation). `trace`, `hunt` and
`debug on|off` elevate.

`hunt` is the step that turns "this tag grows" into "these exact objects leaked":
it records the tag-filtered trace WITH process start/end events, keeps the
allocations still alive whose creating process has EXITED, snapshots the live
kernel with LiveKD (Sysinternals) and reads each object's HandleCount and
PointerCount with kd. HandleCount 0 with PointerCount > 0 after the creator
exited is a kernel-held reference: the leak, by address. Naming the HOLDER
needs a live kernel debugger (`debug on` + reboot), which Secure Boot forbids.

What did NOT work, measured 2026-10-18, so it is not rebuilt: object reference
tracing on every process (`gflags -ko -t Toke`) made the desktop unusable within
minutes; filtered to one image it recorded none of the leaked objects; `!poolfind`
and `s -q` over a 14 GB live dump never finished.

Exit 0 clean, 1 defect found, 2 could-not-determine (which is a FAILURE, not a
pass - a check that cannot run tells you nothing).
"""
from __future__ import annotations

import bisect
import collections
import csv
import ctypes
import os
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request

CREATE_NO_WINDOW = 0x08000000
KERNEL_BASE = 0xFFFF800000000000
# SYSTEM_POOLTAG (x64): Tag@0 PagedAllocs@4 PagedFrees@8 PagedUsed@16
# NonPagedAllocs@24 NonPagedFrees@28 NonPagedUsed@32; 40 bytes; array at offset 8.
POOLTAG = struct.Struct("<4sIIxxxxQIIQ")
SYSTEM_POOLTAG_INFORMATION = 22


def _windows() -> bool:
    return sys.platform == "win32"


def _workdir(prefix: str) -> str:
    """A scratch dir the NON-elevated user can read: on Windows, Python 3.12+
    mkdtemp() restricts the dir to its creator, so output written by an elevated
    run (trace, hunt) was unreadable afterwards (measured 2026-10-18)."""
    path = os.path.join(tempfile.gettempdir(), "%s%d-%d" % (prefix, os.getpid(), int(time.time())))
    os.makedirs(path, exist_ok=True)
    return path


# ------------------------------------------------------------------------- pool
def parse_pool_tags(buf: bytes) -> list:
    """Rows of (tag, paged_bytes, paged_live, nonpaged_bytes, nonpaged_live)."""
    (count,) = struct.unpack_from("<I", buf, 0)
    rows = []
    for i in range(count):
        tag, pa, pf, pu, na, nf, nu = POOLTAG.unpack_from(buf, 8 + i * POOLTAG.size)
        rows.append((tag.decode("latin-1"), pu, pa - pf, nu, na - nf))
    return rows


def read_pool_tags() -> list:
    ntdll = ctypes.WinDLL("ntdll")
    size = 4 << 20
    for _ in range(4):
        buf = ctypes.create_string_buffer(size)
        need = ctypes.c_ulong()
        st = ntdll.NtQuerySystemInformation(SYSTEM_POOLTAG_INFORMATION, buf, size,
                                            ctypes.byref(need)) & 0xFFFFFFFF
        if st == 0:
            return parse_pool_tags(buf.raw)
        if st != 0xC0000004:  # STATUS_INFO_LENGTH_MISMATCH
            raise OSError("NtQuerySystemInformation status 0x%08X" % st)
        size = max(need.value, size * 2)
    raise OSError("pool tag table kept growing")


def pool_verdict(rows: list, max_gb: float) -> tuple:
    paged = sum(r[1] for r in rows)
    nonpaged = sum(r[3] for r in rows)
    total_gb = (paged + nonpaged) / 2**30
    return (1 if total_gb > max_gb else 0), paged, nonpaged


def cmd_pool(args: list) -> int:
    max_gb = float(args[args.index("--max-gb") + 1]) if "--max-gb" in args else 4.0
    rows = read_pool_tags()
    code, paged, nonpaged = pool_verdict(rows, max_gb)
    print("pool paged %.1f GB  nonpaged %.1f GB  (limit %.1f GB total)"
          % (paged / 2**30, nonpaged / 2**30, max_gb))
    print("\n%-5s %10s %12s %10s %12s" % ("tag", "paged MB", "paged live", "NP MB", "NP live"))
    for r in sorted(rows, key=lambda r: r[1] + r[3], reverse=True)[:12]:
        print("%-5s %10.0f %12d %10.0f %12d" % (r[0], r[1] / 2**20, r[2], r[3] / 2**20, r[4]))
    print("\nverdict:", "LEAK - kernel pool over the limit; run `rate` to see what grows"
          if code else "ok")
    return code


def cmd_rate(args: list) -> int:
    secs = float(args[0]) if args else 30.0
    a = {r[0]: r for r in read_pool_tags()}
    t0 = time.time()
    time.sleep(secs)
    b = {r[0]: r for r in read_pool_tags()}
    dt = time.time() - t0
    growth = []
    for tag, rb in b.items():
        ra = a.get(tag, (tag, 0, 0, 0, 0))
        growth.append((tag, (rb[2] - ra[2]) / dt, (rb[4] - ra[4]) / dt,
                       (rb[1] + rb[3] - ra[1] - ra[3]) / dt))
    growth.sort(key=lambda g: g[3], reverse=True)
    print("over %.0f s, fastest-growing tags (live objects/s, bytes/s):" % dt)
    for tag, pl, nl, by in growth[:10]:
        print("  %-5s paged %+9.1f/s  nonpaged %+9.1f/s  %+12.0f B/s" % (tag, pl, nl, by))
    return 0


# -------------------------------------------------------------------------- spawn
def cmd_spawn(args: list) -> int:
    n = int(args[0]) if args else 5
    cmd = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe")
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        subprocess.run([cmd, "/c", "exit"], creationflags=CREATE_NO_WINDOW, check=False)
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    med = times[len(times) // 2]
    print("cmd /c exit x%d: median %.0f ms, max %.0f ms (healthy: < 60 ms)" % (n, med, times[-1]))
    return 1 if med > 250 else 0


# -------------------------------------------------------------------------- trace
WPRP = """<?xml version="1.0" encoding="utf-8"?>
<WindowsPerformanceRecorder Version="1.0"><Profiles>
<SystemCollector Id="SC" Name="NT Kernel Logger"><BufferSize Value="1024"/><Buffers Value="512"/>
</SystemCollector>
<SystemProvider Id="SP"><Keywords><Keyword Value="ProcessThread"/><Keyword Value="Loader"/>
<Keyword Value="Pool"/></Keywords><Stacks><Stack Value="PoolAllocation"/></Stacks>
<PoolTags><PoolTag Value="%s"/></PoolTags></SystemProvider>
<Profile Id="TagLeak.Verbose.File" Name="TagLeak" Description="one pool tag" LoggingMode="File"
 DetailLevel="Verbose"><Collectors><SystemCollectorId Value="SC"><SystemProviderId Value="SP"/>
</SystemCollectorId></Collectors></Profile></Profiles></WindowsPerformanceRecorder>
"""


def cmd_trace(args: list) -> int:
    """Never trace without a tag filter: the unfiltered Pool profile wrote 29 GB in 30 s
    and dropped 413M events (measured 2026-10-18)."""
    if not args or len(args[0]) > 4:
        print("usage: trace TAG [SECS] (TAG is a 1-4 char pool tag, e.g. Toke)")
        return 2
    if not ctypes.windll.shell32.IsUserAnAdmin():
        print("trace needs an elevated shell (wpr talks to the NT Kernel Logger)")
        return 2
    tag, secs = args[0], int(args[1]) if len(args) > 1 else 60
    work = _workdir("kleak-")
    prof, etl, out = (os.path.join(work, n) for n in ("tag.wprp", "tag.etl", "tag.csv"))
    with open(prof, "w", encoding="utf-8") as f:
        f.write(WPRP % tag)

    def run(argv):
        return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", creationflags=CREATE_NO_WINDOW)

    run(["wpr", "-cancel"])
    r = run(["wpr", "-start", prof + "!TagLeak", "-filemode"])
    if r.returncode:
        print("wpr -start failed:", r.stdout, r.stderr)
        return 2
    time.sleep(secs)
    r = run(["wpr", "-stop", etl, "-skipPdbGen"])
    if r.returncode or not os.path.exists(etl):
        print("wpr -stop failed:", r.stdout, r.stderr)
        return 2
    if "dropped" in r.stdout:
        print("WARNING:", r.stdout.strip().splitlines()[-1])
    r = run(["tracerpt", etl, "-o", out, "-of", "CSV", "-y"])
    if r.returncode or not os.path.exists(out):
        print("tracerpt failed:", r.stdout, r.stderr)
        return 2
    print("trace CSV:", out)
    print("next: win-kernel-leak.py attribute", out)
    return 0


# ---------------------------------------------------------------------- attribute
def _h(x: str) -> int:
    x = x.strip()
    return int(x, 16) if x.lower().startswith("0x") else int(x or 0)


def parse_trace(rows) -> dict:
    """Fold tracerpt CSV rows into allocations still alive at the end of the window."""
    allocs, stacks, images, starts, ended = {}, {}, collections.defaultdict(list), {}, set()
    for row in rows:
        if len(row) < 20:
            continue
        ev, typ = row[0].strip(), row[1].strip()
        if ev == "Pool" and typ in ("PoolAllocation", "PoolFree"):
            addr = _h(row[-1])
            if typ == "PoolAllocation":
                allocs[addr] = (int(row[16]), _h(row[9]), _h(row[10]))
            else:
                allocs.pop(addr, None)
        elif ev == "StackWalk" and len(row) > 22:
            stacks.setdefault(_h(row[21]), []).append(
                (int(row[16]), [_h(a) for a in row[22:] if a.strip()]))
        elif ev == "Image" and typ in ("DCStart", "Load"):
            base = _h(row[19])
            key = 0 if base >= KERNEL_BASE else _h(row[21])
            images[key].append((base, base + _h(row[20]),
                                row[-1].strip().strip('"').split("\\")[-1]))
        elif ev == "Process" and typ in ("Start", "DCStart") and len(row) > 27:
            starts[_h(row[20])] = row[27].strip().strip('"')
        elif ev == "Process" and typ == "End" and len(row) > 20:
            ended.add(_h(row[20]))
    for v in stacks.values():
        v.sort(key=lambda s: s[0])
    return {"allocs": allocs, "stacks": stacks,
            "images": {k: sorted(v) for k, v in images.items()},
            "names": starts, "ended": ended}


def module_of(images: dict, pid: int, addr: int) -> str:
    table = images.get(0 if addr >= KERNEL_BASE else pid, [])
    i = bisect.bisect_right(table, (addr, float("inf"), "")) - 1
    if i >= 0 and table[i][0] <= addr < table[i][1]:
        return table[i][2]
    return "?"


def stack_for(t: dict, ts: int, tid: int):
    lst = t["stacks"].get(tid, [])
    j = bisect.bisect_left(lst, (ts, []))
    if j < len(lst) and lst[j][0] - ts < 20000:  # 2 ms in 100 ns units
        return lst[j][1]
    return None


class NtSymbols:
    """ntoskrnl RVA -> symbol via the public PDB (fetched by CodeView GUID) + dbghelp."""

    def __init__(self, cache_dir: str):
        from ctypes import wintypes
        nt = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "ntoskrnl.exe")
        data = open(nt, "rb").read()
        pe = struct.unpack_from("<I", data, 0x3C)[0]
        nsec, optsz = struct.unpack_from("<H", data, pe + 6)[0], struct.unpack_from("<H", data, pe + 20)[0]
        opt = pe + 24
        dbg_rva, dbg_size = struct.unpack_from("<II", data, opt + 112 + 6 * 8)
        secs = [struct.unpack_from("<8sIIII", data, opt + optsz + i * 40) for i in range(nsec)]

        def off(rva):
            for _, vs, va, rs, raw in secs:
                if va <= rva < va + max(vs, rs):
                    return raw + rva - va
            raise ValueError(rva)

        o = off(dbg_rva)
        for i in range(dbg_size // 28):
            typ, _, _, ptr = struct.unpack_from("<12xIIII", data, o + i * 28)
            if typ == 2:  # IMAGE_DEBUG_TYPE_CODEVIEW
                _, guid, age = struct.unpack_from("<4s16sI", data, ptr)
                name = data[ptr + 24:data.index(b"\0", ptr + 24)].decode()
                g = struct.unpack("<IHH8s", guid)
                gid = "%08X%04X%04X%s%X" % (g[0], g[1], g[2], g[3].hex().upper(), age)
        pdb = os.path.join(cache_dir, name)
        if not os.path.exists(pdb):
            url = "https://msdl.microsoft.com/download/symbols/%s/%s/%s" % (name, gid, name)
            req = urllib.request.Request(url, headers={"User-Agent": "Microsoft-Symbol-Server/10.0"})
            with urllib.request.urlopen(req, timeout=300) as r, open(pdb, "wb") as f:
                f.write(r.read())
        self.dbg = ctypes.WinDLL("dbghelp.dll")
        self.h = wintypes.HANDLE(0x4B4C)
        self.base = 0x140000000
        self.dbg.SymSetOptions(0x2 | 0x4)
        self.dbg.SymInitializeW(self.h, cache_dir, False)
        self.dbg.SymLoadModuleExW.restype = ctypes.c_uint64
        self.dbg.SymLoadModuleExW.argtypes = [wintypes.HANDLE, wintypes.HANDLE, wintypes.LPCWSTR,
                                              wintypes.LPCWSTR, ctypes.c_uint64, wintypes.DWORD,
                                              ctypes.c_void_p, wintypes.DWORD]
        self.dbg.SymLoadModuleExW(self.h, None, nt, None, self.base, len(data), None, 0)

    def name(self, rva: int) -> str:
        class SymbolInfo(ctypes.Structure):
            _fields_ = [("SizeOfStruct", ctypes.c_ulong), ("TypeIndex", ctypes.c_ulong),
                        ("Reserved", ctypes.c_uint64 * 2), ("Index", ctypes.c_ulong),
                        ("Size", ctypes.c_ulong), ("ModBase", ctypes.c_uint64),
                        ("Flags", ctypes.c_ulong), ("Value", ctypes.c_uint64),
                        ("Address", ctypes.c_uint64), ("Register", ctypes.c_ulong),
                        ("Scope", ctypes.c_ulong), ("Tag", ctypes.c_ulong),
                        ("NameLen", ctypes.c_ulong), ("MaxNameLen", ctypes.c_ulong),
                        ("Name", ctypes.c_char * 512)]
        si = SymbolInfo()
        si.SizeOfStruct = 88  # sizeof(SYMBOL_INFO) with Name[1]; anything else fails silently
        si.MaxNameLen = 511
        disp = ctypes.c_uint64()
        if self.dbg.SymFromAddr(self.h, ctypes.c_uint64(self.base + rva), ctypes.byref(disp),
                                ctypes.byref(si)):
            return "%s+0x%X" % (si.Name.decode(), disp.value)
        return "nt+%X" % rva


def summarize(t: dict, symbolize=None, top: int = 4) -> list:
    lines = ["allocations alive at end of window: %d" % len(t["allocs"])]
    by_proc = collections.Counter()
    shapes = collections.Counter()
    nt = next((b for b, _, n in t["images"].get(0, []) if n.lower() == "ntoskrnl.exe"), None)
    for ts, pid, tid in t["allocs"].values():
        by_proc[t["names"].get(pid, "pid %d" % pid)] += 1
        st = stack_for(t, ts, tid)
        if not st:
            continue
        frames = []
        for a in st:
            m = module_of(t["images"], pid, a)
            if m.lower() == "ntoskrnl.exe" and nt is not None:
                frames.append(symbolize(a - nt) if symbolize else "nt+%X" % (a - nt))
            elif a >= KERNEL_BASE:
                frames.append(m)
        # drop the ETW/pool plumbing at the top; keep the frames that say WHO allocated
        while frames and frames[0].split("+")[0] in (
                "KeExpandKernelStackAndCalloutInternal", "EtwpTraceStackWalk",
                "EtwpLogKernelEvent", "EtwTracePool", "ExAllocateHeapPool",
                "ExpAllocatePoolWithTagFromNode", "ExAllocatePool2", "ExAllocatePoolWithTag"):
            frames.pop(0)
        shapes[" > ".join(frames[:6])] += 1
    lines.append("\nby allocating process:")
    lines += ["  %6d  %s" % (n, p) for p, n in by_proc.most_common(10)]
    lines.append("\nby kernel path (third-party .sys names appear as themselves):")
    lines += ["  %6d  %s" % (n, s) for s, n in shapes.most_common(top)]
    return lines


def cmd_attribute(args: list) -> int:
    if not args or not os.path.exists(args[0]):
        print("usage: attribute TRACE.csv (from the `trace` mode)")
        return 2
    with open(args[0], encoding="utf-8", errors="replace", newline="") as f:
        t = parse_trace(csv.reader(f, skipinitialspace=True))
    if not t["images"].get(0):
        print("no kernel image rundown in the trace: cannot attribute")
        return 2
    sym = None
    try:
        sym = NtSymbols(os.path.dirname(os.path.abspath(args[0]))).name
    except (OSError, ValueError, UnboundLocalError) as exc:
        print("symbols unavailable (%s); printing raw ntoskrnl offsets" % exc)
    print("\n".join(summarize(t, sym)))
    return 0


# ------------------------------------------------------------------- hunt / debug
KD_DEFAULT = r"C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\kd.exe"
LIVEKD_DEFAULT = r"C:\Sysinternals\livekd64.exe"
SYMPATH = "srv*%s*https://msdl.microsoft.com/download/symbols"


def leaked_by_exited(t: dict) -> list:
    """Addresses still allocated whose CREATING process exited inside the window."""
    return sorted(addr for addr, (_, pid, _) in t["allocs"].items() if pid in t["ended"])


def parse_kd_objects(text: str) -> list:
    """(object, handle_count, pointer_count) from kd `!object` output."""
    out, obj = [], None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("Object:"):
            obj = line.split()[1]
        elif line.startswith("HandleCount:") and obj:
            parts = line.replace(":", " ").split()
            out.append((obj, int(parts[1]), int(parts[3])))
            obj = None
    return out


def _run(argv, timeout=None):
    return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", creationflags=CREATE_NO_WINDOW, timeout=timeout)


def _kd(kd: str, dump: str, commands: list, timeout: int = 900) -> str:
    work = _workdir("kleak-kd-")
    script, log = os.path.join(work, "cmds.txt"), os.path.join(work, "kd.log")
    with open(script, "w", encoding="utf-8") as f:
        f.write("\n".join([".sympath " + SYMPATH % os.path.join(work, "sym"),
                           ".reload /f nt"] + commands + ["q"]) + "\n")
    _run([kd, "-z", dump, "-logo", log, "-cf", script], timeout=timeout)
    with open(log, encoding="utf-8", errors="replace") as f:
        return f.read()


def cmd_hunt(args: list) -> int:
    if not args or len(args[0]) > 4:
        print("usage: hunt TAG [SECS] [--dump-dir DIR] [--keep-dump]")
        return 2
    if not ctypes.windll.shell32.IsUserAnAdmin():
        print("hunt needs an elevated shell (wpr + LiveKD)")
        return 2
    kd = os.environ.get("WKL_KD", KD_DEFAULT)
    livekd = os.environ.get("WKL_LIVEKD", LIVEKD_DEFAULT)
    for tool in (kd, livekd):
        if not os.path.exists(tool):
            print("missing %s (Debugging Tools for Windows / Sysinternals LiveKD)" % tool)
            return 2
    tag = args[0]
    secs = int(args[1]) if len(args) > 1 and args[1].isdigit() else 120
    dump_dir = args[args.index("--dump-dir") + 1] if "--dump-dir" in args else tempfile.gettempdir()
    work = _workdir("kleak-hunt-")
    prof, etl, csv_out = (os.path.join(work, n) for n in ("tag.wprp", "tag.etl", "tag.csv"))
    dump = os.path.join(dump_dir, "kleak-live.dmp")
    with open(prof, "w", encoding="utf-8") as f:
        f.write(WPRP % tag)
    _run(["wpr", "-cancel"])
    if _run(["wpr", "-start", prof + "!TagLeak", "-filemode"]).returncode:
        print("wpr -start failed")
        return 2
    try:
        time.sleep(secs)
        # snapshot BEFORE stopping the trace, so every alive allocation is in the dump
        _run([livekd, "-accepteula", "-ml", "-o", dump, "-k", kd], timeout=1800)
    finally:
        _run(["wpr", "-stop", etl, "-skipPdbGen"])
    if not os.path.exists(dump):
        print("LiveKD wrote no dump")
        return 2
    try:
        _run(["tracerpt", etl, "-o", csv_out, "-of", "CSV", "-y"])
        with open(csv_out, encoding="utf-8", errors="replace", newline="") as f:
            t = parse_trace(csv.reader(f, skipinitialspace=True))
        leaked = leaked_by_exited(t)
        print("%d %s allocations outlived the process that created them (%d s window)"
              % (len(leaked), tag, secs))
        if not leaked:
            return 0
        sample = leaked[:20]
        probe = _kd(kd, dump, ["!object %s+0x%x" % (hex(sample[0]), o)
                               for o in range(0x30, 0x90, 0x10)])
        found = parse_kd_objects(probe)
        if not found:
            print("no object header found at +0x30..+0x80 of %s; not an Ob object tag" % hex(sample[0]))
            return 2
        off = int(found[0][0], 16) - sample[0]
        rows = parse_kd_objects(_kd(kd, dump, ["!object %s+0x%x" % (hex(a), off) for a in sample]))
        held = [r for r in rows if r[1] == 0 and r[2] > 0]
        print("object body at allocation+0x%x; sampled %d:" % (off, len(rows)))
        for obj, hc, pc in rows:
            print("  %s  HandleCount %d  PointerCount %d" % (obj, hc, pc))
        print("\nverdict: %d of %d have no handle but a kernel-held reference - the leak, by address"
              % (len(held), len(rows)))
        with open(os.path.join(work, "leaked.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(hex(a) for a in leaked))
        print("all leaked allocation addresses:", os.path.join(work, "leaked.txt"))
        return 1 if held else 0
    finally:
        if "--keep-dump" not in args:
            try:
                os.remove(dump)
            except OSError:
                pass


def secure_boot_blocks(bcdedit_output: str) -> bool:
    return "protected by Secure Boot policy" in bcdedit_output


def cmd_debug(args: list) -> int:
    action = args[0] if args else "status"
    sb = _run(["powershell", "-NoProfile", "-Command", "Confirm-SecureBootUEFI"]).stdout.strip()
    print("Secure Boot:", sb or "unknown (needs admin)")
    if action == "status":
        r = _run(["bcdedit", "/enum", "{current}"])
        line = next((ln for ln in r.stdout.splitlines() if ln.lower().startswith("debug ")), None)
        print("kernel debug:", line.split()[-1] if line else "off (or needs admin to read)")
        return 0
    if action not in ("on", "off"):
        print("usage: debug status|on|off")
        return 2
    r = _run(["bcdedit", "/debug", action])
    text = (r.stdout + r.stderr).strip()
    print(text)
    if secure_boot_blocks(text):
        print("Secure Boot forbids changing the debug flag. Turn Secure Boot off in the "
              "firmware setup first (anti-cheat games will not start while it is off), "
              "then rerun; it applies at the next boot.")
        return 2
    if r.returncode:
        return 2
    print("applies at the next boot; then `kd -kl` reads the live kernel")
    return 0


# ---------------------------------------------------------------------- self-test
def _self_test() -> int:
    ok = True

    def check(label, cond):
        nonlocal ok
        print("  %s %s" % ("ok  " if cond else "FAIL", label))
        ok = ok and bool(cond)

    buf = struct.pack("<I4x", 2)
    buf += POOLTAG.pack(b"Toke", 10, 4, 7 * 2**30, 0, 0, 0)
    buf += POOLTAG.pack(b"File", 0, 0, 0, 100, 1, 5 * 2**30)
    rows = parse_pool_tags(buf)
    check("pool table parses tag, bytes and live counts",
          rows[0] == ("Toke", 7 * 2**30, 6, 0, 0) and rows[1][4] == 99)
    check("12 GB of pool is a LEAK at the 4 GB limit", pool_verdict(rows, 4.0)[0] == 1)
    check("the same pool is ok under a 16 GB limit", pool_verdict(rows, 16.0)[0] == 0)

    def row(ev, typ, pid, tid, ts, *user):
        return [ev, typ] + ["0"] * 7 + [hex(pid), hex(tid)] + [""] * 5 + [str(ts), "0", "0"] \
            + [str(u) for u in user]

    nt = 0xFFFFF80000000000
    trace = [
        row("Image", "DCStart", 4, 1, 1, hex(nt), hex(0x1000000), 0, '"ntoskrnl.exe"'),
        row("Image", "DCStart", 4, 1, 1, hex(nt + 0x2000000), hex(0x10000), 0, '"leaky.sys"'),
        row("Pool", "PoolAllocation", 50, 7, 100, 1, "0x656B6F54", "0x880", "0xAAA0"),
        row("StackWalk", "Stack", 50, 7, 100, 0, "0x32", 7, hex(nt + 0x2000010), hex(nt + 0x10)),
        row("Pool", "PoolAllocation", 50, 8, 200, 1, "0x656B6F54", "0x880", "0xBBB0"),
        row("Pool", "PoolFree", 50, 8, 300, 1, "0x656B6F54", "0x880", "0xBBB0"),
    ]
    t = parse_trace(trace)
    check("a freed allocation is not counted as leaked", list(t["allocs"]) == [0xAAA0])
    out = "\n".join(summarize(t))
    check("a third-party driver in the leaked stack is named", "leaky.sys" in out)
    check("ntoskrnl frames become offsets without symbols", "nt+10" in out)
    check("an empty trace attributes nothing", parse_trace([])["allocs"] == {})

    exited = parse_trace(trace + [
        row("Process", "Start", 1, 1, 50, "0xffff", "0x32", "0x1", 1, 259, 0, 0, '"u"', '"bash.exe"', '""'),
        row("Process", "End", 1, 1, 400, "0xffff", "0x32", "0x1", 1, 256, 0, 0, '"u"', '"bash.exe"', '""'),
    ])
    check("an allocation whose creator exited is a leak candidate",
          leaked_by_exited(exited) == [0xAAA0])
    check("an allocation whose creator still runs is not",
          leaked_by_exited(parse_trace(trace)) == [])
    kd_text = ("0: kd> !object 0xffff808a7b7a2760+0x50\n"
               "Object: ffff808a7b7a27b0  Type: (ffffa6049a5d2de0) Token\n"
               "    ObjectHeader: ffff808a7b7a2780 (new version)\n"
               "    HandleCount: 0  PointerCount: 2\n"
               "0: kd> !object 0xffff808a7b7a2760+0x60\n"
               "ffff808a7b7a27c0: Not a valid object (ObjectType invalid)\n")
    check("kd !object output yields (object, handles, pointers)",
          parse_kd_objects(kd_text) == [("ffff808a7b7a27b0", 0, 2)])
    check("the Secure Boot refusal from bcdedit is recognized",
          secure_boot_blocks("The value is protected by Secure Boot policy and cannot be modified"))
    check("a successful bcdedit is not mistaken for the refusal",
          not secure_boot_blocks("The operation completed successfully."))

    print("\nwin-kernel-leak --self-test: %s" % ("ALL PASS" if ok else "FAILURES"))
    return 0 if ok else 1


MODES = {"pool": cmd_pool, "rate": cmd_rate, "spawn": cmd_spawn, "trace": cmd_trace,
         "attribute": cmd_attribute, "hunt": cmd_hunt, "debug": cmd_debug}


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "pool"
    if mode == "--self-test":
        return _self_test()
    if mode not in MODES:
        print("unknown mode %r; expected one of: %s (or --self-test)" % (mode, ", ".join(MODES)))
        return 2
    if not _windows():
        print("win-kernel-leak reads the Windows kernel pool; this is %s" % sys.platform)
        return 2
    try:
        return MODES[mode](sys.argv[2:])
    except OSError as exc:
        print("could not judge: %s" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
