"""玩家角色：移动、跳跃、射击、大招（轰炸 / 20 秒武士刀近战形态）、护盾增益。"""

from __future__ import annotations

import math
from typing import List, Optional

import pygame

from . import palette as P
from .config import (
    GRAVITY,
    GROUND_Y,
    MAX_HEARTS,
    PLAYER_JUMP_POWER,
    PLAYER_MOVE_SPEED,
    RENDER_W,
    SKILL_COOLDOWN,
)
from .fonts import get_font
from .world import World

# 玩家碰撞盒尺寸
PLAYER_W = 24
PLAYER_H = 48
SHIELD_DURATION = 180     # 护盾持续时间（帧）≈ 3 秒
ULT_DURATION = 20.0       # 大招（武士刀近战形态）持续时间（秒）
ULT_RECHARGE = 15.0       # 大招冷却（秒）


class Player:
    """玩家实体。"""

    def __init__(self, game: object, x: float, y: float) -> None:
        """初始化玩家。

        :param game: 上层游戏对象（提供 effects、projectiles、相机等）。
        :param x: 出生点世界 x。
        :param y: 出生点世界 y（脚底高度）。
        """
        self.game = game
        self.rect = pygame.Rect(int(x), int(y - PLAYER_H), PLAYER_W, PLAYER_H)
        self.vx = 0.0
        self.vy = 0.0
        self.facing = 1               # 1 右，-1 左
        self.on_ground = True
        self.hp = MAX_HEARTS
        self.max_hp = MAX_HEARTS

        # 状态与动画
        self.state = "idle"
        self.anim_timer = 0
        self.run_frame = 0
        self.shoot_flash = 0          # 射击闪光剩余帧
        self.invuln = 0               # 受击无敌帧
        self.shoot_cd = 0.0           # 攻击冷却（射击/投掷共用，受急速增益影响）

        # 技能
        self.skill_cd = 0.0
        self.ult_cd = 0.0
        # 大招：武士刀近战形态
        self.sword_mode = False       # 是否处于近战形态
        self.sword_timer = 0.0        # 近战形态剩余时间（秒）
        self.sword_phase = 0          # 开场动作：1=起跳举刀, 2=下砸, 3=落地压刀, 0=结束
        self.sword_ac = 0             # 开场动作帧计数
        self.slam_done = False        # 开场下砸是否已释放
        self.slash_cd = 0.0           # 挥砍冷却
        self.slash_flash = 0          # 挥砍闪光剩余帧

        # 护盾
        self.shield_timer = 0.0

        # 统计
        self.score = 0
        self.kills = 0
        self.alive = True

    # ------------------------------------------------------------------
    # 输入 & 更新
    # ------------------------------------------------------------------
    def update(self, keys, world: World, dt: float) -> None:
        """更新玩家逻辑。

        :param keys: pygame.key.get_pressed() 结果。
        :param world: 世界对象（碰撞）。
        :param dt: 帧间隔（秒）。
        """
        if not self.alive:
            return

        # 冷却与护盾计时
        self.skill_cd = max(0.0, self.skill_cd - dt)
        self.ult_cd = max(0.0, self.ult_cd - dt)
        self.shield_timer = max(0.0, self.shield_timer - dt)
        self.shoot_cd = max(0.0, self.shoot_cd - dt)
        self.slash_cd = max(0.0, self.slash_cd - dt)
        self.invuln = max(0, self.invuln - 1)
        self.shoot_flash = max(0, self.shoot_flash - 1)
        self.slash_flash = max(0, self.slash_flash - 1)

        self._handle_input(keys)

        # 开场动作优先
        if self.sword_phase > 0:
            self._update_sword_opening(world)
        elif self.sword_mode:
            # 近战形态：倒计时并沿用普通移动物理
            self.sword_timer -= dt
            if self.sword_timer <= 0:
                self._exit_sword_mode()
            else:
                self._update_movement(keys, world)
        else:
            self._update_movement(keys, world)

        # 动画状态机
        self._update_animation()

        if not self.on_ground and self.sword_phase == 0 and not self.sword_mode:
            self.state = "jump"

    def _handle_input(self, keys) -> None:
        """处理键盘输入（普攻/轰炸/大招/跳跃）。"""
        # 普攻：近战形态为挥砍，否则发射子弹
        if keys[pygame.K_j] or keys[pygame.K_z]:
            self.primary_attack()
        # 技能：全屏轰炸（近战形态下不可用）—— Q 键
        if keys[pygame.K_q] and self.skill_cd <= 0 and not self.sword_mode:
            self._cast_airstrike()
        # 大招：进入武士刀近战形态（20 秒）—— E 键
        if keys[pygame.K_e] and self.ult_cd <= 0 \
                and not self.sword_mode and self.sword_phase == 0:
            self._start_sword_mode()

        # 跳跃
        jump_keys = (keys[pygame.K_SPACE] or keys[pygame.K_w] or keys[pygame.K_UP])
        if jump_keys and self.on_ground and self.sword_phase == 0:
            self.vy = PLAYER_JUMP_POWER
            self.on_ground = False

    def _update_movement(self, keys, world: World) -> None:
        """处理水平移动与重力。"""
        self.vx = 0.0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.vx = -PLAYER_MOVE_SPEED
            self.facing = -1
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.vx = PLAYER_MOVE_SPEED
            self.facing = 1

        self.vy += GRAVITY
        if self.vy > 14:
            self.vy = 14

        self.rect, self.on_ground, _, _ = world.move_entity(self.rect, self.vx, self.vy)

        if self.rect.x < 0 and self.vx < 0:
            self.rect.x = 0

        if self.shoot_flash > 0:
            self.state = "shoot"
        elif not self.on_ground:
            self.state = "jump"
        elif self.vx != 0:
            self.state = "run"
        else:
            self.state = "idle"

    # ------------------------------------------------------------------
    # 攻击接口（键盘与鼠标共用）
    # ------------------------------------------------------------------
    def primary_attack(self) -> None:
        """普攻：近战形态挥砍，否则发射子弹。"""
        if self.sword_mode:
            self.melee_slash()
        else:
            self.fire_gun()

    def fire_gun(self) -> None:
        """射击：发射一颗普通子弹（不消耗弹药），附带枪口闪光与弹壳。"""
        if self.sword_phase > 0 or self.sword_mode or self.shoot_cd > 0:
            return
        gun_x = self.rect.centerx + self.facing * 22
        gun_y = self.rect.centery - 2
        self.game.spawn_player_bullet(gun_x, gun_y, self.facing, 1)
        self.shoot_flash = 6
        self.shoot_cd = max(0.06, 0.22 - self.game.buff_rapid * 0.05)
        # 枪口火花（加亮加多）
        self.game.effects.spawn_particles(
            gun_x, gun_y, (255, 240, 160), 8, 3.0, 14, 3, 0.0,
            base_angle=0 if self.facing > 0 else math.pi)
        self.game.effects.spawn_particles(
            gun_x + self.facing * 3, gun_y, (255, 130, 50), 5, 2.0, 10, 2, 0.0,
            base_angle=0 if self.facing > 0 else math.pi)
        # 弹壳抛壳
        self.game.effects.spawn_particles(
            self.rect.centerx - self.facing * 6, self.rect.centery - 8,
            (220, 180, 90), 2, 3.5, 22, 2, 0.25,
            base_angle=-math.pi / 2 if self.facing > 0 else -math.pi / 2)

    def throw_item(self) -> None:
        """投掷道具：优先手榴弹，其次火箭弹（消耗弹药）。

        无弹药时不动作。
        """
        if self.sword_phase > 0 or self.shoot_cd > 0:
            return
        if self.game.ammo.get("grenade", 0) > 0:
            self.game.ammo["grenade"] -= 1
            self.game.throw_grenade()
            self.shoot_cd = 0.4
        elif self.game.ammo.get("rocket", 0) > 0:
            self.game.ammo["rocket"] -= 1
            self.game.launch_rocket()
            self.shoot_cd = 0.5

    def melee_slash(self) -> None:
        """武士刀挥砍：对身前扇形范围的敌人造成伤害，并播放弧光。"""
        if self.sword_phase > 0 or not self.sword_mode or self.slash_cd > 0:
            return
        self.slash_cd = 0.20
        self.slash_flash = 8
        dmg = max(1, int(round(1.5 * self.game.buff_damage)))
        # 朝向前方的攻击矩形
        w = 50
        h = 70
        if self.facing > 0:
            x = self.rect.centerx
        else:
            x = self.rect.centerx - w
        attack_rect = pygame.Rect(x, self.rect.centery - h // 2, w, h)
        for e in list(self.game.enemies):
            if e.dead:
                continue
            if attack_rect.colliderect(e.rect):
                e.take_damage(self.game, dmg, knockback_dir=self.facing)
        # 弧光与粒子（双层刀光 + 火花）
        fx = self.rect.centerx + self.facing * 26
        fy = self.rect.centery
        self.game.effects.add_slash(fx, fy, self.facing, 50, P.ENERGY)
        self.game.effects.add_slash(fx, fy + 6, self.facing, 40, (200, 250, 255))
        self.game.effects.spawn_particles(fx, fy, (190, 240, 255), 20, 6.0, 22, 3, 0.0,
                                          base_angle=0 if self.facing > 0 else math.pi)
        self.game.effects.spawn_particles(fx, fy, (255, 120, 60), 10, 4.0, 16, 2, 0.0,
                                          base_angle=0 if self.facing > 0 else math.pi)
        self.game.shake_screen(4.0)

    # ------------------------------------------------------------------
    # 技能：全屏轰炸
    # ------------------------------------------------------------------
    def _cast_airstrike(self) -> None:
        """释放技能：召唤全屏轰炸机炮弹从天空落下。"""
        self.skill_cd = SKILL_COOLDOWN
        columns = 7
        start_x = self.game.camera_x - 10
        width = RENDER_W + 20
        for i in range(columns):
            x = start_x + width * (i + 0.5) / columns
            self.game.add_airstrike_column(x)
        self.game.effects.add_text("✈ 轰炸支援!", self.rect.centerx - self.game.camera_x,
                                   self.rect.y - 20, P.UI_ACCENT, 18)

    # ------------------------------------------------------------------
    # 大招：20 秒武士刀近战形态
    # ------------------------------------------------------------------
    def _start_sword_mode(self) -> None:
        """切入武士刀近战形态：先做起跳举刀→下砸的开场动作，随后维持 20 秒。"""
        self.sword_mode = True
        self.sword_timer = ULT_DURATION
        self.sword_phase = 1
        self.sword_ac = 0
        self.slam_done = False
        self.vx = self.facing * PLAYER_MOVE_SPEED * 1.4
        self.vy = PLAYER_JUMP_POWER * 1.55
        self.on_ground = False
        self.game.start_ult_cutin()
        self.game.effects.add_text("⚔ 斩杀形态 · 20秒", self.rect.centerx - self.game.camera_x,
                                   self.rect.y - 24, P.ENERGY, 18)

    def _update_sword_opening(self, world: World) -> None:
        """推进近战形态的开场动作（起跳举刀 → 下砸范围攻击 → 收势）。"""
        self.sword_ac += 1
        self.vy += GRAVITY * 1.4
        if self.vy > 28:
            self.vy = 28
        self.rect, self.on_ground, _, _ = world.move_entity(self.rect, self.vx, self.vy)

        if self.sword_phase == 1:
            if self.vy >= 0 and self.sword_ac > 6:
                self.sword_phase = 2
                self.sword_ac = 0
                self.vy = 28
        elif self.sword_phase == 2:
            if self.on_ground and not self.slam_done:
                self.slam_done = True
                self._do_slam()
                self.sword_phase = 3
                self.sword_ac = 0
        elif self.sword_phase == 3:
            if self.sword_ac > 16:
                self.sword_phase = 0

    def _do_slam(self) -> None:
        """下砸命中地面：大范围伤害与冲击波（大招开场技）。"""
        cx = self.rect.centerx
        cy = self.rect.bottom
        r = self.game.effects
        r.add_shockwave(cx, cy, 120, P.ENERGY)
        r.add_shockwave(cx, cy, 82, P.ENERGY_CORE)
        r.spawn_particles(cx, cy, (190, 240, 255), 30, 8.0, 40, 4, 0.18, math.pi)
        r.spawn_particles(cx, cy, (255, 120, 40), 20, 6.0, 30, 3, 0.15, math.pi)
        self.game.flash(6)
        self.game.shake_screen(10.0)
        self.game.slam_damage(cx, cy, r=110, dmg=int(round(3 * self.game.buff_damage)))

    def _exit_sword_mode(self) -> None:
        """退出近战形态，回到射击形态并进入冷却。"""
        self.sword_mode = False
        self.sword_phase = 0
        self.ult_cd = ULT_RECHARGE
        self.game.effects.add_text("形态结束", self.rect.centerx - self.game.camera_x,
                                   self.rect.y - 24, P.UI_DIM, 16)

    def gain_shield(self) -> None:
        """获得护盾（近战形态击杀敌人时触发）。"""
        self.shield_timer = SHIELD_DURATION
        self.game.effects.add_halo(self.rect.centerx, self.rect.centery, P.SHIELD, 20, 26)

    # ------------------------------------------------------------------
    # 动画
    # ------------------------------------------------------------------
    def _update_animation(self) -> None:
        """根据状态推进动画计时与帧。"""
        frames = self.game.sprites["player"]
        self.anim_timer += 1
        if self.state == "run":
            self.run_frame = int(self.anim_timer) // 8 % len(frames["run"])
        else:
            self.run_frame = 0

    def current_image(self) -> pygame.Surface:
        """返回当前应显示的主角精灵帧（含朝向镜像）。"""
        frames = self.game.sprites["player"]
        half = len(frames["idle"]) // 2

        # 近战形态（大招）
        if self.sword_mode or self.sword_phase > 0:
            if self.sword_phase == 1:
                key, idx = "sword_a", 0
            elif self.sword_phase == 2:
                key, idx = "sword_b", 0
            elif self.sword_phase == 3:
                key, idx = "sword_slam", 0
            elif self.slash_flash > 0:
                key, idx = "sword_b", 0
            elif self.state == "jump":
                key, idx = "sword_a", 0
            elif self.state == "run":
                key, idx = "sword_hold", 0
            else:
                key, idx = "sword_hold", 0
        elif self.state == "run":
            key, idx = "run", self.run_frame % half
        elif self.state == "shoot":
            # 射击：开枪瞬间显示后坐力帧，随后循环到端枪瞄准帧
            key = "shoot_recoil" if self.shoot_flash >= 4 else "shoot"
            idx = 0
        elif self.state == "jump":
            key, idx = "jump", 0
        else:
            key, idx = "idle", 0

        if self.facing < 0:
            idx += half
        lst = frames[key]
        return lst[idx % len(lst)]

    # ------------------------------------------------------------------
    # 伤害
    # ------------------------------------------------------------------
    def take_damage(self, amount: int) -> bool:
        """受到伤害。护盾可吸收一次完全伤害。

        :param amount: 伤害值（颗心）。
        :return: 是否真正造成掉血（False 表示被护盾/无敌挡住）。
        """
        if not self.alive or self.invuln > 0:
            return False
        if self.shield_timer > 0:
            self.shield_timer = 0
            self.invuln = 30
            self.game.effects.spawn_particles(self.rect.centerx, self.rect.centery, P.SHIELD,
                                              20, 5.0, 30, 3, 0.0)
            self.game.effects.add_text("护盾抵挡!", self.rect.centerx - self.game.camera_x,
                                       self.rect.y - 16, P.SHIELD, 16)
            return False
        self.hp -= amount
        self.invuln = 45
        self.game.shake_screen(7.0)
        self.game.hurt_overlay()
        self.game.effects.spawn_particles(self.rect.centerx, self.rect.centery, (255, 80, 80),
                                          18, 6.0, 28, 3, 0.1)
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
        return True

    def add_score(self, value: int) -> None:
        """加分。"""
        self.score += value

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------
    def draw(self, surf: pygame.Surface, cam_x: int) -> None:
        """绘制玩家（含无敌闪烁、护盾光环、近战形态光圈）。"""
        if self.invuln > 0 and (self.invuln // 4) % 2 == 0:
            return
        img = self.current_image()
        spr_w, spr_h = img.get_size()
        px = self.rect.centerx - spr_w // 2 - cam_x
        py = self.rect.bottom - spr_h + 2
        surf.blit(img, (px, py))

        center = (self.rect.centerx - cam_x, self.rect.centery)
        if self.shield_timer > 0:
            pygame.draw.circle(surf, (80, 200, 255), center, 30, 2)
            pygame.draw.circle(surf, (200, 250, 255), center, 26, 1)
        if self.sword_mode:
            pygame.draw.circle(surf, P.ENERGY, center, 34, 2)
            self._draw_ult_bar(surf, cam_x)

    def _draw_ult_bar(self, surf: pygame.Surface, cam_x: int) -> None:
        """在角色头顶绘制大招（近战形态）剩余时间进度条。"""
        ratio = max(0.0, min(1.0, self.sword_timer / ULT_DURATION))
        bw = 56
        bx = self.rect.centerx - bw // 2 - cam_x
        by = self.rect.y - 16
        # 背景框
        pygame.draw.rect(surf, (20, 22, 36), (bx - 1, by - 1, bw + 2, 8))
        # 能量填充（随时间从满到空，颜色渐变）
        col = P.ENERGY if ratio > 0.3 else P.UI_WARN
        pygame.draw.rect(surf, col, (bx, by, int(bw * ratio), 6))
        pygame.draw.rect(surf, P.UI_ACCENT, (bx - 1, by - 1, bw + 2, 8), 1)
        # 标签
        font = get_font(11, bold=True)
        label = font.render(f"{self.sword_timer:.0f}s", True, P.UI_TEXT)
        surf.blit(label, (bx + bw + 4, by - 2))
