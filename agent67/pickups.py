"""地图上的可拾取物：随机增益与道具（手榴弹/火箭弹/血量/护盾）。

rolglike 元素：怪物死亡概率掉落、地图上随机刷新。
"""

from __future__ import annotations

import math
import random
from typing import Optional

import pygame

from . import palette as P
from .config import GROUND_Y, RENDER_H, RENDER_W

# 拾取物类型
KIND_HP = "hp"
KIND_SHIELD = "shield"
KIND_GRENADE = "grenade"
KIND_ROCKET = "rocket"
KIND_DAMAGE = "damage_up"
KIND_SWIFT = "swift"
KIND_RAPID = "rapid"

# 各类型的中文显示名
KIND_NAMES = {
    KIND_HP: "医疗包 +2❤",
    KIND_SHIELD: "能量护盾",
    KIND_GRENADE: "手榴弹 x1",
    KIND_ROCKET: "火箭弹 x1",
    KIND_DAMAGE: "攻击强化",
    KIND_SWIFT: "疾行强化",
    KIND_RAPID: "急速射击",
}

# 会进入"弹药槽"的投掷/发射道具
AMMO_KINDS = {KIND_GRENADE, KIND_ROCKET}


class Pickup:
    """一个可拾取的掉落物。"""

    def __init__(self, kind: str, x: float, y: float, game: object) -> None:
        """初始化掉落物。

        :param kind: 拾取物类型。
        :param x: 世界 x。
        :param y: 世界 y（底部）。
        :param game: 上层游戏对象（用于取精灵）。
        """
        self.kind = kind
        self.x = x
        self.y = y
        self.game = game
        self.timer = 0
        self.bob = random.uniform(0, 6.28)
        self.alive = True

    def update(self) -> None:
        """更新掉落物的上下浮动。"""
        self.timer += 1
        self.bob += 0.08

    def draw(self, surf: pygame.Surface, cam_x: int) -> None:
        """绘制掉落物（带悬浮光晕与上下浮动）。"""
        if not self.alive:
            return
        img = self.game.sprites["pickups"].get(self.kind)
        if img is None:
            return
        hover = int(4 + 3 * math.sin(self.bob))
        sx = int(self.x - img.get_width() // 2 - cam_x)
        sy = int(self.y - img.get_height() - hover)
        # 光晕
        glow = ((int(self.x - cam_x), int(self.y - img.get_height() // 2)), 24, 1)
        pygame.draw.circle(surf, (80, 200, 255), glow[0], glow[1], glow[2])
        surf.blit(img, (sx, sy))

    def rect(self) -> pygame.Rect:
        """返回拾取判定矩形。"""
        img = self.game.sprites["pickups"].get(self.kind)
        w = img.get_width() if img else 18
        h = img.get_height() if img else 18
        return pygame.Rect(int(self.x - w // 2), int(self.y - h), w, h)

    def collect(self, player: object) -> None:
        """将拾取物效果应用到玩家。"""
        g = self.game
        if self.kind == KIND_HP:
            player.hp = min(player.max_hp, player.hp + 2)
            g.effects.add_text("+" + KIND_NAMES[KIND_HP], player.rect.centerx - g.camera_x,
                               player.rect.y - 12, P.UI_GOOD, 16)
        elif self.kind == KIND_SHIELD:
            player.gain_shield()
            g.effects.add_text(KIND_NAMES[KIND_SHIELD], player.rect.centerx - g.camera_x,
                               player.rect.y - 12, P.SHIELD, 16)
        elif self.kind in AMMO_KINDS:
            g.ammo[self.kind] = g.ammo.get(self.kind, 0) + 1
            g.effects.add_text(KIND_NAMES[self.kind], player.rect.centerx - g.camera_x,
                               player.rect.y - 12, P.UI_WARN, 16)
        elif self.kind == KIND_DAMAGE:
            g.buff_damage = max(1.0, g.buff_damage + 0.5)
            g.effects.add_text(KIND_NAMES[KIND_DAMAGE], player.rect.centerx - g.camera_x,
                               player.rect.y - 12, P.UI_ACCENT, 16)
        elif self.kind == KIND_RAPID:
            g.buff_rapid = max(0.0, g.buff_rapid + 0.2)
            g.effects.add_text(KIND_NAMES[KIND_RAPID], player.rect.centerx - g.camera_x,
                               player.rect.y - 12, P.UI_ACCENT, 16)
        elif self.kind == KIND_SWIFT:
            g.buff_speed = min(1.0, g.buff_speed + 0.1)
            g.effects.add_text(KIND_NAMES[KIND_SWIFT], player.rect.centerx - g.camera_x,
                               player.rect.y - 12, P.UI_ACCENT, 16)
        self.alive = False


# 可随机掉落/刷新的增益类型池
BUFF_POOL = [KIND_DAMAGE, KIND_SWIFT, KIND_RAPID, KIND_SHIELD, KIND_HP]
ITEM_POOL = [KIND_GRENADE, KIND_ROCKET, KIND_GRENADE, KIND_ROCKET, KIND_HP]


def random_buff_kind() -> str:
    """随机返回一个增益类型。"""
    return random.choice(BUFF_POOL)


def random_item_kind() -> str:
    """随机返回一个道具类型。"""
    return random.choice(ITEM_POOL)
