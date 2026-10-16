# -*- coding: utf-8 -*-
"""一键打包成 exe。

    python build.py            打包全部
    python build.py launcher   只打包游戏启动器
    python build.py gui        只打包图形工具
    python build.py cli        只打包命令行工具
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist")
BUILD = os.path.join(HERE, "build")
ASSETS = os.path.join(HERE, "assets")
# 图标就放这个文件夹：丢一个 .ico 进来再重新打包，exe 就带上它。
# 留空 = 打出来的 exe 不带图标（源码里不再内置任何图标）。
ICON_DIR = os.path.join(ASSETS, "icon")

HIDDEN = ["core", "core.kg_dat", "core.kg_slot", "core.kg_ttf", "core.kg_font",
          "core.kg_text", "core.kg_pack", "core.kg_deploy", "core.kg_release",
          "core.kg_launch", "core.kg_icon"]

TARGETS = {
    "launcher": {
        "name": "KaguyaEngine_Patch",
        "script": os.path.join(HERE, "launcher", "launcher.py"),
    },
    "gui": {
        "name": "KaguyaPatch",
        "script": os.path.join(HERE, "gui", "app.py"),
        # 把启动器一起打进去，装进游戏时直接铺到游戏目录，用户不用手动复制
        "extra_data": [os.path.join(HERE, "launcher", "KaguyaEngine_Patch.exe")
                       + os.pathsep + "launcher"],
        # GUI 要能把 png/jpg 转成图标，所以内置 Pillow
        "hidden": ["PIL", "PIL.Image"],
    },
    "cli": {
        "name": "KaguyaPatchCLI",
        "script": os.path.join(HERE, "kaguya_patch.py"),
        "extra_data": [os.path.join(HERE, "launcher", "KaguyaEngine_Patch.exe")
                       + os.pathsep + "launcher"],
        "hidden": ["PIL", "PIL.Image"],
    },
}

_ICON_EXTS = (".ico", ".png", ".jpg", ".jpeg", ".bmp", ".gif")


def find_icon():
    """从 assets/icon/ 里挑一个图标。

    优先叫 `icon.ico` 的，其次该目录里第一个图片文件。都没有就返回 None
    —— 这时打出来的 exe 不带图标。放好图标后重新运行本脚本即可生效。
    """
    if not os.path.isdir(ICON_DIR):
        return None
    files = [f for f in sorted(os.listdir(ICON_DIR))
             if os.path.splitext(f)[1].lower() in _ICON_EXTS]
    if not files:
        return None
    for f in files:
        if f.lower() == "icon.ico":
            return os.path.join(ICON_DIR, f)
    return os.path.join(ICON_DIR, files[0])


def _to_ico(path, workdir):
    """保证拿到的是 .ico：不是就用 Pillow 转一个临时的。失败返回 None。"""
    if path.lower().endswith(".ico"):
        return path
    try:
        from PIL import Image
    except Exception:
        print("！%s 不是 .ico，当前环境又没有 Pillow，转不了 → 本次不带图标"
              % os.path.basename(path))
        return None
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    side = max(w, h)
    if (w, h) != (side, side):
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(im, ((side - w) // 2, (side - h) // 2))
        im = canvas
    want = [16, 24, 32, 48, 64, 128, 256]
    sizes = [s for s in want if s <= side] or [want[-1]]
    os.makedirs(workdir, exist_ok=True)
    out = os.path.join(workdir, "_icon_from_source.ico")
    im.save(out, format="ICO", sizes=[(s, s) for s in sizes])
    return out


def build_one(key, onefile=True, windowed=True):
    t = TARGETS[key]
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
            "--name", t["name"],
            "--distpath", DIST,
            "--workpath", os.path.join(BUILD, key),
            "--specpath", BUILD,
            "--paths", HERE,
            "--add-data", "%s%sassets" % (ASSETS, os.pathsep),
            "--onefile" if onefile else "--onedir",
            "--noconsole" if windowed else "--console"]
    for h in HIDDEN + t.get("hidden", []):
        args += ["--hidden-import", h]
    for extra in t.get("extra_data", []):
        src = extra.split(os.pathsep)[0]
        if not os.path.exists(src):
            print("跳过缺失的资源：%s" % src)
            continue
        args += ["--add-data", extra]
    ico = find_icon()
    if ico:
        ico = _to_ico(ico, BUILD)
    if ico:
        args += ["--icon", ico]
        print("使用图标：%s" % ico)
    else:
        # 不给 --icon 的话 PyInstaller 会塞它自己的默认图标；
        # 显式 NONE 才是真正的「不带图标」。
        args += ["--icon", "NONE"]
        print("（assets/icon/ 里没有图标，本次打出的 exe 不带图标）")
    args.append(t["script"])
    print("=" * 70)
    print("打包 %s" % t["name"])
    print(" ".join(args))
    r = subprocess.run(args, cwd=HERE)
    return r.returncode


LAUNCHER_IN_PKG = os.path.join(HERE, "launcher", "KaguyaEngine_Patch.exe")


def publish_launcher():
    """把刚打好的启动器复制一份到 launcher/ 下，供 gui/cli 打包时内嵌。"""
    src = os.path.join(DIST, "KaguyaEngine_Patch.exe")
    if not os.path.exists(src):
        return None
    dst = LAUNCHER_IN_PKG
    if os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(src):
        return dst
    shutil.copy2(src, dst)
    print("内嵌用启动器已更新：%s" % dst)
    return dst


def main():
    which = sys.argv[1:] or ["launcher", "gui", "cli"]
    os.makedirs(DIST, exist_ok=True)

    # gui/cli 要把启动器内嵌进去，所以先保证它存在（且是最新的）
    need_launcher = any(k in ("gui", "cli") for k in which)
    if need_launcher and "launcher" not in which:
        if not os.path.exists(LAUNCHER_IN_PKG):
            print("先打启动器（gui/cli 要把它内嵌进去）")
            build_one("launcher", windowed=True)
            publish_launcher()

    rc = 0
    for key in which:
        if key not in TARGETS:
            print("未知目标：%s（可选 %s）" % (key, "/".join(TARGETS)))
            rc = 2
            continue
        windowed = key != "cli"
        rc = build_one(key, windowed=windowed) or rc
        if key == "launcher":
            publish_launcher()
    print("\n产物在：%s" % DIST)
    if os.path.isdir(DIST):
        for fn in sorted(os.listdir(DIST)):
            p = os.path.join(DIST, fn)
            print("  %-28s %8.1f MB" % (fn, os.path.getsize(p) / 1048576.0))
    return rc


if __name__ == "__main__":
    sys.exit(main())
