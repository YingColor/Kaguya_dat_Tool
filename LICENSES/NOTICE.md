# 第三方组件与许可证说明

本仓库（Kaguya_dat_Tool）**只包含工具本身**，不包含任何游戏数据、游戏译文、
汉化包成品或字体文件。

随本工具分发的第三方二进制如下。它们都保持**上游原样，未做任何修改**。

> **本工具自身的许可证 ≠ 这些第三方组件的许可证。**
> 本工具源码采用 **GNU General Public License v3.0（GPL-3.0）**，
> 见仓库根目录 `LICENSE`；下面这些第三方组件仍按**各自的原许可证**授权 ——
> Nepgear 的 MIT 与 Locale Emulator 的 LGPL-3.0。
> 本仓库的许可证只覆盖本项目作者创作的部分，不改变、也不对任何
> 第三方组件附加限制（LGPL-3.0 尤其不允许附加限制）。

---

## 1. Nepgear — `assets/nepgear/winmm_x86.dll`

| | |
|---|---|
| 许可证 | **MIT** |
| 上游 | https://github.com/SuQiandYing/Nepgear |
| 许可证全文 | 见本目录 `Nepgear-LICENSE.txt` |
| 本仓库使用的产物 | 上游 Release 构建出的 **x86（32 位）** `winmm.dll`，**未修改** |

上游 `LICENSE.txt` 中的版权人一栏是占位符 `<YOUR NAME>`（上游作者未填写）。
本仓库按**原文照抄**，没有擅自补填版权人。

### 关于 UPX（重要）

这个 `winmm.dll` 是 **UPX 压缩**产物：上游的 MSBuild 流程内置了 UPX 5.1.1，
产物约为原体积的 39%。

* UPX 本身是 **GPL-2.0-or-later**；
* 但 UPX 对「被它压缩过的可执行文件」提供了明确的**特殊例外**
  （见 <https://upx.github.io/license.html>，以及 UPX 发行包内的 `LICENSE`）：
  只要同时满足以下三条，压缩产物本身**不受 GPL 约束** ——

  1. 使用**未经修改**的 UPX 版本；
  2. **stub（自解压头）的字节与官方发行版一致**；
  3. **没有复用 stub 中的任何代码**。

因此：**请原样分发这个 dll，不要再压缩、修改或重新打包它。**
一旦重新压缩或改动，特殊例外就不成立，会引入 GPL 义务。

---

## 2. Locale Emulator — `assets/le/*`

| | |
|---|---|
| 许可证 | **LGPL-3.0** |
| 本仓库使用的版本 | **2.5.0.1**（见 `assets/le/LEVersion.xml`） |
| 许可证全文 | 本目录 `Locale-Emulator-COPYING.txt`（GPL-3.0）与 `Locale-Emulator-COPYING.LESSER.txt`（LGPL-3.0） |

**源码获取途径**（版本与 `LEVersion.xml` 一致）：

* 主项目：<https://github.com/xupefei/Locale-Emulator>（原仓库，2022-04-15 归档）
* 现行维护分支：<https://github.com/ooxxTaiwan/Locale-Emulator>
* 核心库：<https://github.com/xupefei/Locale-Emulator-Core>（同为 LGPL-3.0）

本仓库分发的是上游**未修改**的二进制：
`LEProc.exe`、`LECommonLibrary.dll`、`LoaderDll.dll`、`LocaleEmulator.dll`，
以及配置文件 `LEConfig.xml`、`LEVersion.xml`。

按 LGPL-3.0 的要求：

1. **已随附许可证全文**（本目录两个文件）；
2. **已给出源代码获取途径**（见上）；
3. **未对用户替换该库施加任何限制** —— 本工具只是把这些可执行文件
   **原样放进游戏目录，并以独立进程的方式调用**（`LEProc.exe <目标exe>`），
   与本工具之间**不存在链接关系**，属于「聚合（mere aggregation）」。
   因此**本工具自身的源代码不受 LGPL 传染**，仍按仓库根目录 `LICENSE`
   （GPL-3.0）授权。

> 提示：`LEConfig.xml` 里默认 `RedirectRegistry=true`，含义是把注册表读写
> **重定向到 Locale Emulator 自己的私有位置**，不会污染系统区域设置。

---

## 3. PyInstaller

| | |
|---|---|
| 许可证 | **GPL-2.0-or-later，附带例外条款** |
| 上游 | <https://github.com/pyinstaller/pyinstaller> |

用 PyInstaller 打包出来的 exe **不受 GPL 约束**：可以任意授权，也不需要署名
PyInstaller。但 exe 中**内嵌**的第三方内容（即上面第 1、2 项）仍需满足各自的许可证。

---

## 4. CPython / Tcl-Tk

| | |
|---|---|
| 许可证 | **PSF License**（CPython）/ **BSD 类**（Tcl-Tk） |

随 PyInstaller 产物一并分发，附许可证即可。

---

## 5. 字体

本仓库**不包含任何字体文件**，`fonts/` 目录里只有一份说明文字。

工具是在用户本机上、从用户自己电脑里的系统字体**现场生成**游戏字体的。
生成的字体文件如何处置由用户自行决定，详见项目 README 的「字体怎么来的」一节。
