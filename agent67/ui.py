"""菜单与界面组件：按钮、文本、可滚动的各类菜单界面（含入场动画）。"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import pygame

from . import palette as P
from .config import RENDER_H, RENDER_W
from .fonts import get_font

# 菜单布局常量
BTN_H = 38
BTN_GAP = 12
VIEW_TOP = 104                 # 按钮可视区顶部（标题下方）
VIEW_BOTTOM_MARGIN = 26        # 按钮可视区底部留白


class Button:
    """一个可点击/可聚焦的菜单按钮。"""

    def __init__(self, id: str, label: str, value_getter: Optional[Callable[[], str]] = None) -> None:
        """初始化按钮。

        :param id: 按钮唯一标识（供事件回调）。
        :param label: 按钮主标题。
        :param value_getter: 可选右侧附加值显示函数（如当前难度名）。
        """
        self.id = id
        self.label = label
        self.value_getter = value_getter

    def value(self) -> str:
        """返回按钮右侧显示的值。"""
        return self.value_getter() if self.value_getter else ""

    def draw(self, surf: pygame.Surface, rect: pygame.Rect, font, selected: bool,
             alpha: int = 255) -> None:
        """绘制按钮（支持整体透明度的淡入）。

        :param surf: 画布。
        :param rect: 按钮矩形。
        :param font: 字体。
        :param selected: 是否被选中（高亮）。
        :param alpha: 整体不透明度 0~255。
        """
        temp = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg = P.UI_PANEL_EDGE if selected else P.UI_PANEL
        pygame.draw.rect(temp, bg, temp.get_rect())
        pygame.draw.rect(temp, P.UI_ACCENT if selected else P.UI_DIM, temp.get_rect(), 2)
        color = P.UI_TEXT if selected else P.UI_DIM
        txt = font.render(self.label, True, color)
        temp.blit(txt, (14, rect.centery - rect.y - txt.get_height() // 2))
        val = self.value()
        if val:
            vtxt = font.render(val, True, P.UI_ACCENT if selected else P.UI_WARN)
            temp.blit(vtxt, (rect.w - 14 - vtxt.get_width(), rect.centery - rect.y - vtxt.get_height() // 2))
        if alpha < 255:
            temp.set_alpha(alpha)
        surf.blit(temp, (rect.x, rect.y))


class Menu:
    """一组垂直按钮构成的菜单，支持键盘、鼠标、滚轮滚动与按钮入场动画。"""

    def __init__(self, title: str, buttons: List[Button], width: int = 300,
                 image: Optional[pygame.Surface] = None) -> None:
        """初始化菜单。

        :param title: 标题文本。
        :param buttons: 按钮列表。
        :param width: 按钮宽度。
        :param image: 可选的左侧立绘（放于按钮区左侧）。
        """
        self.title = title
        self.buttons = buttons
        self.selected = 0
        self.width = width
        self.image = image
        self.scroll = 0.0
        self._anim_start = pygame.time.get_ticks()   # 入场动画起点
        self.title_font = get_font(40, bold=True)
        self.btn_font = get_font(17, bold=True)
        self.sub_font = get_font(14)

    def reset_anim(self) -> None:
        """重置入场动画（按钮从上到下依次淡入）。"""
        self._anim_start = pygame.time.get_ticks()

    # -- 布局计算 ---------------------------------------------------------
    def _viewport(self) -> pygame.Rect:
        """按钮可视区矩形（有立绘时靠右）。"""
        if self.image is not None:
            x = RENDER_W - self.width - 24
        else:
            x = RENDER_W // 2 - self.width // 2
        return pygame.Rect(x, VIEW_TOP, self.width, RENDER_H - VIEW_TOP - VIEW_BOTTOM_MARGIN)

    def _content_h(self) -> int:
        """按钮内容总高度。"""
        return len(self.buttons) * BTN_H + (len(self.buttons) - 1) * BTN_GAP

    def _max_scroll(self) -> float:
        """最大滚动量。"""
        return max(0.0, float(self._content_h() - self._viewport().height))

    def _rects(self) -> List[pygame.Rect]:
        """当前（含滚动偏移）各按钮矩形。"""
        vp = self._viewport()
        out = []
        for i in range(len(self.buttons)):
            y = vp.y + i * (BTN_H + BTN_GAP) - int(self.scroll)
            out.append(pygame.Rect(vp.x, y, vp.width, BTN_H))
        return out

    def _ensure_selected_visible(self) -> None:
        """滚动到让当前选中项可见。"""
        vp = self._viewport()
        rects = self._rects()
        if not rects:
            return
        r = rects[self.selected]
        if r.top < vp.top:
            self.scroll += (r.top - vp.top)
        elif r.bottom > vp.bottom:
            self.scroll -= (r.bottom - vp.bottom)
        self.scroll = max(0.0, min(self._max_scroll(), self.scroll))

    # -- 交互 -------------------------------------------------------------
    def move(self, delta: int) -> None:
        """移动选中项并自动滚动到可见。"""
        n = len(self.buttons)
        if n == 0:
            return
        self.selected = (self.selected + delta) % n
        self._ensure_selected_visible()

    def handle_wheel(self, dy: int) -> None:
        """滚轮滚动。

        :param dy: 滚轮增量（正=上滚，负=下滚）。
        """
        self.scroll = max(0.0, min(self._max_scroll(), self.scroll - dy * 34))

    def handle_key(self, key: int) -> Optional[str]:
        """处理键盘按键，返回被激活按钮 id（若无则 None）。"""
        if key in (pygame.K_UP, pygame.K_w):
            self.move(-1)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.move(1)
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            return self.buttons[self.selected].id
        return None

    def handle_click(self, pos: Tuple[int, int]) -> Optional[str]:
        """处理鼠标点击（已按滚动偏移换算），返回被点中按钮 id。

        :param pos: 渲染画布坐标。
        """
        for i, rect in enumerate(self._rects()):
            if rect.collidepoint(pos):
                self.selected = i
                return self.buttons[i].id
        return None

    # -- 绘制 -------------------------------------------------------------
    def draw(self, surf: pygame.Surface, subtitle: str = "") -> None:
        """绘制菜单（标题固定顶部；有立绘时绘制在左；按钮错峰淡入）。"""
        # 标题
        title_img = self.title_font.render(self.title, True, P.UI_TEXT)
        surf.blit(title_img, (RENDER_W // 2 - title_img.get_width() // 2, 14))
        if subtitle:
            sub = self.sub_font.render(subtitle, True, P.UI_ACCENT)
            surf.blit(sub, (RENDER_W // 2 - sub.get_width() // 2, 60))

        # 左侧立绘
        if self.image is not None:
            self._draw_image(surf)

        vp = self._viewport()
        old_clip = surf.get_clip()
        surf.set_clip(vp)
        rects = self._rects()
        elapsed = (pygame.time.get_ticks() - self._anim_start) / 1000.0
        for i, rect in enumerate(rects):
            # 从上到下错峰淡入：第 i 个按钮延迟 i*0.12 秒，0.3 秒内淡入
            prog = max(0.0, min(1.0, (elapsed - i * 0.12) / 0.30))
            if prog <= 0.0:
                continue
            alpha = int(prog * 255)
            draw_rect = rect.move(int((1 - prog) * 90), 0)  # 从右侧滑入
            self.buttons[i].draw(surf, draw_rect, self.btn_font, i == self.selected, alpha)
        surf.set_clip(old_clip)

        # 滚动提示与滚动条
        if self._max_scroll() > 0.001:
            self._draw_scrollbar(surf, vp)

    def _draw_image(self, surf: pygame.Surface) -> None:
        """在按钮区左侧绘制立绘（缩放并垂直居中）。"""
        img_h = RENDER_H - 150
        ratio = img_h / self.image.get_height()
        img_w = int(self.image.get_width() * ratio)
        scaled = pygame.transform.smoothscale(self.image, (img_w, img_h))
        x = 26
        y = (RENDER_H - img_h) // 2 + 12
        surf.blit(scaled, (x, y))

    def _draw_scrollbar(self, surf: pygame.Surface, vp: pygame.Rect) -> None:
        """绘制右侧滚动条。"""
        track_x = vp.right + 6
        pygame.draw.rect(surf, (40, 44, 64), (track_x, vp.y, 6, vp.height))
        ratio = vp.height / float(self._content_h())
        thumb_h = max(24, int(vp.height * ratio))
        max_scroll = self._max_scroll()
        pos = int((vp.height - thumb_h) * (self.scroll / max_scroll if max_scroll else 0.0))
        pygame.draw.rect(surf, P.UI_ACCENT, (track_x, vp.y + pos, 6, thumb_h))
        hint = self.sub_font.render("滚轮 或 ↑↓", True, P.UI_DIM)
        surf.blit(hint, (track_x - hint.get_width() - 4, vp.bottom - 20))
