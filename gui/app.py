# -*- coding: utf-8 -*-
"""KaguyaPatch 图形界面。

四个标签页，对应四步：
  1 导出日文原文  ->  2 把译文打回游戏  ->  3 装进游戏  ->  4 开始玩
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import traceback

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

_PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not getattr(sys, "frozen", False) and _PKG not in sys.path:
    sys.path.insert(0, _PKG)

from core import (kg_dat, kg_deploy, kg_font, kg_launch, kg_pack,
                  kg_release, kg_text)
from core.kg_ttf import Font, read_name

APP_TITLE = "KaguyaPatch   ——   Kaguya 引擎游戏汉化工具"
FONT_FILE = "KaguyaPatchCN.ttf"
FONT_FAMILY = "KaguyaPatchCN"
REDIRECT = "KaguyaTrans"
LOG_HEIGHT = 12        # 日志区默认行数（屏幕不够高时会自动压缩）


def read_name_from_file(path):
    """从字体文件里读出它的内部字体名。"""
    f = Font.from_file(path)
    return read_name(f.get("name"), 1) or FONT_FAMILY


class IconPicker:
    """「启动器图标」选择控件，页 3 和页 5 共用。

    三选一：使用游戏图标（默认）/ 自定义图标 / 不带图标。
    对外就一个 collect()，返回 (game_exe, image_file) 给 kg_icon 用。
    """

    MODES = [("game", "使用游戏图标（推荐）"),
             ("custom", "自定义图标"),
             ("none", "不带图标（用启动器自带的样子）")]

    def __init__(self, parent, game_dir_getter=None):
        self.game_dir_getter = game_dir_getter
        self.mode = tk.StringVar(value="game")
        self.v_exe = tk.StringVar()
        self.v_img = tk.StringVar()

        f = ttk.LabelFrame(parent, text="启动器图标", padding=8)
        f.pack(fill="x", pady=(10, 0))

        for val, text in self.MODES:
            ttk.Radiobutton(f, text=text, value=val, variable=self.mode,
                            command=self._sync).pack(anchor="w")

        self.row_exe = ttk.Frame(f)
        self.row_exe.pack(fill="x", padx=(22, 0), pady=(2, 0))
        ttk.Label(self.row_exe, text="游戏启动程序", width=14,
                  anchor="w").pack(side="left")
        ttk.Entry(self.row_exe, textvariable=self.v_exe).pack(
            side="left", fill="x", expand=True)
        ttk.Button(self.row_exe, text="浏览…", width=8,
                   command=self._pick_exe).pack(side="left", padx=(6, 0))

        self.row_img = ttk.Frame(f)
        self.row_img.pack(fill="x", padx=(22, 0), pady=(2, 0))
        ttk.Label(self.row_img, text="图标图片", width=14,
                  anchor="w").pack(side="left")
        ttk.Entry(self.row_img, textvariable=self.v_img).pack(
            side="left", fill="x", expand=True)
        ttk.Button(self.row_img, text="浏览…", width=8,
                   command=self._pick_img).pack(side="left", padx=(6, 0))

        ttk.Label(f, foreground="#888", justify="left", text=(
            "游戏图标＝从你选的启动程序（Start.exe）里读出它的图标，套到启动器上；\n"
            "自定义＝用你自己的图片（.ico 或 png / jpg 等）；"
            "不带＝保持启动器本身的样子。")
        ).pack(anchor="w", pady=(4, 0))
        self._sync()

    def _sync(self):
        m = self.mode.get()
        self._enable(self.row_exe, m == "game")
        self._enable(self.row_img, m == "custom")

    def _enable(self, row, on):
        state = "normal" if on else "disabled"
        for w in row.winfo_children():
            try:
                w.configure(state=state)
            except Exception:
                pass

    def _pick_exe(self):
        start = os.path.dirname(self.v_exe.get().strip())
        opts = {"title": "选游戏启动程序（Start.exe）",
                "filetypes": [("程序", "*.exe"), ("所有文件", "*.*")]}
        if start and os.path.isdir(start):
            opts["initialdir"] = start
        p = filedialog.askopenfilename(**opts)
        if p:
            self.v_exe.set(os.path.normpath(p))

    def _pick_img(self):
        start = os.path.dirname(self.v_img.get().strip())
        opts = {"title": "选图标图片",
                "filetypes": [("图标/图片", "*.ico *.png *.jpg *.jpeg *.bmp *.gif"),
                              ("所有文件", "*.*")]}
        if start and os.path.isdir(start):
            opts["initialdir"] = start
        p = filedialog.askopenfilename(**opts)
        if p:
            self.v_img.set(os.path.normpath(p))

    def autofill(self):
        """按游戏目录自动补上「游戏启动程序」（没填过才补）。"""
        if self.v_exe.get().strip() or not self.game_dir_getter:
            return
        try:
            gdir = self.game_dir_getter()
        except Exception:
            gdir = ""
        if not gdir or not os.path.isdir(gdir):
            return
        try:
            exe = kg_launch.find_game_exe(gdir)
        except Exception:
            exe = None
        if exe:
            self.v_exe.set(os.path.normpath(exe))

    def collect(self, log=None):
        """返回 (game_exe, image_file)；选「不带」返回 (None, None)。

        选了「使用游戏图标」却没指定主程序时**降级成不带图标**并提示，
        不抛错 —— 图标是锦上添花，不该把整个导出流程卡住。
        （除非用户明确填了一个路径却找不到，那才是真填错了。）
        """
        m = self.mode.get()
        if m == "none":
            return (None, None)
        if m == "game":
            exe = self.v_exe.get().strip()
            if not exe:
                if log:
                    log("提示：没指定游戏主程序，这次不给启动器换图标。")
                return (None, None)
            if not os.path.isfile(exe):
                raise ValueError("找不到这个游戏启动程序：\n%s" % exe)
            return (exe, None)
        img = self.v_img.get().strip()
        if not img:
            raise ValueError("选了「自定义图标」，请先指定图片文件。")
        if not os.path.isfile(img):
            raise ValueError("找不到这个图片文件：\n%s" % img)
        return (None, img)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.q = queue.Queue()
        try:
            # 顺手把「自备字体」文件夹和里面的说明准备好（缺了才写）
            kg_font.ensure_font_dir()
        except Exception:
            pass
        self._build_ui()
        self._fit_to_screen()
        self.after(80, self._drain)

    def _fit_to_screen(self):
        """把窗口调到「内容刚好放得下，又不超出屏幕」。

        窗口本来写死 880x680，但内容自然高度有 900 多，
        多出来的部分会把底部日志整个顶出窗口外（实测 y = -83，看不见）。
        这里改成先量出真实需求，再受屏幕高度约束；
        屏幕不够高时先压缩日志区，实在放不下才把窗口压进屏幕。
        """
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        need_w, need_h = self.winfo_reqwidth(), self.winfo_reqheight()

        w = min(max(need_w + 60, 900), max(sw - 60, 400))
        cap = max(sh - 100, 400)          # 留任务栏 + 标题栏

        if need_h > cap:
            # 屏幕不够高：先试着压缩日志区（每减 1 行约省 18px）
            over = need_h - cap
            shrink = min(over // 18, LOG_HEIGHT - 4)
            if shrink > 0:
                self.log.configure(height=LOG_HEIGHT - shrink)
                self.update_idletasks()
                need_h = self.winfo_reqheight()
        h = min(max(need_h, 420), cap)

        x, y = (sw - w) // 2, max(0, (sh - h) // 2 - 20)
        self.geometry("%dx%d+%d+%d" % (w, h, x, y))
        self.minsize(min(880, w), min(max(h - 160, 420), h))

    # ------------------------------------------------------------ 界面

    def _build_ui(self):
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except Exception:
            pass
        style.configure("Big.TButton", font=("Microsoft YaHei UI", 11), padding=8)

        head = ttk.Frame(self, padding=(12, 10, 12, 0))
        head.pack(fill="x")
        ttk.Label(head, text=APP_TITLE,
                  font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w")
        ttk.Label(head, foreground="#555", text=(
            "让 Kaguya 引擎的游戏显示中文。不需要现成的汉化包，"
            "也不需要你懂命令行——从原版游戏出发，四步搞定。")
        ).pack(anchor="w", pady=(2, 0))

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=10)
        self.nb = nb
        nb.add(self._tab_export(nb), text="  1. 导出日文原文  ")
        nb.add(self._tab_build(nb), text="  2. 打回译文、做字体  ")
        nb.add(self._tab_install(nb), text="  3. 装进游戏  ")
        nb.add(self._tab_play(nb), text="  4. 开始玩 / 还原  ")
        nb.add(self._tab_pack(nb), text="  5. 导出汉化包  ")
        nb.bind("<<NotebookTabChanged>>", self._on_tab)

        box = ttk.LabelFrame(self, text="日志", padding=6)
        box.pack(fill="both", padx=12, pady=(0, 4))
        self.log = tk.Text(box, height=LOG_HEIGHT, wrap="word",
                           font=("Consolas", 9), background="#fbfbfb")
        sb = ttk.Scrollbar(box, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)

        bar = ttk.Frame(self, padding=(12, 0, 12, 10))
        bar.pack(fill="x")
        self.status = ttk.Label(bar, text="就绪", foreground="#666")
        self.status.pack(side="left")

    # ------------------------------------------------------------ 小工具

    def _row(self, parent, label, var, is_dir=True, browse_text="浏览…",
             tip="", kind=None, start_var=None, default_name=""):
        """一行「标签 + 输入框 + 按钮」。

        kind 定这个按钮弹哪种对话框：
            "dir"   选一个文件夹
            "open"  选一个**已经存在**的文件（当输入用）
            "save"  真正的「另存为」：能挑文件夹、也能输新文件名
            "text"  纯文本输入，不要按钮（用来填名字之类的）
        """
        mode = kind or ("dir" if is_dir else "open")

        if mode == "text":
            f = ttk.Frame(parent)
            f.pack(fill="x", pady=4)
            ttk.Label(f, text=label, width=14, anchor="w").pack(side="left")
            ttk.Entry(f, textvariable=var).pack(side="left", fill="x",
                                                expand=True)
            if tip:
                ttk.Label(f, text=tip, foreground="#888").pack(side="left",
                                                               padx=(6, 0))
            return f

        f = ttk.Frame(parent)
        f.pack(fill="x", pady=4)
        ttk.Label(f, text=label, width=14, anchor="w").pack(side="left")
        e = ttk.Entry(f, textvariable=var)
        e.pack(side="left", fill="x", expand=True)
        if tip:
            ttk.Label(f, text=tip, foreground="#888").pack(side="left",
                                                           padx=(6, 0))

        def _start_dir():
            """对话框从哪个目录开始：先看当前值，再看 start_var。"""
            cands = [var.get().strip()]
            if start_var is not None:
                try:
                    cands.append(start_var.get().strip())
                except Exception:
                    pass
            for c in cands:
                if not c:
                    continue
                if os.path.isdir(c):
                    return c
                d = os.path.dirname(c)
                if os.path.isdir(d):
                    return d
            return None

        def pick():
            start = _start_dir()
            if mode == "dir":
                opts = {"title": label}
                if start:
                    opts["initialdir"] = start
                p = filedialog.askdirectory(**opts)
            elif mode == "save":
                cur = var.get().strip()
                name = ""
                if cur and not os.path.isdir(cur):
                    name = os.path.basename(cur)
                dn = default_name() if callable(default_name) else default_name
                opts = {"title": label, "defaultextension": ".txt",
                        "initialfile": name or dn or "译文.txt",
                        "filetypes": [("文本文件", "*.txt"),
                                      ("所有文件", "*.*")]}
                if start:
                    opts["initialdir"] = start
                p = filedialog.asksaveasfilename(**opts)
            else:
                opts = {"title": label}
                if start:
                    opts["initialdir"] = start
                p = filedialog.askopenfilename(**opts)
            if p:
                var.set(os.path.normpath(p))

        ttk.Button(f, text=browse_text, command=pick, width=9).pack(
            side="left", padx=(6, 0))
        return f

    def _default_export_name(self):
        """导出译文时给「另存为」一个顺手的默认文件名。"""
        label = self.v_expmode.get() if hasattr(self, "v_expmode") else ""
        if "纯译文" in label:
            return "译文_纯译文.txt"
        return "译文.txt"

    def _export_mode(self):
        """下拉框当前选的是哪种导出方式。"""
        label = self.v_expmode.get()
        for key, text in kg_text.EXPORT_MODES:
            if text == label:
                return key
        return kg_text.MODE_ID

    def _say(self, s):
        self.q.put(("log", str(s)))

    def _status(self, s):
        """任何线程都能调：状态栏更新也走队列，由主线程来改。"""
        self.q.put(("status", str(s)))

    def _drain(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                try:
                    if kind == "log":
                        self.log.insert("end", payload + "\n")
                        self.log.see("end")
                    elif kind == "status":
                        self.status.configure(text=payload)
                    elif kind == "call":
                        fn, arg = payload
                        if fn:
                            fn(arg)
                except Exception:
                    self.log.insert("end", traceback.format_exc() + "\n")
                    self.log.see("end")
        except queue.Empty:
            pass
        self.after(80, self._drain)

    def _run(self, fn, done=None, busy="处理中…"):
        """把耗时活儿丢到后台线程跑，界面不卡。

        注意：后台线程绝对不能碰 tk 控件（会抛 main thread is not in
        main loop）。所有界面更新都塞进队列，由 _drain 在主线程里做。
        """
        self._status(busy)

        def worker():
            try:
                result = fn()
            except Exception as e:
                msg = str(e)
                self._say("")
                self._say("出错：%s" % msg)
                self._say(traceback.format_exc())
                self._status("出错")
                # msg 要先取出来：except 块一结束 e 就失效了
                self.q.put(("call", (lambda _a, m=msg: messagebox.showerror(
                    "出错", m), None)))
                return
            self._status("完成")
            if done:
                self.q.put(("call", (done, result)))

        threading.Thread(target=worker, daemon=True).start()

    def _task(self, collect, work, done=None, busy="处理中…"):
        """collect 在主线程里跑（只有它能读输入框），work 在后台跑。

        tk 控件只能在主线程碰，所以参数一律先在主线程取好，再交给后台。
        """
        try:
            args = collect()
        except Exception as e:
            self._say("出错：%s" % e)
            messagebox.showerror("出错", str(e))
            return
        if isinstance(args, tuple):
            self._run(lambda: work(*args), done, busy=busy)
        elif args is None:
            self._run(work, done, busy=busy)
        else:
            self._run(lambda: work(args), done, busy=busy)

    # ------------------------------------------------------------ 页 1

    def _tab_export(self, nb):
        f = ttk.Frame(nb, padding=14)
        ttk.Label(f, foreground="#444", text=(
            "从游戏里读出全部日文台词，导成一份 txt。\n"
            "你（或者翻译）只要改每个制表符后面的文字就行。")
        ).pack(anchor="w", pady=(0, 10))

        self.v_game = tk.StringVar()
        self.v_dat = tk.StringVar()
        self.v_txt = tk.StringVar()
        self._row(f, "游戏目录", self.v_game, True,
                  tip="里面有 Start.exe 的那一层")
        self._row(f, "文本包 message.dat", self.v_dat, False,
                  tip="留空就自动从游戏目录里找")
        self._row(f, "译文文件（导出到）", self.v_txt, False,
                  kind="save", browse_text="另存为…",
                  start_var=self.v_game,
                  default_name=self._default_export_name,
                  tip="挑个文件夹、顺便起个名字")

        row = ttk.Frame(f)
        row.pack(fill="x", pady=(10, 2))
        ttk.Label(row, text="导出成", width=14, anchor="w").pack(side="left")
        self.v_expmode = tk.StringVar(value=kg_text.EXPORT_MODES[0][1])
        self.cb_expmode = ttk.Combobox(row, textvariable=self.v_expmode,
                                       width=52, state="readonly")
        self.cb_expmode["values"] = [lb for _k, lb in kg_text.EXPORT_MODES]
        self.cb_expmode.pack(side="left")

        row2 = ttk.Frame(f)
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="", width=14).pack(side="left")
        self.v_keepnl = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text="保留每条结尾的 \\n",
                        variable=self.v_keepnl).pack(side="left")
        ttk.Label(row2, foreground="#888",
                  text="（去勾看起来更干净，打包时会自动补回去）"
                  ).pack(side="left", padx=(6, 0))

        def collect():
            """在主线程里读界面（后台线程绝对不许碰输入框）。"""
            dat = self.v_dat.get().strip()
            if not dat:
                g = self.v_game.get().strip()
                if not g:
                    raise ValueError("先选游戏目录")
                cand = [os.path.join(g, "message.dat"),
                        os.path.join(g, "KaguyaTrans", "message.dat")]
                dat = next((c for c in cand if os.path.exists(c)), "")
                if not dat:
                    raise ValueError("游戏目录里没有 message.dat")
                self.v_dat.set(dat)
            out = self.v_txt.get().strip()
            if not out:
                raise ValueError("先选译文文件的保存位置")
            return (dat, out, self._export_mode(), bool(self.v_keepnl.get()))

        def work(dat, out, mode, keep):
            self._say("导出中：%s" % dat)
            d = kg_dat.parse_file(dat)
            counts = kg_text.export_translation(d, out, mode=mode,
                                                keep_trailing_nl=keep)
            self._say("完成。人名 %d 条、选项 %d 条、正文 %d 条"
                      % (counts["names"], counts["choices"],
                         counts["messages"]))
            self._say("译文文件：%s" % out)
            if mode == kg_text.MODE_PLAIN:
                self._say("纯译文格式：一共 %d 行，顺序是人名 → 选项 → 正文。"
                          % counts["lines"])
                self._say("打包时按行对齐，所以顺序不能调、行数不能少"
                          "（想保持日文就留个空行）。")
            else:
                self._say("◇ 后面那串编号不要动；删掉的行会自动保持原文。")
            return {"out": out, "counts": counts, "mode": mode}

        def done(info=None):
            info = info or {}
            out = info.get("out") or self.v_txt.get()
            c = info.get("counts") or {}
            if info.get("mode") == kg_text.MODE_PLAIN:
                body = ("这种格式没有编号，翻译完打包时按行对齐，务必记住：\n\n"
                        "· 顺序不能调（人名 → 选项 → 正文）\n"
                        "· 一行都不能删（想保留日文就留一个空行）\n\n"
                        "一共 %d 行 = 人名 %d + 选项 %d + 正文 %d。"
                        % (c.get("lines", 0), c.get("names", 0),
                           c.get("choices", 0), c.get("messages", 0)))
            else:
                body = ("用记事本或 Translater++ 打开，只改制表符后面的文字。\n"
                        "◇ 后面那串编号别动；删掉的行会自动保持日文。")
            messagebox.showinfo("导出完成", "已经导出到：\n%s\n\n%s" % (out, body))

        ttk.Button(f, text="开始导出", style="Big.TButton",
                   command=lambda: self._task(collect, work, done,
                                              busy="正在导出…")).pack(
            anchor="w", pady=14)
        return f

    # ------------------------------------------------------------ 页 2

    def _tab_build(self, nb):
        f = ttk.Frame(nb, padding=14)
        ttk.Label(f, foreground="#444", text=(
            "把翻译好的文本重新写回游戏能读的格式，同时现做一份能显示简体中文的字体。\n"
            "字体是用你电脑上本来就有的中文字体做的，不用另外下载。")
        ).pack(anchor="w", pady=(0, 10))

        self.v_src = tk.StringVar()
        self.v_tr = tk.StringVar()
        self.v_out = tk.StringVar()
        self._row(f, "原版 message.dat", self.v_src, False,
                  tip="必须是没汉化过的原版，尾部数据要以它为准")
        self._row(f, "译文文件", self.v_tr, False, tip="第 1 步导出的那份")
        self._row(f, "输出文件夹", self.v_out, True)

        self.v_family = tk.StringVar(value=FONT_FAMILY)
        self.v_fontname = tk.StringVar(value=FONT_FILE)
        self.v_base = tk.StringVar(value="自动挑一个中文字体")

        row = ttk.Frame(f)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="字体名", width=14, anchor="w").pack(side="left")
        ttk.Entry(row, textvariable=self.v_fontname, width=26).pack(side="left")
        ttk.Label(row, text="字体内部名", width=12, anchor="e").pack(side="left")
        ttk.Entry(row, textvariable=self.v_family, width=20).pack(side="left")

        row2 = ttk.Frame(f)
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="底座字体", width=14, anchor="w").pack(side="left")
        self.cb_base = ttk.Combobox(row2, textvariable=self.v_base, width=44,
                                    state="readonly")
        # 标签 -> (显示名, 路径, 序号)；界面上的字带备注，实际用的还是干净值
        self._base_map = {}
        for label, val in kg_font.base_font_menu():
            self._base_map[label] = val
        self.cb_base["values"] = ["自动挑一个中文字体"] + list(self._base_map)
        self.cb_base.pack(side="left")

        ttk.Label(f, text="底座就是「从哪个字体里借中文字形」。做出来给别人用的话，"
                          "选开源字体（思源/Noto）更稳妥；", anchor="w",
                  foreground="#666666").pack(fill="x", pady=(0, 0))
        ttk.Label(f, text="想用自己下载的字体，把 .ttf 放进程序目录的 fonts 文件夹，"
                          "重启一下就会出现在上面。", anchor="w",
                  foreground="#666666").pack(fill="x", pady=(0, 4))

        def collect():
            src = self.v_src.get().strip()
            tr = self.v_tr.get().strip()
            out = self.v_out.get().strip()
            if not (src and tr and out):
                raise ValueError("三项都要填：原版 message.dat、译文文件、输出文件夹")
            return (src, tr, out, self.v_base.get(),
                    self.v_family.get().strip() or FONT_FAMILY,
                    self.v_fontname.get().strip() or FONT_FILE)

        def work(src, tr, out, base_sel, family, font_file):
            base = None
            if base_sel and base_sel != "自动挑一个中文字体":
                base = self._base_map.get(base_sel)
                if base is None:
                    for n, p, i in kg_font.list_base_fonts():
                        if n == base_sel:
                            base = (n, p, i)
                            break
            self._say("=" * 60)
            man = kg_pack.build(src, tr, out, base_font=base,
                                family=family, font_file=font_file,
                                log=self._say)
            self._say("汉化数据在：%s" % out)
            return man

        def done(man=None):
            messagebox.showinfo(
                "做好了",
                "两个文件已经生成：\n"
                "  message.dat     —— 中文文本\n"
                "  %s  —— 中文字体\n\n"
                "接下来去第 3 步，把它装进游戏。"
                % ((man or {}).get("font_file", FONT_FILE)))

        ttk.Button(f, text="开始打包", style="Big.TButton",
                   command=lambda: self._task(collect, work, done,
                                              busy="正在打包、做字体…")).pack(
            anchor="w", pady=14)
        return f

    # ------------------------------------------------------------ 页 3

    def _tab_install(self, nb):
        f = ttk.Frame(nb, padding=14)
        ttk.Label(f, foreground="#444", text=(
            "把上一步做好的文件 + 显示中文要用的钩子 + 启动器，一起放进游戏目录。\n"
            "原来的文件会保留，随时可以在第 4 步还原。\n"
            "想把自己做的汉化打成包发给别人，去第 5 页。")
        ).pack(anchor="w", pady=(0, 10))

        self.v_igame = tk.StringVar()
        self.v_idata = tk.StringVar()
        self._row(f, "游戏目录", self.v_igame, True,
                  tip="里面有 Start.exe 的那一层")
        self._row(f, "汉化数据文件夹", self.v_idata, True,
                  tip="第 2 步的输出文件夹（导出汉化包时可以留空）")

        ttk.Label(f, foreground="#888", text=(
            "（想换字体请回第 2 步选「底座字体」——字体是在那一步做出来的）")
        ).pack(anchor="w", pady=(2, 0))
        ttk.Label(f, foreground="#888", justify="left", text=(
            "「游戏目录」这两栏只是被“读”：导出汉化包时用它记下要启动哪个 exe、\n"
            "顺便给包起个名。工具从头到尾不会改动游戏里的任何文件。")
        ).pack(anchor="w", pady=(2, 0))

        self.icon_install = IconPicker(
            f, game_dir_getter=lambda: self.v_igame.get().strip())

        def collect():
            game = self.v_igame.get().strip()
            data = self.v_idata.get().strip()
            if not game:
                raise ValueError("先选游戏目录")
            if not data:
                raise ValueError("先选汉化数据文件夹")
            dat = os.path.join(data, "message.dat")
            if not os.path.exists(dat):
                raise ValueError("这个文件夹里没有 message.dat，确认一下是不是第 2 步的输出")

            fonts = [fn for fn in os.listdir(data) if fn.lower().endswith(".ttf")]
            if not fonts:
                raise ValueError("这个文件夹里没有 .ttf 字体")
            exe = kg_launch.find_game_exe(game)
            self.icon_install.autofill()
            icon_game_exe, icon_image = self.icon_install.collect(
                log=self._say)
            return (game, data, dat, os.path.join(data, fonts[0]),
                    os.path.basename(exe) if exe else "",
                    icon_game_exe, icon_image)

        def work(game, data, dat, font, game_exe, icon_game_exe, icon_image):
            family = read_name_from_file(font)
            res = kg_deploy.deploy(game, message_dat=dat, font_file=font,
                                   font_family=family, redirect_dir=REDIRECT,
                                   game_exe=game_exe, log=self._say,
                                   icon_game_exe=icon_game_exe,
                                   icon_image=icon_image)
            if game_exe:
                self._say("游戏主程序：%s" % game_exe)
            else:
                self._say("⚠ 没找到游戏主程序，请在游戏目录里确认 exe 名字")
            if res.get("launcher"):
                self._say("启动器已放好：%s" % os.path.basename(res["launcher"]))
            else:
                self._say("⚠ 没能自动放启动器，请从工具的 dist 文件夹里"
                          "把 KaguyaEngine_Patch.exe 复制进游戏目录")
            self._say("安装完成。双击游戏目录里的 KaguyaEngine_Patch.exe "
                      "就能玩中文版。")
            return game

        def done(game=None):
            messagebox.showinfo("装好了",
                                "已经装进：\n%s\n\n"
                                "双击游戏目录里的 KaguyaEngine_Patch.exe 就能玩中文版，\n"
                                "也可以直接在第 4 页点「启动游戏」。\n\n"
                                "顺便说一句：现在这个游戏目录本身就已经是个"
                                "现成的汉化包了，想发给朋友可以点「导出汉化包」。" % (game or ""))

        btns = ttk.Frame(f)
        btns.pack(anchor="w", pady=14)
        ttk.Button(btns, text="装进游戏", style="Big.TButton",
                   command=lambda: self._task(collect, work, done,
                                              busy="正在安装…")).pack(side="left")

        ttk.Label(f, foreground="#666", text=(
            "装完之后，这个游戏目录本身就已经是一份现成的汉化包了。\n"
            "想把它打成能直接发出去的压缩包，去第 5 页。")
        ).pack(anchor="w", pady=(0, 0))
        return f

    # ------------------------------------------------------------ 页 5

    def _tab_pack(self, nb):
        f = ttk.Frame(nb, padding=14)
        ttk.Label(f, foreground="#444", text=(
            "把第 2 步做好的两个文件（中文 message.dat + 中文字体），"
            "连同启动器和钩子打成一套自包含的包。\n"
            "别人拿到后解压 → 全部复制进干净的原版游戏目录 → 双击就能玩中文版，"
            "不需要这个工具。")
        ).pack(anchor="w", pady=(0, 10))

        self.v_pdata = tk.StringVar()
        self.v_pname = tk.StringVar(value="KaguyaPatch汉化包_中文版")
        self.v_pexe = tk.StringVar(value="Start.exe")
        self.v_plauncher = tk.StringVar(value=kg_deploy.LAUNCHER_NAME)
        self.v_pout = tk.StringVar()

        self._row(f, "汉化数据文件夹", self.v_pdata, True,
                  tip="第 2 步的输出：里面有 message.dat 和 .ttf")
        self._row(f, "汉化包名字", self.v_pname, False, kind="text",
                  tip="压缩包用这个名字，随便改")
        self._row(f, "要启动的 exe", self.v_pexe, False, kind="text",
                  tip="游戏主程序名，一般就是 Start.exe")
        self._row(f, "启动器文件名", self.v_plauncher, False, kind="text",
                  tip="包里那个启动器叫什么；留空就用默认名")
        self._row(f, "放哪儿", self.v_pout, True,
                  tip="汉化包（一个 zip）生成到这个文件夹里")

        ttk.Label(f, foreground="#888", justify="left", text=(
            "exe 名字填错也不致命：拿包的人双击启动器时，它自己还会再找一遍。\n"
            "包里不含游戏本体、不含运行日志，也不含任何本机路径。")
        ).pack(anchor="w", pady=(2, 0))

        self.icon_pack = IconPicker(
            f, game_dir_getter=lambda: self.v_igame.get().strip())

        def collect():
            data = self.v_pdata.get().strip()
            name = self.v_pname.get().strip()
            exe = self.v_pexe.get().strip()
            out = self.v_pout.get().strip()
            if not data or not os.path.isdir(data):
                raise ValueError("先选「汉化数据文件夹」（第 2 步的输出）")
            if not os.path.exists(os.path.join(data, "message.dat")):
                raise ValueError("这个文件夹里没有 message.dat，"
                                 "确认一下是不是第 2 步的输出")
            if not [fn for fn in os.listdir(data)
                    if fn.lower().endswith(".ttf")]:
                raise ValueError("这个文件夹里没有 .ttf 字体，"
                                 "确认一下是不是第 2 步的输出")
            if not name:
                raise ValueError("给汉化包起个名字")
            if not exe:
                raise ValueError("填一下要启动的 exe 名字（一般 Start.exe）")
            if not out:
                raise ValueError("选个「放哪儿」——汉化包要生成到哪个文件夹")
            self.icon_pack.autofill()
            icon_game_exe, icon_image = self.icon_pack.collect(
                log=self._say)
            out = os.path.normpath(out)
            lname = self.v_plauncher.get().strip()

            # 同名 zip 已经存在：在这里先问清楚，别等到打包时才报错。
            # collect 跑在主线程，所以能弹窗。
            overwrite = False
            zpath = os.path.join(out, name + ".zip")
            if os.path.exists(zpath):
                overwrite = messagebox.askyesno(
                    "同名汉化包已存在",
                    "这个位置已经有一个同名的汉化包了：\n%s\n\n"
                    "要覆盖它吗？\n\n"
                    "选「否」可以回去改个名字再导出。" % zpath)
                if not overwrite:
                    raise ValueError("已取消。换个名字再导出，"
                                     "或者先手动删掉上面那个 zip。")
            return (data, name, exe, out, lname,
                    icon_game_exe, icon_image, overwrite)

        def work(data, name, exe, out, lname, icon_game_exe, icon_image,
                 overwrite):
            fonts = [fn for fn in os.listdir(data)
                     if fn.lower().endswith(".ttf")]
            if not exe.lower().endswith(".exe"):
                self._say("提示：「%s」看着不像 exe 名字，"
                          "拿包的人启动时它会自己再扫一遍。" % exe)
            self._say("打包：%s" % data)
            return kg_release.make_pack(
                out, message_dat=os.path.join(data, "message.dat"),
                font_file=os.path.join(data, fonts[0]),
                game_exe=os.path.basename(exe), folder_name=name,
                launcher_name=lname, overwrite=overwrite,
                log=self._say, icon_game_exe=icon_game_exe,
                icon_image=icon_image)

        ttk.Button(f, text="导出汉化包", style="Big.TButton",
                   command=lambda: self._task(collect, work, self._pack_done,
                                              busy="正在导出汉化包…")).pack(
            anchor="w", pady=14)
        return f

    def _pack_done(self, res=None):
        res = res or {}
        zip_path = res.get("zip") or ""
        body = "汉化包已经做好了：\n\n%s\n" % zip_path
        body += ("\n怎么用：解压后把里面的东西全部复制进游戏目录"
                 "（有 Start.exe 的那一层），双击里头的启动器。\n"
                 "这个包是自包含的，别人不需要这个工具。")
        messagebox.showinfo("汉化包做好了", body)

    # ------------------------------------------------------------ 页 4

    def _tab_play(self, nb):
        f = ttk.Frame(nb, padding=14)
        ttk.Label(f, foreground="#444", text=(
            "游戏必须转成日文区域才能启动（否则会闪退），这一步工具会自动处理。\n"
            "如果游戏目录路径里有中文，工具会自动在英文路径下开个通道绕过去。")
        ).pack(anchor="w", pady=(0, 10))

        self.v_pgame = tk.StringVar()
        self._row(f, "游戏目录", self.v_pgame, True)

        btns = ttk.Frame(f)
        btns.pack(anchor="w", pady=14)

        def game_dir():
            """取游戏目录，第 4 页没填就自动沿用第 3 页的。"""
            g = self.v_pgame.get().strip()
            if not g and self.v_igame.get().strip():
                g = self.v_igame.get().strip()
                self.v_pgame.set(g)
            if not g:
                raise ValueError(
                    "还没选游戏目录。\n\n"
                    "点上面的「浏览…」，挑那个里面有 Start.exe 的文件夹。\n"
                    "如果第 3 步已经装过，这里会自动填上。")
            if not os.path.isdir(g):
                raise ValueError("这个文件夹不存在：\n%s" % g)
            return g

        def launch():
            g = game_dir()
            self._say("启动：%s" % g)
            self._run(lambda: kg_launch.launch(g, log=self._say),
                      busy="正在启动游戏…")

        def uninstall():
            g = game_dir()
            if not messagebox.askyesno(
                    "确认",
                    "把汉化钩子和汉化文件从游戏目录里删掉，恢复成原版？\n\n"
                    "游戏本身的文件（Start.exe、各个 .arc、原版数据）\n"
                    "一个都不会动。"):
                return
            removed = kg_deploy.uninstall(g, REDIRECT, log=self._say)
            self._say("（%s 和 %s 是工具自己放的小文件，留着不影响游戏，"
                      "要干净可以手动删掉）"
                      % (kg_deploy.LAUNCHER_NAME, kg_deploy.CONFIG_NAME))
            if removed:
                self._say("共删除 %d 项。" % len(removed))
                messagebox.showinfo("好了", "游戏已经恢复成原版。\n删除了 %d 项。"
                                    % len(removed))
            else:
                self._say("这个目录里没有找到汉化文件——本来就是原版。")
                messagebox.showinfo("好了", "没找到汉化文件，这个目录本来就是原版。")

        def check():
            g = game_dir()
            self._say("=" * 60)
            exe = kg_launch.find_game_exe(g)
            self._say("主程序：%s" % exe)
            if exe:
                info = kg_launch.scan_pe(exe)
                if info:
                    self._say("位数：%d 位" % info["arch"])
                    self._say("导入 WINMM.dll：%s"
                              % ("是（可以挂钩子）"
                                 if any(n.lower() == "winmm.dll"
                                        for n in info["imports"]) else "否"))
            self._say("路径含中文：%s" % ("是（会自动绕过）"
                                      if not kg_launch.is_ascii_path(g) else "否"))
            self._say("汉化是否已装：%s"
                      % ("是" if os.path.exists(os.path.join(g, "winmm.dll"))
                         and os.path.exists(os.path.join(g, "Nepgear.ini"))
                         else "否"))
            try:
                kg_launch.work_root()
                self._say("临时工作目录：可用")
            except Exception as e:
                self._say("临时工作目录：不可用（%s）" % e)
            try:
                kg_launch.stage_le()
                self._say("转区组件（Locale Emulator）：就绪")
            except Exception as e:
                self._say("转区组件：缺失（%s）" % e)

        ttk.Button(btns, text="启动游戏", style="Big.TButton",
                   command=self._guard(launch)).pack(side="left")
        ttk.Button(btns, text="自检", style="Big.TButton",
                   command=self._guard(check)).pack(side="left", padx=8)
        ttk.Button(btns, text="卸掉汉化，恢复原版", style="Big.TButton",
                   command=self._guard(uninstall)).pack(side="left")

        ttk.Label(f, foreground="#666", text=(
            "小提示：\n"
            "· 第一次启动会慢一点，请耐心等窗口出来。\n"
            "· 如果游戏闪退，先点「自检」看看。\n"
            "· 想直接双击进游戏，把 KaguyaEngine_Patch.exe 放到游戏目录里就行。")
        ).pack(anchor="w", pady=18)
        return f

    def _guard(self, fn):
        def wrapped():
            try:
                fn()
            except Exception as e:
                self._say("出错：%s" % e)
                messagebox.showerror("出错", str(e))
        return wrapped

    def _on_tab(self, _event=None):
        """切页时顺手把参数带过去，省得用户重复填。"""
        try:
            idx = self.nb.index(self.nb.select())
        except Exception:
            return

        if idx == 3:
            # 第 4 页：还没填游戏目录，就沿用第 3 页的
            v = getattr(self, "v_pgame", None)
            g = getattr(self, "v_igame", None)
            if v is None or g is None:
                return
            if not v.get().strip() and g.get().strip():
                v.set(g.get().strip())
            return

        if idx == 4:
            # 第 5 页：从第 3 页带「汉化数据文件夹」过来，顺手填好「放哪儿」
            dst = getattr(self, "v_pdata", None)
            if dst is None:
                return
            src = getattr(self, "v_idata", None)
            if not dst.get().strip() and src is not None \
                    and src.get().strip():
                dst.set(src.get().strip())
            out = getattr(self, "v_pout", None)
            data = dst.get().strip()
            if out is not None and not out.get().strip() \
                    and data and os.path.isdir(data):
                out.set(os.path.dirname(os.path.abspath(data)))


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
