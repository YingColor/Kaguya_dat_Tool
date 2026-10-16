# -*- coding: utf-8 -*-
"""Kaguya 引擎 ``[SCR-MESSAGE]`` 文本包的解析与写出。

文件结构::

    [SCR-MESSAGE]  13 字节
    ver4.0          6 字节
    encrypted       1 字节
    xorkey          1 字节
    names   : int32 条数 + [int16 长度 + 字节] × N
    choices : int32 条数 + [int16 长度 + 字节] × N
    msgs    : int32 条数 + [int32 条目长 + 条目] × N
              条目 = int32 文本长 + 文本 + 语音数据(该条目剩余全部字节)
    cmds    : 之后的全部字节（命令表 + 尾部数据），原样保留、不加密

``encrypted != 0`` 时只有 names/choices/msgs 的载荷字节按 xorkey 异或，
长度字段与 cmds 之后的数据不参与。
"""

from __future__ import annotations

import struct

SIG = b"[SCR-MESSAGE]"
SIG_LEN = 13
VER_LEN = 6
HDR = SIG_LEN + VER_LEN + 2          # 21

PLAYER_CHAR = "\ue000"               # 引擎的玩家名变量
PLAYER_BYTES = b"\xf0\x40"

DEFAULT_ENCODING = "cp932"

__all__ = ["DatFile", "parse_bytes", "parse_file", "PLAYER_CHAR", "PLAYER_BYTES"]


def _xor(data, key):
    if not key:
        return bytes(data)
    return bytes(b ^ key for b in data)


class DatFile:
    def __init__(self):
        self.version = b"ver4.0"
        self.encrypted = 0
        self.xorkey = 0
        self.names = []              # list[bytes]
        self.choices = []            # list[bytes]
        self.messages = []           # list[dict(raw=bytes, voice=bytes)]
        self.tail = b""              # cmds + 尾部，原样
        self.encoding = DEFAULT_ENCODING
        self.source_path = ""
        self.warnings = []

    # -------------------------------------------------------- 文本视图

    def name_texts(self, dec=None):
        return [_dec(b, dec or self.encoding) for b in self.names]

    def choice_texts(self, dec=None):
        return [_dec(b, dec or self.encoding) for b in self.choices]

    def message_texts(self, dec=None):
        return [_dec(m["raw"], dec or self.encoding) for m in self.messages]

    def stats(self):
        return {
            "names": len(self.names),
            "choices": len(self.choices),
            "messages": len(self.messages),
            "tail_bytes": len(self.tail),
            "encrypted": self.encrypted,
            "xorkey": self.xorkey,
        }

    # -------------------------------------------------------- 写出

    def serialize(self, encrypted=None, xorkey=None):
        """重建成字节。默认写成不加密（与汉化包一致，游戏能正常读）。"""
        enc = self.encrypted if encrypted is None else int(encrypted)
        key = self.xorkey if xorkey is None else int(xorkey)
        out = bytearray()
        out += SIG
        out += self.version[:VER_LEN].ljust(VER_LEN, b"\x00")
        out.append(enc & 0xFF)
        out.append(key & 0xFF)

        blob = bytearray()
        blob += struct.pack("<i", len(self.names))
        for b in self.names:
            blob += struct.pack("<h", len(b)) + _xor(b, key if enc else 0)
        blob += struct.pack("<i", len(self.choices))
        for b in self.choices:
            blob += struct.pack("<h", len(b)) + _xor(b, key if enc else 0)
        blob += struct.pack("<i", len(self.messages))
        for m in self.messages:
            text = _xor(m["raw"], key if enc else 0)
            voice = _xor(m.get("voice", b""), key if enc else 0)
            item = (_xor(struct.pack("<i", len(m["raw"])), key if enc else 0)
                    + text + voice)
            blob += struct.pack("<i", len(item)) + item
        out += blob
        out += self.tail
        return bytes(out)

    def write(self, path, **kw):
        data = self.serialize(**kw)
        with open(path, "wb") as fh:
            fh.write(data)
        return len(data)


def _dec(b, enc):
    try:
        return b.decode(enc)
    except Exception:
        return b.decode(enc, "replace")


def parse_bytes(data, encoding=DEFAULT_ENCODING, source_path=""):
    d = DatFile()
    d.encoding = encoding
    d.source_path = source_path
    if not data.startswith(SIG):
        raise ValueError("不是 Kaguya 的 [SCR-MESSAGE] 文本包（开头是 %r）" % data[:16])
    d.version = data[SIG_LEN:SIG_LEN + VER_LEN]
    d.encrypted = data[SIG_LEN + VER_LEN]
    d.xorkey = data[SIG_LEN + VER_LEN + 1]
    key = d.xorkey if d.encrypted else 0
    o = HDR

    def rd(n):
        nonlocal o
        v = data[o:o + n]
        o += n
        return v

    def ri(fmt):
        nonlocal o
        v = struct.unpack_from(fmt, data, o)[0]
        o += struct.calcsize(fmt)
        return v

    n = ri("<i")
    if not (0 <= n <= 1 << 22):
        raise ValueError("names 条数异常: %d" % n)
    for _ in range(n):
        ln = ri("<h")
        d.names.append(_xor(rd(ln), key))

    n = ri("<i")
    if not (0 <= n <= 1 << 22):
        raise ValueError("choices 条数异常: %d" % n)
    for _ in range(n):
        ln = ri("<h")
        d.choices.append(_xor(rd(ln), key))

    n = ri("<i")
    if not (0 <= n <= 1 << 24):
        raise ValueError("msgs 条数异常: %d" % n)
    for _ in range(n):
        ilen = ri("<i")
        tlen = struct.unpack("<i", _xor(rd(4), key))[0]
        if tlen < 0:
            raise ValueError("文本长度异常: %d" % tlen)
        text = _xor(rd(tlen), key)
        rest = ilen - 4 - tlen
        if rest < 0:
            raise ValueError("条目长度不一致 (ilen=%d tlen=%d)" % (ilen, tlen))
        voice = _xor(rd(rest), key)
        d.messages.append({"raw": text, "voice": voice})

    d.tail = data[o:]
    return d


def parse_file(path, encoding=DEFAULT_ENCODING):
    with open(path, "rb") as fh:
        data = fh.read()
    return parse_bytes(data, encoding, path)
