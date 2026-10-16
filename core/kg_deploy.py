# -*- coding: utf-8 -*-
"""把汉化数据 + 钩子部署进游戏目录。

游戏从汉化包里要三样东西：
  1. 钩子     —— Nepgear 编译出来的 winmm.dll（伪装成系统组件，游戏自己会加载）
  2. 配置     —— Nepgear.ini（必须是 UTF-16 LE，钩子才认得）
  3. 内容     —— 重定向文件夹里的 message.dat 与字体

这些文件都放在游戏目录里，和 Start.exe 同级，游戏启动就自动生效。
"""

from __future__ import annotations

import os
import shutil
import sys


def _assets_dir():
    """资源目录。打包成 exe 后从 _MEIPASS 取。"""
    cands = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        cands.append(os.path.join(base, "assets"))
    here = os.path.dirname(os.path.abspath(__file__))
    cands.append(os.path.join(os.path.dirname(here), "assets"))
    for c in cands:
        if os.path.isdir(c):
            return c
    return cands[-1]


def apply_launcher_icon(exe, *, game_exe=None, image_file=None, log=print):
    """给启动器副本换图标。game_exe / image_file 都不给 = 不动。

    单个失败不致命：图标只是好看，换不上不该让整个安装/导出失败。
    返回 True/False 表示有没有真的换。
    """
    if not (game_exe or image_file):
        return False
    if not os.path.exists(exe):
        return False
    try:
        from . import kg_icon
        kg_icon.set_exe_icon(exe, game_exe=game_exe, image_file=image_file)
    except Exception as e:
        log("  ⚠ 换图标没成功（不影响使用）：%s" % e)
        return False
    log("  已给启动器换上%s图标" % ("游戏" if game_exe else "自定义"))
    return True


HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = _assets_dir()
NEPGEAR_DIR = os.path.join(ASSETS, "nepgear")
LE_DIR = os.path.join(ASSETS, "le")

WINMM_X86 = os.path.join(NEPGEAR_DIR, "winmm_x86.dll")
WINMM_X64 = os.path.join(NEPGEAR_DIR, "winmm_x64.dll")
INI_TEMPLATE = os.path.join(NEPGEAR_DIR, "Nepgear.ini.template")

LE_FILES = ["LEProc.exe", "LoaderDll.dll", "LocaleEmulator.dll",
            "LECommonLibrary.dll", "LEConfig.xml", "LEVersion.xml"]
LE_PROFILE_JA = "8f4c8cb4-c323-4bd4-9025-bc4ecffa08b6"

__all__ = ["deploy", "uninstall", "make_config", "write_config",
           "read_ini_any", "write_ini_utf16", "set_ini_value",
           "build_nepgear_ini", "find_launcher_exe", "apply_launcher_icon",
           "LE_DIR", "ASSETS", "LAUNCHER_NAME", "CONFIG_NAME"]


# ---------------------------------------------------------------- ini 工具

def read_ini_any(path):
    with open(path, "rb") as fh:
        data = fh.read()
    for enc in ("utf-16", "utf-8-sig", "utf-8", "gbk", "cp932"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode("utf-16", "replace")


def set_ini_value(text, section, key, value):
    """设置 [section] 下的 key=value；同名节全部生效。返回新文本。"""
    lines = text.replace("\r\n", "\n").split("\n")
    cur = None
    done = 0
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("[") and s.endswith("]"):
            cur = s[1:-1].strip().lower()
            continue
        if cur != section.lower():
            continue
        if s.startswith(";") or s.startswith("#") or "=" not in ln:
            continue
        if ln.split("=", 1)[0].strip().lower() == key.lower():
            lines[i] = "%s=%s" % (key, value)
            done += 1
    if not done:
        lines.append("[%s]" % section)
        lines.append("%s=%s" % (key, value))
    return "\n".join(lines)


def set_ini_many(text, pairs):
    for section, key, value in pairs:
        text = set_ini_value(text, section, key, value)
    return text


def write_ini_utf16(path, text):
    text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    with open(path, "wb") as fh:
        fh.write(b"\xff\xfe")
        fh.write(text.encode("utf-16-le"))


def build_nepgear_ini(template=None, *, font_file, face_name,
                      redirect_folder, charset=128, log_file=1):
    text = template
    if text is None:
        text = read_ini_any(INI_TEMPLATE)
    text = set_ini_many(text, [
        ("System", "Enable", 1),
        ("System", "ShowStartupPopup", 0),
        ("Font", "Enable", 1),
        ("Font", "FileName", font_file),
        ("Font", "FaceName", face_name),
        ("Font", "Charset", charset),
        ("Font", "EnableFaceNameReplace", 1),
        ("Font", "EnableCharsetReplace", 0),
        ("Font", "EnableHeightScale", 1),
        ("Font", "HeightScale", "1.0"),
        ("Font", "EnableWidthScale", 1),
        ("Font", "WidthScale", "1.0"),
        ("Font", "EnableWeight", 1),
        ("Font", "Weight", 0),
        ("FileRedirect", "Enable", 1),
        ("FileRedirect", "Folder", redirect_folder),
        ("FileHook", "VFSMode", 1),
        ("LocaleEmulator", "Enable", 0),
        ("CodePage", "Enable", 0),
        ("Window", "Enable", 0),
        ("Debug", "Enable", 0),
        ("Debug", "LogToFile", log_file),
    ])
    return text


LAUNCHER_NAME = "KaguyaEngine_Patch.exe"
CONFIG_NAME = "KaguyaPatch.json"

# 「game_dir」故意留空：启动器会把自己所在的文件夹当成游戏目录。
# 这样游戏改名、搬家、整个文件夹拷到别人电脑上，都照样能用；
# 也让「装进游戏」和「导出汉化包」产出的东西完全一致。
def make_config(*, game_dir="", game_exe="", redirect_dir="KaguyaTrans",
                font_file="KaguyaPatchCN.ttf", font_family="KaguyaPatchCN",
                use_le=True):
    return {"game_dir": game_dir, "game_exe": game_exe,
            "redirect_dir": redirect_dir, "font_file": font_file,
            "font_family": font_family, "use_le": use_le}


def write_config(target_dir, **fields):
    """写启动器配置。默认 game_dir 为空（= 启动器按自身位置找游戏）。"""
    import json
    cfg = make_config(**fields)
    path = os.path.join(target_dir, CONFIG_NAME)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
    return path


def find_launcher_exe():
    """找出 KaguyaEngine_Patch.exe，好一起铺到游戏目录里。

    打包后它被塞在 exe 内部的 launcher/ 下；源码运行时在 launcher/ 或 dist/。
    """
    cands = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        cands.append(os.path.join(base, "launcher", LAUNCHER_NAME))
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        cands.append(os.path.join(exe_dir, LAUNCHER_NAME))
        cands.append(os.path.join(exe_dir, "dist", LAUNCHER_NAME))
    pkg = os.path.dirname(HERE)
    cands.append(os.path.join(pkg, "launcher", LAUNCHER_NAME))
    cands.append(os.path.join(pkg, "dist", LAUNCHER_NAME))
    cands.append(os.path.join(HERE, "dist", LAUNCHER_NAME))
    for c in cands:
        if os.path.exists(c):
            return c
    return None


# ---------------------------------------------------------------- 部署

def _copy(src, dst, log, tag):
    if not os.path.exists(src):
        raise FileNotFoundError("缺少资源：%s" % src)
    if os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(src):
        with open(src, "rb") as f1, open(dst, "rb") as f2:
            if f1.read() == f2.read():
                return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    log("  写入 %s" % tag)
    return True


def deploy(game_dir, *, message_dat, font_file, font_family,
           redirect_dir="KaguyaTrans", game_exe="", log=print, arch=32,
           launcher_exe=None, icon_game_exe=None, icon_image=None):
    """把钩子 + 配置 + 数据 + 启动器装进游戏目录。返回摘要。"""
    game_dir = os.path.abspath(game_dir)
    if not os.path.isdir(game_dir):
        raise NotADirectoryError("游戏目录不存在：%s" % game_dir)

    dll = WINMM_X86 if arch == 32 else WINMM_X64
    if not os.path.exists(dll):
        dll = WINMM_X86
    log("部署到：%s" % game_dir)
    _copy(dll, os.path.join(game_dir, "winmm.dll"), log, "winmm.dll（钩子）")

    ini = build_nepgear_ini(font_file=os.path.basename(font_file),
                            face_name=font_family,
                            redirect_folder=redirect_dir)
    ini_path = os.path.join(game_dir, "Nepgear.ini")
    write_ini_utf16(ini_path, ini)
    log("  写入 Nepgear.ini（UTF-16 LE）")

    rdir = os.path.join(game_dir, redirect_dir)
    os.makedirs(rdir, exist_ok=True)
    _copy(message_dat, os.path.join(rdir, "message.dat"), log, "message.dat")
    # 字体放重定向目录，同时放一份到根目录（有些加载路径只找根目录）
    _copy(font_file, os.path.join(rdir, os.path.basename(font_file)), log,
          "字体")
    _copy(font_file, os.path.join(game_dir, os.path.basename(font_file)), log,
          "字体（根目录副本）")

    # 启动器：放一份到游戏目录，用户以后双击它就进中文版
    if launcher_exe is None:
        launcher_exe = find_launcher_exe()
    dst_launcher = os.path.join(game_dir, LAUNCHER_NAME)
    if launcher_exe and os.path.exists(launcher_exe):
        if _copy(launcher_exe, dst_launcher, log,
                 "%s（以后双击它就进游戏）" % LAUNCHER_NAME):
            log("  已铺好启动器，以后双击它就能玩中文版")
    else:
        log("  （没找到 %s，可稍后手动复制过去）" % LAUNCHER_NAME)

    # 启动器图标：游戏图标 / 自定义（不给就保持启动器自带的样子）
    apply_launcher_icon(dst_launcher, game_exe=icon_game_exe,
                        image_file=icon_image, log=log)

    # 启动器配置：game_dir 留空，启动器按自身所在目录找游戏
    write_config(game_dir, game_exe=game_exe, redirect_dir=redirect_dir,
                 font_file=os.path.basename(font_file),
                 font_family=font_family)
    log("  写入 %s（游戏目录留空，跟着文件夹走）" % CONFIG_NAME)

    return {"game_dir": game_dir, "redirect_dir": rdir,
            "font": os.path.basename(font_file), "family": font_family,
            "config": os.path.join(game_dir, CONFIG_NAME),
            "launcher": dst_launcher if os.path.exists(dst_launcher) else ""}


def _our_fonts(game_dir, font_file=None):
    """只会删我们自己做出来的字体，绝不动游戏自带的文件。"""
    names = []
    if font_file:
        names.append(os.path.basename(font_file))
    names.append("KaguyaPatchCN.ttf")
    try:
        import json
        with open(os.path.join(game_dir, "KaguyaPatch.json"),
                  encoding="utf-8") as fh:
            names.append(os.path.basename(json.load(fh).get("font_file") or ""))
    except Exception:
        pass
    out = []
    for n in names:
        if n and n.lower().endswith(".ttf") and n not in out:
            out.append(n)
    return out


def uninstall(game_dir, redirect_dir="KaguyaTrans", font_file=None, log=print):
    """卸掉钩子，恢复成原版可直接运行的样子。返回删掉的东西（相对路径）。

    只删三类：钩子（winmm.dll）、配置（Nepgear.ini / Nepgear.log /
    KaguyaPatch.json）、我们生成的字体和重定向文件夹。
    游戏本体一个字节都不碰。
    """
    game_dir = os.path.abspath(game_dir)
    if not os.path.isdir(game_dir):
        raise NotADirectoryError("游戏目录不存在：%s" % game_dir)
    removed = []
    victims = [os.path.join(game_dir, "winmm.dll"),
               os.path.join(game_dir, "Nepgear.ini"),
               os.path.join(game_dir, "Nepgear.log"),
               os.path.join(game_dir, CONFIG_NAME)]
    # 我们的字体名要从配置里读，所以先取字体清单再删配置文件
    for n in _our_fonts(game_dir, font_file):
        victims.append(os.path.join(game_dir, n))
    # 钩子的备份（如果有）
    for extra in ("winmm.dll.bak", "Nepgear.ini.bak"):
        victims.append(os.path.join(game_dir, extra))
    for v in victims:
        if os.path.isfile(v):
            try:
                os.remove(v)
                removed.append(os.path.basename(v))
                log("  删除 %s" % os.path.basename(v))
            except OSError as e:
                log("  删不掉 %s（%s）" % (os.path.basename(v), e))
    rdir = os.path.abspath(os.path.join(game_dir, redirect_dir))
    # 安全护栏：只删确实在游戏目录里面的那个文件夹
    if (os.path.isdir(rdir)
            and os.path.normcase(os.path.dirname(rdir))
            == os.path.normcase(game_dir)):
        try:
            shutil.rmtree(rdir)
            removed.append(redirect_dir + "\\")
            log("  删除 %s\\" % redirect_dir)
        except OSError as e:
            log("  删不掉 %s\\（%s）" % (redirect_dir, e))
    return removed
