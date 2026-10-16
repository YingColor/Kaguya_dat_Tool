# -*- coding: utf-8 -*-
"""导出「汉化包」——一整套自包含文件。

别人拿到这个包，把里面的东西全部复制进一个干净的原版游戏目录，
双击 KaguyaEngine_Patch.exe 就能玩中文版：不需要这个工具，也不需要
他再做什么。

包里有什么（和「装进游戏」铺出来的东西完全一样）：

    KaguyaEngine_Patch.exe    启动器（自带转区组件）
    winmm.dll                 钩子（Nepgear 编译产物）
    Nepgear.ini               钩子配置（UTF-16 LE）
    KaguyaPatch.json          启动器配置（游戏目录留空，跟着文件夹走）
    KaguyaPatchCN.ttf         中文字体（根目录一份）
    使用说明.txt              给拿到包的人看的
    KaguyaTrans\\            重定向目录
        message.dat           中文文本
        KaguyaPatchCN.ttf     中文字体

刻意不包含：Nepgear.log（运行日志）、游戏自己的原版文件、任何本机路径。
"""

from __future__ import annotations

import os
import re
import shutil
import zipfile

from . import kg_deploy
from .kg_ttf import Font, read_name

PACK_PREFIX = "KaguyaPatch汉化包_"
README_NAME = "使用说明.txt"

# 文件名里不能出现的字符（Windows）
_ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def safe_name(text, fallback="游戏"):
    """把游戏名收拾成能当文件夹名的样子。"""
    s = _ILLEGAL.sub("_", str(text or "")).strip()
    s = s.strip(" .")
    s = re.sub(r"_{2,}", "_", s)
    return (s[:60].strip() or fallback)


def guess_pack_name(game_dir="", folder_name=""):
    """默认包名：KaguyaPatch汉化包_<游戏目录名>。"""
    if folder_name:
        return safe_name(folder_name, "游戏")
    base = os.path.basename(os.path.abspath(game_dir)) if game_dir else ""
    return PACK_PREFIX + safe_name(base, "游戏")


HELP = """KaguyaPatch 汉化包 —— 使用说明
=================================

一、怎么用（拿到这个包的人看这里）
  1. 把本文件夹里的**全部内容**复制到游戏目录。
     游戏目录 = 有 Start.exe 的那一层（message.dat 也在那里）。
     已经汉化过、装过旧版的，直接用新的覆盖即可。
  2. 双击 KaguyaEngine_Patch.exe，开始玩中文版。

  注意：KaguyaEngine_Patch.exe 要和游戏放在一起，别单独挪到桌面去点。

二、包里都是什么
  KaguyaEngine_Patch.exe    启动器：自动转区 + 挂钩子 + 启动游戏
  winmm.dll                 字体/文件钩子（开源项目 Nepgear 的编译产物）
  Nepgear.ini               钩子配置（UTF-16 LE，别用记事本改存成别的编码）
  KaguyaPatch.json          启动器配置
  KaguyaPatchCN.ttf         中文字体（根目录一份）
  KaguyaTrans\\message.dat  中文文本包
  KaguyaTrans\\KaguyaPatchCN.ttf
  使用说明.txt              本文件

三、为什么必须用启动器
  这游戏在中文系统下直接双击 Start.exe 会闪退——它内部按日文区域读文件。
  启动器内置了绿色的区域模拟（Locale Emulator），并且会自动绕开中文路径，
  这两件事它都替你做了。

四、想恢复原版
  在游戏目录里删掉这几样就行：
      winmm.dll
      Nepgear.ini
      Nepgear.log
      KaguyaPatch.json
      KaguyaTrans\\（整个文件夹）
      KaguyaPatchCN.ttf
  游戏自带的 message.dat 从来没有被改动过，删掉这些就回到原版。
  （也可以运行：KaguyaEngine_Patch.exe --uninstall）

五、启动不了怎么办
  在游戏目录里打开命令行，运行：
      KaguyaEngine_Patch.exe --check
  它会打印诊断信息并把结果弹出来。
  少数游戏不需要转区，可以试试 KaguyaEngine_Patch.exe --no-le。
"""


# ---------------------------------------------------------------- 生成

_SIGNATURE = (kg_deploy.LAUNCHER_NAME, "Nepgear.ini",
              kg_deploy.CONFIG_NAME, "winmm.dll")


def _is_ours(folder):
    """判断这个文件夹是不是我们自己生成的包（避免误删用户的东西）。

    靠内容特征：一个汉化包必然同时有 启动器 + 钩子配置 + 启动器配置 + 钩子。
    不用额外放标记文件——分享出去的包干净一点。
    """
    return all(os.path.exists(os.path.join(folder, n)) for n in _SIGNATURE)


def _fresh(folder, overwrite=True, log=print):
    """准备一个干净的输出文件夹。"""
    if os.path.exists(folder):
        if not os.path.isdir(folder):
            raise FileExistsError("输出位置被一个同名文件占着了：%s" % folder)
        if not overwrite:
            raise FileExistsError("这个文件夹已经存在：%s" % folder)
        if not _is_ours(folder):
            raise FileExistsError(
                "这个文件夹已存在，而且不是 KaguyaPatch 生成的：\n%s\n\n"
                "怕删错你的东西，请换一个输出位置，或者先手动改名/删除。"
                % folder)
        shutil.rmtree(folder)
        log("  清掉旧的汉化包文件夹")
    os.makedirs(folder, exist_ok=True)
    return folder


def _copy(src, dst, log=None, tag=""):
    if not os.path.exists(src):
        raise FileNotFoundError("缺少文件：%s" % src)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    if log:
        log("  %s" % (tag or os.path.basename(dst)))
    return dst


def make_pack(out_dir, *, message_dat, font_file, font_family="",
              game_dir="", game_exe="", redirect_dir="KaguyaTrans",
              launcher_exe=None, folder_name="", zip_it=True,
              overwrite=True, log=print):
    """生成自包含汉化包。返回摘要字典。

    out_dir      汉化包放哪儿（里面会新建一个包文件夹，再打一个同名 zip）
    message_dat  中文 message.dat（第 2 步的产物）
    font_file    中文字体 ttf（第 2 步的产物）
    font_family  字体内部名，留空就自己从字体里读
    game_dir     游戏目录，只用来猜包名和找主程序名，可以留空
    game_exe     主程序文件名（如 Start.exe），留空就自己找
    """
    out_dir = os.path.abspath(out_dir)
    message_dat = os.path.abspath(message_dat)
    font_file = os.path.abspath(font_file)

    if not os.path.isfile(message_dat):
        raise FileNotFoundError("找不到 message.dat：%s" % message_dat)
    if not os.path.isfile(font_file):
        raise FileNotFoundError("找不到字体文件：%s" % font_file)
    oext = os.path.splitext(font_file)[1].lower()
    if oext not in (".ttf", ".otf"):
        raise ValueError("字体文件应该是 .ttf/.otf：%s" % font_file)

    if not font_family:
        font_family = read_name(Font.from_file(font_file).get("name"), 1) \
            or "KaguyaPatchCN"

    if not launcher_exe:
        launcher_exe = kg_deploy.find_launcher_exe()
    if not launcher_exe or not os.path.exists(launcher_exe):
        raise FileNotFoundError(
            "找不到 %s。\n\n"
            "它是这个包的必需品（启动器）。\n"
            "如果你在源码里跑：先在 KaguyaPatch 目录运行 build.py 打包，"
            "再重试。" % kg_deploy.LAUNCHER_NAME)

    name = guess_pack_name(game_dir, folder_name)
    os.makedirs(out_dir, exist_ok=True)
    folder = _fresh(os.path.join(out_dir, name), overwrite=overwrite, log=log)

    font_base = os.path.basename(font_file)
    dirname = redirect_dir or "KaguyaTrans"
    log("生成汉化包：%s" % folder)

    # 1) 重定向目录：中文文本 + 字体
    rdir = os.path.join(folder, dirname)
    _copy(message_dat, os.path.join(rdir, "message.dat"), log, "%s\\message.dat" % dirname)
    _copy(font_file, os.path.join(rdir, font_base), log, "%s\\%s" % (dirname, font_base))

    # 2) 字体在根目录也放一份（有些加载路径只找根目录）
    _copy(font_file, os.path.join(folder, font_base), log, font_base)

    # 3) 钩子 + 配置
    dll = kg_deploy.WINMM_X86
    _copy(dll, os.path.join(folder, "winmm.dll"), log, "winmm.dll（钩子）")
    kg_deploy.write_ini_utf16(
        os.path.join(folder, "Nepgear.ini"),
        kg_deploy.build_nepgear_ini(font_file=font_base, face_name=font_family,
                                    redirect_folder=dirname))
    log("  Nepgear.ini（UTF-16 LE）")

    # 4) 启动器配置：game_dir 留空
    if not game_exe and game_dir and os.path.isdir(game_dir):
        from . import kg_launch
        found = kg_launch.find_game_exe(game_dir)
        game_exe = os.path.basename(found) if found else ""
    kg_deploy.write_config(folder, game_exe=game_exe, redirect_dir=dirname,
                           font_file=font_base, font_family=font_family)
    log("  %s（游戏目录留空，跟着文件夹走）" % kg_deploy.CONFIG_NAME)

    # 5) 启动器本体
    _copy(launcher_exe, os.path.join(folder, kg_deploy.LAUNCHER_NAME), log,
          "%s（启动器）" % kg_deploy.LAUNCHER_NAME)

    # 6) 使用说明
    with open(os.path.join(folder, README_NAME), "w", encoding="utf-8") as fh:
        fh.write(HELP)

    files = []
    for root, _dirs, names in os.walk(folder):
        for fn in names:
            files.append(os.path.relpath(os.path.join(root, fn), folder))

    zpath = ""
    if zip_it:
        zpath = os.path.join(out_dir, name + ".zip")
        zip_folder(folder, zpath)
        log("已打包 zip：%s" % zpath)

    log("完成。把「%s」里的东西全部复制到游戏目录，"
        "双击 %s 就能玩中文版。" % (name, kg_deploy.LAUNCHER_NAME))
    return {"folder": folder, "name": name, "zip": zpath,
            "files": sorted(files), "font": font_base,
            "family": font_family, "game_exe": game_exe}


def zip_folder(folder, zip_path, base_in_zip=None):
    """把文件夹压成 zip，zip 里保留顶层文件夹名，解压出来是干净的。"""
    folder = os.path.abspath(folder)
    base_in_zip = base_in_zip or os.path.basename(folder)
    tmp = zip_path + ".part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, names in os.walk(folder):
            for fn in names:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, folder)
                z.write(full, os.path.join(base_in_zip, rel))
    os.replace(tmp, zip_path)
    return zip_path


# ---------------------------------------------------------------- 从成品反推

def pack_from_game(game_dir, out_dir, *, redirect_dir="KaguyaTrans",
                   folder_name="", zip_it=True, overwrite=True, log=print):
    """「我游戏目录里已经装好了，照这个样子导出成包」。

    直接从游戏目录里把已经铺好的东西收进包里，不需要汉化数据目录。
    """
    game_dir = os.path.abspath(game_dir)
    if not os.path.isdir(game_dir):
        raise NotADirectoryError("游戏目录不存在：%s" % game_dir)
    from . import kg_launch

    ini = os.path.join(game_dir, "Nepgear.ini")
    config = os.path.join(game_dir, kg_deploy.CONFIG_NAME)
    if not os.path.exists(ini) or not os.path.exists(config):
        raise FileNotFoundError(
            "这个游戏目录里没有找到汉化痕迹（缺 Nepgear.ini 或 %s）。\n\n"
            "想导出汉化包的话，请先在「装进游戏」那一步装好，"
            "或者用「汉化数据文件夹」的方式导出。" % kg_deploy.CONFIG_NAME)

    rdir = os.path.join(game_dir, redirect_dir)
    msgdat = os.path.join(rdir, "message.dat")
    if not os.path.exists(msgdat):
        raise FileNotFoundError("找不到 %s\\message.dat" % redirect_dir)

    ttf = ""
    for cand in (os.path.join(rdir, "KaguyaPatchCN.ttf"),
                 os.path.join(game_dir, "KaguyaPatchCN.ttf")):
        if os.path.exists(cand):
            ttf = cand
            break
    if not ttf:
        fonts = [f for f in os.listdir(rdir) if f.lower().endswith(".ttf")]
        if not fonts:
            raise FileNotFoundError("在游戏目录里找不到中文字体")
        ttf = os.path.join(rdir, fonts[0])

    exe = kg_launch.find_game_exe(game_dir)
    return make_pack(out_dir, message_dat=msgdat, font_file=ttf,
                     game_dir=game_dir,
                     game_exe=os.path.basename(exe) if exe else "",
                     redirect_dir=redirect_dir, folder_name=folder_name,
                     zip_it=zip_it, overwrite=overwrite, log=log)
