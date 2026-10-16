# -*- coding: utf-8 -*-
"""一键把「原版 message.dat + 译文」做成可用的汉化数据（dat + 字体）。"""

from __future__ import annotations

import json
import os

from . import kg_dat, kg_font, kg_slot, kg_text
from .kg_dat import PLAYER_CHAR

MANIFEST = "kaguya_pack.json"


def build(source_dat, translation=None, out_dir=".", *,
          base_font=None, family=kg_font.DEFAULT_FAMILY,
          redirect_dir="KaguyaTrans", font_file=None,
          log=print):
    """生成汉化数据。``translation`` 为 None 时按纯原文重排（用于自检）。

    返回 manifest dict。
    """
    os.makedirs(out_dir, exist_ok=True)
    font_file = font_file or (family + ".ttf")

    src = kg_dat.parse_file(source_dat)
    log("原版：%s（人名 %d / 选项 %d / 正文 %d）"
        % (os.path.basename(source_dat), len(src.names),
           len(src.choices), len(src.messages)))

    if translation:
        mode, payload = kg_text.load_translation(translation)
        st = kg_text.apply_translation(src, payload, mode)
        if mode == kg_text.MODE_PLAIN:
            log("译文：纯译文格式，按顺序对齐（人名 %d / 选项 %d / 正文 %d）"
                % (len(src.names), len(src.choices), len(src.messages)))
        log("译文：命中 人名%d 选项%d 正文%d，文件里多余的 %d 条"
            % (st["names"], st["choices"], st["messages"], st["missing"]))
        names = src._names_text
        choices = src._choices_text
        msgs = src._msgs_text
    else:
        table = {}
        names = src.name_texts()
        choices = src.choice_texts()
        msgs = src.message_texts()

    # 槽位分配：正文用到的字符不能和槽撞车，原文里出现的字符也要避开
    all_out = names + choices + msgs
    origin = src.name_texts() + src.choice_texts() + src.message_texts()
    slot_table, left = kg_slot.make_table(all_out, extra_reserved=origin)
    log("需要槽位 %d 个，剩余可用 %d 个" % (len(slot_table), len(left)))

    # 编码
    enc_names = [kg_slot.encode_text(t, slot_table) for t in names]
    enc_choices = [kg_slot.encode_text(t, slot_table) for t in choices]
    enc_msgs = [kg_slot.encode_text(t, slot_table) for t in msgs]

    bad = []
    for i, t in enumerate(all_out):
        for ch in t:
            if ch in ("\n", "\r", PLAYER_CHAR):
                continue
            if not kg_slot.is_encodable(ch) and ch not in slot_table:
                bad.append(ch)
    if bad:
        log("  ⚠ 有 %d 个字符既编不进 cp932 也没分到槽位：%s"
            % (len(set(bad)), "".join(sorted(set(bad))[:40])))

    out = kg_dat.DatFile()
    out.version = src.version
    out.encrypted = 0
    out.xorkey = 0
    out.names = enc_names
    out.choices = enc_choices
    out.messages = [{"raw": b, "voice": m["voice"]}
                    for b, m in zip(enc_msgs, src.messages)]
    out.tail = src.tail
    out.encoding = "cp932"

    dat_name = "message.dat"
    dat_path = os.path.join(out_dir, dat_name)
    size = out.write(dat_path)
    log("文本包已生成：%s（%.2f MB，尾部数据原样保留 %d 字节）"
        % (dat_path, size / 1048576.0, len(src.tail)))

    # 字体
    font_path = os.path.join(out_dir, font_file)
    info = kg_font.build_font(slot_table, font_path, base=base_font,
                              family=family, log=log)

    # 槽位表
    slot_path = os.path.join(out_dir, "slotmap.txt")
    with open(slot_path, "w", encoding="utf-8") as fh:
        fh.write("# 槽位表：左=要显示的简体字  右=借用的 cp932 码位\n")
        fh.write("\n".join(kg_slot.table_to_lines(slot_table)))
        fh.write("\n")

    man = {
        "source_dat": os.path.abspath(source_dat),
        "translation": os.path.abspath(translation) if translation else None,
        "message_dat": os.path.abspath(dat_path),
        "font": os.path.abspath(font_path),
        "font_family": family,
        "redirect_dir": redirect_dir,
        "font_file": font_file,
        "slots": len(slot_table),
        "font_info": info,
        "counts": {"names": len(enc_names), "choices": len(enc_choices),
                   "messages": len(enc_msgs)},
    }
    with open(os.path.join(out_dir, MANIFEST), "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=2)
    log("完成。")
    return man
