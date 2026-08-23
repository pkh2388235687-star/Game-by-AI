"""HUD：生命、分数、技能冷却、弹药、增益、Boss 血条。"""

from __future__ import annotations

import pygame

from . import palette as P
from .config import RENDER_H, RENDER_W
from .fonts import get_font


class HUD:
    """游戏内状态叠加层。"""

    def __init__(self) -> None:
        """初始化 HUD。"""
        self.font_big = get_font(20, bold=True)
        self.font_mid = get_font(14, bold=True)
        self.font_small = get_font(12)

    def draw(self, surf: pygame.Surface, game: object) -> None:
        """绘制 HUD。

        :param surf: 渲染画布。
        :param game: 游戏对象。
        """
        self._draw_hearts(surf, game.player)
        self._draw_score(surf, game.player)
        self._draw_skills(surf, game)
        self._draw_ammo(surf, game)
        self._draw_buffs(surf, game)
        self._draw_boss_bar(surf, game)
        if game.settings.get("show_fps", False):
            self._draw_fps(surf, game)

    def _draw_hearts(self, surf: pygame.Surface, player: object) -> None:
        """绘制生命值（颗心）。"""
        x, y = 12, 12
        for i in range(player.max_hp):
            heart_x = x + i * 18
            color = (230, 60, 70) if i < player.hp else (70, 40, 46)
            # 简单心形
            pygame.draw.circle(surf, color, (heart_x + 4, y + 4), 4)
            pygame.draw.circle(surf, color, (heart_x + 10, y + 4), 4)
            pygame.draw.polygon(surf, color, [(heart_x + 2, y + 5), (heart_x + 12, y + 5),
                                              (heart_x + 7, y + 12)])

    def _draw_score(self, surf: pygame.Surface, player: object) -> None:
        """绘制分数与击杀数。"""
        txt = self.font_big.render(f"分数 {player.score}", True, P.UI_TEXT)
        surf.blit(txt, (12, 40))
        kills = self.font_small.render(f"击杀 {player.kills}", True, P.UI_DIM)
        surf.blit(kills, (12, 62))

    def _draw_skills(self, surf: pygame.Surface, game: object) -> None:
        """绘制两个技能的冷却。"""
        # 技能1：轰炸
        self._draw_skill_icon(surf, 12, RENDER_H - 52, game.skill_cd_ratio(), game.player.skill_cd, "炸弹")
        # 技能2：大招
        self._draw_skill_icon(surf, 48, RENDER_H - 52, game.ult_cd_ratio(), game.player.ult_cd, "大招")

    def icon_rect(self, name: str) -> pygame.Rect:
        """返回技能图标的可点击矩形（渲染画布坐标）。

        :param name: "skill" 或 "ult"。
        """
        if name == "skill":
            return pygame.Rect(12, RENDER_H - 52, 32, 32)
        return pygame.Rect(48, RENDER_H - 52, 32, 32)

    def _draw_skill_icon(self, surf: pygame.Surface, x: int, y: int, ratio: float,
                         cd: float, name: str) -> None:
        """绘制单个技能图标与冷却遮罩。"""
        rect = pygame.Rect(x, y, 32, 32)
        pygame.draw.rect(surf, P.UI_PANEL, rect)
        ready = ratio <= 0.0
        border = P.UI_ACCENT if ready else P.UI_DIM
        pygame.draw.rect(surf, border, rect, 2)
        if ready:
            pygame.draw.rect(surf, (70, 200, 230), rect)
        else:
            pygame.draw.rect(surf, P.UI_PANEL, rect)
            # 冷却遮罩从上往下
            cover_h = int(32 * ratio)
            pygame.draw.rect(surf, (80, 80, 100), (x, y, 32, cover_h))
        lbl = self.font_small.render(name, True, P.UI_DIM)
        surf.blit(lbl, (x, y + 34))
        if not ready:
            cd_txt = self.font_small.render(f"{cd:.1f}", True, P.UI_WARN)
            surf.blit(cd_txt, (x + 4, y + 8))

    def _draw_ammo(self, surf: pygame.Surface, game: object) -> None:
        """绘制手榴弹/火箭弹弹药量。"""
        x = RENDER_W - 120
        y = RENDER_H - 92
        gr = game.ammo.get("grenade", 0)
        rk = game.ammo.get("rocket", 0)
        txt = self.font_mid.render(f"榴弹×{gr}  火箭×{rk}", True, P.UI_TEXT)
        surf.blit(txt, (x, y))

    def _draw_buffs(self, surf: pygame.Surface, game: object) -> None:
        """绘制当前增益状态。"""
        parts = []
        if game.buff_damage > 1.0:
            parts.append(f"攻{game.buff_damage:.1f}")
        if game.buff_rapid > 0.0:
            parts.append(f"射{game.buff_rapid:.1f}")
        if game.buff_speed > 0.0:
            parts.append(f"速{game.buff_speed:.1f}")
        if player_shield := game.player.shield_timer > 0:
            parts.append("护盾")
        if parts:
            txt = self.font_small.render(" | ".join(parts), True, P.UI_ACCENT)
            surf.blit(txt, (12, RENDER_H - 90))

    def _draw_boss_bar(self, surf: pygame.Surface, game: object) -> None:
        """绘制 Boss 大血条。"""
        boss = game.active_boss
        if not boss:
            return
        width = RENDER_W - 200
        x = 100
        y = 18
        label = self.font_mid.render(f"Boss · {boss.kind} 强化体", True, P.UI_ACCENT_PINK)
        surf.blit(label, (x, y - 16))
        pygame.draw.rect(surf, (30, 20, 30), (x, y, width, 12))
        ratio = max(0.0, boss.hp / boss.max_hp)
        pygame.draw.rect(surf, (220, 60, 120), (x, y, int(width * ratio), 12))
        pygame.draw.rect(surf, (255, 150, 200), (x, y, width, 12), 1)

    def _draw_fps(self, surf: pygame.Surface, game: object) -> None:
        """绘制帧率。"""
        txt = self.font_small.render(f"FPS {game.framerate:.0f}", True, P.UI_DIM)
        surf.blit(txt, (RENDER_W - 80, 6))
