"""敌人与 Boss：近战/远程普通敌人以及远程/近战 Boss。

机制（按需求）：
- 攻击间隔 2 秒
- 普通敌人 2 颗心（攻击 2 次死亡），Boss 20 颗心
- 头顶血条
- 死亡时播放特效并掉落/加分
"""

from __future__ import annotations

import math
import random
from typing import List, Optional

import pygame

from . import palette as P
from .config import (
    BOSS_HP,
    ENEMY_ATTACK_INTERVAL,
    RENDER_H,
    RENDER_W,
    GROUND_Y,
)
from .world import World

# 敌人碰撞盒
ENEMY_W = 26
ENEMY_H = 46
BOSS_W = 52
BOSS_H = 66


class Enemy:
    """单个敌人实例。"""

    def __init__(
        self,
        game: object,
        kind: str,
        x: float,
        y: float,
        hp: int,
        speed_mult: float,
        interval_mult: float,
        boss: bool = False,
        roof_rect: Optional[pygame.Rect] = None,
    ) -> None:
        """初始化敌人。

        :param game: 上层游戏对象。
        :param kind: "melee" 或 "ranged"。
        :param x: 出生世界 x。
        :param y: 出生世界 y（脚底）。
        :param hp: 生命值（颗心）。
        :param speed_mult: 速度倍率（来自难度）。
        :param interval_mult: 攻击间隔倍率（来自难度；>1 更慢）。
        :param boss: 是否为 Boss。
        :param roof_rect: 若出生在屋顶平台，传入平台矩形用于巡逻边界。
        """
        self.game = game
        self.kind = kind
        self.boss = boss
        if boss:
            self.rect = pygame.Rect(int(x), int(y - BOSS_H), BOSS_W, BOSS_H)
        else:
            self.rect = pygame.Rect(int(x), int(y - ENEMY_H), ENEMY_W, ENEMY_H)
        self.hp = hp
        self.max_hp = hp
        self.speed = (1.2 if kind == "melee" else 0.9) * speed_mult
        self.interval = ENEMY_ATTACK_INTERVAL * interval_mult
        self.attack_timer = random.uniform(0.5, self.interval)
        self.vx = 0.0
        self.vy = 0.0
        self.facing = -1
        self.on_ground = False
        self.state = "idle"
        self.anim_timer = 0
        self.run_frame = 0
        self.hit_flash = 0       # 受击闪白帧
        self.dead = False
        self.death_timer = 0     # 死亡后残留特效时长
        self.roof = roof_rect    # 巡逻边界平台
        self.invuln = 0          # 无敌帧（防止一次攻击多次命中）
        self.spawn_timer = 1.5   # 生成后 1.5 秒内不能攻击
        # Boss 属性
        self.boss_phase_announced = False

    # ------------------------------------------------------------------
    # 更新
    # ------------------------------------------------------------------
    def update(self, game: object, world: World, dt: float) -> None:
        """更新敌人逻辑。

        :param game: 上层游戏对象。
        :param world: 世界对象。
        :param dt: 帧间隔（秒）。
        """
        self.hit_flash = max(0, self.hit_flash - 1)
        self.invuln = max(0, self.invuln - 1)
        self.spawn_timer = max(0.0, self.spawn_timer - dt)
        if self.dead:
            self.death_timer += 1
            return

        player = game.player
        self.anim_timer += 1
        self.attack_timer -= dt

        # 计算与玩家的水平距离与垂直差
        dx = player.rect.centerx - self.rect.centerx
        dy = player.rect.centery - self.rect.centery
        dist = abs(dx)
        self.facing = 1 if dx > 0 else -1

        if self.kind == "melee":
            self._update_melee(game, world, dx, dy, dist)
        else:
            self._update_ranged(game, world, dx, dy, dist)

        # 重力 & 移动
        self.vy += 0.5
        if self.vy > 12:
            self.vy = 12
        self.rect, self.on_ground, _, _ = world.move_entity(self.rect, self.vx, self.vy)

        # 巡逻边界（屋顶敌人不越界/不坠落）
        if self.roof is not None:
            self._clamp_to_roof()

        # 动画状态
        self._update_anim_state()

        # 死亡检测交由外部（take_damage 处理）

    # -- 攻击条件 ---------------------------------------------------------
    def _on_screen(self, game: object) -> bool:
        """判断敌人是否处于当前可见屏幕内（含少量边缘）。

        :param game: 上层游戏对象（提供 camera_x）。
        :return: 是否在屏内。
        """
        cam = game.camera_x
        return self.rect.right > cam - 20 and self.rect.left < cam + RENDER_W + 20

    def _can_attack(self, game: object) -> bool:
        """是否可以攻击：生成保护期结束且在屏幕内。

        :param game: 上层游戏对象。
        :return: 是否可以攻击。
        """
        return self.spawn_timer <= 0.0 and self._on_screen(game)

    def _update_melee(self, game: object, world: World, dx: float, dy: float, dist: float) -> None:
        """近战敌人：向玩家推进，贴近后攻击。

        屋顶近战敌人会在玩家位于其下方且较近时走下屋顶追击。
        """
        # 玩家在地面（低于屋顶）且距离可接受时，解除屋顶限制迫降
        if self.roof is not None and game.player.rect.bottom > self.roof.top + 4 \
                and abs(dx) < 320:
            self.roof = None
        # 朝玩家移动
        self.vx = self.speed * self.facing
        if dist < 46 and abs(dy) < 40:
            self.vx = 0
            if self.attack_timer <= 0 and self._can_attack(game):
                self._melee_attack(game)

    def _melee_attack(self, game: object) -> None:
        """近战攻击：对玩家造成一次伤害并播放挥击特效。"""
        if not self._can_attack(game):
            return
        self.attack_timer = self.interval
        self.state = "attack"
        # 命中判定
        if abs(self.rect.centerx - game.player.rect.centerx) < 52 and \
           abs(self.rect.centery - game.player.rect.centery) < 46:
            game.player.take_damage(1)
        # 挥击特效
        fx = self.rect.centerx + self.facing * 24
        fy = self.rect.centery
        self.game.effects.spawn_particles(fx, fy, (255, 220, 160), 8, 4.0, 16, 2, 0.0,
                                          base_angle=0 if self.facing > 0 else math.pi)

    def _update_ranged(self, game: object, world: World, dx: float, dy: float, dist: float) -> None:
        """远程敌人：保持一定距离并射击。"""
        # 若距离太近则后退，太远则靠近
        if 120 < dist < 420 and abs(dy) < 200:
            self.vx = 0
        else:
            self.vx = self.speed * self.facing
        # 射击（需在保护期外且在屏内）
        if dist < 480 and abs(dy) < 160:
            if self.attack_timer <= 0 and self._can_attack(game):
                self._range_attack(game)

    def _range_attack(self, game: object) -> None:
        """远程攻击：朝玩家方向发射一发子弹。"""
        if not self._can_attack(game):
            return
        self.attack_timer = self.interval
        self.state = "shoot"
        bx = self.rect.centerx + self.facing * 20
        by = self.rect.centery - 4
        # 计算朝玩家方向的单位向量
        dx = game.player.rect.centerx - bx
        dy = game.player.rect.centery - by
        length = max(0.001, math.hypot(dx, dy))
        vx = dx / length * 6.0
        vy = dy / length * 6.0
        game.spawn_enemy_bullet(bx, by, vx, vy)
        self.game.effects.spawn_particles(bx, by, (255, 190, 120), 5, 2.0, 12, 2, 0.0,
                                          base_angle=math.atan2(vy, vx))

    def _clamp_to_roof(self) -> None:
        """让屋顶敌人不越出平台边界、不掉落。"""
        if self.rect.left < self.roof.left:
            self.rect.left = self.roof.left
            self.facing = 1
        if self.rect.right > self.roof.right:
            self.rect.right = self.roof.right
            self.facing = -1

    def _update_anim_state(self) -> None:
        """更新动画状态。"""
        if self.dead:
            return
        if self.state in ("attack", "shoot"):
            # 保持短暂攻击姿态
            self.state = "idle" if self.attack_timer > self.interval - 0.2 else self.state
            if self.attack_timer > self.interval - 0.4:
                # 攻击姿态帧
                self.state = "attack" if self.kind == "melee" else "shoot"
        if abs(self.vx) > 0.05 and self.state not in ("attack", "shoot"):
            self.state = "run"

    # ------------------------------------------------------------------
    # 受伤与死亡
    # ------------------------------------------------------------------
    def take_damage(self, game: object, amount: int, knockback_dir: int = 1) -> bool:
        """受到伤害。返回是否被击杀。

        :param game: 上层对象。
        :param amount: 伤害（颗心）。
        :param knockback_dir: 击退方向（1 右，-1 左）。
        :return: True 表示被击杀。
        """
        if self.dead or self.invuln > 0:
            return False
        self.hp -= amount
        self.invuln = 4
        self.hit_flash = 6
        # 击退
        self.vx += knockback_dir * 2.0
        self.vy = -3.0
        # 命中反馈：火花 + 方向性冲击 + 白色爆点
        cx = self.rect.centerx
        cy = self.rect.centery
        self.game.effects.spawn_particles(cx, cy, (255, 250, 180), 12, 5.0, 20, 3, 0.0)
        self.game.effects.spawn_particles(cx, cy, (255, 140, 40), 8, 4.0, 16, 3, 0.0,
                                          base_angle=0 if knockback_dir > 0 else math.pi)
        self.game.effects.spawn_particles(cx, cy, (220, 220, 235), 6, 6.0, 14, 2, 0.0)
        self.game.effects.add_text(str(amount), cx - self.game.camera_x, self.rect.y - 10,
                                   P.UI_WARN, 14)
        if self.hp <= 0:
            self._die(game)
            return True
        return False

    def _die(self, game: object) -> None:
        """死亡：标记、特效、加分、掉落。"""
        self.dead = True
        self.death_timer = 0
        cx, cy = self.rect.centerx, self.rect.centery
        self.game.effects.spawn_particles(cx, cy, (255, 150, 60), 16, 5.0, 30, 4, 0.12)
        self.game.effects.spawn_particles(cx, cy, (200, 200, 210), 12, 4.0, 40, 3, 0.2)
        base_score = 100 if not self.boss else 500
        game.player.add_score(int(base_score * game.difficulty.score_mult))
        game.on_enemy_killed(self)

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------
    def current_image(self) -> pygame.Surface:
        """返回当前精灵帧（列表前半为朝右，后半为镜像朝左）。"""
        key = "boss_" + self.kind if self.boss else self.kind
        frames = self.game.sprites["enemies"][key]
        half = len(frames["idle"]) // 2
        state = self.state
        if state not in frames:
            state = "idle"
        # 动画帧只在前半段，朝向决定是取原帧还是镜像帧
        anim = self.run_frame if state == "run" else 0
        idx = anim % half if half else 0
        if self.facing < 0:
            idx += half
        lst = frames[state]
        return lst[idx % len(lst)]

    def draw(self, surf: pygame.Surface, cam_x: int) -> None:
        """绘制敌人（含血条）。若已死亡仅绘制残留粒子由特效层处理，这里跳过实体。"""
        if self.dead:
            return
        img = self.current_image()
        spr_w, spr_h = img.get_size()
        px = self.rect.centerx - spr_w // 2 - cam_x
        py = self.rect.bottom - spr_h + 2
        if self.hit_flash > 0:
            # 受击闪白
            white = img.copy()
            white.fill((255, 255, 255, 60), special_flags=pygame.BLEND_RGBA_ADD)
            surf.blit(white, (px, py))
        else:
            surf.blit(img, (px, py))
        self._draw_hp_bar(surf, cam_x)

    def _draw_hp_bar(self, surf: pygame.Surface, cam_x: int) -> None:
        """绘制头顶血条。普通敌人用心形，Boss 用更明显血条。"""
        width = 44 if self.boss else 30
        bx = self.rect.centerx - width // 2 - cam_x
        by = self.rect.y - 10
        ratio = max(0.0, self.hp / self.max_hp)
        # 背景
        pygame.draw.rect(surf, (30, 30, 40), (bx, by, width, 5))
        color = (220, 60, 60) if ratio > 0.4 else (255, 160, 50)
        pygame.draw.rect(surf, color, (bx, by, int(width * ratio), 5))
        pygame.draw.rect(surf, (20, 20, 30), (bx, by, width, 5), 1)
        if self.boss:
            pygame.draw.rect(surf, (255, 220, 120), (bx - 2, by - 2, width + 4, 9), 1)
