# -*- coding: utf-8 -*-
"""KaguyaPatch 命令行工具。

    python kaguya_patch.py extract <message.dat> <译文.txt> [--plain] [--no-nl]
    python kaguya_patch.py build   <原版message.dat> <译文.txt> <输出目录> [底座字体]
    python kaguya_patch.py fonts
    python kaguya_patch.py install <游戏目录> <汉化数据目录> [重定向目录名]
    python kaguya_patch.py launch  <游戏目录> [主程序名]
    python kaguya_patch.py uninstall <游戏目录>
    python kaguya_patch.py check   <游戏目录>
    python kaguya_patch.py release <游戏目录> <汉化数据目录> <输出目录> [--no-zip] [--name 名字]
    python kaguya_patch.py pack    <游戏目录> <输出目录> [--no-zip] [--name 名字]

release 从「汉化数据目录」做汉化包；pack 从「已经装好的游戏目录」直接收一份。
两种都是自包含的，别人拿到复制进干净的原版游戏目录就能玩。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import (kg_dat, kg_deploy, kg_font, kg_launch, kg_pack,   # noqa
                  kg_release, kg_text)


def usage():
    print(__doc__)


def cmd_extract(dat, out, *opts):
    """--plain 只导出译文不带编号；--no-nl 去掉每条结尾的 \\n。"""
    mode = kg_text.MODE_PLAIN if "--plain" in opts else kg_text.MODE_ID
    keep = "--no-nl" not in opts
    d = kg_dat.parse_file(dat)
    c = kg_text.export_translation(d, out, mode=mode, keep_trailing_nl=keep)
    print("导出完成：%s（人名 %d / 选项 %d / 正文 %d）"
          % (out, c["names"], c["choices"], c["messages"]))
    if mode == kg_text.MODE_PLAIN:
        print("纯译文格式：%d 行，顺序 人名->选项->正文，"
              "顺序不能调、行数不能少。" % c["lines"])
    if not keep:
        print("已去掉每条结尾的换行（打包时自动补回）。")


def cmd_fonts(*_):
    """看看有哪些字体可以当底座（做中文字体时从哪儿借字形）。"""
    d = kg_font.ensure_font_dir()
    print("可用的「底座字体」（越靠前越推荐）：")
    for label, (n, p, i) in kg_font.base_font_menu():
        print("  %-44s %s" % (label, p))
    print()
    print("要自己加字体：把 .ttf 丢进 %s" % d)
    print("做出来的汉化包要给别人用的话，底座建议选思源/Noto 这类")
    print("开源字体（SIL OFL 许可，允许再分发），静态版优先，别用 VF。")
    print("生成出来的字体里会原样带着底座的版权与许可声明。")


def cmd_build(src, txt, out, *rest):
    """第三个之后的参数可以写底座字体名（用 fonts 命令看有哪些）。"""
    base = None
    if rest:
        for n, p, i in kg_font.list_base_fonts():
            if rest[0] in (n, p) or os.path.basename(p).lower() == rest[0].lower():
                base = (n, p, i)
                break
        if base is None:
            print("找不到这个底座字体（用 fonts 命令看看有哪些）：%s" % rest[0])
            return
    kg_pack.build(src, txt, out, base_font=base)


def cmd_install(game, data, redirect="KaguyaTrans"):
    dat, font = _pick_data(data)
    family = _font_family(font)
    exe = kg_launch.find_game_exe(game)
    kg_deploy.deploy(game, message_dat=dat, font_file=font,
                     font_family=family, redirect_dir=redirect,
                     game_exe=os.path.basename(exe) if exe else "")
    print("安装完成。双击游戏目录里的 KaguyaEngine_Patch.exe 就能玩中文版。")
    print("（配置里的游戏目录留空，跟着文件夹走——改名搬家都不用重装。）")


def cmd_launch(game, exe=None):
    kg_launch.launch(game, exe_name=exe)


def cmd_uninstall(game, redirect="KaguyaTrans"):
    removed = kg_deploy.uninstall(game, redirect)
    if removed:
        print("已还原成原版，删除 %d 项：%s"
              % (len(removed), "、".join(removed)))
    else:
        print("没找到汉化文件，这个目录本来就是原版。")


def cmd_check(game):
    exe = kg_launch.find_game_exe(game)
    print("游戏目录：", os.path.abspath(game))
    print("主程序：", exe)
    if exe:
        info = kg_launch.scan_pe(exe)
        if info:
            print("位数：", info["arch"])
            print("导入 WINMM.dll：",
                  any(n.lower() == "winmm.dll" for n in info["imports"]))
    print("路径含中文：", not kg_launch.is_ascii_path(game))
    kg_launch.stage_le(log=lambda *a: None)
    print("Locale Emulator：就绪")


def _pkg_dir():
    """本模块所在目录（打包后是解包出来的临时目录）。"""
    return os.path.dirname(os.path.abspath(__file__))


def _app_dir():
    """可执行文件所在目录（打包后就是 exe 旁边）。"""
    return os.path.dirname(os.path.abspath(sys.executable))


def find_launcher():
    return kg_deploy.find_launcher_exe()


def _pick_data(data):
    """从汉化数据目录里挑出 message.dat 和字体。"""
    dat = os.path.join(data, "message.dat")
    fonts = [f for f in os.listdir(data) if f.lower().endswith(".ttf")]
    if not os.path.exists(dat) or not fonts:
        raise SystemExit("汉化数据目录里缺 message.dat 或字体：%s" % data)
    return dat, os.path.join(data, fonts[0])


def _font_family(font):
    from core.kg_ttf import Font, read_name
    return read_name(Font.from_file(font).get("name"), 1) or "KaguyaPatchCN"


def _pack_opts(opts):
    """从命令行尾巴里挑出 --no-zip / --name xxx。"""
    return {"zip_it": "--no-zip" not in opts,
            "folder_name": _opt_value(opts, "--name")}


def _opt_value(opts, key, default=""):
    if key in opts:
        i = opts.index(key)
        if i + 1 < len(opts):
            return opts[i + 1]
    return default


def _report(res):
    print("汉化包已生成：%s" % res["folder"])
    for fn in res["files"]:
        print("   " + fn)
    if res.get("zip"):
        mb = os.path.getsize(res["zip"]) / 1048576.0
        print("压缩包：%s（%.1f MB）" % (res["zip"], mb))
    print("这个包是自包含的：别人把它解压，里面的东西全部复制到干净的原版")
    print("游戏目录，双击 KaguyaEngine_Patch.exe 就能玩中文版。")


def cmd_release(game, data, out, *opts):
    """从汉化数据目录做汉化包。"""
    dat, font = _pick_data(data)
    res = kg_release.make_pack(out, message_dat=dat, font_file=font,
                               game_dir=game, **_pack_opts(opts))
    _report(res)


def cmd_pack(game, out, *opts):
    """从已经装好汉化的游戏目录里，照着收一份汉化包出来。"""
    res = kg_release.pack_from_game(game, out, **_pack_opts(opts))
    _report(res)


HELP = kg_release.HELP      # 汉化包里那份「使用说明.txt」的正文


def main(argv):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass
    if len(argv) < 2:
        usage()
        return 1
    cmd, rest = argv[1], argv[2:]
    fns = {"extract": cmd_extract, "build": cmd_build, "fonts": cmd_fonts,
           "install": cmd_install, "launch": cmd_launch,
           "uninstall": cmd_uninstall, "check": cmd_check,
           "release": cmd_release, "pack": cmd_pack}
    if cmd not in fns:
        usage()
        return 1
    try:
        fns[cmd](*rest)
    except TypeError as e:
        print("参数不对：%s" % e)
        usage()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
