# -*- coding: utf-8 -*-
"""译文的导出 / 导入。

两种导出方式：

**带编号（默认）** —— 每行 ``◇<ID><TAB><译文>``，前面带注释头::

    # KaguyaPatch 译文文件
    # 每行格式：◇<ID><TAB><译文>
    #   ID 由原文计算，请勿改动；只改 TAB 后面的内容。
    #   \\n = 换行  \\\\ = 反斜杠  <玩家名> = 玩家名变量
    #   删掉某行或留空表示该条保持原文。
    # 段落标记：N=人名  C=选项  M=正文

    ◇N3F2A11C4\t红音
    ◇C59B0E7A1\t观看序章
    ◇M8A21D0F3\t「……呐，太一君。总觉得今天，有点想进行仪式呢，放学后……\\n有时间吗？」\\n

ID 由**原文**算出来，所以可以跨版本复用；没改的行、被删掉的行都会自动回退成原文，
也能只翻一部分。

**纯译文** —— 一行就是一条译文，不带编号、不带注释，适合整篇丢给 AI 翻译::

    「……好。这样就完成了」\\n
    把为了参赛写完的稿子重新检查完之后，\\n我终于放松了肩膀，伸了个懒腰。\\n

少了编号就没法定位了，所以这种文件**行数必须和原文一条不差**，顺序是
人名 → 选项 → 正文。留空行表示该条保持原文。

``keep_trailing_nl=False`` 可以把每条结尾的 ``\\n`` 也去掉，看起来更干净::

    「……好。这样就完成了」
    把为了参赛写完的稿子重新检查完之后，\\n我终于放松了肩膀，伸了个懒腰。

注意**中间**的 ``\\n`` 一定会保留（那是游戏里的换行），只有末尾那个能被去掉；
打包时程序会自动把它补回去。
"""

from __future__ import annotations

import binascii

from .kg_dat import PLAYER_CHAR

BOM = "\ufeff"
TOKEN = "<玩家名>"

MODE_ID = "id"          # ◇<ID><TAB><译文>
MODE_PLAIN = "plain"    # 只有译文

EXPORT_MODES = [
    (MODE_ID, "带编号（◇……）—— 可删行、可只翻一部分"),
    (MODE_PLAIN, "纯译文（无编号）—— 一行一条，适合整篇交给 AI"),
]

HEADER = [
    "# KaguyaPatch 译文文件",
    "# 每行格式：◇<ID><TAB><译文>",
    "#   ID 由原文计算，请勿改动；只改 TAB 后面的内容。",
    "#   \\n = 换行  \\\\ = 反斜杠  %s = 玩家名变量" % TOKEN,
    "#   删掉某行或留空表示该条保持原文。",
    "# 段落标记：N=人名  C=选项  M=正文",
]


def text_id(prefix, raw):
    return "%s%08X" % (prefix, binascii.crc32(raw) & 0xFFFFFFFF)


def _esc(s):
    s = s.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r")
    s = s.replace("\t", "\\t").replace(PLAYER_CHAR, TOKEN)
    return s


def _unesc(s):
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            if n == "n":
                out.append("\n")
                i += 2
                continue
            if n == "r":
                out.append("\r")
                i += 2
                continue
            if n == "t":
                out.append("\t")
                i += 2
                continue
            if n == "\\":
                out.append("\\")
                i += 2
                continue
        out.append(c)
        i += 1
    return "".join(out).replace(TOKEN, PLAYER_CHAR)


def _strip_trailing_nl(s):
    """只去掉末尾的换行，中间的换行一个不动。"""
    return s.rstrip("\n").rstrip("\r")


def _align_trailing_nl(new, old):
    """把译文末尾的换行对齐原文。

    导出时可以去掉末尾换行（看起来干净），打包时得还回去，否则这一条
    就没有结尾换行了。只补不缺——用户自己写了换行就尊重他。
    """
    if new.endswith("\n") or not old.endswith("\n"):
        return new
    return new + "\n"


def _read_text(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    text = None
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk", "cp932", "utf-16"):
        try:
            text = raw.decode(enc)
            break
        except Exception:
            continue
    if text is None:
        text = raw.decode("utf-8", "replace")
    # 记事本存成 CRLF、或者混着来，都统一成 LF 再按行拆
    return text.replace("\r\n", "\n").replace("\r", "\n")


# ------------------------------------------------------------------ 导出

def export_translation(dat, path, with_original=True, mode=MODE_ID,
                       keep_trailing_nl=True):
    """把 dat 导出成译文文件（值默认填原文，方便直接在原文上改）。

    mode               MODE_ID 带编号 / MODE_PLAIN 纯译文
    keep_trailing_nl   False 时去掉每条结尾的 \\n（中间的 \n 始终保留）
    """
    plain = (mode == MODE_PLAIN)
    counts = {"names": 0, "choices": 0, "messages": 0}
    lines = [] if plain else list(HEADER)

    def fmt(t):
        if not keep_trailing_nl:
            t = _strip_trailing_nl(t)
        return _esc(t)

    def add(prefix, raw, key):
        t = raw.decode(dat.encoding, "replace")
        if plain:
            lines.append(fmt(t))
        else:
            lines.append("◇%s\t%s" % (text_id(prefix, raw), fmt(t)))
        counts[key] += 1

    if not plain:
        lines += ["", "# ===== 人名 ====="]
    for raw in dat.names:
        add("N", raw, "names")

    if not plain:
        lines += ["", "# ===== 选项 ====="]
    for raw in dat.choices:
        add("C", raw, "choices")

    if not plain:
        lines += ["", "# ===== 正文 ====="]
    for m in dat.messages:
        add("M", m["raw"], "messages")

    data = "\n".join(lines) + "\n"
    with open(path, "w", encoding="utf-8-sig", newline="\n") as fh:
        fh.write(data)
    counts["mode"] = mode
    counts["keep_trailing_nl"] = keep_trailing_nl
    counts["lines"] = (counts["names"] + counts["choices"] + counts["messages"]
                       if plain else 0)
    return counts


# ------------------------------------------------------------------ 导入

def load_translation(path):
    """读译文文件，返回 ``(mode, payload)``。

    mode == MODE_ID    -> payload 是 ``{ID: 译文}``
    mode == MODE_PLAIN -> payload 是 ``[译文, ...]``（按顺序，空串=保持原文）

    靠首行有没有 ``◇`` 自动分辨，两种格式都能吃。
    """
    raw = _read_text(path).splitlines()

    first = None
    for ln in raw:
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        first = ln
        break

    if first is not None and first.lstrip().startswith("◇"):
        table = {}
        cur = None
        for ln in raw:
            if not ln or ln.startswith("#"):
                continue
            if ln.startswith("◇"):
                body = ln[1:]
                if "\t" in body:
                    tid, val = body.split("\t", 1)
                else:
                    parts = body.split(None, 1)
                    tid, val = (parts[0], parts[1] if len(parts) > 1 else "")
                table[tid.strip()] = _unesc(val)
                cur = tid.strip()
            elif cur is not None:
                # 没写 ID 的续行：接到上一条
                table[cur] += "\n" + _unesc(ln)
        return MODE_ID, table

    lines = [_unesc(ln) for ln in raw if not ln.lstrip().startswith("#")]
    return MODE_PLAIN, lines


def apply_translation(dat, payload, mode=MODE_ID):
    """把译文套回 dat（就地写 dat._names_text 等）。返回统计。"""
    st = {"names": 0, "choices": 0, "messages": 0, "missing": 0,
          "mode": mode}
    src_msgs = [m["raw"] for m in dat.messages]

    if mode == MODE_ID:
        table = payload

        def pick(raw, prefix):
            return table.get(text_id(prefix, raw))
    else:
        seq = list(payload)
        expected = len(dat.names) + len(dat.choices) + len(src_msgs)
        if len(seq) != expected:
            # 编辑器有时会在文件首尾悄悄多留空行，能剥就剥掉；
            # 但用户自己留的空行（表示保持原文）必须原样保留。
            while len(seq) > expected and seq and not seq[-1].strip():
                seq.pop()
            while len(seq) > expected and seq and not seq[0].strip():
                seq.pop(0)
        if len(seq) != expected:
            diff = len(seq) - expected
            raise ValueError(
                "纯译文文件行数对不上。\n\n"
                "应该有 %d 行（人名 %d + 选项 %d + 正文 %d），"
                "这份文件是 %d 行，%s %d 行。\n\n"
                "行数一变就没法确定哪一行对哪一条，会全部错位，"
                "所以这里停下来。\n"
                "请检查是不是多删/多加了行（想保留日文就留一个空行），"
                "或者改用「带编号」的方式导出。"
                % (expected, len(dat.names), len(dat.choices),
                   len(src_msgs), len(seq),
                   "多了" if diff > 0 else "少了", abs(diff)))
        cursor = [0]

        def pick(raw, prefix):
            i = cursor[0]
            cursor[0] = i + 1
            return seq[i]

    def collect(raws, prefix, key):
        out = []
        for raw in raws:
            old = raw.decode(dat.encoding, "replace")
            v = pick(raw, prefix)
            if v is None or v == "":
                out.append(old)          # 留空 / 没写 -> 保持原文
            else:
                out.append(_align_trailing_nl(v, old))
                st[key] += 1
        return out

    dat._names_text = collect(dat.names, "N", "names")
    dat._choices_text = collect(dat.choices, "C", "choices")
    dat._msgs_text = collect(src_msgs, "M", "messages")

    if mode == MODE_ID and payload:
        known = set()
        for raws, pre in ((dat.names, "N"), (dat.choices, "C"),
                          (src_msgs, "M")):
            for raw in raws:
                known.add(text_id(pre, raw))
        st["missing"] = len(set(payload) - known)
    return st


# ------------------------------------------------------------------ 兼容旧接口

def parse_translation(path):
    """旧接口：只返回 {ID: 译文}。新代码请用 :func:`load_translation`。"""
    mode, payload = load_translation(path)
    if mode == MODE_ID:
        return payload
    return {}
