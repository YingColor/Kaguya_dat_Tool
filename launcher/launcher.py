# -*- coding: utf-8 -*-
"""KaguyaEngine_Patch.exe —— 汉化版游戏启动器。

把它和汉化数据一起放进游戏目录，双击就开始玩中文版。

它做的四件事：
  1. 检查钩子和汉化数据在不在；
  2. 游戏路径里有中文的话，先在纯英文路径下建一个目录联接绕过去；
  3. 把内置的 Locale Emulator 铺到临时目录；
  4. 用日文区域启动游戏主程序。

命令行：
  KaguyaEngine_Patch.exe            正常启动
  KaguyaEngine_Patch.exe --install  只部署不启动
  KaguyaEngine_Patch.exe --uninstall 卸掉钩子，恢复原版
  KaguyaEngine_Patch.exe --check    自检并打印诊断
  KaguyaEngine_Patch.exe --no-le    不转区，直接启动（少数游戏不需要）
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import time

APP_TITLE = "KaguyaPatch"
CONFIG_NAME = "KaguyaPatch.json"

DEFAULTS = {
    "game_dir": "",
    "game_exe": "Start.exe",
    "redirect_dir": "KaguyaTrans",
    "font_file": "KaguyaPatchCN.ttf",
    "font_family": "KaguyaPatchCN",
    "use_le": True,
}


# ---------------------------------------------------------------- 基础

def bundle_root():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def freeze_support():
    if getattr(sys, "frozen", False):
        return
    root = bundle_root()
    if root not in sys.path:
        sys.path.insert(0, root)


def msgbox(text, title=APP_TITLE, flags=0x40):
    try:
        ctypes.windll.user32.MessageBoxW(None, str(text), str(title), flags)
    except Exception:
        print(text)


def load_config(base):
    cfg = dict(DEFAULTS)
    p = os.path.join(base, CONFIG_NAME)
    if os.path.exists(p):
        for enc in ("utf-8-sig", "utf-8", "gbk"):
            try:
                with open(p, encoding=enc) as fh:
                    cfg.update(json.load(fh))
                break
            except Exception:
                continue
    if not cfg.get("game_dir"):
        cfg["game_dir"] = base
    return cfg


def save_config(base, cfg):
    p = os.path.join(base, CONFIG_NAME)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- 主流程

def prepare(cfg, log=print):
    """确保钩子与数据就位，返回 (game_dir, redirect_dir, 问题列表)"""
    from core import kg_deploy

    game_dir = os.path.abspath(cfg["game_dir"])
    problems = []
    if not os.path.isdir(game_dir):
        return game_dir, "", ["游戏目录不存在：%s" % game_dir]

    rdir = os.path.join(game_dir, cfg["redirect_dir"])
    dat = os.path.join(rdir, "message.dat")
    font = os.path.join(rdir, cfg["font_file"])

    if not os.path.exists(dat):
        problems.append("缺少汉化文本：%s" % dat)
    if not os.path.exists(font):
        problems.append("缺少字体：%s" % font)

    # 钩子
    dll = os.path.join(game_dir, "winmm.dll")
    if not os.path.exists(dll):
        if os.path.exists(kg_deploy.WINMM_X86):
            os.makedirs(game_dir, exist_ok=True)
            with open(kg_deploy.WINMM_X86, "rb") as a, open(dll, "wb") as b:
                b.write(a.read())
            log("  已补上钩子 winmm.dll")

    ini = os.path.join(game_dir, "Nepgear.ini")
    if not os.path.exists(ini):
        text = kg_deploy.build_nepgear_ini(
            font_file=cfg["font_file"], face_name=cfg["font_family"],
            redirect_folder=cfg["redirect_dir"])
        kg_deploy.write_ini_utf16(ini, text)
        log("  已补上 Nepgear.ini")

    return game_dir, rdir, problems


def do_launch(cfg, log=print):
    from core import kg_launch

    game_dir, rdir, problems = prepare(cfg, log=log)
    if problems:
        msgbox("启动不了，缺少这些文件：\n\n" + "\n".join(problems) +
               "\n\n请把汉化包里的 KaguyaTrans 文件夹\n和本程序放在游戏目录下。",
               APP_TITLE, 0x30)
        return 2

    exe = kg_launch.find_game_exe(game_dir, hint=cfg.get("game_exe"))
    if not exe:
        msgbox("在游戏目录里找不到主程序（.exe）。\n\n请把本程序放到游戏目录下。",
               APP_TITLE, 0x30)
        return 2
    log("  找到游戏主程序：%s" % os.path.basename(exe))

    use_le = bool(cfg.get("use_le", True))
    try:
        kg_launch.launch(game_dir, exe_name=os.path.basename(exe),
                         use_le=use_le, log=log,
                         le_proc=cfg.get("le_proc") or None)
    except Exception as e:
        msgbox("启动失败：\n\n%s" % e, APP_TITLE, 0x10)
        return 3
    return 0


def main(argv):
    freeze_support()
    base = bundle_root()
    cfg = load_config(base)
    args = [a for a in argv[1:]]

    def log(s):
        if sys.stdout is not None:
            try:
                print(s)
            except Exception:
                pass

    log("%s 启动器" % APP_TITLE)
    log("程序目录：%s" % base)
    log("游戏目录：%s" % cfg["game_dir"])

    if "--check" in args:
        game_dir, rdir, problems = prepare(cfg, log=log)
        from core import kg_launch
        exe = kg_launch.find_game_exe(game_dir, hint=cfg.get("game_exe"))
        log("主程序：%s" % exe)
        info = kg_launch.scan_pe(exe) if exe else None
        if info:
            log("位数：%d  导入 WINMM：%s"
                % (info["arch"],
                   any(n.lower() == "winmm.dll" for n in info["imports"])))
        log("路径含中文：%s" % (not kg_launch.is_ascii_path(game_dir)))
        log("问题：%s" % (problems or "无"))
        kg_launch.stage_le(log=log)
        log("Locale Emulator 就绪")
        msgbox("自检完成：\n\n游戏目录：%s\n主程序：%s\n问题：%s"
               % (game_dir, os.path.basename(exe) if exe else "未找到",
                  "、".join(problems) if problems else "无"),
               APP_TITLE)
        return 0 if not problems else 2

    if "--uninstall" in args:
        from core import kg_deploy
        removed = kg_deploy.uninstall(cfg["game_dir"], cfg["redirect_dir"],
                                      cfg.get("font_file"), log=log)
        if removed:
            msgbox("钩子已卸掉，游戏恢复成原版。\n删除了 %d 项。"
                   % len(removed), APP_TITLE)
        else:
            msgbox("没找到汉化文件，本来就是原版。", APP_TITLE)
        return 0

    if "--install" in args:
        game_dir, rdir, problems = prepare(cfg, log=log)
        if problems:
            msgbox("有问题：\n\n" + "\n".join(problems), APP_TITLE, 0x30)
            return 2
        msgbox("钩子已装好。以后双击 KaguyaEngine_Patch.exe 就能进游戏。",
               APP_TITLE)
        return 0

    if "--no-le" in args:
        cfg["use_le"] = False

    rc = do_launch(cfg, log=log)
    if rc == 0:
        time.sleep(0.3)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
