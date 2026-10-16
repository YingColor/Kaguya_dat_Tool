# -*- coding: utf-8 -*-
"""转区启动游戏。

为什么必须转区：这游戏（以及多数 Kaguya 系游戏）在中文系统下直接双击
Start.exe 会当场闪退——它内部按日文区域去读配置和文件名。必须用
「Locale Emulator」把进程伪装成日文环境。

为什么还要绕开中文路径：转区后游戏按 Shift-JIS 解码路径，一旦游戏所在的
文件夹名字里有中文，它就读不到自己的存档/脚本，弹「システムデータの
ロードに失敗しました！」。所以启动前先在纯英文路径下建一个目录联接
（Junction）指向游戏目录，再从联接路径启动。

Locale Emulator 是绿色便携的：LEProc.exe 只读同目录的 LEConfig.xml，
不写注册表。所以我们把它直接打包进工具里，用户什么都不用装。
"""

from __future__ import annotations

import os
import struct
import subprocess
import sys

from . import kg_deploy

CREATE_NO_WINDOW = 0x08000000


# ---------------------------------------------------------------- PE 扫描

def scan_pe(path):
    """返回 {'arch':32/64, 'imports':[...]}，失败返回 None。"""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
        if data[:2] != b"MZ":
            return None
        e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
        if data[e_lfanew:e_lfanew + 4] != b"PE\x00\x00":
            return None
        machine = struct.unpack_from("<H", data, e_lfanew + 4)[0]
        nsec = struct.unpack_from("<H", data, e_lfanew + 6)[0]
        opt_size = struct.unpack_from("<H", data, e_lfanew + 20)[0]
        opt = e_lfanew + 24
        magic = struct.unpack_from("<H", data, opt)[0]
        arch = 64 if magic == 0x20B else 32
        nrva = struct.unpack_from("<I", data, opt + 92)[0]
        imp_rva = struct.unpack_from("<I", data, opt + 96 + 8)[0]
        secs = []
        for i in range(nsec):
            o = opt + opt_size + 40 * i
            va, vsize, raw, rsize = struct.unpack_from("<IIII", data, o + 12)
            secs.append((va, vsize, raw, rsize))
        if not imp_rva:
            return {"arch": arch, "imports": []}

        def rva2off(rva):
            for va, vsize, raw, rsize in secs:
                if va <= rva < va + max(vsize, rsize):
                    return raw + (rva - va)
            return None

        imports = []
        off = rva2off(imp_rva)
        if off is None:
            return {"arch": arch, "imports": []}
        while True:
            ent = data[off:off + 20]
            if len(ent) < 20 or ent == b"\x00" * 20:
                break
            name_rva = struct.unpack_from("<I", ent, 12)[0]
            if name_rva:
                no = rva2off(name_rva)
                if no is not None:
                    end = data.index(b"\x00", no)
                    imports.append(data[no:end].decode("latin1"))
            off += 20
        return {"arch": arch, "imports": imports}
    except Exception:
        return None


def find_game_exe(game_dir, hint=None, exclude=("KaguyaEngine_Patch.exe",)):
    """找出游戏的主程序。优先挑导入了 WINMM.dll 的那个。"""
    if hint:
        p = hint if os.path.isabs(hint) else os.path.join(game_dir, hint)
        if os.path.exists(p):
            return p
    cands = []
    for fn in os.listdir(game_dir):
        if not fn.lower().endswith(".exe"):
            continue
        if fn in exclude:
            continue
        p = os.path.join(game_dir, fn)
        info = scan_pe(p)
        cands.append((fn, p, info, os.path.getsize(p)))
    if not cands:
        return None
    for fn, p, info, sz in cands:
        if info and any(n.lower() == "winmm.dll" for n in info["imports"]):
            return p
    cands.sort(key=lambda x: -x[3])
    return cands[0][1]


# ---------------------------------------------------------------- 路径处理

def is_ascii_path(path):
    try:
        path.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _stage_roots():
    roots = []
    pd = os.environ.get("ProgramData")
    if pd and is_ascii_path(pd):
        roots.append(os.path.join(pd, "KaguyaPatch"))
    la = os.environ.get("LOCALAPPDATA")
    if la and is_ascii_path(la):
        roots.append(os.path.join(la, "KaguyaPatch"))
    drive = os.path.splitdrive(os.path.abspath(os.sep))[0]
    if drive:
        roots.append(os.path.join(drive + os.sep, "KaguyaPatch"))
    return roots


def work_root(log=print):
    """挑一个纯英文、可写的工作目录。"""
    last = None
    for r in _stage_roots():
        try:
            os.makedirs(r, exist_ok=True)
            probe = os.path.join(r, ".w")
            with open(probe, "w") as fh:
                fh.write("1")
            os.remove(probe)
            return r
        except Exception as e:
            last = e
            continue
    raise OSError("找不到可用的纯英文工作目录：%s" % last)


def _junction_name(game_dir):
    import hashlib
    h = hashlib.md5(os.path.abspath(game_dir).lower().encode("utf-8"))
    return "game_" + h.hexdigest()[:10]


def ensure_junction(game_dir, log=print):
    """游戏路径含非 ASCII 时，在纯英文路径下建一个联接。返回可用于启动的路径。"""
    game_dir = os.path.abspath(game_dir)
    if is_ascii_path(game_dir):
        return game_dir
    root = work_root(log=log)
    link = os.path.join(root, _junction_name(game_dir))
    if os.path.isdir(link):
        try:
            if os.path.samefile(link, game_dir):
                return link
        except OSError:
            pass
        _remove_junction(link)
    os.makedirs(root, exist_ok=True)
    p = subprocess.run(["cmd", "/c", "mklink", "/J", link, game_dir.rstrip("\\/")],
                       capture_output=True, creationflags=CREATE_NO_WINDOW)
    if p.returncode != 0 or not os.path.isdir(link):
        msg = (p.stdout + p.stderr).decode("gbk", "replace").strip()
        raise OSError("建立目录联接失败：%s\n%s" % (link, msg))
    log("  已建立英文路径联接：%s -> %s" % (link, game_dir))
    return link


def _remove_junction(link):
    """只删联接本身，绝不动目标目录里的东西。"""
    if not os.path.isdir(link):
        return
    try:
        os.rmdir(link)
    except OSError:
        subprocess.run(["cmd", "/c", "rmdir", link],
                       capture_output=True, creationflags=CREATE_NO_WINDOW)


# ---------------------------------------------------------------- LE 启动

def stage_le(log=print):
    """把内置的 Locale Emulator 铺到纯英文路径，返回 LEProc.exe 路径。"""
    root = work_root(log=log)
    le = os.path.join(root, "le")
    os.makedirs(le, exist_ok=True)
    for fn in kg_deploy.LE_FILES:
        src = os.path.join(kg_deploy.LE_DIR, fn)
        if not os.path.exists(src):
            continue
        dst = os.path.join(le, fn)
        need = True
        if os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(src):
            with open(src, "rb") as f1, open(dst, "rb") as f2:
                need = f1.read() != f2.read()
        if need:
            import shutil
            shutil.copy2(src, dst)
    proc = os.path.join(le, "LEProc.exe")
    if not os.path.exists(proc):
        raise FileNotFoundError("内置的 Locale Emulator 缺失：%s" % proc)
    return proc


def launch(game_dir, exe_name=None, extra_args=(), wait=False, log=print,
           le_proc=None, use_le=True):
    """启动游戏。返回被启动进程的 Popen 对象（或 None）。"""
    game_dir = os.path.abspath(game_dir)
    launch_dir = ensure_junction(game_dir, log=log) if use_le else game_dir
    exe = find_game_exe(game_dir, hint=exe_name)
    if not exe:
        raise FileNotFoundError("在 %s 里找不到游戏主程序" % game_dir)
    target = os.path.join(launch_dir, os.path.basename(exe))

    if not use_le:
        log("  直接启动（未转区）")
        return subprocess.Popen([target, *extra_args], cwd=launch_dir)

    le = le_proc or stage_le(log=log)
    args = [le, "-runas", kg_deploy.LE_PROFILE_JA, target, *extra_args]
    log("  转区启动：%s" % os.path.basename(target))
    log("  %s" % " ".join('"%s"' % a if " " in a else a for a in args))
    p = subprocess.Popen(args, cwd=os.path.dirname(le),
                         creationflags=CREATE_NO_WINDOW)
    if wait:
        p.wait()
    return p


def cleanup(game_dir, log=print):
    """清掉为启动而建的东西（联接、临时 LE）。"""
    root = None
    try:
        root = work_root(log=lambda *a: None)
    except OSError:
        return
    link = os.path.join(root, _junction_name(game_dir))
    if os.path.isdir(link):
        _remove_junction(link)
        log("  已移除联接 %s" % link)
