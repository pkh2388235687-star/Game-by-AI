"""世界与地图生成：赛博朋克街景背景、随机屋顶平台、实体物理碰撞。"""

from __future__ import annotations

import math
import random
from typing import List, Optional

import pygame

from . import palette as P
from . import sprites as sprite_mod
from .config import GROUND_Y, RENDER_H, RENDER_W


class Platform:
    """一个可站立平台（地面或屋顶）。"""

    def __init__(self, x: float, y: float, width: float, is_ground: bool = False) -> None:
        """初始化平台。

        :param x: 平台左边缘世界坐标。
        :param y: 平台顶面世界坐标（脚底可站高度）。
        :param width: 平台宽度。
        :param is_ground: 是否为无限地面。
        """
        self.rect = pygame.Rect(int(x), int(y), int(width), 12)
        self.is_ground = is_ground

    @property
    def right(self) -> float:
        """平台右边缘。"""
        return self.rect.right


class World:
    """管理背景、平台生成与实体碰撞。"""

    SHOP_W = 96

    def __init__(self, rng: Optional[random.Random] = None) -> None:
        """初始化世界。

        :param rng: 随机数生成器（用于可复现）。默认新建。
        """
        self.rng = rng or random.Random()
        self.platforms: List[Platform] = []
        # 沿街随机生成的建筑/房子
        self.buildings: List[dict] = []
        self._next_build_x = 0.0
        # 建筑配色池（赛博朋克风）
        self.body_colors = [(52, 60, 96), (62, 46, 96), (44, 74, 82), (70, 52, 70),
                            (58, 58, 90), (50, 70, 108), (66, 48, 88)]
        self.neon_colors = [P.SIGN_NEON, P.SIGN_NEON_PINK, P.SIGN_NEON_YELLOW,
                            (120, 255, 160), (255, 150, 90), (170, 120, 255)]
        self.win_colors = [(120, 220, 255), (255, 200, 120), (190, 255, 190),
                           (255, 140, 190), (200, 200, 220)]
        self.tiles = sprite_mod.make_sprites()["bg"]

    # ------------------------------------------------------------------
    # 生成
    # ------------------------------------------------------------------
    def _ensure_blocks(self, up_to_x: float) -> None:
        """向前随机生成沿街建筑（含可跳屋顶），直到覆盖 x 位置。"""
        while self._next_build_x < up_to_x + RENDER_W:
            x = self._next_build_x
            w = self.rng.randint(110, 240)
            roll = self.rng.random()
            if roll < 0.5:                       # 低层：屋顶可跳
                h = self.rng.randint(72, 116)
                has_roof = True
                tower = False
            elif roll < 0.82:                    # 中层建筑
                h = self.rng.randint(130, 176)
                has_roof = False
                tower = False
            else:                                # 高塔（仅背景）
                h = self.rng.randint(188, 240)
                has_roof = False
                tower = True
            top = GROUND_Y - h
            bld = {
                "x": x, "w": w, "top": top,
                "body": self.rng.choice(self.body_colors),
                "neon": self.rng.choice(self.neon_colors),
                "win": self.rng.choice(self.win_colors),
                "roof": has_roof, "tower": tower,
                "seed": self.rng.randint(0, 999),
            }
            self.buildings.append(bld)
            if has_roof:
                # 屋顶即为可站立平台
                self.platforms.append(Platform(x + 4, top, w - 8))
            self._next_build_x = x + w

    def ensure(self, cam_x: float) -> None:
        """确保建筑与屋顶平台已生成到相机前方。"""
        self._ensure_blocks(cam_x)

    def current_enemy_roofs(self) -> List[pygame.Rect]:
        """返回可生成敌人的屋顶平台矩形（宽度足够的）。"""
        return [p.rect for p in self.platforms if p.rect.width >= 90]

    # ------------------------------------------------------------------
    # 碰撞
    # ------------------------------------------------------------------
    def move_entity(
        self, rect: pygame.Rect, vx: float, vy: float, ground_y: float = GROUND_Y
    ) -> tuple:
        """移动一个实体并解析与地面/屋顶平台的碰撞。

        屋顶平台为"单向"：仅当实体向下穿过平台顶面时被接住，可从下方穿过。

        :param rect: 实体当前矩形（会被修改为移动后的位置）。
        :param vx: 水平位移量。
        :param vy: 垂直位移量。
        :param ground_y: 地面高度（实体脚底下限）。
        :return: (rect, on_ground, blocked_x, blocked_y)
                 on_ground 表示是否站在某个表面上。
        """
        rect.x += vx
        prev_bottom = rect.bottom
        rect.y += vy
        on_ground = False
        blocked_x = False
        blocked_y = False

        # 地面（水平无限，不能低于地面）
        if rect.bottom > ground_y:
            rect.bottom = int(ground_y)
            on_ground = True
            blocked_y = True
            vy = 0.0

        # 屋顶平台（单向，只接住从上往下落）
        if vy >= 0:
            for p in self.platforms:
                r = p.rect
                if rect.right > r.left and rect.left < r.right:
                    # 垂直穿过平台顶面
                    if prev_bottom <= r.top + 2 and rect.bottom >= r.top:
                        rect.bottom = r.top
                        on_ground = True
                        blocked_y = True
                        vy = 0.0
                        break
        if blocked_y and not on_ground:
            # 撞到平台侧面（一般不会，因单向）；保留防止穿透
            pass
        return rect, on_ground, blocked_x, blocked_y

    def on_platform(self, rect: pygame.Rect) -> bool:
        """判断实体当前是否正站在某个平台顶（用于敌人巡逻边界）。"""
        for p in self.platforms:
            r = p.rect
            if rect.bottom == r.top and rect.right > r.left and rect.left < r.right:
                return True
        return rect.bottom >= GROUND_Y - 1

    def platform_under(self, rect: pygame.Rect) -> Optional[pygame.Rect]:
        """返回实体当前脚下的平台矩形（若无则返回 None）。"""
        for p in self.platforms:
            r = p.rect
            if abs(rect.bottom - r.top) <= 2 and rect.right > r.left and rect.left < r.right:
                return r
        if abs(rect.bottom - GROUND_Y) <= 2:
            return pygame.Rect(int(rect.centerx - 100000), GROUND_Y, 200000, 60)
        return None

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------
    def draw_background(self, surf: pygame.Surface, cam_x: int) -> None:
        """绘制星空、远景楼群与随机生成的沿街建筑（按视差滚动）。"""
        # 天空渐变 + 霓虹地平线
        for yy in range(RENDER_H):
            t = yy / RENDER_H
            col = (
                int(P.SKY_TOP[0] + (P.SKY_BOTTOM[0] - P.SKY_TOP[0]) * t),
                int(P.SKY_TOP[1] + (P.SKY_BOTTOM[1] - P.SKY_TOP[1]) * t),
                int(P.SKY_TOP[2] + (P.SKY_BOTTOM[2] - P.SKY_TOP[2]) * t),
            )
            pygame.draw.line(surf, col, (0, yy), (RENDER_W, yy))

        # 远景楼群（视差因子 0.4 与 0.7，营造景深）
        bld = self.tiles["bld_a"]
        period = bld.get_width()
        offset = int(cam_x * 0.4)
        start_i = offset // period - 1
        for i in range(start_i, start_i + RENDER_W // period + 3):
            sy = RENDER_H - bld.get_height() + 30
            surf.blit(bld, (i * period - offset, sy))
        bld2 = self.tiles["bld_b"]
        period2 = bld2.get_width()
        offset2 = int(cam_x * 0.72)
        start_i2 = offset2 // period2 - 1
        for i in range(start_i2, start_i2 + RENDER_W // period2 + 3):
            sy = RENDER_H - bld2.get_height() + 62
            surf.blit(bld2, (i * period2 - offset2, sy))

        # 沿街建筑（视差 1.0，随前进随机生成）
        self._draw_buildings(surf, cam_x)

    def _draw_buildings(self, surf: pygame.Surface, cam_x: int) -> None:
        """绘制随机生成的沿街建筑/房子。

        :param surf: 画布。
        :param cam_x: 相机 x。
        """
        for b in self.buildings:
            bx, bw, top = b["x"], b["w"], b["top"]
            if bx + bw < cam_x - 10 or bx > cam_x + RENDER_W + 10:
                continue
            sx = int(bx - cam_x)
            body_h = GROUND_Y - top
            body = b["body"]
            dark = (int(body[0] * 0.55), int(body[1] * 0.55), int(body[2] * 0.6))
            lighter = (min(255, int(body[0] * 1.25) + 12), min(255, int(body[1] * 1.25) + 12),
                       min(255, int(body[2] * 1.25) + 14))

            # 主体
            pygame.draw.rect(surf, body, (sx, top, bw, body_h))
            # 左侧暗边（微弱体积感）
            pygame.draw.rect(surf, dark, (sx, top, 4, body_h))
            # 顶部檐口
            pygame.draw.rect(surf, dark, (sx, top, bw, 6))

            # 窗户网格（用世界坐标决定点亮，滚动时保持稳定）
            win_side = b["win"]
            for wy in range(top + 20, GROUND_Y - 52, 24):
                for wx in range(6, bw - 10, 26):
                    world_wx = int(bx + wx)
                    lit = ((world_wx * 31 + b["seed"] * 17 + int(top)) % 10) < 4
                    col = win_side if lit else (24, 24, 40)
                    pygame.draw.rect(surf, col, (sx + wx, wy, 12, 16))

            # 底层店面：卷帘门 + 门口
            door_y = GROUND_Y - 40
            pygame.draw.rect(surf, (60, 74, 96), (sx + 8, door_y, bw - 16, 40))
            pygame.draw.rect(surf, (44, 56, 74), (sx + 8, door_y, bw - 16, 6))
            # 卷帘门格栅
            for gy in range(door_y + 12, GROUND_Y - 4, 10):
                pygame.draw.line(surf, (30, 38, 50), (sx + 10, gy), (sx + bw - 10, gy))
            # 门店招牌（霓虹）
            sign_y = top + 10
            sign = b["neon"]
            pygame.draw.rect(surf, (18, 18, 30), (sx + 6, sign_y, bw - 12, 14))
            pygame.draw.rect(surf, sign, (sx + 6, sign_y + 2, bw - 12, 4))
            # 招牌文字块（模拟霓虹字）
            for tx in range(sx + 14, sx + bw - 16, 18):
                pygame.draw.rect(surf, sign, (tx, sign_y + 6, 10, 5))

            if b["roof"]:
                # 可跳屋顶：顶部亮色平台与护栏
                pygame.draw.rect(surf, P.ROOF_TOP, (sx, top - 2, bw, 5))
                pygame.draw.rect(surf, P.ROOF_EDGE, (sx, top + 3, bw, 3))
                # 屋顶小护栏
                for gx in range(sx + 6, sx + bw - 6, 16):
                    pygame.draw.rect(surf, (150, 140, 120), (gx, top - 8, 6, 6))
                # 空调外机
                pygame.draw.rect(surf, (90, 90, 100), (sx + 14, top - 14, 16, 10))
            elif b["tower"]:
                # 高塔：顶部尖顶与闪烁警示灯
                pygame.draw.rect(surf, (40, 40, 60), (sx, top, bw, 6))
                cxs = sx + bw // 2
                pygame.draw.rect(surf, dark, (cxs - 8, top - 12, 16, 12))
                blink = ((int(bx) // 30) % 2) == 0
                c = (255, 90, 80) if blink else (150, 80, 90)
                pygame.draw.circle(surf, c, (cxs, top - 16), 3)
            else:
                # 中层屋顶
                pygame.draw.rect(surf, dark, (sx, top, bw, 5))
                pygame.draw.rect(surf, lighter, (sx + 20, top - 8, 26, 6))

    def draw_ground(self, surf: pygame.Surface, cam_x: int) -> None:
        """绘制地面砖块。"""
        ground = self.tiles["ground"]
        w = ground.get_width()
        first = int(cam_x / w) - 1
        for i in range(first, first + RENDER_W // w + 3):
            world_x = i * w
            surf.blit(ground, (world_x - cam_x, GROUND_Y - 10))

    def draw_platforms(self, surf: pygame.Surface, cam_x: int) -> None:
        """绘制屋顶平台。"""
        plat = self.tiles["platform"]
        for p in self.platforms:
            if p.rect.right < cam_x - 10 or p.rect.x > cam_x + RENDER_W + 10:
                continue
            surf.blit(plat, (p.rect.x - cam_x, p.rect.y - 6))

    def nearest_platform_y(self, x: float, height: int) -> float:
        """估计在 x 附近可能站立的平台顶面高度（用于敌人/道具放置）。"""
        for p in self.platforms:
            r = p.rect
            if r.left <= x <= r.right and r.top + height <= GROUND_Y:
                return float(r.top)
        return float(GROUND_Y)
