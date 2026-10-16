# Kaguya_dat_Tool —— Kaguya 引擎「文本包」汉化工具

让 **Kaguya（かぐや）引擎**的游戏显示中文。不依赖任何现成汉化包：
从原版游戏出发，导出文本 → 翻译 → 打回去，工具自己现做一份能显示简体中文的字体，
再给你一个双击就能进的启动器。

工具本体叫 **KaguyaPatch**，打包出两个程序：图形界面的 `KaguyaPatch.exe`
和命令行的 `KaguyaPatchCLI.exe`；装进游戏里的启动器叫 `KaguyaEngine_Patch.exe`。

> **本项目由 AI 生成。** 源码与文档均由 AI 编写；虽已通过实际游戏的端到端测试，
> 仍可能存在错误或疏漏，请自行评估后使用。

---

## 免责声明

* 本仓库**只提供工具**，**不包含**任何游戏本体文件、游戏数据、译文文本、
  汉化包成品或字体文件。
* 本项目与 Kaguya 引擎的开发者、以及任何使用该引擎的游戏厂商
  **没有任何关联**，也未获得其授权或认可。文中出现的引擎名仅用于
  **说明兼容性**的**描述性**用途，相关商标与著作权归各自权利人所有。
* 请**支持正版**：使用本工具的前提是你已合法拥有所汉化的游戏。
  因使用本工具产生的任何后果由使用者自负。
* 请**不要**在本仓库的 Issue / Discussion / Pull Request 中提交或索要
  汉化包、游戏数据、译文文本、游戏截图或任何受版权保护的内容 ——
  这类内容会被直接删除。
* 本工具仅供**学习、研究与个人语言偏好**之用。
* 本工具采用 **GPL-3.0** 开源授权，详见下一节。

---

## 授权

本项目源码采用 **GNU General Public License v3.0（GPL-3.0）** 授权，
全文见仓库根目录 [`LICENSE`](LICENSE)。

随包分发的第三方组件（Nepgear、Locale Emulator 等）按**各自的原许可证**授权，
见 [`LICENSES/NOTICE.md`](LICENSES/NOTICE.md)。

---

## 一、为什么 Kaguya 的汉化比别的引擎麻烦

| 麻烦 | 说明 | 本工具怎么解决 |
|---|---|---|
| **文本包是加密的** | `message.dat` 的 `[SCR-MESSAGE] ver4.0` 结构，原版 `encrypted=1, xorkey=0xFF`，且长度字段和正文一起参与异或 | `kg_dat` 完整解析/写出，逐字节可还原 |
| **游戏只认 cp932** | 引擎把文本字节按日文 Shift-JIS 解释，简体字（总/觉/进/时/间/吗/红/观…）**根本写不进去** | 槽位映射：借 cp932 里生僻汉字的码位「寄放」简体字 |
| **系统字体没有那些字形** | 借了壳，码位上还是日文字形，直接显示会不对 | 现做字体：把槽位码位在 cmap 里指向真正的简体字形 |
| **游戏必须转区** | 中文系统下直接双击 `Start.exe` 会闪退（`0xC0000005`） | 内置绿色版 Locale Emulator，启动器自动转区 |
| **中文路径必炸** | 转区后游戏按 Shift-JIS 解路径，路径里有中文就报「システムデータのロードに失敗しました」 | 启动器自动在纯英文路径下建目录联接（Junction）绕过去 |

---

## 二、五步做完

```
第 1 步  导出日文原文          message.dat  ->  zh-CN.txt
第 2 步  打回译文、现做字体     zh-CN.txt + 原版 message.dat  ->  message.dat + *.ttf
第 3 步  装进游戏              上面两个文件 + 钩子 + 启动器  ->  游戏目录
第 4 步  双击 KaguyaEngine_Patch.exe 开始玩
第 5 步  导出汉化包            上面这些  ->  一套自包含的文件 + zip（可选）
```

### 图形界面
双击 `KaguyaPatch.exe`，五个标签页一一对应上面五步，全部中文，鼠标点就行。

### 导出汉化包（把自己的汉化分享出去）

第 5 页那个「**导出汉化包**」按钮，会生成一整套**自包含**的文件。
只需要填三样：第 2 步的输出文件夹、**汉化包名字**、**要启动的 exe 名字**，
再选个放哪儿。不需要指游戏目录。

```
<你起的名字>\
    KaguyaEngine_Patch.exe    启动器（自带转区组件）
    winmm.dll                 钩子
    Nepgear.ini               钩子配置（UTF-16 LE）
    KaguyaPatch.json          启动器配置（游戏目录留空）
    KaguyaPatchCN.ttf         中文字体
    KaguyaTrans\message.dat   中文文本
    KaguyaTrans\KaguyaPatchCN.ttf
    使用说明.txt
```

同时还会打一个同名的 **zip**，可以直接发出去。别人拿到之后：
**解压 → 把里面的东西全部复制进一个干净的原版游戏目录 → 双击
`KaguyaEngine_Patch.exe`**，就这么简单。他不需要这个工具，也不需要装任何东西。

包里刻意不含：`Nepgear.log`（运行日志）、游戏自己的文件、任何本机路径。

**为什么能直接分享**：配置里的 `game_dir` 是留空的，启动器会把自己所在的文件夹
当成游戏目录。所以游戏目录改名、搬家、整个拷到别人电脑上，都不用重装。
「装进游戏」写出来的配置也是这个样子——**装好的游戏目录本身就是一个现成的汉化包**，
想分享直接导出就行。

### 译文文件的两种导出方式

第 1 步的「导出成」下拉框可以选：

| 方式 | 长什么样 | 用途 |
|---|---|---|
| **带编号**（默认） | `◇M8A21D0F3` TAB `「……这……这是文本啦！」\n` | 最稳。ID 由原文算出，可以删行、可以乱序、可以只翻一部分 |
| **纯译文** | `「……这……这是文本啦！」\n` | 一行一条、没有编号没有注释，适合整篇丢给 AI 翻译 |

下面还有一个「保留每条结尾的 `\n`」勾选框。去掉勾就变成：

```
「……这……这是文本啦！」
不……不要……不要看了啦！\n……这……这只是一个文本而已啦！。
```

注意 **中间**的 `\n` 一定会留（那是游戏里的换行），只有末尾那个能被去掉；打包时会自动补回来。

纯译文没有编号，只能按行序对齐（人名 → 选项 → 正文），所以**顺序不能调、行数不能少**，
想保留日文的那条就留一个空行。行数对不上时打包会直接停下来报错，不会闷声写坏。
两种文件打包时都能自动识别，不用手动选。

### 命令行
```bat
python kaguya_patch.py extract  <message.dat> <译文.txt>            :: 默认带编号
python kaguya_patch.py extract  <message.dat> <译文.txt> --plain     :: 只导出译文
python kaguya_patch.py extract  <message.dat> <译文.txt> --no-nl     :: 去掉每条结尾的 \n
python kaguya_patch.py build    <原版message.dat> <译文.txt> <输出目录>
python kaguya_patch.py install  <游戏目录> <汉化数据目录>
python kaguya_patch.py launch   <游戏目录>
python kaguya_patch.py check    <游戏目录>
python kaguya_patch.py uninstall <游戏目录>
python kaguya_patch.py release  <游戏目录> <汉化数据目录> <输出目录>   :: 从汉化数据做汉化包
python kaguya_patch.py release  <游戏目录> <汉化数据目录> <输出目录> --no-zip  :: 不要 zip
python kaguya_patch.py release  <游戏目录> <汉化数据目录> <输出目录> --name 名字
python kaguya_patch.py pack     <游戏目录> <输出目录>   :: 从已装好的游戏目录直接收一份
```

---

## 三、原理（想懂再看）

### 1. 文本包格式 `[SCR-MESSAGE] ver4.0`

```
"[SCR-MESSAGE]"      13 字节
"ver4.0"              6 字节
encrypted              1 字节
xorkey                 1 字节
names   : int32 条数 + [int16 长度 + 字节] × N
choices : int32 条数 + [int16 长度 + 字节] × N
msgs    : int32 条数 + [int32 条目长 + 条目] × N
          条目 = int32 文本长 + 文本 + 语音数据(该条目剩下的全部字节)
之后    : 命令表 + 尾部数据，原样保留，不参与加密
```

`encrypted != 0` 时：names/choices 的**载荷**、以及 msgs 条目里的
「文本长字段 + 文本 + 语音」整体，按 `xorkey` 逐字节异或；
外层条数、`int16` 长度字段、`int32 条目长` 都不参与。
本工具写出时统一用 `encrypted=0`，与现成汉化包一致，游戏读得没问题。

### 2. 槽位映射（本工具的核心）

简体字里有一大批 cp932 编不出来。做法是「借壳」：

```
简体字「总」 --cp932 编不出--> 借 cp932 里生僻的「総」当槽
封包时：文本中的「总」写成「総」的 cp932 字节 (0x919C)
做字体时：把字体 cmap 里 U+7DCF(総) 指向 U+603B(总) 的字形
游戏：字节 -> cp932 解成「総」-> 字体取字形 -> 拿到的是「总」
```

槽位池是 cp932 里全部 **7076** 个汉字，会自动扣掉「正文与译文里本来就用到的字」，
剩下的才是真正可借的槽。所以卡住的**不是字数、也不是句数，而是译文里出现了
多少种「不同的汉字」**：

* 实测一份约 3.3 万行的完整汉化译文，用掉 3039 个不同汉字，
  其中 cp932 编不出的有 **1049 个**需要占槽 → 可借池还剩 3317；
* 把同一份译文的行数**放大 20 倍**（65.9 万行 / 2585 万字符），
  需要占槽的**仍然一模一样是 1049 个**；
* 想撞墙，得让译文里出现约 **4400 个**「cp932 编不出的不同汉字」——
  相当于把简体中文几乎所有字都过一遍，正常译文远达不到。

所以**译文有 30 万句也完全不是问题**。文本量变大真正影响的是
`message.dat` 的体积、打包与读写耗时、以及译文 txt 的大小（都是线性的）；
**字体体积与文本量无关**（字体是整份底座，体积固定）。

### 3. 字体怎么来的

用**你电脑上本来就有**的中文字体当底座（默认自动挑一个覆盖面最大的，
也可以手动指定），只重写它的 `cmap` 表 + 改字体名，`glyf` 等表原样不动。
所以工具不附带任何字体文件。

`kg_ttf` 是纯 Python 手写的 TrueType 读写（能处理 TTC、format 4/12 的
cmap 解析与生成、表目录与校验和重算），不依赖 fontTools。

**关于字体版权**：工具本身不含字体，但生成出来的 `KaguyaPatchCN.ttf`
会跟着汉化包一起分发，里面装的正是底座字体的字形数据 —— 这是整条链上
唯一把字体版权带出去的环节。所以：

* 只自己玩、小圈子传：用系统自带的微软雅黑就行，效果最好；
* 汉化包要公开发给别人：底座请换成允许再分发的开源字体
  （思源黑体 / Noto Sans SC，SIL OFL 1.1）。

生成字体时会**原样保留底座的全部版权与许可记录**（name 表 ID
0/7/9/11/13/14），只替换字体名相关的 ID —— 这既是事实（字形确实来自底座），
也是 OFL 对再分发的要求。

想用自己的字体：把 `.ttf` 丢进程序目录的 `fonts/` 文件夹，重开程序即可。
**要下静态版**（文件名带 `Regular`），不要下 Variable / VF 版本 ——
系统自带的 `NotoSansSC-VF.ttf` 默认那一档是最细的 Thin，拿来当底座
游戏里的字会细得像没上墨。这种情况工具会在日志里明确告警。

### 4. 转区与路径

`LEProc.exe <目标exe>` 用 `LEConfig.xml` 里的 "Run in Japanese" 配置
（GUID `8f4c8cb4-c323-4bd4-9025-bc4ecffa08b6`）启动进程。
Locale Emulator 是绿色便携的：只读同目录的 XML，配置里 `RedirectRegistry=true`，
含义是**把注册表读写重定向到它自己的私有位置**，既不会污染系统的区域设置，
也不会给游戏所在机器留下系统级改动，所以整份打包进工具里没有副作用。

启动器启动前会检查：游戏路径是否含非 ASCII 字符，是的话在
`%ProgramData%\KaguyaPatch\` 下建一个目录联接（Junction，不需要管理员权限），
从英文路径启动。联接只删自身，**绝不会动游戏目录里的文件**。

---

## 四、目录结构

```
Kaguya_dat_Tool/
  core/
    kg_dat.py      [SCR-MESSAGE] 解析 / 写出（加密、长度字段、尾部保真）
    kg_slot.py     槽位映射：简体字 -> 借用的 cp932 码位
    kg_ttf.py      纯 Python TrueType 读写 / cmap 重写 / 改字体名（保留原版权声明）
    kg_font.py     用系统字体现做游戏字体 + 底座字体挑选
    kg_text.py     译文导出 / 导入（带编号、纯译文两种格式，自动识别）
    kg_pack.py     一键打包：原版 dat + 译文 -> dat + 字体
    kg_deploy.py   把钩子 / 配置 / 数据 / 启动器装进游戏目录
    kg_release.py  导出「汉化包」（自包含，可直接分享，自动打 zip）
    kg_launch.py   转区启动 + 中文路径自动绕行 + PE 导入表扫描
  launcher/
    launcher.py    KaguyaEngine_Patch.exe 的源程序
  gui/
    app.py         KaguyaPatch.exe 的源程序（tkinter，五个标签页）
  assets/
    app.ico        图标（由 build.py 现场绘制）
    nepgear/       开源钩子 Nepgear 的编译产物（winmm.dll，MIT）+ 配置模板
    le/            绿色版 Locale Emulator 的运行时（LGPL-3.0）
  fonts/
    说明.txt       自备底座字体放这里；字体文件本身不入库
  LICENSES/        第三方组件许可证全文 + NOTICE.md
  LICENSE          本工具自身的许可证（GPL-3.0）
  kaguya_patch.py  命令行入口
  build.py         一键打包 exe
  README.md
  使用说明_新游戏怎么用.md
```

> 打包产物（`dist/`、`build/`）与汉化产物（`汉化成品/`、`效果截图/` 等）
> **都不进仓库**，见 `.gitignore`。第一次跑 `build.py` 时会自动先编译内嵌用的启动器。

---

## 五、环境

* Windows 10/11
* 打包用 Python 3.11（需要 tkinter 和 PyInstaller）
* 运行时用 PyInstaller 打出的 exe，**目标机器不需要装 Python**

```bat
python build.py            :: 打包全部
python build.py launcher   :: 只打包启动器
```

---

## 六、已知限制

* 只支持 `[SCR-MESSAGE]` 这一种文本包（Kaguya 系主流的台词包）。
  游戏菜单项（はじめから / つづきから…）是写死在 exe 里的，不在文本包里。
* 译文里如果出现底座字体没有的字符（例如 ♪），会在日志里告警，
  可以换一个底座字体重做。
* 底座选择：默认用微软雅黑；对外发布汉化包建议改用开源字体
  （见「字体怎么来的」一节），`fonts/` 里放自备字体即可。
  系统自带的 Noto Sans SC 是可变字体，默认字重极细，别直接选。
* 需要目标游戏导入了 `WINMM.dll`（Nepgear 的挂钩方式）。
  Kaguya 系基本都有；`--check` 可以先扫一遍确认。
* 极少数不需要转区的 Kaguya 游戏，启动时加 `--no-le` 即可。

---

## 七、用到的开源项目与许可证

本仓库只分发**工具**，所有第三方组件都保持**上游原样，未做任何修改**。

| 组件 | 用途 | 许可证 | 需要做的事 |
|---|---|---|---|
| **Nepgear** | Galgame 钩子框架，伪装 `winmm.dll`，提供字体替换、文件重定向 | **MIT** | 附版权声明全文 |
| ↳ 其 `winmm.dll` 是 **UPX 压缩**产物 | — | UPX 本身 GPL-2.0+，但压缩产物有**特殊例外** | **原样分发，不要再压 / 改这个 dll** |
| **Locale Emulator** | 区域模拟，让日文游戏在中文系统下正常启动 | **LGPL-3.0** | 附 `COPYING` + `COPYING.LESSER` 全文 + 给出源码出处；不得限制用户替换它 |
| **PyInstaller** | 把工具打成单文件 exe | GPL-2.0+ **例外** | 打出的 exe 可任意授权、无需署名；但内嵌的第三方内容仍受各自许可证约束 |
| **CPython / Tcl-Tk** | 运行时 | PSF / BSD 类 | 随 exe 附许可证 |

* **Nepgear**：<https://github.com/SuQiandYing/Nepgear>
  用的是上游 Release 的 x86 产物，未修改。
  （注：上游 `LICENSE.txt` 的版权人一栏是占位符 `<YOUR NAME>`，此处按原文照抄，未擅自补名。）
* **UPX 特殊例外**的三条件：使用未经修改的 UPX、stub 字节与官方发行版一致、
  未复用 stub 中的任何代码。所以**原样分发即可，绝不要动这个 dll**。
* **Locale Emulator**：<https://github.com/xupefei/Locale-Emulator>
  （原仓库 2022-04-15 归档；现行维护分支 <https://github.com/ooxxTaiwan/Locale-Emulator>）
  核心库 <https://github.com/xupefei/Locale-Emulator-Core>。
  本仓库用的版本是 **2.5.0.1**（见 `assets/le/LEVersion.xml`）。
  它只是被**原样放进游戏目录、以独立进程方式调用**（`LEProc.exe <目标exe>`），
  与本工具之间**不存在链接关系**（属于聚合），
  因此**本工具自身的源码不受 LGPL 传染**，仍按仓库根目录 `LICENSE`
  （GPL-3.0）授权。

完整说明见 `LICENSES/NOTICE.md`，许可证全文在 `LICENSES/` 目录下。

---

## 八、关于字体与游戏内容

整条链上**只有三样东西**会把版权问题带出去，本仓库一样都不含：

| 东西 | 风险在哪 | 你要注意什么 |
|---|---|---|
| **字体底座** | 生成的 `KaguyaPatchCN.ttf` 里装的正是底座字体的字形数据 | 自己玩用微软雅黑就行；**汉化包要公开发，就把底座换成开源字体**（思源 / Noto，SIL OFL）——操作见「三、3. 字体怎么来的」 |
| **游戏译文** | `message.dat` 里的译文是原作的**衍生作品** | 本仓库不含任何译文，`.gitignore` 已排除 `*.dat` |
| **游戏画面** | 截图里是厂商的美术资源 | 本仓库不含任何截图 |

这三类内容都**不要**提交到本仓库，也别放进 Issue / Discussion / Release。
