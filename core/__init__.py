# -*- coding: utf-8 -*-
"""KaguyaPatch 核心库。

    kg_dat      [SCR-MESSAGE] 文本包解析/写出
    kg_slot     槽位映射（简体字 -> 借用的 cp932 码位）
    kg_ttf      纯 Python TrueType 读写 / cmap 重写 / 改名
    kg_font     用系统字体现做游戏字体
    kg_text     译文导出/导入
    kg_pack     一键打包（原版 dat + 译文 -> dat + 字体）
    kg_deploy   把钩子/配置/数据装进游戏目录
    kg_release  导出「汉化包」（一整套自包含文件，可直接分享）
    kg_launch   内置 Locale Emulator 转区启动 + 中文路径自动绕行
    kg_icon     给 exe 换图标（游戏图标 / 自定义 / 不带）
"""

from . import (kg_dat, kg_deploy, kg_font, kg_icon, kg_launch, kg_pack,
               kg_release, kg_slot, kg_text, kg_ttf)

__version__ = "1.1.0"
__all__ = ["kg_dat", "kg_slot", "kg_ttf", "kg_font", "kg_text", "kg_pack",
           "kg_deploy", "kg_release", "kg_launch", "kg_icon", "__version__"]
