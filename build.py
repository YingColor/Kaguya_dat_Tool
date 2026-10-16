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

HIDDEN = ["core", "core.kg_dat", "core.kg_slot", "core.kg_ttf", "core.kg_font",
          "core.kg_text", "core.kg_pack", "core.kg_deploy", "core.kg_release",
          "core.kg_launch"]

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
    },
    "cli": {
        "name": "KaguyaPatchCLI",
        "script": os.path.join(HERE, "kaguya_patch.py"),
        "extra_data": [os.path.join(HERE, "launcher", "KaguyaEngine_Patch.exe")
                       + os.pathsep + "launcher"],
    },
}


def make_ico(path):
    """画一个简单的图标（没有就跳过）。"""
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([16, 16, 240, 240], 40, fill=(46, 84, 150, 255))
        d.text((70, 96), "汉", fill=(255, 255, 255, 255))
        img.save(path)
        return path
    except Exception:
        return None


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
    for h in HIDDEN:
        args += ["--hidden-import", h]
    for extra in t.get("extra_data", []):
        src = extra.split(os.pathsep)[0]
        if not os.path.exists(src):
            print("跳过缺失的资源：%s" % src)
            continue
        args += ["--add-data", extra]
    ico = os.path.join(ASSETS, "app.ico")
    if not os.path.exists(ico):
        ico = make_ico(ico)
    if ico:
        args += ["--icon", ico]
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
