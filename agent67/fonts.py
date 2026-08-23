"""中文字体加载。

不使用 pygame 的 SysFont（其系统字体扫描在部分机器上会崩溃），
而是直接按路径加载一款中文字体，并支持打包进 exe 后从 _MEIPASS 读取。

对外暴露 get_font(size, bold)。
"""

from __future__ import annotations

import os
import sys

import pygame

# 字体缓存：key=(size, bold)
_cache = {}


def _font_path() -> str:
    """解析可用字体文件路径。

    :return: 字体文件绝对路径；找不到返回空字符串。
    """
    candidates: list = []

    if getattr(sys, "frozen", False):
        # 打包运行：数据被解压到 sys._MEIPASS
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        candidates.append(os.path.join(base, "game_assets", "font.ttf"))
    else:
        pkg = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(os.path.dirname(pkg), "game_assets", "font.ttf"))

    # 系统常见中文字体兜底
    candidates += [
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simsun.ttc",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return ""


def get_font(size: int, bold: bool = False) -> pygame.font.Font:
    """获取（带缓存）中文字体对象。

    :param size: 字号（像素）。
    :param bold: 是否加粗。
    :return: pygame.font.Font 实例。
    """
    key = (size, bold)
    if key not in _cache:
        path = _font_path()
        font = pygame.font.Font(path, size) if path else pygame.font.Font(None, size)
        font.set_bold(bold)
        _cache[key] = font
    return _cache[key]


def clear_cache() -> None:
    """清空字体缓存（用于全屏/重开等场景，非必需）。"""
    _cache.clear()
