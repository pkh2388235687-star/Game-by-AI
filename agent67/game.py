"""游戏主编排：状态机、玩法循环、实体交互与 Boss 逻辑。"""

from __future__ import annotations

import math
import os
import random
import sys
from typing import Dict, List, Optional, Tuple

import pygame

from . import palette as P
from . import sprites as sprite_mod
from .config import (
    BOSS_SCORE_THRESHOLD,
    DEFAULT_WIN_H,
    DEFAULT_WIN_W,
    DIFFICULTIES,
    FPS,
    GROUND_Y,
    MAX_ONSCREEN_ENEMIES,
    PROJECTILE_SPEED,
    RENDER_H,
    RENDER_W,
    Settings,
    SKILL_COOLDOWN,
    ULT_COOLDOWN,
    KILLS_PER_GROWTH_TIER,
    GROWTH_FACTOR,
)
from .effects import EffectSystem
from .enemies import BOSS_H, BOSS_W, ENEMY_H, ENEMY_W, Enemy
from .fonts import get_font
from .hud import HUD
from .player import Player, ULT_DURATION
from .projectiles import Projectile
from .pickups import Pickup, random_buff_kind, random_item_kind
from .savegame import SaveSystem
from .ui import Button, Menu
from .world import World

# ---------------------------------------------------------------------------
# Windows 全局键盘读取（绕过窗口焦点限制）
# 某些环境下 pygame 收不到键盘事件（鼠标却正常），用 GetAsyncKeyState
# 直接读取物理按键状态即可让键盘始终有效。
# ---------------------------------------------------------------------------
import ctypes  # noqa: E402

_WIN_USER32 = None
if sys.platform == "win32":
    try:
        _WIN_USER32 = ctypes.windll.user32
    except Exception:
        _WIN_USER32 = None

# pygame 按键常量 -> Windows 虚拟键码 VK
_VK_SPECIAL = {
    pygame.K_LEFT: 0x25, pygame.K_RIGHT: 0x27,
    pygame.K_UP: 0x26, pygame.K_DOWN: 0x28,
    pygame.K_F11: 0x7A,
}


def _vk_for(pygame_key: int) -> int:
    """把 pygame 按键常量映射为 Windows 虚拟键码。

    :param pygame_key: pygame 按键常量（如 pygame.K_a）。
    :return: 虚拟键码（若不是可读键则原样返回）。
    """
    if pygame_key in _VK_SPECIAL:
        return _VK_SPECIAL[pygame_key]
    if pygame.K_a <= pygame_key <= pygame.K_z:
        return pygame_key - 32          # 小写字母转大写字母的 VK
    return pygame_key                   # 空格/回车/退格/Esc 等常量本身即 VK


def _win_key_down(pygame_key: int) -> bool:
    """查询某个物理键当前是否按下（不依赖窗口焦点）。

    :param pygame_key: pygame 按键常量。
    :return: 是否按下。
    """
    if _WIN_USER32 is None:
        return False
    try:
        return bool(_WIN_USER32.GetAsyncKeyState(_vk_for(pygame_key)) & 0x8000)
    except Exception:
        return False


class KeyState:
    """按键状态包装：合并事件驱动按住键、Windows 全局键盘与 pygame.get_pressed()。

    即使某一来源失效（如 pygame 收不到键盘事件），也能保证按键可用。
    """

    def __init__(self, held: set, win: set, pressed) -> None:
        """初始化。

        :param held: 由 KEYDOWN/KEYUP 事件维护的按住键集合。
        :param win: 由 GetAsyncKeyState 读取到的当前按下键集合。
        :param pressed: pygame.key.get_pressed() 结果。
        """
        self.held = held
        self.win = win
        self.pressed = pressed

    def __getitem__(self, key: int) -> bool:
        """返回某个按键是否被按住。"""
        return key in self.held or key in self.win or bool(self.pressed[key])


class Game:
    """游戏顶层对象。"""

    def __init__(self, base_dir: str) -> None:
        """初始化游戏。

        :param base_dir: 可写目录（用于设置/存档）。
        """
        self.base_dir = base_dir
        pygame.init()
        # 音频初始化容错：无声卡环境也不阻断游戏
        try:
            pygame.mixer.init()
        except pygame.error:
            pass

        # 设置与存档
        self.settings = Settings(os.path.join(base_dir, "settings.json"))
        self.save = SaveSystem(base_dir)

        # 窗口
        fs = self.settings.get("fullscreen", False)
        self.screen = pygame.display.set_mode((DEFAULT_WIN_W, DEFAULT_WIN_H),
                                              pygame.FULLSCREEN if fs else 0)
        pygame.display.set_caption("特工67")
        self.render = pygame.Surface((RENDER_W, RENDER_H)).convert()
        # 强制窗口获得键盘焦点（避免启动后键盘无响应）
        self._focus_window()

        # 精灵
        self.sprites = sprite_mod.make_sprites()
        self.hud = HUD()
        # 菜单左侧立绘（透明背景主角图；加载失败则无立绘）
        self.hero_image = self._load_image("menu_hero.png")
        if self.hero_image:
            try:
                pygame.display.set_icon(
                    pygame.transform.smoothscale(self.hero_image, (128, 128)))
            except Exception:
                pass

        # 状态
        self.state = "menu"
        self.framerate = FPS
        self.flash_level = 0
        self.clock = pygame.time.Clock()
        self.shake = 0.0           # 屏幕震动强度
        self.shake_x = 0           # 当前震动水平偏移
        self.shake_y = 0           # 当前震动垂直偏移
        self.hurt_flash = 0        # 受伤红闪剩余帧
        self.ult_cutin = 0         # 大招登场特写剩余帧
        self._held: set = set()       # 事件驱动的按住键集合
        self._win_prev: set = set()   # 上一帧的全局按键状态（用于上升沿检测）
        self.help_scroll = 0.0        # 操作说明界面的滚动量

        # 对局数据
        self.difficulty = self.settings.difficulty()
        self._build_menus()
        self._reset_run_stats()

    # ------------------------------------------------------------------
    # 菜单构建
    # ------------------------------------------------------------------
    def _build_menus(self) -> None:
        """构建各界面菜单。"""
        def fmt_diff() -> str:
            return DIFFICULTIES[self.settings.get("difficulty", "normal")].name

        def fmt_str() -> str:
            return self.settings.get("enemy_strength", "normal")

        def fmt_fs() -> str:
            return "开" if self.settings.get("fullscreen", False) else "关"

        cont = Button("continue", "继续游戏") if self.save.has_run() else None
        main_buttons = [Button("start", "开始游戏")]
        if cont:
            main_buttons.append(cont)
        main_buttons += [
            Button("help", "操作说明"),
            Button("settings", "设置"),
            Button("quit", "退出游戏"),
        ]
        self.menu_main = Menu("特工67", main_buttons, image=self.hero_image)
        self.menu_main.reset_anim()  # 启动即播放按钮入场动画

        self.menu_settings = Menu(
            "设置",
            [
                Button("fullscreen", "全屏", fmt_fs),
                Button("difficulty", "难度", fmt_diff),
                Button("strength", "敌人强度", fmt_str),
                Button("volume", "音量"),
                Button("fps", "显示FPS"),
                Button("back", "返回"),
            ],
        )

        self.menu_pause = Menu("暂停", [
            Button("resume", "继续游戏"),
            Button("save", "存档并退出"),
            Button("restart", "重新开始"),
            Button("back_menu", "返回主菜单"),
        ])
        self.menu_over = Menu("游戏结束", [])
        self.menu_victory = Menu("胜利", [])
        self.menu_confirm_save = Menu("已存档", [Button("ok", "确定")])

    def _reset_run_stats(self) -> None:
        """重置每局统计与增益。"""
        self.score = 0
        self.ammo: Dict[str, int] = {"grenade": 0, "rocket": 0}
        self.buff_damage = 1.0
        self.buff_rapid = 0.0
        self.buff_speed = 0.0
        self.active_boss: Optional[Enemy] = None
        # Boss 机制：每击杀 BOSS_MOB_REQUIRED 个小兵刷新一个 Boss
        self.mob_kills = 0
        self.boss_mob_required = 20

    # ------------------------------------------------------------------
    # 对局开始/结束
    # ------------------------------------------------------------------
    def start_run(self, resume: bool = False) -> None:
        """开始（或继续）一局游戏。

        :param resume: 是否从存档快照继续。
        """
        self.difficulty = self.settings.difficulty()
        self.world = World()
        self.effects = EffectSystem()
        self.enemies: List[Enemy] = []
        self.projectiles: List[Projectile] = []
        self.pickups: List[Pickup] = []
        self.pending_strikes: List[List[float]] = []
        self.next_spawn_x = 0.0
        self.spawn_gap = 150.0
        self._cam_x = 0.0

        # 玩家出生
        start_x = 90.0
        start_y = float(GROUND_Y)
        self.player = Player(self, start_x, start_y)

        if resume:
            snap = self.save.load_run()
            if snap:
                self._apply_snapshot(snap)

        self._reset_run_stats()
        # 初始敌人与地面保证
        self.world.ensure(self.player.rect.centerx)
        self.next_spawn_x = self.player.rect.centerx + RENDER_W + 80
        self._spawn_initial_enemies()
        self.state = "playing"

    def _apply_snapshot(self, snap: Dict) -> None:
        """应用存档快照以恢复对局。

        :param snap: 存档快照字典。
        """
        self.player.hp = int(snap.get("hp", self.player.max_hp))
        self.player.score = int(snap.get("score", 0))
        self.buff_damage = float(snap.get("buff_damage", 1.0))
        self.buff_rapid = float(snap.get("buff_rapid", 0.0))
        self.buff_speed = float(snap.get("buff_speed", 0.0))
        self.ammo = dict(snap.get("ammo", {}))
        self.difficulty = DIFFICULTIES.get(snap.get("difficulty", "normal"), self.difficulty)

    def _snapshot(self) -> Dict:
        """生成对局快照字典。"""
        return {
            "hp": self.player.hp,
            "score": self.player.score,
            "buff_damage": self.buff_damage,
            "buff_rapid": self.buff_rapid,
            "buff_speed": self.buff_speed,
            "ammo": self.ammo,
            "difficulty": self.settings.get("difficulty", "normal"),
        }

    def end_run(self, victory: bool = False) -> None:
        """结束对局，进入结算界面。"""
        self.state = "victory" if victory else "gameover"
        self.score = self.player.score
        is_record = self.save.record_game_over(self.score, self.player.kills)
        self.last_record = is_record
        if victory:
            self.menu_victory = Menu("任务完成", [
                Button("restart", "再次挑战"),
                Button("back_menu", "返回主菜单"),
            ])
        else:
            self.menu_over = Menu("特工阵亡", [
                Button("retry", "再次挑战"),
                Button("back_menu", "返回主菜单"),
            ])

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------
    def run(self) -> None:
        """运行主循环。"""
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            self.framerate = self.clock.get_fps()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.WINDOWFOCUSLOST:
                    # 真正丢失焦点时清空按键，避免"卡键"
                    self._held.clear()
                if event.type == pygame.KEYDOWN:
                    self._held.add(event.key)
                elif event.type == pygame.KEYUP:
                    self._held.discard(event.key)
                if event.type == pygame.MOUSEBUTTONDOWN:
                    # 鼠标点击时通常窗口获得焦点；仅在未聚焦时再强化一次
                    if not pygame.key.get_focused():
                        self._focus_window()
                if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                    self.toggle_fullscreen()
                if self.state in ("playing", "pause", "menu", "settings", "help", "gameover",
                                  "victory") and event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self._on_escape()
                self._handle_event(event)

            # 处理全局键盘（GetAsyncKeyState），菜单导航与全局快捷键
            self._process_win_keys()

            self.update(dt)
            self.draw()

        pygame.quit()
        sys.exit(0)

    def _on_escape(self) -> None:
        """按 Esc 时的界面切换。"""
        if self.state == "playing":
            self.state = "pause"
            self.menu_pause.reset_anim()
        elif self.state == "pause":
            self.state = "playing"
        elif self.state in ("menu", "settings", "help"):
            self.state = "menu"
            self.menu_main.reset_anim()

    def _handle_event(self, event: pygame.event.Event) -> None:
        """分发键盘/鼠标事件给当前界面。"""
        # 滚轮滚动：用于菜单与帮助界面
        if event.type == pygame.MOUSEWHEEL:
            self._on_wheel(event.y)

        # 对局中：点击 HUD 技能图标也可释放技能（鼠标兜底）
        if self.state == "playing" and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = self._to_render(event.pos)
            if self.hud.icon_rect("skill").collidepoint(pos):
                if self.player.skill_cd <= 0 and not self.player.sword_mode:
                    self.player._cast_airstrike()
            elif self.hud.icon_rect("ult").collidepoint(pos):
                if self.player.ult_cd <= 0 and not self.player.sword_mode and self.player.sword_phase == 0:
                    self.player._start_sword_mode()

        if self.state == "menu":
            if event.type == pygame.KEYDOWN:
                self._menu_action(self.menu_main.handle_key(event.key))
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._menu_action(self.menu_main.handle_click(self._to_render(event.pos)))
        elif self.state == "settings":
            if event.type == pygame.KEYDOWN:
                self._menu_action(self.menu_settings.handle_key(event.key))
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._menu_action(self.menu_settings.handle_click(self._to_render(event.pos)))
        elif self.state == "help":
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN,
                                                             pygame.K_SPACE, pygame.K_BACKSPACE):
                self.state = "menu"
        elif self.state == "pause":
            if event.type == pygame.KEYDOWN:
                self._menu_action(self.menu_pause.handle_key(event.key))
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._menu_action(self.menu_pause.handle_click(self._to_render(event.pos)))
        elif self.state == "gameover":
            if event.type == pygame.KEYDOWN:
                self._menu_action(self.menu_over.handle_key(event.key))
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._menu_action(self.menu_over.handle_click(self._to_render(event.pos)))
        elif self.state == "victory":
            if event.type == pygame.KEYDOWN:
                self._menu_action(self.menu_victory.handle_key(event.key))
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._menu_action(self.menu_victory.handle_click(self._to_render(event.pos)))

    def _on_wheel(self, dy: int) -> None:
        """滚轮事件：滚动当前菜单或帮助界面。

        :param dy: 滚轮增量（正=上滚，负=下滚）。
        """
        if self.state in ("menu", "settings", "pause", "gameover", "victory"):
            menu = self._current_menu()
            if menu:
                menu.handle_wheel(dy)
        elif self.state == "help":
            self.help_scroll = max(0.0, min(self._help_max_scroll(), self.help_scroll - dy * 34))

    def _current_menu(self) -> Optional[Menu]:
        """返回当前状态对应的菜单对象。"""
        if self.state == "menu":
            return self.menu_main
        if self.state == "settings":
            return self.menu_settings
        if self.state == "pause":
            return self.menu_pause
        if self.state == "gameover":
            return self.menu_over
        if self.state == "victory":
            return self.menu_victory
        return None

    def _to_render(self, pos: Tuple[int, int]) -> Tuple[int, int]:
        """把窗口坐标换算到内部渲染画布坐标。

        :param pos: 窗口坐标 (x, y)。
        :return: 渲染画布坐标。
        """
        w, h = self.screen.get_size()
        if w <= 0 or h <= 0:
            return pos
        return (int(pos[0] * RENDER_W / w), int(pos[1] * RENDER_H / h))

    def _menu_action(self, action: Optional[str]) -> None:
        """执行菜单动作。"""
        if self.state == "menu":
            if action == "start":
                self.start_run()
            elif action == "continue":
                self.start_run(resume=True)
            elif action == "help":
                self.state = "help"
                self.help_scroll = 0.0
            elif action == "settings":
                self.state = "settings"
                self.menu_settings.reset_anim()
            elif action == "quit":
                pygame.event.post(pygame.event.Event(pygame.QUIT))
        elif self.state == "settings":
            if action == "fullscreen":
                self.toggle_fullscreen()
            elif action == "difficulty":
                self.settings.cycle_difficulty()
            elif action == "strength":
                self.settings.cycle_enemy_strength()
            elif action == "volume":
                self._next_volume()
            elif action == "fps":
                self.settings.set("show_fps", not self.settings.get("show_fps", False))
            elif action == "back":
                self.state = "menu"
                self.menu_main.reset_anim()
        elif self.state == "pause":
            if action == "resume":
                self.state = "playing"
            elif action == "save":
                self.save.save_run(self._snapshot())
                self.state = "menu"
                self.menu_main.reset_anim()
            elif action == "restart":
                self.start_run()
            elif action == "back_menu":
                self.state = "menu"
                self.menu_main.reset_anim()
        elif self.state == "gameover":
            if action == "retry":
                self.start_run()
            elif action == "back_menu":
                self.state = "menu"
                self.menu_main.reset_anim()
        elif self.state == "victory":
            if action == "restart":
                self.start_run()
            elif action == "back_menu":
                self.state = "menu"
                self.menu_main.reset_anim()

    def _next_volume(self) -> None:
        """循环切换音量档位。"""
        v = self.settings.get("volume", 0.8)
        steps = [0.0, 0.2, 0.5, 0.8, 1.0]
        idx = steps.index(v) if v in steps else 1
        self.settings.set("volume", steps[(idx + 1) % len(steps)])

    def toggle_fullscreen(self) -> None:
        """切换全屏。"""
        fs = self.settings.toggle_fullscreen()
        self.screen = pygame.display.set_mode((DEFAULT_WIN_W, DEFAULT_WIN_H),
                                              pygame.FULLSCREEN if fs else 0)
        self._focus_window()

    def _asset_path(self, name: str) -> str:
        """返回打包/源码两种运行方式下游戏资源文件的绝对路径。

        :param name: game_assets 下的文件名。
        :return: 绝对路径。
        """
        if getattr(sys, "frozen", False):
            base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, "game_assets", name)

    def _load_image(self, name: str) -> Optional[pygame.Surface]:
        """从 game_assets 加载一张图片（失败返回 None）。

        :param name: 文件名。
        :return: Surface 或 None。
        """
        path = self._asset_path(name)
        try:
            if os.path.exists(path):
                return pygame.image.load(path).convert_alpha()
        except Exception:
            pass
        return None

    def _focus_window(self) -> None:
        """尽力把 pygame 窗口拉到前台并获得键盘焦点（Windows）。"""
        try:
            import ctypes
            info = pygame.display.get_wm_info()
            hwnd = info.get("window")
            if not hwnd:
                return
            user32 = ctypes.windll.user32
            # SW_RESTORE = 9
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
        except Exception:
            # 焦点 API 不可用/被系统限制时忽略，不影响运行
            pass

    def _current_win_keys(self) -> set:
        """返回当前通过 GetAsyncKeyState 读到的、游戏关心的按键集合。

        :return: 被按下的 pygame 按键常量集合。
        """
        keys = [pygame.K_a, pygame.K_d, pygame.K_w, pygame.K_s,
                pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN,
                pygame.K_SPACE, pygame.K_j, pygame.K_z, pygame.K_q,
                pygame.K_e, pygame.K_ESCAPE, pygame.K_RETURN,
                pygame.K_BACKSPACE, pygame.K_F11]
        return {k for k in keys if _win_key_down(k)}

    def _process_win_keys(self) -> None:
        """处理全局按键的"上升沿"（刚按下），用于菜单导航与全局快捷键。

        仅当 pygame 收不到键盘事件（窗口未聚焦）时才启用，避免与事件系统重复触发。
        """
        if pygame.key.get_focused():
            return
        down = self._current_win_keys()
        new_pressed = down - self._win_prev
        self._win_prev = down
        for key in new_pressed:
            if key == pygame.K_ESCAPE:
                self._on_escape()
                continue
            if key == pygame.K_F11:
                self.toggle_fullscreen()
                continue
            self._route_win_key(key)

    def _route_win_key(self, key: int) -> None:
        """把全局按键路由到当前界面的菜单处理器。

        :param key: pygame 按键常量。
        """
        if self.state == "menu":
            self._menu_action(self.menu_main.handle_key(key))
        elif self.state == "settings":
            self._menu_action(self.menu_settings.handle_key(key))
        elif self.state == "pause":
            self._menu_action(self.menu_pause.handle_key(key))
        elif self.state == "gameover":
            self._menu_action(self.menu_over.handle_key(key))
        elif self.state == "victory":
            self._menu_action(self.menu_victory.handle_key(key))
        elif self.state == "help":
            if key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE, pygame.K_BACKSPACE):
                self.state = "menu"

    # ------------------------------------------------------------------
    # 每帧更新
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        """更新当前状态。"""
        self.flash_level = max(0, self.flash_level - 1)
        # 屏幕震动 / 受伤红闪 / 大招特写 计时（各状态下都递减）
        self.shake = max(0.0, self.shake - 0.7)
        self.shake_x = int((random.random() * 2 - 1) * self.shake)
        self.shake_y = int((random.random() * 2 - 1) * self.shake)
        self.hurt_flash = max(0, self.hurt_flash - 1)
        self.ult_cutin = max(0, self.ult_cutin - 1)
        if self.state != "playing":
            return
        self._update_playing(dt)

    def shake_screen(self, mag: float = 8.0) -> None:
        """触发屏幕震动。

        :param mag: 震动强度。
        """
        self.shake = max(self.shake, mag)

    def hurt_overlay(self) -> None:
        """触发受伤红闪。"""
        self.hurt_flash = 22

    def start_ult_cutin(self) -> None:
        """触发大招登场特写（显示主角立绘与光效）。"""
        self.ult_cutin = 50

    def _touch_rects(self) -> Dict[str, pygame.Rect]:
        """返回屏幕虚拟按键的矩形（渲染画布坐标），供鼠标/触控操作。

        :return: 含 left/right/jump 三个矩形的字典。
        """
        y = RENDER_H - 56
        return {
            "left": pygame.Rect(RENDER_W - 158, y, 42, 42),
            "right": pygame.Rect(RENDER_W - 110, y, 42, 42),
            "jump": pygame.Rect(RENDER_W - 62, y, 42, 42),
        }

    def _draw_touch(self, surf: pygame.Surface) -> None:
        """绘制屏幕虚拟按键。"""
        rects = self._touch_rects()
        for key, rect in rects.items():
            pygame.draw.rect(surf, (30, 34, 52), rect)
            pygame.draw.rect(surf, P.UI_ACCENT, rect, 2)
            if key == "left":
                pygame.draw.polygon(surf, P.UI_TEXT,
                                    [(rect.centerx + 7, rect.centery),
                                     (rect.centerx - 7, rect.centery - 10),
                                     (rect.centerx - 7, rect.centery + 10)])
            elif key == "right":
                pygame.draw.polygon(surf, P.UI_TEXT,
                                    [(rect.centerx - 7, rect.centery),
                                     (rect.centerx + 7, rect.centery - 10),
                                     (rect.centerx + 7, rect.centery + 10)])
            else:
                font = get_font(16, bold=True)
                img = font.render("跳", True, P.UI_TEXT)
                surf.blit(img, (rect.centerx - img.get_width() // 2,
                                rect.centery - img.get_height() // 2))

    def _update_playing(self, dt: float) -> None:
        """更新对局内容。"""
        # 鼠标：虚拟按键与射击判定
        mb = pygame.mouse.get_pressed()
        mpos = self._to_render(pygame.mouse.get_pos())
        tr = self._touch_rects()
        over_touch = (tr["left"].collidepoint(mpos) or tr["right"].collidepoint(mpos)
                      or tr["jump"].collidepoint(mpos)
                      or self.hud.icon_rect("skill").collidepoint(mpos)
                      or self.hud.icon_rect("ult").collidepoint(mpos))

        # 合成输入：真实键盘（事件 + 全局读取）+ 屏幕虚拟按键（鼠标按住对应按钮）
        win_keys = self._current_win_keys()
        input_keys = set(self._held)
        if mb[0]:
            if tr["left"].collidepoint(mpos):
                input_keys.add(pygame.K_LEFT)
            if tr["right"].collidepoint(mpos):
                input_keys.add(pygame.K_RIGHT)
            if tr["jump"].collidepoint(mpos):
                input_keys.add(pygame.K_SPACE)
        keys = KeyState(input_keys, win_keys, pygame.key.get_pressed())

        # 玩家
        self.player.update(keys, self.world, dt)

        # 相机（死区滚动，玩家先在屏幕内明显移动，到达边缘才卷动画面）
        self._update_camera()

        # 鼠标攻击：左键发射子弹（光标在虚拟按键上时不射击），右键投掷道具
        if mb[0] and not over_touch:
            self.player.primary_attack()
        if mb[2]:
            self.player.throw_item()

        # 世界生成（保证覆盖到玩家前方）
        cam = self.camera_x
        self.world.ensure(max(cam, self.player.rect.centerx) + RENDER_W)

        # 敌人生成（前进刷新）
        self._spawn_enemies_ahead(cam)
        self._update_enemies(dt, cam)
        self._despawn_behind(cam)

        # 投射物
        self._update_projectiles(dt)

        # 拾取物刷新与收集
        self._update_pickups(cam)

        # 轰炸打击结算
        self._update_strikes()

        # 特效
        self.effects.update()

        # 玩家死亡
        if not self.player.alive:
            self.end_run(victory=False)

    @property
    def camera_x(self) -> int:
        """当前相机 x（带死区滚动，且不小于 0）。"""
        return max(0, int(self._cam_x))

    def _update_camera(self) -> None:
        """非对称活动区相机。

        人物在屏幕上 [ZONE_LEFT, ZONE_RIGHT] 之间自由移动，此时相机固定；
        一旦走出该区域（越过左界向左 / 越过右界向右），相机才向对应方向卷动。
        前后视距不同（右前方留出更多视野，便于观察来袭敌人）。
        """
        ZONE_LEFT = 120     # 活动区左边界（屏幕坐标）
        ZONE_RIGHT = 412    # 活动区右边界（屏幕坐标，右侧留出更大视距）
        p_center = self.player.rect.centerx
        cam = self._cam_x
        if p_center < cam + ZONE_LEFT:
            cam = p_center - ZONE_LEFT        # 走出左边界 → 相机左移
        elif p_center > cam + ZONE_RIGHT:
            cam = p_center - ZONE_RIGHT       # 走出右边界 → 相机右移
        self._cam_x = max(0, cam)

    # ------------------------------------------------------------------
    # 敌人生成
    # ------------------------------------------------------------------
    def _spawn_initial_enemies(self) -> None:
        """开局在前方生成少量敌人。"""
        for i in range(3):
            x = self.player.rect.centerx + 260 + i * 140
            self._spawn_enemy_at(x)

    def _spawn_enemies_ahead(self, cam: int) -> None:
        """当玩家前进时按间距在前方刷新敌人。"""
        frontier = max(cam, self.player.rect.centerx) + RENDER_W + 60
        density = self.difficulty.spawn_density
        # 控制屏幕内敌人数量
        visible = [e for e in self.enemies if cam - 40 < e.rect.centerx < cam + RENDER_W + 60]
        if len(visible) < MAX_ONSCREEN_ENEMIES and self.next_spawn_x < frontier:
            self._spawn_enemy_at(self.next_spawn_x)
            self.next_spawn_x += self.spawn_gap / max(0.5, density)
            # 随机，间距带变化
            self.spawn_gap = random.uniform(150, 240) / max(0.5, density)

    def _spawn_enemy_at(self, x: float) -> None:
        """在 x 位置生成一个敌人（可能在地面或屋顶）。

        :param x: 世界 x。
        """
        # 是否生成 Boss 类型的普通敌人变体由分数触发（此处为普通敌人）
        kind = "ranged" if random.random() < 0.35 else "melee"
        # 选择屋顶或地面
        roof_rect = None
        y = float(GROUND_Y)
        if random.random() < 0.35:
            roofs = [p for p in self.world.current_enemy_roofs() if p.left <= x <= p.right]
            if roofs:
                roof_rect = random.choice(roofs)
                y = float(roof_rect.top)
        self._add_enemy(kind, x, y, roof_rect)

    def _add_enemy(self, kind: str, x: float, y: float, roof_rect: Optional[pygame.Rect] = None,
                   boss: bool = False) -> None:
        """实例化并加入一个敌人（含成长机制：每击杀若干敌人，后续血量 ×1.5）。"""
        str_mult = self.settings.enemy_strength_mult()
        diff = self.difficulty
        # 成长：按玩家累计击杀数分档（每 KILLS_PER_GROWTH_TIER 击杀 ×GROWTH_FACTOR）
        tier = self.player.kills // KILLS_PER_GROWTH_TIER
        growth = GROWTH_FACTOR ** tier
        base_hp = 20 if boss else 2
        hp = max(1, int(round(base_hp * str_mult * diff.enemy_hp_mult * growth)))
        enemy = Enemy(self, kind, x, y, hp, diff.enemy_speed_mult, diff.enemy_interval_mult,
                      boss=boss, roof_rect=roof_rect)
        self.enemies.append(enemy)

    def _update_enemies(self, dt: float, cam: int) -> None:
        """更新所有敌人（敌人仅通过自身攻击/子弹对玩家造成伤害，碰触不掉血）与清理。"""
        for e in list(self.enemies):
            e.update(self, self.world, dt)
        # 清理已死亡且死亡动画结束的敌人
        self.enemies = [e for e in self.enemies if not (e.dead and e.death_timer > 24)]

    def _despawn_behind(self, cam: int) -> None:
        """移除远离相机背后的敌人。"""
        self.enemies = [e for e in self.enemies if e.rect.right > cam - 420]

    # ------------------------------------------------------------------
    # 投射物
    # ------------------------------------------------------------------
    def spawn_player_bullet(self, x: float, y: float, facing: int, dmg: int) -> None:
        """生成玩家子弹（受攻击强化与急速加成）。"""
        dmg2 = int(round(dmg * self.buff_damage))
        speed = PROJECTILE_SPEED * (1.0 + self.buff_rapid * 0.5)
        self.projectiles.append(Projectile(x, y, facing * speed, 0.0, "bullet", "player", dmg2))
        # 手榴弹/火箭弹优先于普通子弹（若不使用则发射子弹，此处仍保留普通子弹）

    def spawn_enemy_bullet(self, x: float, y: float, vx: float, vy: float) -> None:
        """生成敌方子弹。"""
        self.projectiles.append(Projectile(x, y, vx, vy, "enemy_bullet", "enemy", 1))

    def throw_grenade(self) -> None:
        """玩家投掷手榴弹。"""
        p = self.player
        x = p.rect.centerx + p.facing * 16
        y = p.rect.centery - 6
        self.projectiles.append(Projectile(x, y, p.facing * 7.0, -8.0, "grenade", "player",
                                           int(round(2 * self.buff_damage)), splash=60))
        self.effects.add_text("榴弹!", p.rect.centerx - self.camera_x, p.rect.y - 16, P.UI_WARN, 14)
        p.shoot_flash = 4

    def launch_rocket(self) -> None:
        """玩家发射火箭弹。"""
        p = self.player
        x = p.rect.centerx + p.facing * 26
        y = p.rect.centery - 4
        self.projectiles.append(Projectile(x, y, p.facing * 12.0, 0.0, "rocket", "player",
                                           int(round(3 * self.buff_damage)), splash=54))
        p.shoot_flash = 6
        self.effects.spawn_particles(x, y, (255, 150, 60), 6, 3.0, 14, 2, 0.0,
                                     base_angle=0 if p.facing > 0 else math.pi)

    def add_airstrike_column(self, x: float) -> None:
        """为轰炸支援增加一列落弹（视觉 + 延迟爆炸）。

        :param x: 落弹的世界 x 坐标。
        """
        self.effects.add_bombstrike(x, GROUND_Y)
        # 落弹到地面约 26 帧后爆炸
        self.pending_strikes.append([x, 26.0])

    def _update_strikes(self) -> None:
        """处理轰炸爆炸结算。"""
        for st in list(self.pending_strikes):
            st[1] -= 1
            if st[1] <= 0:
                x = st[0]
                self.pending_strikes.remove(st)
                self._explode(x, GROUND_Y, 46, int(round(2 * self.buff_damage)))

    def _explode(self, x: float, y: float, radius: float, dmg: int) -> None:
        """在指定位置造成范围爆炸（伤害敌人 + 特效）。"""
        self.effects.spawn_particles(x, y, P.EXPLOSION, 26, 7.0, 34, 4, 0.12)
        self.effects.spawn_particles(x, y, (255, 120, 40), 18, 6.0, 26, 3, 0.1)
        self.effects.add_shockwave(x, y, radius * 1.4, P.BOMB)
        self.flash(2)
        for e in list(self.enemies):
            if e.dead:
                continue
            cx = e.rect.centerx
            cy = e.rect.centery
            if math.hypot(cx - x, cy - y) <= radius or abs(cx - x) <= radius:
                e.take_damage(self, dmg, knockback_dir=1 if cx > x else -1)

    def slam_damage(self, cx: float, cy: float, r: float, dmg: int) -> None:
        """大招落地范围伤害。"""
        for e in list(self.enemies):
            if e.dead:
                continue
            ex = e.rect.centerx
            ey = e.rect.centery
            if math.hypot(ex - cx, ey - cy) <= r:
                e.take_damage(self, dmg, knockback_dir=1 if ex > cx else -1)

    def _update_projectiles(self, dt: float) -> None:
        """更新并处理投射物碰撞与爆炸。"""
        player = self.player
        for pr in list(self.projectiles):
            pr.update(self.world)
            if not pr.alive:
                if pr.exploded and pr.splash > 0:
                    ex, ey = pr.x, pr.y
                    self._explode(ex, ey, pr.splash, pr.damage)
                self.projectiles.remove(pr)
                continue

            if pr.owner == "player":
                # 命中敌人
                hit = False
                for e in list(self.enemies):
                    if e.dead:
                        continue
                    if pr.rect.colliderect(e.rect):
                        if pr.splash > 0:
                            ex, ey = pr.x, pr.y
                            pr.alive = False
                            self._explode(ex, ey, pr.splash, pr.damage)
                        else:
                            died = e.take_damage(self, pr.damage, knockback_dir=1 if pr.vx > 0 else -1)
                            pr.alive = False
                        hit = True
                        break
                if hit:
                    self.projectiles.remove(pr)
            else:
                # 敌方子弹命中玩家
                if pr.rect.colliderect(player.rect):
                    player.take_damage(1)
                    if pr in self.projectiles:
                        self.projectiles.remove(pr)

    # ------------------------------------------------------------------
    # 拾取物
    # ------------------------------------------------------------------
    def _spawn_pickup(self, kind: str, x: float, y: float) -> None:
        """生成一个拾取物。"""
        self.pickups.append(Pickup(kind, x, y, self))

    def _update_pickups(self, cam: int) -> None:
        """刷新掉落、处理拾取与收集。"""
        # 玩家接触拾取
        for pk in list(self.pickups):
            pk.update()
            if pk.alive and pk.rect().colliderect(self.player.rect):
                pk.collect(self.player)
            if not pk.alive:
                self.pickups.remove(pk)

        # 随机在地图上刷新增益/道具（肉鸽元素）
        if random.random() < 0.006:
            x = self.player.rect.centerx + random.uniform(200, 420)
            y = float(GROUND_Y)
            roofs = [p for p in self.world.current_enemy_roofs() if p.left <= x <= p.right]
            if roofs:
                y = float(random.choice(roofs).top)
            kind = random_buff_kind() if random.random() < 0.5 else random_item_kind()
            self._spawn_pickup(kind, x, y)

    def on_enemy_killed(self, enemy: Enemy) -> None:
        """敌人被击杀时的统一处理（得分已加，此处处理增益反馈、掉落与 Boss 触发）。"""
        self.player.kills += 1
        # 近战形态（大招）增益：击杀获得护盾
        if self.player.sword_mode:
            self.player.gain_shield()
        # 概率掉落拾取物
        if random.random() < 0.18:
            kind = random_item_kind() if random.random() < 0.6 else random_buff_kind()
            self._spawn_pickup(kind, enemy.rect.centerx, enemy.rect.bottom)
        # Boss 死亡：血条（active_boss）立即清空，直到下一个 Boss 刷新才再次显示
        if enemy.boss:
            if self.active_boss is enemy:
                self.active_boss = None
            self.effects.add_text("BOSS 击破!", self.camera_x + RENDER_W // 2 - 40, 90,
                                  P.UI_ACCENT_PINK, 22)
        else:
            # 击杀小兵计数，满 BOSS_MOB_REQUIRED 且屏幕内无存活 Boss 时刷新 Boss
            self.mob_kills += 1
            if self.mob_kills >= self.boss_mob_required and not self._alive_boss():
                self._spawn_boss(self._next_boss_kind())
                self.mob_kills = 0

    # ------------------------------------------------------------------
    # Boss
    # ------------------------------------------------------------------
    def _alive_boss(self) -> bool:
        """当前屏幕是否存在未死亡的 Boss。"""
        return any(e.boss and not e.dead for e in self.enemies)

    def _next_boss_kind(self) -> str:
        """返回下一个 Boss 的种类（近战/远程交替）。"""
        # 依据已刷 Boss 数量交替
        boss_count = sum(1 for e in self.enemies if e.boss)
        return "melee" if boss_count % 2 == 0 else "ranged"

    def _spawn_boss(self, kind: str) -> None:
        """在玩家前方刷出一个 Boss，并设为血条显示目标。

        :param kind: "melee" 或 "ranged"。
        """
        x = self.camera_x + RENDER_W + 60
        self._add_enemy(kind, x, float(GROUND_Y), boss=True)
        boss = self.enemies[-1]
        self.active_boss = boss
        self.effects.add_text("⚠ BOSS 出现!", self.camera_x + RENDER_W // 2 - 60, 60,
                              P.UI_ACCENT_PINK, 24)

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------
    def draw(self) -> None:
        """绘制整帧并缩放到窗口。"""
        r = self.render
        r.fill((0, 0, 0))

        if self.state == "playing":
            self._draw_playing(r)
        elif self.state == "pause":
            self._draw_playing(r)
            self._dim(r)
            self.menu_pause.draw(r)
        elif self.state == "menu":
            self._draw_menu_bg(r)
            sub = f"最高分 {self.save.high_score}"
            self.menu_main.draw(r, sub)
        elif self.state == "settings":
            self._draw_menu_bg(r)
            self.menu_settings.draw(r)
        elif self.state == "help":
            self._draw_menu_bg(r)
            ov = pygame.Surface((RENDER_W, RENDER_H))
            ov.set_alpha(215)
            ov.fill((10, 12, 24))
            r.blit(ov, (0, 0))
            self._draw_help(r)
        elif self.state == "gameover":
            self._draw_menu_bg(r)
            rec = " · 新纪录!" if getattr(self, "last_record", False) else ""
            self.menu_over.draw(r, f"得分 {self.score}{rec}")
        elif self.state == "victory":
            self._draw_menu_bg(r)
            rec = " · 新纪录!" if getattr(self, "last_record", False) else ""
            self.menu_victory.draw(r, f"得分 {self.score}{rec}")

        # 全屏闪烁
        if self.flash_level > 0:
            alpha = int(255 * self.flash_level / 6)
            ov = pygame.Surface((RENDER_W, RENDER_H))
            ov.set_alpha(alpha)
            ov.fill((255, 255, 255))
            r.blit(ov, (0, 0))

        # 缩放到窗口
        self.screen.blit(pygame.transform.scale(r, self.screen.get_size()), (0, 0))
        pygame.display.flip()

    def _draw_playing(self, surf: pygame.Surface) -> None:
        """绘制对局画面。"""
        # 屏幕震动：整体把世界绘制平移到偏移量（水平震动）
        shake_x = self.shake_x
        cam = max(0, self.camera_x + shake_x)
        self.world.draw_background(surf, cam)
        self.world.draw_platforms(surf, cam)
        self.world.draw_ground(surf, cam)

        # 投射物、拾取物、敌人、玩家
        for pr in self.projectiles:
            pr.draw(surf, cam)
        for pk in self.pickups:
            pk.draw(surf, cam)
        self.player.draw(surf, cam)
        for e in self.enemies:
            if not e.dead:
                e.draw(surf, cam)

        # 特效（世界坐标）
        self.effects.draw(surf, cam, 0)

        # HUD
        self.hud.draw(surf, self)

        # 屏幕虚拟按键（鼠标/触控兜底）
        self._draw_touch(surf)

        # 受伤红闪（暗角）
        if self.hurt_flash > 0:
            self._draw_hurt_vignette(surf)

        # 大招登场特写
        if self.ult_cutin > 0:
            self._draw_ult_cutin(surf)

    def _draw_hurt_vignette(self, surf: pygame.Surface) -> None:
        """绘制受伤时屏幕边缘的红光暗角。"""
        a = int(120 * self.hurt_flash / 22)
        if a <= 0:
            return
        edge = 24
        color = (190, 30, 45)
        # 四周红边
        pygame.draw.rect(surf, color, (0, 0, RENDER_W, edge))
        pygame.draw.rect(surf, color, (0, RENDER_H - edge, RENDER_W, edge))
        pygame.draw.rect(surf, color, (0, 0, edge, RENDER_H))
        pygame.draw.rect(surf, color, (RENDER_W - edge, 0, edge, RENDER_H))
        # 中间轻微红晕
        ov = pygame.Surface((RENDER_W, RENDER_H))
        ov.set_alpha(int(28 * self.hurt_flash / 22))
        ov.fill(color)
        surf.blit(ov, (0, 0))

    def _draw_ult_cutin(self, surf: pygame.Surface) -> None:
        """大招登场特写：中央放大显示主角立绘、能量光圈与文字（出现即亮，随后淡出）。"""
        t = self.ult_cutin / 50.0            # 1→0
        alpha = max(0, min(255, int(255 * t)))
        if alpha <= 0:
            return
        # 半透明底幕（压暗背景）
        bg = pygame.Surface((RENDER_W, RENDER_H))
        bg.set_alpha(min(210, int(alpha * 0.85)))
        bg.fill((8, 6, 22))
        surf.blit(bg, (0, 0))

        cx = RENDER_W // 2
        cy = RENDER_H // 2 - 12
        if self.hero_image:
            h = max(120, int(210 * (0.9 + 0.1 * t)))
            ratio = h / self.hero_image.get_height()
            w = int(self.hero_image.get_width() * ratio)
            scaled = pygame.transform.smoothscale(self.hero_image, (w, h))
            scaled.set_alpha(alpha)
            surf.blit(scaled, (cx - w // 2, cy - h // 2))
            # 能量光圈（脉冲扩张）
            ring_r = int(w * 0.62 * (1.15 - 0.15 * t))
            pygame.draw.circle(surf, P.ENERGY, (cx, cy), ring_r, 3)
            pygame.draw.circle(surf, (220, 250, 255), (cx, cy), int(w * 0.5 * (1.15 - 0.15 * t)), 1)
        font = get_font(32, bold=True)
        label = font.render("斩 杀 形 态", True, P.UI_ACCENT)
        label.set_alpha(alpha)
        surf.blit(label, (cx - label.get_width() // 2, cy + 150))
        font2 = get_font(15, bold=True)
        sub = font2.render("武士刀 · 20 秒 · 击杀获得护盾", True, P.UI_TEXT)
        sub.set_alpha(alpha)
        surf.blit(sub, (cx - sub.get_width() // 2, cy + 188))

    def _draw_menu_bg(self, surf: pygame.Surface) -> None:
        """绘制主菜单背景（星空 + 街景剪影）。"""
        for yy in range(RENDER_H):
            t = yy / RENDER_H
            col = (int(P.SKY_TOP[0] + (P.SKY_BOTTOM[0] - P.SKY_TOP[0]) * t),
                   int(P.SKY_TOP[1] + (P.SKY_BOTTOM[1] - P.SKY_TOP[1]) * t),
                   int(P.SKY_TOP[2] + (P.SKY_BOTTOM[2] - P.SKY_TOP[2]) * t))
            pygame.draw.line(surf, col, (0, yy), (RENDER_W, yy))
        # 运行中的对局背景若存在则透出
        if hasattr(self, "world"):
            self.world.draw_background(surf, 0)

    def _draw_help(self, surf: pygame.Surface) -> None:
        """绘制操作说明面板（两栏布局，超出一屏可用滚轮滚动）。"""
        rows = [
            ("移动", "◀／▶ 或 ←→ ／ A D"),
            ("跳跃", "跳按钮 或 空格 ／ W ／ ↑"),
            ("射击", "左键 或 J ／ Z"),
            ("投掷道具", "右键"),
            ("技能·轰炸", "Q 或 点左下「炸弹」"),
            ("大招·近战", "E 或 点左下「大招」"),
            ("暂停 ／ 返回", "Esc"),
            ("切换全屏", "F11"),
        ]
        notes = [
            "冷却：轰炸 10 秒，大招 15 秒（近战形态持续 20 秒）。",
            "近战形态下 左键 ／ J ／ Z = 挥砍，击杀获得 3 秒护盾。",
            "成长：每击杀 10 个敌人，后续敌人与 Boss 血量 ×1.5。",
        ]
        font_title = get_font(30, bold=True)
        font_row = get_font(13)
        font_small = get_font(11)
        title = font_title.render("操作说明", True, P.UI_TEXT)
        surf.blit(title, (RENDER_W // 2 - title.get_width() // 2, 16))

        y0 = 82
        view_bottom = RENDER_H - 20
        scroll = int(self.help_scroll)
        row_h = 20
        content_h = len(rows) * row_h + 10 + len(notes) * 15
        view_h = view_bottom - y0

        # 内容区裁剪，避免画出标题/提示
        old_clip = surf.get_clip()
        surf.set_clip(pygame.Rect(0, y0, RENDER_W, view_h))
        y = y0 - scroll
        for label, val in rows:
            kimg = font_row.render(label, True, P.UI_ACCENT)
            vimg = font_row.render(val, True, P.UI_TEXT)
            surf.blit(kimg, (90, y))
            surf.blit(vimg, (250, y))
            y += row_h
        y += 10
        for note in notes:
            img = font_small.render(note, True, P.UI_DIM)
            surf.blit(img, (90, y))
            y += 15
        surf.set_clip(old_clip)

        # 滚动条
        if content_h > view_h:
            track_x = RENDER_W - 16
            pygame.draw.rect(surf, (40, 44, 64), (track_x, y0, 6, view_h))
            ratio = view_h / content_h
            thumb_h = max(24, int(view_h * ratio))
            pos = int((view_h - thumb_h) * (self.help_scroll / (content_h - view_h)))
            pygame.draw.rect(surf, P.UI_ACCENT, (track_x, y0 + pos, 6, thumb_h))

        hint = font_small.render("按 Enter / Esc 返回主菜单", True, P.UI_WARN)
        surf.blit(hint, (RENDER_W // 2 - hint.get_width() // 2, RENDER_H - 18))

    def _help_max_scroll(self) -> float:
        """操作说明内容的最大滚动量。"""
        rows = 8
        notes = 3
        content_h = rows * 20 + 10 + notes * 15
        view_h = (RENDER_H - 20) - 82
        return max(0.0, float(content_h - view_h))

    def _dim(self, surf: pygame.Surface) -> None:
        """压暗整屏（用于暂停）。"""
        ov = pygame.Surface((RENDER_W, RENDER_H))
        ov.set_alpha(120)
        ov.fill((0, 0, 0))
        surf.blit(ov, (0, 0))

    def flash(self, level: int) -> None:
        """触发屏幕闪烁。

        :param level: 闪烁强度（越大越白）。
        """
        self.flash_level = max(self.flash_level, level)

    # 供 HUD 查询
    def skill_cd_ratio(self) -> float:
        """技能（轰炸）冷却比例。"""
        return self.player.skill_cd / SKILL_COOLDOWN

    def ult_cd_ratio(self) -> float:
        """大招冷却比例。"""
        return self.player.ult_cd / ULT_COOLDOWN
