# -*- coding: utf-8 -*-
"""用系统字体现做一份「能显示简体中文」的游戏字体。

做法：拿一个覆盖简体中文的字体当底座，把「槽码位」在 cmap 里指向
目标汉字的字形。底座字体本身不动，只重写 cmap + 改字体名。
因为是在用户自己机器上用他自带的字体生成，所以不需要附带任何字体文件。

**关于版权**：工具本身不带字体，但生成出来的 KaguyaPatchCN.ttf 会被放进
汉化包分发，里面装的正是底座字体的字形数据 —— 这是整条链上唯一把字体
版权带出去的环节。底座的版权/许可声明会**原样保留**（见 kg_ttf.rewrite_name），
所以要用它对外发布，底座请换成允许再分发的开源字体（思源/Noto，SIL OFL）。
"""

from __future__ import annotations

import os
import struct
import sys

from .kg_ttf import Font, name_ids, read_name

# (显示名, 路径, TTC 里的第几个, 能不能自动挑)
# 最后一个字段为 False 的（默认字重极细的可变字体）只在用户手动指定时使用。
CANDIDATES = [
    ("微软雅黑", r"C:\Windows\Fonts\msyh.ttc", 0, True),
    ("等线", r"C:\Windows\Fonts\Deng.ttf", 0, True),
    ("黑体", r"C:\Windows\Fonts\simhei.ttf", 0, True),
    ("宋体", r"C:\Windows\Fonts\simsun.ttc", 0, True),
    ("微软正黑", r"C:\Windows\Fonts\msjh.ttc", 0, True),
    ("Noto Sans SC（系统自带）",
     r"C:\Windows\Fonts\NotoSansSC-VF.ttf", 0, False),
    ("Noto Sans JP（系统自带）",
     r"C:\Windows\Fonts\NotoSansJP-VF.ttf", 0, False),
]

DEFAULT_FAMILY = "KaguyaPatchCN"

# OS/2 ulCodePageRange1 里要打开的代码页位。
# 17 = 932 日文（必须！日文游戏按 SHIFTJIS_CHARSET 请求字体，
#            字体不声明 932 就会被 GDI 筛掉，中文一个也显示不出来）
# 18 = 936 简体中文, 19 = 949 韩文, 20 = 950 繁体中文, 0 = 1252 西文
CODEPAGE_BITS1 = (1 << 0) | (1 << 17) | (1 << 18) | (1 << 19) | (1 << 20)

# 字重低于这个值的可变字体，显示出来细得不像话，不自动选
_THIN_WEIGHT = 300


def app_dir():
    """程序所在的目录（打包成 exe 后就是 exe 所在目录，不是解包临时目录）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def font_dirs():
    """放「自备字体」的目录（用户下载的开源字体丢这儿就能被认出来）。

    对外发布汉化包时建议把底换成思源/Noto 这类 OFL 字体 —— 下载静态版
    （文件名带 Regular 的那个，不要 VF/可变字体）放进 fonts/ 即可。
    """
    base = app_dir()
    cands = [os.path.join(base, "fonts"), os.path.join(base, "字体")]
    if not getattr(sys, "frozen", False):
        # 源码运行时也认一下当前目录，方便脚本调用
        cands.append(os.path.join(os.getcwd(), "fonts"))
    out = []
    seen = set()
    for d in cands:
        k = os.path.normcase(os.path.abspath(d))
        if k in seen:
            continue
        seen.add(k)
        out.append(d)
    return out


def _fvar_default_weight(fvar):
    """从 fvar 表里读出 wght 轴的默认值（不是可变字体返回 None）。"""
    if not fvar or len(fvar) < 16:
        return None
    try:
        _maj, _min, axoff, _res, axn, axsize = struct.unpack_from(">HHHHHH", fvar, 0)
    except Exception:
        return None
    for i in range(axn):
        o = axoff + i * axsize
        if o + 20 > len(fvar):
            break
        if fvar[o:o + 4] == b"wght":
            dv = struct.unpack_from(">i", fvar, o + 8)[0]
            return dv / 65536.0
    return None


def font_traits(path, index=0):
    """底座体检：是不是可变字体、默认字重、覆盖多少字。"""
    try:
        f = Font.from_file(path, index)
    except Exception:
        return None
    info = {
        "path": path,
        "index": index,
        "variable": "fvar" in f.tables,
        "weight": None,
        "cmap": len(f.cmap_map()),
        "license": read_name(f.get("name"), 13),
        "copyright": read_name(f.get("name"), 0),
    }
    if info["variable"]:
        info["weight"] = _fvar_default_weight(f.tables.get("fvar"))
    info["thin"] = bool(info["variable"] and info["weight"] is not None
                        and info["weight"] < _THIN_WEIGHT)
    return info


def _scan_dir(d):
    out = []
    if not d or not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if fn.lower().endswith((".ttf", ".ttc", ".otf")):
            out.append((fn, os.path.join(d, fn), 0, True))
    return out


FONTS_README = """把下载的中文字体（.ttf / .ttc / .otf）放进这个文件夹，
重新打开 KaguyaPatch，它就会出现在「底座字体」下拉框里。
（不放任何字体也能正常用，默认用系统自带的微软雅黑。）

【底座是什么】
做汉化要造一个游戏能用的中文字体：找一份现成的中文字体，把里面的中文字形
搬过来。那份被搬的字体就叫「底座」，它长什么样，游戏里的中文就长什么样。

【为什么要挑字体】
工具自己不附带字体，做出来的 KaguyaPatchCN.ttf 会跟着汉化包发给别人，
里面装的正是底座的字形数据。
  * 只自己玩、小圈子传  -> 用系统自带的微软雅黑就行，效果最好。
  * 要公开发给别人      -> 请换成开源字体（见下）。

微软雅黑 / 等线 / 黑体 / 宋体 是微软、方正的商业字体，许可条款不允许这样
再分发。思源黑体 / Noto Sans CJK 是 SIL OFL 1.1 许可，明确允许修改和再分发，
本工具生成字体时会原样保留底座的版权与许可声明。

【推荐放什么】
搜「Noto Sans SC Regular ttf 下载」或「思源黑体 下载」，取静态版：
  * Noto Sans SC      -> NotoSansSC-Regular.ttf
  * Adobe 思源黑体     -> SourceHanSansSC-Regular.otf

注意：不要下 Variable / VF 版本。系统自带的 NotoSansSC-VF.ttf 是可变字体，
默认那一档是最细的 Thin，拿来当底座游戏里的字会细得像没上墨。

【要求】
  * 扩展名 .ttf / .ttc / .otf
  * 覆盖简体中文常用字，越全越好
  * 单个文件即可，不需要装进系统
"""


def ensure_font_dir():
    """确保 fonts 目录存在，并放一份说明进去（只在缺失时写）。"""
    d = font_dirs()[0]
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        return None
    note = os.path.join(d, "说明.txt")
    if not os.path.exists(note):
        try:
            with open(note, "w", encoding="utf-8") as fh:
                fh.write(FONTS_README)
        except Exception:
            pass
    return d


def list_base_fonts(extra_dirs=()):
    """可选底座：[(显示名, 路径, TTC 序号)]。

    系统字体之外，还会扫 ``fonts/`` 里用户自己放的开源字体。
    """
    items = []
    for it in CANDIDATES:
        if os.path.exists(it[1]):
            items.append(it)
    for d in list(extra_dirs) + font_dirs():
        items += _scan_dir(d)

    out = []
    seen = set()
    for name, path, idx, _auto in items:
        k = os.path.normcase(os.path.abspath(path))
        if k in seen:
            continue
        seen.add(k)
        out.append((name, path, idx))
    return out


def base_font_menu(extra_dirs=()):
    """给界面用：[(下拉框里显示的文字, (显示名, 路径, 序号))]，细的会标出来。"""
    menu = []
    for name, path, idx in list_base_fonts(extra_dirs):
        label = name
        try:
            t = font_traits(path, idx)
        except Exception:
            t = None
        if t:
            if t["thin"]:
                label = "%s　［字重偏细，别选］" % name
            elif t["cmap"] < 15000:
                label = "%s　［中文字覆盖偏少］" % name
        menu.append((label, (name, path, idx)))
    return menu


def pick_base_font(preferred=None):
    fonts = list_base_fonts()
    if not fonts:
        raise FileNotFoundError("系统里找不到可用的中文字体")
    if preferred:
        for name, path, idx in fonts:
            if preferred in (name, path) or os.path.basename(path).lower() == preferred.lower():
                return (name, path, idx)
    for name, path, idx in fonts:
        try:
            f = Font.from_file(path, idx)
            if len(f.cmap_map()) <= 15000:
                continue
        except Exception:
            continue
        t = font_traits(path, idx)
        if t and t["thin"]:
            continue                      # 默认字重太细，别自动挑它
        return (name, path, idx)
    return fonts[0]


def coverage(path, index=0):
    f = Font.from_file(path, index)
    return f.cmap_map()


def build_font(slot_table, out_path, base=None, family=DEFAULT_FAMILY,
               log=print, extra_keep=()):
    """按槽位表生成字体。

    ``slot_table``: {需要显示的字符: 槽字符}
    返回统计字典。
    """
    if base is None:
        base = pick_base_font()
    name, path, idx = base
    log("底座字体：%s (%s)" % (name, path))
    f = Font.from_file(path, idx)
    cmap = f.cmap_map()
    orig_name = read_name(f.get("name"), 1)

    traits = font_traits(path, idx) or {}
    if traits.get("thin"):
        log("  ⚠ 这底座是可变字体，默认字重 %s（最细一档），显示会明显偏细。"
            % (("%g" % traits["weight"]) if traits.get("weight") else "很低"))
        log("    换成静态版开源字体（文件名带 Regular、不要 VF）会正常。")

    keep_ids = name_ids(f.get("name"))
    orig_license = read_name(f.get("name"), 13)
    orig_copyright = read_name(f.get("name"), 0)

    missing = []
    added = 0
    for need, slot in sorted(slot_table.items()):
        g = cmap.get(ord(need))
        if g is None:
            missing.append(need)
            continue
        if cmap.get(ord(slot)) != g:
            cmap[ord(slot)] = g
            added += 1

    keep_missing = [c for c in extra_keep if ord(c) not in cmap]

    f.rebuild_cmap(cmap)
    kept_name = f.set_names(family)
    if kept_name:
        kept = sorted(n for n in (0, 7, 9, 11, 13, 14) if n in keep_ids)
        if kept:
            log("  底座的版权/许可记录已原样保留（name ID %s）"
                % "/".join(str(n) for n in kept))
    new_ids = name_ids(f.get("name"))
    old_cp = f.codepage_range()
    f.set_codepage_range(CODEPAGE_BITS1, 0)
    new_cp = f.codepage_range()
    if old_cp != new_cp:
        log("  代码页声明：0x%08X -> 0x%08X（补上日文 932，"
            "否则日文游戏会直接不用这个字体）" % (old_cp[0], new_cp[0]))

    d = os.path.dirname(os.path.abspath(out_path))
    if d:
        os.makedirs(d, exist_ok=True)
    size = f.save(out_path)
    log("字体已生成：%s（%s -> %s，改了 %d 个码位，%.1f MB）"
        % (out_path, orig_name, family, added, size / 1048576.0))
    if missing:
        log("  ⚠ 底座字体里没有这些字：%s" % "".join(missing[:60]))
    if keep_missing:
        log("  ⚠ 原文里这些字底座字体也没有：%s" % "".join(keep_missing[:60]))

    return {
        "base_name": name,
        "base_path": path,
        "source_family": orig_name,
        "family": family,
        "patched": added,
        "missing": missing,
        "keep_missing": keep_missing,
        "size": size,
        "name_patched": bool(kept_name),
        "kept_name_ids": sorted(n for n in (0, 7, 9, 11, 13, 14) if n in new_ids),
        "base_license": orig_license,
        "base_copyright": orig_copyright,
        "variable": bool(traits.get("variable")),
        "base_weight": traits.get("weight"),
    }
