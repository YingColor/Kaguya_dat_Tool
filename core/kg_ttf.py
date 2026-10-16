# -*- coding: utf-8 -*-
"""纯 Python 的 TrueType/OpenType 读写（只做我们需要的部分）。

用途：把一个已有的 CJK 字体读进来，替换 / 追加它的 cmap 映射、改字体名，
再原样写回。不依赖 fontTools。

支持：
  * sfnt 单字体（0x00010000 / OTTO / true）与 TTC 集合中取第 N 个字体
  * cmap format 0 / 4 / 6 / 12 的解析
  * cmap format 4 / 12 的生成（含 idDelta 优化与 idRangeOffset 回退）
  * name 表：整体重建，或只替换字体名而保留版权/许可记录
  * 表目录、校验和、head.checkSumAdjustment 的正规重算
"""

from __future__ import annotations

import struct

__all__ = ["Font", "build_cmap", "build_format4", "build_format12",
           "parse_cmap", "build_name", "rewrite_name", "name_ids", "read_name"]

# ---------------------------------------------------------------- 工具

def _u16(b, o):
    return struct.unpack_from(">H", b, o)[0]


def _i16(b, o):
    return struct.unpack_from(">h", b, o)[0]


def _u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def _pad4(n):
    return (n + 3) & ~3


# ---------------------------------------------------------------- Font

class Font:
    """一个 sfnt 字体。``tables`` 里 tag -> 原始表字节。"""

    def __init__(self, tables=None, order=None, sfnt_version=b"\x00\x01\x00\x00"):
        self.tables = dict(tables or {})
        self.order = list(order or self.tables.keys())
        self.sfnt_version = sfnt_version

    # ---------------------------------------------------- 读

    @classmethod
    def from_file(cls, path, index=0):
        with open(path, "rb") as fh:
            data = fh.read()
        return cls.from_bytes(data, index)

    @classmethod
    def from_bytes(cls, data, index=0):
        if data[:4] == b"ttcf":
            n = _u32(data, 8)
            if index >= n:
                raise ValueError("TTC 里只有 %d 个字体，取不到第 %d 个" % (n, index))
            base = _u32(data, 12 + 4 * index)
        else:
            if index:
                raise ValueError("这不是 TTC，没有第 %d 个字体" % index)
            base = 0
        tagged = data[base:base + 4]
        num = _u16(data, base + 4)
        tables = {}
        order = []
        for i in range(num):
            off = base + 12 + 16 * i
            tag = data[off:off + 4].decode("latin1")
            toff, tlen = struct.unpack_from(">II", data, off + 8)
            tables[tag] = data[toff:toff + tlen]
            order.append(tag)
        return cls(tables, order, tagged)

    @classmethod
    def ttc_font_count(cls, data):
        if data[:4] != b"ttcf":
            return 1
        return _u32(data, 8)

    # ---------------------------------------------------- 写

    def to_bytes(self):
        tags = [t for t in self.order if t in self.tables]
        tags = list(dict.fromkeys(tags))                     # 去重保序
        num = len(tags)
        # 先算 head 的校验和补偿
        out = bytearray()
        offset = 12 + 16 * num
        entries = []
        chunks = []
        for tag in tags:
            data = self.tables[tag]
            if tag == "head":
                data = bytearray(data)
                struct.pack_into(">I", data, 8, 0)           # 先清零再算
                data = bytes(data)
            off = offset
            entries.append([tag, _checksum(data), off, len(data)])
            chunks.append(data)
            offset += _pad4(len(data))
        total = 12 + 16 * num + sum(_pad4(len(c)) for c in chunks)
        # head.checkSumAdjustment
        body = bytearray(total)
        sfnt = self.sfnt_version
        search_range = 16 * (1 << (num.bit_length() - 1)) if num else 0
        entry_selector = (num.bit_length() - 1) if num else 0
        range_shift = num * 16 - search_range
        struct.pack_into(">4sHHHH", body, 0, sfnt, num, search_range,
                         entry_selector, range_shift)
        for i, (tag, cs, off, ln) in enumerate(entries):
            struct.pack_into(">4sIII", body, 12 + 16 * i,
                             tag.encode("latin1"), cs, off, ln)
        pos = 12 + 16 * num
        for (tag, cs, off, ln), chunk in zip(entries, chunks):
            body[off:off + len(chunk)] = chunk
            pos = off + _pad4(len(chunk))
        adj = (0xB1B0AFBA - _checksum(bytes(body))) & 0xFFFFFFFF
        if "head" in self.tables:
            head_off = entries[tags.index("head")][2]
            struct.pack_into(">I", body, head_off + 8, adj)
        return bytes(body)

    def save(self, path):
        data = self.to_bytes()
        with open(path, "wb") as fh:
            fh.write(data)
        return len(data)

    # ---------------------------------------------------- 便捷操作

    def cmap_map(self, unicode_only=True):
        """把所有 cmap 子表合并成 {码位: 字形号}。"""
        m = {}
        for item in parse_cmap(self.tables.get("cmap", b"")):
            if unicode_only and not item["unicode"]:
                continue
            m.update(item["map"])
        return m

    def set_names(self, family, subfamily="Regular", unique=None,
                  full=None, postscript=None, version="Version 1.00",
                  keep_original=True):
        """改字体名。

        ``keep_original=True``（默认）时走 ``rewrite_name``：**只在原 name 表
        上打补丁**，把 1/2/3/4/6（以及存在时的 16/17）换成新名字，
        其余记录（0 版权、7 商标、9 设计者、11 厂商网址、13/14 许可说明）
        **逐条原样保留**。

        这一点是有法律意义的：微软雅黑声明「Any other use is prohibited」，
        思源/Noto 是 SIL OFL —— OFL 明确要求分发（含修改后分发）时必须
        带着原始版权与许可声明。原来那个「整体重建 name 表」的做法会把它们
        统统抹掉，对开源字体反而是违规。
        """
        if keep_original and self.tables.get("name"):
            data = rewrite_name(self.tables["name"], family, subfamily,
                                unique or family, full or family,
                                postscript or _ps_name(family))
            if data:
                self.tables["name"] = data
                if "name" not in self.order:
                    self.order.append("name")
                return True
        self.tables["name"] = build_name(
            family, subfamily, unique or family, full or family,
            postscript or _ps_name(family), version)
        if "name" not in self.order:
            self.order.append("name")
        return False

    def rebuild_cmap(self, mapping, drop_symbol=True):
        """用 mapping 整体替换 cmap。"""
        self.tables["cmap"] = build_cmap(mapping, drop_symbol=drop_symbol)
        if "cmap" not in self.order:
            self.order.append("cmap")

    def get(self, tag):
        return self.tables.get(tag)

    def set_codepage_range(self, bits1=0, bits2=0):
        """在 OS/2 的 ulCodePageRange 里打开若干代码页位。

        **这一步是能不能显示中文的关键**：GDI 会按字体声明的代码页来过滤
        字号请求。日文游戏用 SHIFTJIS_CHARSET(128) 请求字体，如果字体没声明
        支持 932（日文），GDI 直接把它筛掉，退回系统日文字体，
        于是我们辛苦做的字形一个都用不上（显示成方框或别的字）。
        微软雅黑只声明了 936（简中），所以必须手动补上 932 这一位。
        """
        data = self.tables.get("OS/2")
        if not data or len(data) < 86:
            return False
        buf = bytearray(data)
        c1, c2 = struct.unpack_from(">II", buf, 78)
        struct.pack_into(">I", buf, 78, c1 | (bits1 & 0xFFFFFFFF))
        struct.pack_into(">I", buf, 82, c2 | (bits2 & 0xFFFFFFFF))
        self.tables["OS/2"] = bytes(buf)
        return True

    def codepage_range(self):
        data = self.tables.get("OS/2")
        if not data or len(data) < 86:
            return (0, 0)
        return struct.unpack_from(">II", data, 78)

    def __repr__(self):
        return "<Font %s tables=%d>" % (self.sfnt_version.hex(), len(self.tables))


def _checksum(data):
    d = bytes(data)
    if len(d) % 4:
        d += b"\x00" * (4 - len(d) % 4)
    s = 0
    for i in range(0, len(d), 4):
        s = (s + _u32(d, i)) & 0xFFFFFFFF
    return s


def _ps_name(family):
    out = []
    for ch in family:
        if ch.isalnum() or ch in "-_":
            out.append(ch)
        elif ch == " ":
            pass
    s = "".join(out) or "Font"
    return s[:62]


# ---------------------------------------------------------------- cmap 解析

def parse_cmap(data):
    """返回 [{pid, eid, fmt, map:{cp:gid}, unicode:bool}, ...]"""
    if not data:
        return []
    num = _u16(data, 2)
    out = []
    for i in range(num):
        pid, eid, so = struct.unpack_from(">HHI", data, 4 + 8 * i)
        if so + 4 > len(data):
            continue
        fmt = _u16(data, so)
        try:
            if fmt == 0:
                m = _f0(data, so)
            elif fmt == 4:
                m = _f4(data, so)
            elif fmt == 6:
                m = _f6(data, so)
            elif fmt == 12:
                m = _f12(data, so)
            else:
                continue
        except Exception:
            continue
        uni = (pid == 3 and eid in (1, 10)) or (pid == 0 and eid in (3, 4))
        out.append({"pid": pid, "eid": eid, "fmt": fmt, "map": m, "unicode": uni})
    return out


def _f0(data, off):
    m = {}
    for c in range(256):
        g = data[off + 6 + c]
        if g:
            m[c] = g
    return m


def _f4(data, off):
    length, lang, segx2 = struct.unpack_from(">HHH", data, off + 2)
    seg = segx2 // 2
    if seg == 0:
        return {}
    ends = [_u16(data, off + 14 + 2 * i) for i in range(seg)]
    starts = [_u16(data, off + 16 + segx2 + 2 * i) for i in range(seg)]
    deltas = [_i16(data, off + 16 + 2 * segx2 + 2 * i) for i in range(seg)]
    rob = off + 16 + 3 * segx2
    ros = [_u16(data, rob + 2 * i) for i in range(seg)]
    m = {}
    for i in range(seg):
        for c in range(starts[i], min(ends[i], 0xFFFE) + 1):
            if ros[i] == 0:
                g = (c + deltas[i]) & 0xFFFF
            else:
                gi = rob + 2 * i + ros[i] + 2 * (c - starts[i])
                if gi + 2 > len(data):
                    continue
                g = _u16(data, gi)
                if g:
                    g = (g + deltas[i]) & 0xFFFF
            if g:
                m[c] = g
    return m


def _f6(data, off):
    first, cnt = struct.unpack_from(">HH", data, off + 6)
    m = {}
    for i in range(cnt):
        g = _u16(data, off + 10 + 2 * i)
        if g:
            m[first + i] = g
    return m


def _f12(data, off):
    ng = _u32(data, off + 12)
    m = {}
    for i in range(ng):
        s, e, g = struct.unpack_from(">III", data, off + 16 + 12 * i)
        for k in range(s, e + 1):
            m[k] = g + (k - s)
    return m


# ---------------------------------------------------------------- cmap 生成

def build_format4(mapping, num_glyphs=None):
    """mapping: {BMP 码位: 字形号}（>0xFFFF 的会被忽略）"""
    items = sorted((c, g) for c, g in mapping.items()
                   if 0 <= c <= 0xFFFE and g)
    segments = []                      # [start, end, delta_or_None, [gids]]
    i = 0
    n = len(items)
    while i < n:
        start, gid = items[i]
        end = start
        delta = (gid - start) & 0xFFFF
        j = i + 1
        while j < n and items[j][0] == items[j - 1][0] + 1:
            if ((items[j][1] - items[j][0]) & 0xFFFF) != delta:
                break
            end = items[j][0]
            j += 1
        if j - i >= 2:
            segments.append((start, end, delta, None))
            i = j
            continue
        # 单点：往后吃连续码位，做成 idRangeOffset 段（更省空间）
        end = start
        gids = [gid]
        j = i + 1
        while j < n and items[j][0] == items[j - 1][0] + 1 and len(gids) < 8:
            gids.append(items[j][1])
            end = items[j][0]
            j += 1
        if len(gids) == 1:
            segments.append((start, end, delta, None))
        else:
            segments.append((start, end, None, gids))
        i = j
    # 终止段
    segments.append((0xFFFF, 0xFFFF, 1, None))

    seg = len(segments)
    glyph_count = sum(len(s[3]) for s in segments if s[3])
    length = 16 + 8 * seg + 2 * glyph_count
    if length > 0xFFFF:
        raise ValueError("format4 表过大 (%d 字节)，超出 65535 限制" % length)

    out = bytearray(length)
    struct.pack_into(">HHHHHHH", out, 0, 4, length, 0, seg * 2, 0, 0, 0)
    ends_o = 14
    starts_o = ends_o + seg * 2 + 2
    deltas_o = starts_o + seg * 2
    ros_o = deltas_o + seg * 2
    garr_o = ros_o + seg * 2
    k = 0
    for idx, (start, end, delta, gids) in enumerate(segments):
        struct.pack_into(">H", out, ends_o + 2 * idx, end)
        struct.pack_into(">H", out, starts_o + 2 * idx, start)
        if gids:
            struct.pack_into(">H", out, deltas_o + 2 * idx, 0)
            struct.pack_into(">H", out, ros_o + 2 * idx,
                             (seg - idx) * 2 + 2 * k)
            for g in gids:
                struct.pack_into(">H", out, garr_o + 2 * k, g)
                k += 1
        else:
            struct.pack_into(">H", out, deltas_o + 2 * idx, delta & 0xFFFF)
            struct.pack_into(">H", out, ros_o + 2 * idx, 0)
    return bytes(out)


def build_format12(mapping):
    """mapping: {码位: 字形号}，任意范围。"""
    items = sorted((c, g) for c, g in mapping.items() if g)
    groups = []
    for c, g in items:
        if groups and c == groups[-1][1] + 1 and g == groups[-1][2] + (c - groups[-1][0]):
            groups[-1][1] = c
        else:
            groups.append([c, c, g])
    length = 16 + 12 * len(groups)
    out = bytearray(length)
    struct.pack_into(">HHIII", out, 0, 12, 0, length, 0, len(groups))
    for i, (s, e, g) in enumerate(groups):
        struct.pack_into(">III", out, 16 + 12 * i, s, e, g)
    return bytes(out)


def build_cmap(mapping, drop_symbol=True):
    """生成一个完整 cmap 表：(0,3)f4 + (3,1)f4 + (0,4)f12 + (3,10)f12。

    format4 过大时自动省略 BMP 子表并只保留 format12。
    """
    bmp = {c: g for c, g in mapping.items() if c <= 0xFFFF}
    subs = []
    try:
        f4 = build_format4(bmp)
        subs.append((0, 3, f4))
        subs.append((3, 1, f4))
    except ValueError:
        f4 = None
    f12 = build_format12(mapping)
    subs.append((0, 4, f12))
    subs.append((3, 10, f12))
    num = len(subs)
    hdr = 4 + 8 * num
    out = bytearray(hdr)
    struct.pack_into(">HH", out, 0, 0, num)
    pos = hdr
    for i, (pid, eid, data) in enumerate(subs):
        struct.pack_into(">HHI", out, 4 + 8 * i, pid, eid, pos)
        out += data
        pos += len(data)
    return bytes(out)


# ---------------------------------------------------------------- name 表

# 换名字时要替换掉的 name ID。
# 1=字体族名 2=子族名 3=唯一标识 4=全名 6=PostScript 名
# 16/17=排版族名/子族名（有才换，中文 Windows 下 GDI 可能优先看这两个）
_REPLACE_IDS = (1, 2, 3, 4, 6, 16, 17)

# 新记录写成哪些语言。0x409=英文，0x804=简体中文。
# 中文系统上 GDI 会优先查 0x804，只写 0x409 的话中文系统可能仍匹配到旧名字。
_NEW_LANGS = (0x409, 0x804)


def rewrite_name(orig, family, subfamily="Regular", unique=None,
                 full=None, postscript=None):
    """在原始 name 表上打补丁，只换字体名，其余记录原样保留。

    做法：逐条复制原记录，丢掉要替换的 ID 和 format-1 的语言标签记录
    （输出一律是 format 0），再把新名字按 0x409 / 0x804 追加进去。
    """
    if not orig or len(orig) < 6:
        return None
    count, str_off = struct.unpack_from(">HH", orig, 2)

    values = {
        1: family,
        2: subfamily,
        3: unique or family,
        4: full or family,
        6: postscript or _ps_name(family),
        16: family,
        17: subfamily,
    }

    present = set()
    kept = []
    seen = set()
    for i in range(count):
        o = 6 + 12 * i
        if o + 12 > len(orig):
            break
        pid, eid, lid, nid, ln, off = struct.unpack_from(">HHHHHH", orig, o)
        present.add(nid)
        if lid >= 0x8000:            # format 1 的 langTag 引用，我们不输出
            continue
        end = str_off + off + ln
        if end > len(orig):
            continue
        key = (pid, eid, lid, nid)
        if key in seen:
            continue
        seen.add(key)
        kept.append((pid, eid, lid, nid, orig[str_off + off:end]))

    # 只替换真正存在的 ID：1/2/4/6 保证有，16/17 有才补
    patch = {}
    for nid, val in values.items():
        if nid in (16, 17) and nid not in present:
            continue
        if nid in (1, 2, 3, 4, 6) or nid in present:
            patch[nid] = val
    if not patch:
        return None

    # 去掉旧记录里所有要替换的（含我们已经删掉语言的），再追加新的
    kept = [r for r in kept if r[3] not in patch]
    for nid in sorted(patch):
        raw = patch[nid].encode("utf-16-be")
        for lid in _NEW_LANGS:
            kept.append((3, 1, lid, nid, raw))

    kept.sort(key=lambda r: (r[0], r[1], r[2], r[3]))

    storage = bytearray()
    records = []
    for pid, eid, lid, nid, raw in kept:
        records.append((pid, eid, lid, nid, len(raw), len(storage)))
        storage += raw

    n = len(records)
    if not n:
        return None
    str_off = 6 + 12 * n
    out = bytearray(str_off + len(storage))
    struct.pack_into(">HHH", out, 0, 0, n, str_off)
    for i, (pid, eid, lid, nid, ln, off) in enumerate(records):
        struct.pack_into(">HHHHHH", out, 6 + 12 * i, pid, eid, lid, nid, ln, off)
    out[str_off:] = storage
    return bytes(out)


def name_ids(data):
    """name 表里出现过哪些 ID（测试/自检用）。"""
    if not data or len(data) < 6:
        return set()
    count = struct.unpack_from(">H", data, 2)[0]
    out = set()
    for i in range(count):
        o = 6 + 12 * i
        if o + 12 > len(data):
            break
        out.add(struct.unpack_from(">H", data, o + 6)[0])
    return out


def build_name(family, subfamily="Regular", unique=None, full=None,
               postscript=None, version="Version 1.00"):
    """重建 name 表。只写 Windows Unicode (3,1,0x409) 记录。"""
    pairs = [
        (0, "Copyright (c) KaguyaPatch"),
        (1, family),
        (2, subfamily),
        (3, unique or family),
        (4, full or family),
        (5, version),
        (6, postscript or _ps_name(family)),
    ]
    records = []
    storage = bytearray()
    for nid, text in pairs:
        raw = text.encode("utf-16-be")
        records.append((nid, len(storage), len(raw)))
        storage += raw
    count = len(records)
    str_off = 6 + 12 * count
    out = bytearray(str_off + len(storage))
    struct.pack_into(">HHH", out, 0, 0, count, str_off)
    for i, (nid, off, ln) in enumerate(records):
        struct.pack_into(">HHHHHH", out, 6 + 12 * i, 3, 1, 0x409, nid, ln, off)
    out[str_off:] = storage
    return bytes(out)


def read_name(data, nid=1):
    if not data:
        return None
    count, so = struct.unpack_from(">HH", data, 2)
    for i in range(count):
        pid, eid, lid, n, ln, off = struct.unpack_from(">HHHHHH", data, 6 + 12 * i)
        if n != nid:
            continue
        raw = data[so + off:so + off + ln]
        try:
            if pid == 3:
                return raw.decode("utf-16-be")
            if pid == 1 and eid == 0:
                return raw.decode("mac-roman")
        except Exception:
            pass
    return None
