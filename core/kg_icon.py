# -*- coding: utf-8 -*-
"""给 exe 换图标（直接改 PE 里的图标资源）。

纯 ctypes 调用 Windows 自带的 kernel32，**不需要编译器、不需要任何第三方工具**。

能做的三件事：
  1. 从某个 exe（例如游戏的 Start.exe）里把图标抠出来；
  2. 把图标（来自 exe，或来自 .ico / png / jpg 文件）写进另一个 exe；
  3. 把某个 exe 的主图标导成独立 .ico（调试/预览用）。

对外的「来源」就三种，对应界面上的三选一：

    游戏图标   set_exe_icon(dst, game_exe="...\\Start.exe")
    自定义图标 set_exe_icon(dst, image_file="...\\my.ico" 或 my.png)
    不带图标   set_exe_icon(dst)              # 什么都不做，保持 dst 自带图标
"""

from __future__ import annotations

import os
import struct
import sys

RT_ICON = 3
RT_GROUP_ICON = 14
_RT_ICON, _RT_GROUP_ICON = RT_ICON, RT_GROUP_ICON

# 生成多尺寸图标时用的尺寸（Pillow 支持到 256）
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]

__all__ = [
    "set_exe_icon", "apply_icon_resources", "read_icon_resources",
    "main_icon_resources_from_exe", "resources_from_image",
    "resources_from_ico_bytes", "extract_main_icon", "pillow_available",
    "IconError", "RT_ICON", "RT_GROUP_ICON", "ICO_SIZES",
]


class IconError(Exception):
    """换图标过程中的可预期错误（会原样显示给用户）。"""


# ---------------------------------------------------------------- kernel32

_k32 = None


def _load_k32():
    global _k32
    if _k32 is not None:
        return _k32
    if sys.platform != "win32":
        raise IconError("换图标只能在 Windows 上做。")
    import ctypes
    from ctypes import wintypes

    k = ctypes.WinDLL("kernel32", use_last_error=True)

    k.LoadLibraryExW.restype = ctypes.c_void_p
    k.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, wintypes.DWORD]
    k.FreeLibrary.restype = wintypes.BOOL
    k.FreeLibrary.argtypes = [ctypes.c_void_p]
    k.FindResourceW.restype = ctypes.c_void_p
    k.FindResourceW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    k.SizeofResource.restype = wintypes.DWORD
    k.SizeofResource.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    k.LoadResource.restype = ctypes.c_void_p
    k.LoadResource.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    k.LockResource.restype = ctypes.c_void_p
    k.LockResource.argtypes = [ctypes.c_void_p]

    k.BeginUpdateResourceW.restype = ctypes.c_void_p
    k.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
    k.UpdateResourceW.restype = wintypes.BOOL
    k.UpdateResourceW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                  wintypes.WORD, ctypes.c_void_p, wintypes.DWORD]
    k.EndUpdateResourceW.restype = wintypes.BOOL
    k.EndUpdateResourceW.argtypes = [ctypes.c_void_p, wintypes.BOOL]

    k._ENUM = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p,
                                 ctypes.c_void_p, ctypes.c_void_p)
    k.EnumResourceNamesW.restype = ctypes.c_bool
    k.EnumResourceNamesW.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                     k._ENUM, ctypes.c_void_p]
    _k32 = k
    return k


def _res_name(lp):
    """资源名：低位是整数 ID 就返回 int，否则返回字符串。"""
    import ctypes
    v = ctypes.cast(lp, ctypes.c_void_p).value
    if v is None:
        return None
    if v < 0x10000:
        return v
    return ctypes.cast(lp, ctypes.c_wchar_p).value


def _res_ptr(x):
    """把 int（MAKEINTRESOURCE）或 str 转成 API 要的 LPCWSTR 指针。"""
    import ctypes
    if isinstance(x, int):
        return ctypes.c_void_p(x)
    return ctypes.cast(ctypes.c_wchar_p(x), ctypes.c_void_p)


# ---------------------------------------------------------------- 读 exe 图标

def read_icon_resources(exe):
    """读 exe 里的图标资源，返回 {RT_ICON:{id:bytes}, RT_GROUP_ICON:{id:bytes}}。"""
    k = _load_k32()
    import ctypes
    LOAD_LIBRARY_AS_DATAFILE = 0x2
    LOAD_LIBRARY_AS_IMAGE_RESOURCE = 0x20
    h = k.LoadLibraryExW(exe, None,
                         LOAD_LIBRARY_AS_DATAFILE | LOAD_LIBRARY_AS_IMAGE_RESOURCE)
    if not h:
        raise IconError("打不开 exe：%s" % exe)
    out = {RT_ICON: {}, RT_GROUP_ICON: {}}

    def cb(hMod, lpType, lpName, lpParam):
        t = _res_name(lpType)
        if t in out:
            hr = k.FindResourceW(hMod, lpName, lpType)
            if hr:
                sz = k.SizeofResource(hMod, hr)
                p = k.LockResource(k.LoadResource(hMod, hr))
                out[t][_res_name(lpName)] = ctypes.string_at(p, sz)
        return True

    try:
        enum = k._ENUM(cb)
        for rt in (RT_ICON, RT_GROUP_ICON):
            k.EnumResourceNamesW(h, _res_ptr(rt), enum, None)
    finally:
        k.FreeLibrary(h)
    return out


def _normalize_group1(res):
    """把主组（id 最小）重映射成 组 id=1、图标 id=1..N，保证 shell 认它是主图标。"""
    groups = res.get(RT_GROUP_ICON) or {}
    if not groups:
        return None
    gid = min(groups)                       # Windows 认 id 最小的组为主图标
    gdata = groups[gid]
    if len(gdata) < 6:
        return None
    _rsv, _typ, count = struct.unpack_from("<HHH", gdata, 0)
    new_group = bytearray(struct.pack("<HHH", 0, 1, count))
    new_icons = {}
    for i in range(count):
        off = 6 + i * 14
        if off + 14 > len(gdata):
            break
        bw, bh, bcc, brsv, planes, bitcnt, nbytes, nid = \
            struct.unpack_from("<BBBBHHIH", gdata, off)
        new_id = i + 1
        new_group += struct.pack("<BBBBHHIH", bw, bh, bcc, brsv, planes,
                                 bitcnt, nbytes, new_id)
        blob = res[RT_ICON].get(nid)
        if blob:
            new_icons[new_id] = blob
    if not new_icons:
        return None
    return {RT_ICON: new_icons, RT_GROUP_ICON: {1: bytes(new_group)}}


def main_icon_resources_from_exe(exe):
    """从 exe 抽出主图标并规范化。exe 没有图标时返回 None。"""
    if not os.path.isfile(exe):
        raise IconError("找不到文件：%s" % exe)
    res = read_icon_resources(exe)
    return _normalize_group1(res)


# ---------------------------------------------------------------- 从 .ico / 图片

def resources_from_ico_bytes(data):
    """解析一个 .ico 的字节，转成资源字典（组 id=1、图标 id=1..N）。"""
    data = bytes(data)
    if len(data) < 6:
        raise IconError("不是有效的 .ico 文件（太小）")
    reserved, itype, count = struct.unpack_from("<HHH", data, 0)
    if reserved != 0 or itype != 1 or count <= 0:
        raise IconError("不是有效的 .ico 文件（文件头不对）")
    icons = {}
    group = bytearray(struct.pack("<HHH", 0, 1, count))
    for i in range(count):
        off = 6 + i * 16
        if off + 16 > len(data):
            raise IconError("不是有效的 .ico 文件（目录项越界）")
        bw, bh, bcc, brsv, planes, bitcnt, nbytes, imgoff = \
            struct.unpack_from("<BBBBHHII", data, off)
        blob = data[imgoff:imgoff + nbytes]
        if len(blob) != nbytes:
            raise IconError("不是有效的 .ico 文件（图像数据不完整）")
        nid = i + 1
        icons[nid] = blob
        group += struct.pack("<BBBBHHIH", bw, bh, bcc, brsv, planes, bitcnt,
                             nbytes, nid)
    if not icons:
        raise IconError("这个 .ico 里没有图像")
    return {RT_ICON: icons, RT_GROUP_ICON: {1: bytes(group)}}


def _pil_module():
    """延迟、隐蔽地拿到 PIL.Image。

    这里刻意用 `__import__` + 运行时拼出来的模块名。只要写成
    `from PIL import Image`，PyInstaller 的静态分析就会把 7 MB 的 Pillow
    （还会顺带把 tkinter 一起拉进来）塞进**每一个** exe ——
    包括根本用不到它的游戏启动器（体积直接翻倍）。
    """
    return __import__("PIL" + ".Image", fromlist=["Image"])


def pillow_available():
    try:
        _pil_module()
        return True
    except Exception:
        return False


def resources_from_image(path):
    """从文件取图标资源：.ico 直接读；其它图片用 Pillow 转成多尺寸 ico。"""
    if not os.path.isfile(path):
        raise IconError("找不到图片文件：%s" % path)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".ico":
        with open(path, "rb") as fh:
            return resources_from_ico_bytes(fh.read())
    try:
        Image = _pil_module()
    except Exception as e:
        raise IconError(
            "把 %s 这种图片转成图标需要 Pillow（打包好的 exe 里已内置；\n"
            "从源码跑的话请 pip install pillow）。\n"
            "也可以直接提供 .ico 文件。\n（%s）" % (ext or "该", e))
    import io
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    side = max(w, h)
    if (w, h) != (side, side):          # 补成正方形，别把图拉变形
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(im, ((side - w) // 2, (side - h) // 2))
        im = canvas
    sizes = [s for s in ICO_SIZES if s <= side]
    if not sizes:
        sizes = [max(1, min(ICO_SIZES, key=lambda s: abs(s - side)))]
    buf = io.BytesIO()
    im.save(buf, format="ICO", sizes=[(s, s) for s in sizes])
    return resources_from_ico_bytes(buf.getvalue())


# ---------------------------------------------------------------- 写进 exe

def _pe_image_end(data):
    """算出 PE 映像本体在文件里到哪儿结束（最后一节的原始数据末尾）。

    PE 映像之后的字节属于「附加数据（overlay）」：PyInstaller 单文件 exe 的
    PKG 归档、数字签名等都挂在这里，不属于 PE 结构。
    """
    if len(data) < 0x40 or data[:2] != b"MZ":
        return 0
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if e_lfanew + 24 > len(data) or data[e_lfanew:e_lfanew + 4] != b"PE\0\0":
        return 0
    coff = e_lfanew + 4
    nsec = struct.unpack_from("<H", data, coff + 2)[0]
    opt_size = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    if opt + 64 > len(data):
        return 0
    end = struct.unpack_from("<I", data, opt + 60)[0]      # SizeOfHeaders
    sec = opt + opt_size
    for i in range(nsec):
        off = sec + i * 40
        if off + 40 > len(data):
            break
        rsd = struct.unpack_from("<I", data, off + 16)[0]  # SizeOfRawData
        prd = struct.unpack_from("<I", data, off + 20)[0]  # PointerToRawData
        if rsd and prd:
            end = max(end, prd + rsd)
    return end


def _read_overlay(target):
    """读出 target 的附加数据（PE 映像之后的部分）。没有就返回 b""。"""
    with open(target, "rb") as fh:
        data = fh.read()
    end = _pe_image_end(data)
    if 0 < end < len(data):
        return data[end:]
    return b""


def _restore_overlay(target, overlay):
    """EndUpdateResource 之后把附加数据补回去。

    系统 API 只重写 PE 映像本体，映像后面的字节会被整段丢掉 ——
    PyInstaller 单文件 exe 的 PKG 归档正好在那里，不补回去 exe 就跑不起来。
    """
    if not overlay:
        return
    with open(target, "rb") as fh:
        new = fh.read()
    end = _pe_image_end(new)
    if 0 < end <= len(new):
        new = new[:end]
    with open(target, "wb") as fh:
        fh.write(new + overlay)


def apply_icon_resources(target, res):
    """把 res 里的图标资源写进 target exe（先清掉 target 原有的全部图标资源）。"""
    if not res or not res.get(RT_GROUP_ICON):
        raise IconError("没有可用的图标数据")
    if not os.path.isfile(target):
        raise IconError("目标文件不存在：%s" % target)
    k = _load_k32()
    import ctypes

    overlay = _read_overlay(target)     # 写完要原样补回去，先留一份

    h = k.BeginUpdateResourceW(target, False)
    if not h:
        raise IconError("打不开目标文件（可能正在运行？）：%s" % target)

    def upd(rt, name, data):
        if data is None:
            ok = k.UpdateResourceW(h, _res_ptr(rt), _res_ptr(name), 0, None, 0)
        else:
            buf = ctypes.create_string_buffer(data, len(data))
            ok = k.UpdateResourceW(h, _res_ptr(rt), _res_ptr(name), 0,
                                   ctypes.cast(buf, ctypes.c_void_p), len(data))
        if not ok:
            raise IconError("写入图标资源失败（rt=%r id=%r）" % (rt, name))

    try:
        old = read_icon_resources(target)
        for rt in (RT_ICON, RT_GROUP_ICON):        # 先删旧的
            for name in list(old[rt]):
                upd(rt, name, None)
        for rt in (RT_ICON, RT_GROUP_ICON):        # 再写新的
            for name, data in res[rt].items():
                upd(rt, name, data)
    except Exception:
        k.EndUpdateResourceW(h, True)              # 出错就丢弃改动
        raise
    if not k.EndUpdateResourceW(h, False):
        raise IconError("保存图标失败：%s" % target)
    _restore_overlay(target, overlay)
    return True


def set_exe_icon(target, *, game_exe=None, image_file=None):
    """给 target 换图标。

    game_exe   给游戏主程序路径 → 用它里面的图标（界面的「使用游戏图标」）
    image_file 给图片/ico 路径  → 用它（界面的「自定义图标」）
    两个都不给                   → 什么都不做（界面的「不带图标」），返回 False
    """
    if image_file:
        res = resources_from_image(image_file)
    elif game_exe:
        res = main_icon_resources_from_exe(game_exe)
        if not res:
            raise IconError("这个文件里没有图标：\n%s" % game_exe)
    else:
        return False
    apply_icon_resources(target, res)
    return True


def extract_main_icon(exe, out_ico):
    """把 exe 的主图标导成独立 .ico 文件（调试/预览用）。"""
    res = main_icon_resources_from_exe(exe)
    if not res:
        raise IconError("这个文件里没有图标：%s" % exe)
    group = res[RT_GROUP_ICON][1]
    _rsv, _typ, count = struct.unpack_from("<HHH", group, 0)
    entries = []
    for i in range(count):
        off = 6 + i * 14
        bw, bh, bcc, brsv, planes, bitcnt, nbytes, nid = \
            struct.unpack_from("<BBBBHHIH", group, off)
        entries.append((bw, bh, bcc, brsv, planes, bitcnt, nbytes, nid))
    out = bytearray(struct.pack("<HHH", 0, 1, count))
    data_off = 6 + count * 16
    blobs = []
    for (bw, bh, bcc, brsv, planes, bitcnt, nbytes, nid) in entries:
        blob = res[RT_ICON].get(nid, b"")
        out += struct.pack("<BBBBHHII", bw, bh, bcc, brsv, planes, bitcnt,
                           len(blob), data_off)
        blobs.append(blob)
        data_off += len(blob)
    for blob in blobs:
        out += blob
    with open(out_ico, "wb") as fh:
        fh.write(out)
    return out_ico
