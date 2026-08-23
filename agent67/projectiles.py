"""投射物：玩家/敌人子弹、手榴弹、火箭弹。

所有投射物统一由 Projectile 管理；手榴弹受重力、落地爆炸，火箭弹直飞命中爆炸。
"""

from __future__ import annotations

import math
from typing import Optional

import pygame

from . import palette as P
from .config import GROUND_Y, PROJECTILE_SPEED
from .world import World


class Projectile:
    """一个投射物实例。"""

    def __init__(
        self,
        x: float,
        y: float,
        vx: float,
        vy: float,
        kind: str,
        owner: str,
        damage: int,
        splash: float = 0.0,
    ) -> None:
        """初始化投射物。

        :param x: 初始 x。
        :param y: 初始 y。
        :param vx: 水平速度。
        :param vy: 垂直速度。
        :param kind: "bullet" | "enemy_bullet" | "grenade" | "rocket"。
        :param owner: "player" | "enemy"。
        :param damage: 直接命中伤害。
        :param splash: 爆炸半径（0 表示无溅射）。
        """
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.kind = kind
        self.owner = owner
        self.damage = damage
        self.splash = splash
        self.radius = 4 if kind in ("bullet", "enemy_bullet") else 7
        self.life = 120
        self.alive = True
        self.exploded = False
        self.trail_timer = 0

    @property
    def rect(self) -> pygame.Rect:
        """投影物当前占用的矩形（用于碰撞）。"""
        r = self.radius
        return pygame.Rect(int(self.x - r), int(self.y - r), r * 2, r * 2)

    def update(self, world: World) -> None:
        """更新投射物逻辑。

        :param world: 世界对象（手榴弹需要地面碰撞）。
        """
        self.life -= 1
        if self.life <= 0:
            self.alive = False
            return

        if self.kind == "grenade":
            # 手榴弹：受重力，落地或撞平台爆炸
            self.vy += 0.35
            prev_bottom = self.y
            self.y += self.vy
            self.x += self.vx
            on_ground = False
            if self.y >= GROUND_Y - self.radius:
                self.y = GROUND_Y - self.radius
                on_ground = True
            for p in world.platforms:
                r = p.rect
                if self.rect.colliderect(r) and prev_bottom <= r.top:
                    self.y = r.top - self.radius
                    on_ground = True
            if on_ground:
                self.alive = False
                self.exploded = True
            return

        # 直飞型：子弹/火箭弹/敌方子弹
        self.x += self.vx
        self.y += self.vy
        if self.kind == "rocket":
            self.trail_timer += 1

    def draw(self, surf: pygame.Surface, cam_x: int) -> None:
        """绘制投射物。"""
        sx = int(self.x - cam_x)
        sy = int(self.y)
        if self.kind == "bullet":
            pygame.draw.rect(surf, (255, 240, 160), (sx - 4, sy - 2, 8, 4))
            pygame.draw.rect(surf, (255, 255, 255), (sx + 2, sy - 1, 3, 2))
        elif self.kind == "enemy_bullet":
            pygame.draw.rect(surf, (255, 120, 120), (sx - 3, sy - 3, 6, 6))
            pygame.draw.circle(surf, (255, 200, 200), (sx, sy), 2)
        elif self.kind == "grenade":
            pygame.draw.rect(surf, (70, 74, 84), (sx - 4, sy - 5, 8, 9))
            pygame.draw.rect(surf, (120, 124, 132), (sx - 2, sy - 8, 4, 3))
            pygame.draw.polygon(surf, (150, 150, 160), [(sx - 1, sy + 4), (sx + 1, sy + 4), (sx, sy + 8)])
        elif self.kind == "rocket":
            pygame.draw.rect(surf, (200, 205, 215), (sx - 5, sy - 3, 10, 6))
            pygame.draw.rect(surf, (255, 120, 50), (sx + 3, sy - 2, 6, 4))
            pygame.draw.polygon(surf, (255, 220, 120), [(sx - 5, sy - 3), (sx - 5, sy + 3), (sx - 11, sy)])

    def should_explode_on_rect(self, rect: pygame.Rect) -> bool:
        """判断投射物是否应因撞到目标矩形而溅射爆炸。"""
        if self.splash > 0 and self.rect.colliderect(rect):
            return True
        return False

    def explode_at(self) -> tuple:
        """返回爆炸中心坐标（用于溅射伤害）。"""
        return self.x, self.y
