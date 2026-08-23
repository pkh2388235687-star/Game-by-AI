"""游戏特效：粒子、浮字、爆炸、冲击波、空中轰炸、挥刀轨迹、屏幕震动。"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

import pygame

from . import palette as P
from .fonts import get_font

Color = Tuple[int, int, int]


class Particle:
    """单个粒子。"""

    def __init__(
        self,
        x: float,
        y: float,
        vx: float,
        vy: float,
        color: Color,
        life: float,
        size: int = 3,
        gravity: float = 0.0,
    ) -> None:
        """初始化粒子。

        :param x: 初始 x 坐标。
        :param y: 初始 y 坐标。
        :param vx: 水平速度。
        :param vy: 垂直速度。
        :param color: 粒子颜色。
        :param life: 存活帧数。
        :param size: 粒子大小（像素）。
        :param gravity: 重力加速度（向下为正）。
        """
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.life = float(life)
        self.max_life = float(life)
        self.size = size
        self.gravity = gravity

    def update(self) -> bool:
        """更新粒子，返回是否仍存活。"""
        self.life -= 1
        if self.life <= 0:
            return False
        self.vy += self.gravity
        self.x += self.vx
        self.y += self.vy
        return True

    def draw(self, surf: pygame.Surface, cam_x: int = 0, cam_y: int = 0) -> None:
        """绘制粒子（按剩余寿命衰减，应用相机偏移）。"""
        t = max(0.0, self.life / self.max_life)
        radius = max(1, int(self.size * t))
        pygame.draw.rect(surf, self.color, (int(self.x - cam_x), int(self.y - cam_y), radius, radius))


class FloatText:
    """上浮的文本（伤害数字、提示等）。"""

    def __init__(self, text: str, x: float, y: float, color: Color, size: int = 16) -> None:
        """初始化浮字。

        :param text: 文本内容。
        :param x: 初始 x。
        :param y: 初始 y。
        :param color: 文本颜色。
        :param size: 字号。
        """
        self.text = text
        self.x = x
        self.y = y
        self.color = color
        self.life = 45
        self.vy = -0.9
        self.font = get_font(size, bold=True)

    def update(self) -> bool:
        """更新浮字，返回是否仍存活。"""
        self.life -= 1
        self.y += self.vy
        return self.life > 0

    def draw(self, surf: pygame.Surface, cam_x: int = 0, cam_y: int = 0) -> None:
        """绘制浮字（带描边，应用相机偏移）。"""
        alpha = max(60, min(255, int(self.life * 6)))
        img = self.font.render(self.text, True, self.color)
        img.set_alpha(alpha)
        outline = self.font.render(self.text, True, (0, 0, 0))
        outline.set_alpha(alpha)
        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y)
        surf.blit(outline, (sx - 1, sy))
        surf.blit(outline, (sx + 1, sy))
        surf.blit(outline, (sx, sy - 1))
        surf.blit(outline, (sx, sy + 1))
        surf.blit(img, (sx, sy))


class EffectSystem:
    """集中管理粒子、浮字、冲击波、轰炸、挥刀轨迹。"""

    def __init__(self) -> None:
        """初始化特效系统。"""
        self.particles: List[Particle] = []
        self.texts: List[FloatText] = []
        self.shockwaves: List["Shockwave"] = []
        self.bombs: List["Bomb"] = []
        self.haloes: List["Halo"] = []
        self.slashes: List["SlashArc"] = []

    def clear(self) -> None:
        """清空所有特效。"""
        self.particles.clear()
        self.texts.clear()
        self.shockwaves.clear()
        self.bombs.clear()
        self.haloes.clear()
        self.slashes.clear()

    def spawn_particles(
        self,
        x: float,
        y: float,
        color: Color,
        count: int = 12,
        speed: float = 4.0,
        life: int = 30,
        size: int = 3,
        gravity: float = 0.12,
        spread: float = 2 * math.pi,
        base_angle: float = 0.0,
    ) -> None:
        """生成一簇粒子。

        :param x: 中心 x。
        :param y: 中心 y。
        :param color: 粒子颜色。
        :param count: 粒子数量。
        :param speed: 发射速度上限。
        :param life: 存活帧数。
        :param size: 粒子大小。
        :param gravity: 重力。
        :param spread: 发射角度范围（默认全圆）。
        :param base_angle: 发射角度的基准朝向。
        """
        for _ in range(count):
            ang = base_angle + random.uniform(-spread / 2, spread / 2)
            spd = random.uniform(speed * 0.3, speed)
            self.particles.append(
                Particle(
                    x, y,
                    math.cos(ang) * spd,
                    math.sin(ang) * spd,
                    color,
                    random.randint(int(life * 0.6), int(life)),
                    random.randint(size // 2, size),
                    gravity,
                )
            )

    def add_text(self, text: str, x: float, y: float, color: Color, size: int = 16) -> None:
        """添加一条上浮文本。"""
        self.texts.append(FloatText(text, x, y, color, size))

    def add_shockwave(self, x: float, y: float, radius: float = 90, color: Color = P.ENERGY) -> None:
        """添加一个冲击波圈。"""
        self.shockwaves.append(Shockwave(x, y, radius, color))

    def add_halo(self, x: float, y: float, color: Color, duration: int = 20, radius: float = 20) -> None:
        """添加一个光环（用于护盾/增益提示）。"""
        self.haloes.append(Halo(x, y, color, duration, radius))

    def add_slash(self, x: float, y: float, facing: int, radius: float = 46,
                  color: Color = P.ENERGY) -> None:
        """添加一道武士刀挥砍弧光。"""
        self.slashes.append(SlashArc(x, y, facing, radius, color))

    def add_bombstrike(self, x: float, y: float) -> None:
        """从屏幕顶部落下一枚轰炸机炮弹，命中 y 处爆炸。"""
        self.bombs.append(Bomb(x, y))

    def update(self) -> None:
        """更新全部特效。"""
        self.particles = [p for p in self.particles if p.update()]
        self.texts = [t for t in self.texts if t.update()]
        self.shockwaves = [s for s in self.shockwaves if s.update()]
        self.bombs = [b for b in self.bombs if b.update()]
        self.haloes = [h for h in self.haloes if h.update()]
        self.slashes = [s for s in self.slashes if s.update()]

    def draw(self, surf: pygame.Surface, cam_x: int, cam_y: int) -> None:
        """绘制全部特效（相机偏移后）。"""
        for p in self.particles:
            p.draw(surf, cam_x, cam_y)
        for t in self.texts:
            t.draw(surf, cam_x, cam_y)
        for h in self.haloes:
            h.draw(surf, cam_x, cam_y)
        for s in self.shockwaves:
            s.draw(surf, cam_x, cam_y)
        for b in self.bombs:
            b.draw(surf, cam_x, cam_y)
        for s in self.slashes:
            s.draw(surf, cam_x, cam_y)

    def draw_particles_world(self, surf: pygame.Surface, cam_x: int, cam_y: int) -> None:
        """仅绘制粒子（供叠加使用）。"""
        for p in self.particles:
            p.draw(surf, cam_x, cam_y)


class Shockwave:
    """扩散冲击波圈。"""

    def __init__(self, x: float, y: float, radius: float, color: Color) -> None:
        """初始化冲击波。"""
        self.x = x
        self.y = y
        self.max_r = radius
        self.r = 4.0
        self.color = color
        self.life = 26

    def update(self) -> bool:
        """更新冲击波，返回是否存活。"""
        self.life -= 1
        if self.life <= 0:
            return False
        self.r += (self.max_r - self.r) * 0.25
        return True

    def draw(self, surf: pygame.Surface, cam_x: int, cam_y: int) -> None:
        """绘制冲击波。"""
        t = max(0.0, self.life / 26)
        width = max(1, int(4 * t))
        rect = pygame.Rect(int(self.x - cam_x - self.r), int(self.y - cam_y - self.r),
                           int(self.r * 2), int(self.r * 2))
        pygame.draw.ellipse(surf, self.color, rect, width)


class Halo:
    """光环效果（护盾/增益）。"""

    def __init__(self, x: float, y: float, color: Color, duration: int, radius: float) -> None:
        """初始化光环。"""
        self.x = x
        self.y = y
        self.color = color
        self.life = duration
        self.radius = radius

    def update(self) -> bool:
        """更新光环，返回是否存活。"""
        self.life -= 1
        return self.life > 0

    def draw(self, surf: pygame.Surface, cam_x: int, cam_y: int) -> None:
        """绘制光环。"""
        t = self.life / 20.0
        r = int(self.radius * (0.6 + 0.4 * t))
        center = (int(self.x - cam_x), int(self.y - cam_y))
        pygame.draw.circle(surf, self.color, center, r, 2)
        pygame.draw.circle(surf, (200, 250, 255), center, r - 3, 1)


class SlashArc:
    """武士刀挥砍弧光特效。"""

    def __init__(self, x: float, y: float, facing: int, radius: float, color: Color) -> None:
        """初始化弧光。

        :param x: 弧光中心世界 x。
        :param y: 弧光中心世界 y。
        :param facing: 朝向（1 右，-1 左）。
        :param radius: 弧光半径。
        :param color: 弧光颜色。
        """
        self.x = x
        self.y = y
        self.facing = facing
        self.radius = radius
        self.color = color
        self.life = 14
        self.max = 14

    def update(self) -> bool:
        """更新弧光，返回是否存活。"""
        self.life -= 1
        return self.life > 0

    def draw(self, surf: pygame.Surface, cam_x: int, cam_y: int) -> None:
        """绘制弧光（沿朝向张开一定角度）。"""
        t = max(0.0, self.life / self.max)
        cx = int(self.x - cam_x)
        cy = int(self.y - cam_y)
        rect = pygame.Rect(cx - self.radius, cy - self.radius, self.radius * 2, self.radius * 2)
        if self.facing > 0:
            start, end = -70, 70
        else:
            start, end = 110, 250
        width = max(1, int(5 * t))
        pygame.draw.arc(surf, self.color, rect, math.radians(start), math.radians(end), width)
        # 内层亮弧
        pygame.draw.arc(surf, (220, 250, 255), rect, math.radians(start), math.radians(end), max(1, width - 2))


class Bomb:
    """从天而降的轰炸机炸弹。从屏幕顶部落到目标 y 后爆炸。"""

    def __init__(self, x: float, target_y: float) -> None:
        """初始化炸弹。"""
        self.x = x
        self.y = -20.0
        self.target_y = target_y
        self.speed = 12.0
        self.exploded = False

    def update(self) -> bool:
        """更新炸弹，返回是否存活。"""
        if self.exploded:
            return False
        self.y += self.speed
        if self.y >= self.target_y:
            self.exploded = True
            return False
        return True

    def draw(self, surf: pygame.Surface, cam_x: int, cam_y: int) -> None:
        """绘制炸弹与下落尾焰。"""
        sx = int(self.x - cam_x)
        sy = int(self.y - cam_y)
        # 尾焰
        pygame.draw.line(surf, P.FIRE, (sx, sy), (sx, sy + 40), 4)
        pygame.draw.line(surf, P.BOMB_CORE, (sx, sy), (sx, sy + 24), 2)
        # 弹体
        pygame.draw.rect(surf, (60, 60, 70), (sx - 5, sy - 10, 10, 14))
        pygame.draw.rect(surf, (140, 140, 150), (sx - 6, sy - 12, 12, 4))
        pygame.draw.polygon(surf, (200, 60, 40), [(sx - 5, sy - 12), (sx + 5, sy - 12), (sx, sy - 20)])
