"""存档系统：保存最高分、统计信息，以及一份可"继续游戏"的对局快照。"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

_SAVE_NAME = "save.json"


class SaveSystem:
    """管理存档文件的读写（原子写）。"""

    def __init__(self, directory: str) -> None:
        """初始化存档系统。

        :param directory: 存档目录。
        """
        self.path = os.path.join(directory, _SAVE_NAME)
        self.data: Dict[str, Any] = self._empty()
        self.load()

    @staticmethod
    def _empty() -> Dict[str, Any]:
        """返回空存档结构。"""
        return {
            "high_score": 0,
            "total_kills": 0,
            "games_played": 0,
            "run": None,  # 存档的对局快照
        }

    def load(self) -> None:
        """从磁盘加载存档；缺失或损坏时重置。"""
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as fh:
                    loaded = json.load(fh)
                if isinstance(loaded, dict):
                    base = self._empty()
                    base.update(loaded)
                    self.data = base
        except (OSError, json.JSONDecodeError, ValueError):
            self.data = self._empty()

    def save(self) -> None:
        """原子写入存档。"""
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            pass

    # -- 统计 -------------------------------------------------------------
    def record_game_over(self, score: int, kills: int) -> bool:
        """记录一局结束，更新最高分。

        :param score: 本局得分。
        :param kills: 本局击杀。
        :return: 是否刷新最高分。
        """
        self.data["games_played"] = self.data.get("games_played", 0) + 1
        self.data["total_kills"] = self.data.get("total_kills", 0) + kills
        is_record = score > self.data.get("high_score", 0)
        if is_record:
            self.data["high_score"] = score
        self.data["run"] = None  # 对局结束，清除快照
        self.save()
        return is_record

    # -- 对局快照 ----------------------------------------------------------
    def save_run(self, snapshot: Dict[str, Any]) -> None:
        """保存对局快照供"继续游戏"。

        :param snapshot: 描述对局状态的字典。
        """
        self.data["run"] = snapshot
        self.save()

    def has_run(self) -> bool:
        """是否存在可继续的对局快照。"""
        return self.data.get("run") is not None

    def load_run(self) -> Optional[Dict[str, Any]]:
        """读取对局快照（不删除）。"""
        run = self.data.get("run")
        return dict(run) if isinstance(run, dict) else None

    @property
    def high_score(self) -> int:
        """最高分。"""
        return self.data.get("high_score", 0)

    @property
    def total_kills(self) -> int:
        """累计击杀。"""
        return self.data.get("total_kills", 0)

    @property
    def games_played(self) -> int:
        """已进行局数。"""
        return self.data.get("games_played", 0)
