# -*- coding: utf-8 -*-
"""槽位映射：把 cp932 编不出来的简体字，寄放到 cp932 里某个生僻汉字码位上。

原理（这也是现成汉化包的通行做法）：游戏全程按 cp932 处理字节，
所以文本里出现的每个字符必须能用 cp932 写出。简体字里有一大批
（总/觉/进/时/间/吗/红/观/别/对/请/说…）cp932 根本没有，写不进去。

做法是「借壳」：
  * 从 cp932 里挑一个生僻、且在正文里不会用到的汉字码位当「槽」；
  * 封包时把这个简体字写成该槽的 cp932 字节；
  * 同时把字体的 cmap 里该槽的码位指向这个简体字的字形。

游戏把字节按 cp932 解成槽字 → 去字体里取字形 → 拿到的是简体字字形。
"""

from __future__ import annotations

import unicodedata

PLAYER_CHAR = "\ue000"

_SKIP = {"\n", "\r", "\t", PLAYER_CHAR}

_POOL_CACHE = None


def is_encodable(ch, enc="cp932"):
    try:
        ch.encode(enc)
        return True
    except Exception:
        return False


def _is_ideograph(ch):
    try:
        n = unicodedata.name(ch)
    except ValueError:
        return False
    return ("CJK UNIFIED IDEOGRAPH" in n) or ("CJK COMPATIBILITY IDEOGRAPH" in n)


def all_cp932_ideographs():
    """cp932 里所有「汉字」字符（按码位顺序）。"""
    global _POOL_CACHE
    if _POOL_CACHE is not None:
        return _POOL_CACHE
    out = []
    for lead in range(0x81, 0xFD):
        for trail in list(range(0x40, 0x7F)) + list(range(0x80, 0xFD)):
            b = bytes((lead, trail))
            try:
                ch = b.decode("cp932")
            except Exception:
                continue
            if len(ch) != 1:
                continue
            if _is_ideograph(ch):
                out.append(ch)
    _POOL_CACHE = out
    return out


def build_pool(reserved):
    """可用于当槽的字符：cp932 汉字里，没有出现在正文中的那些。"""
    reserved = set(reserved)
    return [c for c in all_cp932_ideographs() if c not in reserved]


def need_slots(texts):
    """哪些字符需要槽位。"""
    need = set()
    for t in texts:
        for ch in t:
            if ch in _SKIP:
                continue
            if not is_encodable(ch):
                need.add(ch)
    return need


def make_table(texts, extra_reserved=(), max_slots=None):
    """根据最终正文算出 {简体字: 槽字} 映射表。

    参数 ``texts`` 是**最终**要写进 dat 的全部文本，
    ``extra_reserved`` 可追加额外要避开的字符（例如未翻译的原文）。
    """
    texts = list(texts)
    used = set()
    for t in texts:
        used.update(t)
    for r in extra_reserved:
        used.update(r)

    needed = need_slots(texts)
    pool = build_pool(used)
    if max_slots:
        pool = pool[:max_slots]
    if len(needed) > len(pool):
        raise ValueError("需要 %d 个槽位，但可用的只有 %d 个" % (len(needed), len(pool)))
    table = {}
    for ch, slot in zip(sorted(needed), pool):
        table[ch] = slot
    return table, pool[len(needed):]


def encode_text(text, table):
    """把一段文本编成 cp932 字节（需要槽位的字符走槽）。"""
    out = bytearray()
    for ch in text:
        if ch == PLAYER_CHAR:
            out += b"\xf0\x40"
            continue
        try:
            out += ch.encode("cp932")
            continue
        except Exception:
            pass
        slot = table.get(ch)
        if slot is None:
            out += "?".encode("cp932")
            continue
        out += slot.encode("cp932")
    return bytes(out)


def decode_text(raw, table, enc="cp932"):
    """反向：把 dat 里的字节解回「意图中的」文本（用于导出时对照）。"""
    rev = {v: k for k, v in table.items()}
    s = raw.decode(enc, "replace")
    return "".join(rev.get(ch, ch) for ch in s)


def table_to_lines(table):
    return ["%s\t%s" % (k, v) for k, v in sorted(table.items())]


def table_from_lines(lines):
    out = {}
    for ln in lines:
        ln = ln.rstrip("\r\n")
        if not ln or ln.startswith("#"):
            continue
        parts = ln.split("\t")
        if len(parts) >= 2 and parts[0]:
            out[parts[0]] = parts[1]
    return out
