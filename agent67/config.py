"""全局配置与设定。

包含两类内容：
1. 游戏常量（分辨率、物理参数等），供各模块统一引用。
2. 难度/敌人强度设定，以及可持久化到 settings.json 的玩家设置。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# 渲染与分辨率
# ---------------------------------------------------------------------------
# 内部渲染画布（低分辨率，用于像素风），显示时会放大到窗口。
RENDER_W = 640
RENDER_H = 360
# 默认窗口尺寸（16:9）。全屏时自适应屏幕。
DEFAULT_WIN_W = 1280
DEFAULT_WIN_H = 720
FPS = 60

# ---------------------------------------------------------------------------
# 物理常量（基于内部画布 640x360 的像素单位）
# ---------------------------------------------------------------------------
GRAVITY = 0.55            # 重力加速度 px/frame^2
PLAYER_MOVE_SPEED = 4.2   # 玩家水平移动速度
PLAYER_JUMP_POWER = -12.5 # 起跳初速度（负值向上）
ENEMY_MOVE_SPEED = 1.5    # 敌人水平移动速度
GROUND_Y = 302            # 地面（角色脚底）基准高度
PROJECTILE_SPEED = 11.0   # 子弹速度
SKILL_COOLDOWN = 10.0     # 轰炸技能冷却（秒）
ULT_COOLDOWN = 15.0       # 大招冷却（秒）
# 成长机制：每击杀 KILLS_PER_GROWTH_TIER 个敌人，后续敌人血量 ×1.5
KILLS_PER_GROWTH_TIER = 10
GROWTH_FACTOR = 1.5

# ---------------------------------------------------------------------------
# 调色板（赛博朋克风 + 参考图配色）
# ---------------------------------------------------------------------------
from .palette import COLORS  # noqa: E402

# ---------------------------------------------------------------------------
# 敌人设定
# ---------------------------------------------------------------------------
# 敌人攻击间隔（秒）
ENEMY_ATTACK_INTERVAL = 2.0
# 普通敌人生命值（颗心）——攻击 2 次死亡
BASE_ENEMY_HP = 2
# 屏幕内同时存在的敌人上限
MAX_ONSCREEN_ENEMIES = 5
# 出现 Boss 的分数阈值
BOSS_SCORE_THRESHOLD = 800
# Boss 生命值（颗心）
BOSS_HP = 20
# 玩家最大生命值（颗心）
MAX_HEARTS = 8


@dataclass
class Difficulty:
    """一档难度所包含的各项数值放大因子。"""

    name: str
    enemy_hp_mult: float       # 敌人血量倍率
    enemy_speed_mult: float    # 敌人速度倍率
    enemy_interval_mult: float # 敌人攻击间隔倍率（>1 更慢）
    score_mult: float          # 得分倍率
    spawn_density: float       # 敌人刷新密度倍率


# 三档难度
DIFFICULTIES: Dict[str, Difficulty] = {
    "easy": Difficulty("简单", 1.0, 0.9, 1.2, 1.0, 0.9),
    "normal": Difficulty("普通", 1.0, 1.0, 1.0, 1.0, 1.0),
    "hard": Difficulty("困难", 1.2, 1.15, 0.8, 1.4, 1.2),
}

# 敌人强度档位（影响额外血量与攻击力，独立于难度）
ENEMY_STRENGTH_LEVELS: Dict[str, float] = {
    "weak": 0.8,
    "normal": 1.0,
    "strong": 1.3,
}


def _default_settings() -> Dict[str, Any]:
    """返回默认设置的字典（全屏、音效、难度、敌人强度等）。"""
    return {
        "fullscreen": False,       # 全屏
        "volume": 0.8,             # 音效音量 0.0~1.0
        "difficulty": "normal",    # 难度等级
        "enemy_strength": "normal",# 敌人强度
        "show_fps": False,         # 显示帧率
    }


class Settings:
    """玩家设置：负责从/向 settings.json 读写，并解析难度相关数值。"""

    def __init__(self, path: str) -> None:
        """初始化设置管理器。

        :param path: 设置文件路径（JSON）。不存在时使用默认值。
        """
        self.path = path
        self.data: Dict[str, Any] = _default_settings()
        self.load()

    def load(self) -> None:
        """从 JSON 加载设置；文件缺失或损坏时回退到默认值。"""
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as fh:
                    loaded = json.load(fh)
                if isinstance(loaded, dict):
                    # 合并默认值，防止旧版文件缺字段
                    merged = _default_settings()
                    merged.update(loaded)
                    self.data = merged
        except (OSError, json.JSONDecodeError, ValueError):
            # 任何异常都回退默认，保证游戏可启动
            self.data = _default_settings()

    def save(self) -> None:
        """将设置写入 JSON（原子写入：先写临时文件再替换）。"""
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            # 保存失败不阻断游戏
            pass

    def get(self, key: str, default: Any = None) -> Any:
        """读取设置项。

        :param key: 设置键名。
        :param default: 缺失时返回的默认值。
        :return: 设置值。
        """
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """写入并立即保存设置项。"""
        self.data[key] = value
        self.save()

    def toggle_fullscreen(self) -> bool:
        """切换全屏，返回切换后的状态。"""
        current = bool(self.get("fullscreen", False))
        self.set("fullscreen", not current)
        return not current

    def cycle_difficulty(self) -> str:
        """在难度档位间循环，返回新的难度键。"""
        keys = list(DIFFICULTIES.keys())
        cur = self.get("difficulty", "normal")
        nxt = keys[(keys.index(cur) + 1) % len(keys)]
        self.set("difficulty", nxt)
        return nxt

    def cycle_enemy_strength(self) -> str:
        """在敌人强度档位间循环，返回新的强度键。"""
        keys = list(ENEMY_STRENGTH_LEVELS.keys())
        cur = self.get("enemy_strength", "normal")
        nxt = keys[(keys.index(cur) + 1) % len(keys)]
        self.set("enemy_strength", nxt)
        return nxt

    # -- 由设置推导出的运行时数值 -----------------------------------------
    def difficulty(self) -> Difficulty:
        """返回当前难度对象（若键无效则回退到普通）。"""
        return DIFFICULTIES.get(self.get("difficulty", "normal"), DIFFICULTIES["normal"])

    def enemy_strength_mult(self) -> float:
        """返回当前敌人强度倍率。"""
        return ENEMY_STRENGTH_LEVELS.get(self.get("enemy_strength", "normal"), 1.0)
