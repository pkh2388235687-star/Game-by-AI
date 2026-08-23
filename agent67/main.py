"""特工67 游戏入口。

运行方式：
    python -m agent67.main            # 作为包运行
    或 直接运行打包后的 exe
"""

from __future__ import annotations

import os
import sys


def _base_dir() -> str:
    """确定可写目录（设置/存档存放处）。

    打包为 exe 后，使用 exe 所在目录；否则使用项目根目录。
    :return: 可写目录路径。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    """启动游戏。"""
    from .game import Game

    game = Game(_base_dir())
    game.run()


if __name__ == "__main__":
    main()
