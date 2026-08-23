"""程序化像素精灵生成。

不依赖外部贴图，全部用矩形/像素绘制出带有赛博朋克 & 参考图风格的角色、
敌人、Boss、道具与背景贴片方块。所有 Surface 使用 SRCALPHA 支持透明。

对外暴露：make_sprites() -> dict[str, dict]，组织为按类别命名的精灵集。
"""

from __future__ import annotations

from typing import Callable, Dict, List, Tuple

import pygame

from . import palette as P

Color = Tuple[int, int, int]


# ---------------------------------------------------------------------------
# 基础绘制工具
# ---------------------------------------------------------------------------
def _surf(w: int, h: int) -> pygame.Surface:
    """创建带透明通道的 Surface。"""
    return pygame.Surface((w, h), pygame.SRCALPHA)


def _rect(s: pygame.Surface, color: Color, x: int, y: int, w: int, h: int) -> None:
    """绘制一个像素风矩形（无抗锯齿）。"""
    pygame.draw.rect(s, color, (x, y, w, h))


def _px(s: pygame.Surface, color: Color, x: int, y: int, size: int = 1) -> None:
    """绘制单个像素点（可指定大小）。"""
    pygame.draw.rect(s, color, (x, y, size, size))


def flip_surfaces(
    frames: Dict[str, List[pygame.Surface]]
) -> Dict[str, List[pygame.Surface]]:
    """把每帧水平镜像一份，追加成新的动画帧列表（用于面向左侧）。"""
    out: Dict[str, List[pygame.Surface]] = {}
    for key, lst in frames.items():
        out[key] = lst + [pygame.transform.flip(f, True, False) for f in lst]
    return out


# ---------------------------------------------------------------------------
# 人类/机器人角色绘制（参数化）
# ---------------------------------------------------------------------------
def _humanoid(
    scheme: Dict[str, Color],
    pose: str,
    width: int,
    height: int,
    scale: float = 1.0,
) -> pygame.Surface:
    """按姿势绘制一个像素风格人形。

    :param scheme: 配色字典（hair/hair_dk/skin/red/white/dark/chest/pants/boot）。
    :param pose: 姿势名（idle/run1/run2/jump/shoot/sword_a/sword_b/sword_slam）。
    :param width: 画布宽度（含余量）。
    :param height: 画布高度。
    :param scale: 整体缩放（Boss 更大）。
    :return: 绘制好的 Surface。
    """
    surf = _surf(width, height)
    cx = width // 2
    foot = height - 4  # 脚底贴近画布底部

    # 依据姿势决定四肢状态
    if pose == "run1":
        (leg, leg_y, arm, arm_y) = (10, 2, 4, 6)
    elif pose == "run2":
        (leg, leg_y, arm, arm_y) = (-10, 2, -4, 6)
    elif pose == "jump":
        (leg, leg_y, arm, arm_y) = (4, 8, -6, -2)
    elif pose == "shoot":
        (leg, leg_y, arm, arm_y) = (6, 0, 12, 2)  # 双手端枪瞄准（手臂向前但不夸张）
    elif pose == "shoot_recoil":
        (leg, leg_y, arm, arm_y) = (6, 0, 9, 0)  # 后坐力：手臂略微回收
    elif pose == "sword_a":
        (leg, leg_y, arm, arm_y) = (0, 10, 16, -6)  # 举刀起跳
    elif pose == "sword_b":
        (leg, leg_y, arm, arm_y) = (8, 2, 34, 8)     # 挥刀中
    elif pose == "sword_slam":
        (leg, leg_y, arm, arm_y) = (14, 4, 30, 16)   # 下砸
    elif pose == "sword_hold":
        (leg, leg_y, arm, arm_y) = (6, 0, 22, 4)     # 持刀待机
    else:  # idle
        (leg, leg_y, arm, arm_y) = (6, 0, 3, 3)

    # 尺寸（按 scale 缩放基本块）
    def sc(v: float) -> int:
        return max(1, int(round(v * scale)))

    head_w = sc(16)
    head_h = sc(16)
    torso_w = sc(22)
    torso_h = sc(20)

    # --- 腿部 ---
    leg_w = sc(7)
    leg_h = sc(14)
    # 后腿
    _rect(surf, scheme["pants"], cx + sc(-8) - leg_w, foot - leg_h - sc(2), leg_w, leg_h)
    _rect(surf, scheme["boot"], cx + sc(-8) - leg_w, foot - sc(5), leg_w, sc(5))
    # 前腿（带步伐偏移）
    fx = cx + max(-sc(16), min(sc(16), sc(leg)))
    _rect(surf, scheme["pants"], fx, foot - leg_h - sc(2) - sc(leg_y), leg_w, leg_h)
    _rect(surf, scheme["boot"], fx, foot - sc(5) - sc(leg_y), leg_w, sc(5) + sc(leg_y))

    # --- 躯干 ---
    tx = cx - torso_w // 2
    ty = foot - leg_h - torso_h - sc(4)
    _rect(surf, scheme["red"], tx, ty, torso_w, torso_h)
    # 白色胸甲（中间）
    _rect(surf, scheme["white"], tx + sc(3), ty + sc(3), torso_w - sc(6), torso_h - sc(6))
    # 胸口能量核心
    core_y = ty + sc(6)
    _rect(surf, scheme["chest"], cx - sc(3), core_y, sc(6), sc(5))
    _px(surf, (220, 250, 255), cx - sc(2), core_y, max(1, sc(2)))
    # 肩甲
    _rect(surf, scheme["white"], tx - sc(3), ty + sc(1), sc(5), sc(6))
    _rect(surf, scheme["white"], tx + torso_w - sc(2), ty + sc(1), sc(5), sc(6))
    _rect(surf, scheme["red"], tx - sc(1), ty + sc(2), sc(2), sc(4))
    _rect(surf, scheme["red"], tx + torso_w - sc(1), ty + sc(2), sc(2), sc(4))
    # 腰带
    _rect(surf, scheme.get("belt", (150, 110, 40)), tx, ty + torso_h - sc(3), torso_w, sc(2))

    # --- 手臂 ---
    arm_w = sc(5)
    arm_h = sc(12)
    # 后臂
    _rect(surf, scheme["red"], cx - torso_w // 2 - sc(3), ty + sc(4), arm_w, arm_h)
    # 前臂（依姿势）
    ax = cx + max(-sc(16), min(sc(30), sc(arm)))
    _rect(surf, scheme["red"], ax, ty + sc(4) - sc(max(0, arm_y)), arm_w, arm_h)
    # 拳
    _px(surf, scheme["skin"], ax, ty + sc(4) - sc(max(0, arm_y)) + arm_h, max(1, sc(4)))

    # --- 头部 ---
    hx = cx - head_w // 2
    hy = ty - head_h - sc(2)
    _rect(surf, scheme["skin"], hx, hy, head_w, head_h)           # 脸
    # 头发（顶部 + 两侧，参考稿的尖刺蓝发）
    hair = scheme["hair"]
    hair_dk = scheme["hair_dk"]
    _rect(surf, hair, hx - sc(2), hy - sc(4), head_w + sc(4), sc(7))
    _rect(surf, hair_dk, hx - sc(3), hy - sc(2), sc(4), sc(6))
    _rect(surf, hair_dk, hx + head_w - sc(1), hy - sc(2), sc(4), sc(6))
    # 前额头发尖
    _px(surf, hair, cx - sc(2), hy - sc(4), sc(2))
    _px(surf, hair, cx + sc(1), hy - sc(5), sc(2))
    # 眼睛
    eye_y = hy + sc(7)
    _px(surf, (20, 30, 40), cx - sc(4), eye_y, max(1, sc(2)))
    _px(surf, (20, 30, 40), cx + sc(2), eye_y, max(1, sc(2)))

    # --- 姿势附加物：手持枪械 ---
    # 除近战/大招姿势外，主角始终手持一把枪；射击时端枪瞄准并有后坐力与枪口火光
    if pose not in ("sword_a", "sword_b", "sword_slam", "sword_hold"):
        _draw_player_gun(surf, scheme, ax, arm_w, ty, sc, pose)

    return surf


def _draw_player_gun(surf: pygame.Surface, scheme, ax: int, arm_w: int, ty: int,
                     sc, pose: str) -> None:
    """在角色前手位置绘制一把枪。

    :param surf: 画布。
    :param scheme: 配色字典。
    :param ax: 前臂左缘 x。
    :param arm_w: 前臂宽度。
    :param ty: 躯干顶 y。
    :param sc: 缩放函数。
    :param pose: 姿势名。
    """
    gun = scheme.get("gun", (58, 62, 78))
    dark = (40, 44, 56)
    metal = (96, 102, 118)
    aiming = pose in ("shoot", "shoot_recoil")
    recoil = pose == "shoot_recoil"

    gx = ax + arm_w - sc(1) - (sc(3) if recoil else 0)
    gy = ty + sc(5)
    # 枪托（抵肩）
    _rect(surf, dark, gx, gy, sc(4), sc(6))
    # 机匣
    _rect(surf, gun, gx, gy, sc(14), sc(6))
    # 上导轨/瞄具
    _rect(surf, metal, gx + sc(5), gy - sc(2), sc(4), sc(2))
    # 枪管（射击时更长）
    barrel = sc(10) if aiming else sc(6)
    _rect(surf, metal, gx + sc(14), gy + sc(2), barrel, sc(3))
    # 枪口
    _px(surf, (30, 30, 40), gx + sc(14) + barrel, gy + sc(2), sc(2))
    # 弹匣（向下）
    _rect(surf, (60, 66, 84), gx + sc(5), gy + sc(6), sc(4), sc(6))
    # 前握把
    _rect(surf, dark, gx + sc(9), gy + sc(6), sc(3), sc(5))
    # 射击：枪口火焰 + 准星
    if aiming:
        muzzle = (gx + sc(14) + barrel, gy + sc(3))
        pygame.draw.polygon(
            surf, (255, 230, 120),
            [(muzzle[0], muzzle[1]), (muzzle[0] + sc(6), muzzle[1] - sc(3)),
             (muzzle[0] + sc(6), muzzle[1] + sc(3))])
        pygame.draw.polygon(
            surf, (255, 150, 60),
            [(muzzle[0], muzzle[1]), (muzzle[0] + sc(4), muzzle[1] - sc(2)),
             (muzzle[0] + sc(4), muzzle[1] + sc(2))])
        if recoil:
            _rect(surf, (255, 240, 160), gx + sc(4), gy + sc(2), sc(4), sc(2))


# ---------------------------------------------------------------------------
# 敌人类绘制
# ---------------------------------------------------------------------------
def _enemy_humanoid(
    scheme: Dict[str, Color], pose: str, width: int, height: int, boss: bool = False
) -> pygame.Surface:
    """绘制牛仔机器人敌人。与主角共用肢体布局，但用机器人配色与帽子。"""
    surf = _surf(width, height)
    cx = width // 2
    foot = height - 4
    scale = 1.15 if boss else 1.0

    def sc(v: float) -> int:
        return max(1, int(round(v * scale)))

    leg, leg_y, arm = 6, 0, 3
    if pose == "run1":
        leg, leg_y, arm = 10, 2, 4
    elif pose == "run2":
        leg, leg_y, arm = -10, 2, -4
    elif pose == "shoot":
        leg, leg_y, arm = 6, 0, 30
    elif pose == "attack":
        leg, leg_y, arm = 8, 0, 22

    leg_w = sc(8)
    leg_h = sc(15)
    torso_w = sc(24)
    torso_h = sc(22)

    # 腿（牛仔裤）
    _rect(surf, scheme["pants"], cx - sc(9) - leg_w, foot - leg_h - sc(2), leg_w, leg_h)
    _rect(surf, scheme["boot"], cx - sc(9) - leg_w, foot - sc(5), leg_w, sc(5))
    fx = cx + max(-sc(18), min(sc(18), sc(leg)))
    _rect(surf, scheme["disc"], fx, foot - leg_h - sc(2) - sc(leg_y), leg_w, leg_h)
    _rect(surf, scheme["boot"], fx, foot - sc(5) - sc(leg_y), leg_w, sc(5) + sc(leg_y))

    # 躯干（金属）
    tx = cx - torso_w // 2
    ty = foot - leg_h - torso_h - sc(4)
    _rect(surf, scheme["body"], tx, ty, torso_w, torso_h)
    _rect(surf, scheme["metal"], tx + sc(3), ty + sc(3), torso_w - sc(6), torso_h - sc(6))
    # 发光核心
    _px(surf, (255, 180, 80), cx - sc(2), ty + sc(7), sc(4))
    _px(surf, (255, 230, 160), cx - sc(1), ty + sc(8), sc(2))

    # 手臂
    arm_w = sc(6)
    arm_h = sc(13)
    _rect(surf, scheme["metal_dk"], cx - torso_w // 2 - sc(3), ty + sc(5), arm_w, arm_h)
    ax = cx + max(-sc(18), min(sc(30), sc(arm)))
    _rect(surf, scheme["metal_dk"], ax, ty + sc(5), arm_w, arm_h)
    _px(surf, scheme["bandana"], ax + arm_w - sc(2), ty + sc(6), max(1, sc(3)))

    # 头部 + 帽子
    head_w = sc(18)
    head_h = sc(16)
    hx = cx - head_w // 2
    hy = ty - head_h - sc(2)
    _rect(surf, scheme["skin"], hx, hy, head_w, head_h)
    # 头巾遮脸
    _rect(surf, scheme["bandana"], hx, hy + sc(6), head_w, sc(8))
    # 眼睛
    _px(surf, (250, 250, 250), cx - sc(4), hy + sc(8), max(1, sc(2)))
    _px(surf, (250, 250, 250), cx + sc(2), hy + sc(8), max(1, sc(2)))
    # 牛仔帽
    _rect(surf, scheme["hat"], hx - sc(3), hy - sc(5), head_w + sc(6), sc(5))
    _rect(surf, scheme["hat"], hx - sc(6), hy - sc(1), sc(6), sc(3))
    _rect(surf, scheme["hat_dk"], hx + sc(2), hy - sc(5), head_w - sc(4), sc(2))

    if pose == "shoot":
        _rect(surf, (50, 52, 64), ax + arm_w, ty + sc(7), sc(12), sc(3))
        _px(surf, (250, 230, 120), ax + arm_w + sc(12), ty + sc(8), sc(2))

    return surf


# ---------------------------------------------------------------------------
# 主角精灵集
# ---------------------------------------------------------------------------
def _build_player() -> Dict[str, List[pygame.Surface]]:
    """返回主角各动画帧（列表元素为连续帧，含左右镜像）。"""
    scheme = {
        "hair": P.PLAYER_HAIR,
        "hair_dk": P.PLAYER_HAIR_DK,
        "skin": P.PLAYER_SKIN,
        "red": P.PLAYER_ARMOR_RED,
        "white": P.PLAYER_ARMOR_WHITE,
        "dark": P.PLAYER_ARMOR_DK,
        "chest": P.PLAYER_CHEST,
        "pants": P.PLAYER_PANTS,
        "boot": P.PLAYER_BOOT,
        "belt": P.PLAYER_BELT,
        "gun": (60, 64, 80),
    }
    w, h = 80, 60
    frames: Dict[str, List[pygame.Surface]] = {
        "idle": [_humanoid(scheme, "idle", w, h)],
        "run": [_humanoid(scheme, f"run{i}", w, h) for i in (1, 2)],
        "jump": [_humanoid(scheme, "jump", w, h)],
        "shoot": [_humanoid(scheme, "shoot", w, h)],
        "shoot_recoil": [_humanoid(scheme, "shoot_recoil", w, h)],
        "sword_hold": [_humanoid(scheme, "sword_hold", w, h)],
        "sword_a": [_humanoid(scheme, "sword_a", w, h)],
        "sword_b": [_humanoid(scheme, "sword_b", w, h)],
        "sword_slam": [_humanoid(scheme, "sword_slam", w, h)],
    }
    return {k: v + [pygame.transform.flip(f, True, False) for f in v] for k, v in frames.items()}


# ---------------------------------------------------------------------------
# 敌人 & Boss 精灵集
# ---------------------------------------------------------------------------
def _build_enemies() -> Dict[str, Dict[str, List[pygame.Surface]]]:
    """返回三种敌人的精灵集：melee / ranged / boss_melee / boss_ranged。"""
    base = {
        "body": P.ENEMY_BODY,
        "metal": P.ENEMY_METAL,
        "metal_dk": P.ENEMY_METAL_DK,
        "disc": P.ENEMY_PANTS,
        "pants": P.ENEMY_PANTS,
        "boot": (60, 60, 70),
        "bandana": P.ENEMY_BANDANA,
        "hat": P.ENEMY_HAT,
        "hat_dk": (70, 54, 32),
        "skin": (200, 150, 110),
    }
    melee_scheme = dict(base, skin=(210, 170, 130))
    ranged_scheme = dict(base, body=(90, 110, 130), metal=(130, 160, 190), metal_dk=(80, 100, 120))
    boss_m_scheme = dict(base, body=P.BOSS_MELEE, metal=(200, 120, 70), metal_dk=(120, 70, 40),
                         bandana=(210, 70, 50))
    boss_r_scheme = dict(base, body=P.BOSS_RANGED, metal=(80, 200, 170), metal_dk=(40, 120, 100),
                         bandana=(70, 200, 180))

    w, h = 52, 64
    bw, bh = 96, 112

    def mkin(scheme, boss=False):
        return {
            "idle": [_enemy_humanoid(scheme, "idle", w, h, boss)],
            "run": [_enemy_humanoid(scheme, f"run{i}", w, h, boss) for i in (1, 2)],
            "shoot": [_enemy_humanoid(scheme, "shoot", w, h, boss)],
            "attack": [_enemy_humanoid(scheme, "attack", w, h, boss)],
        }

    def mirror(d):
        return {k: v + [pygame.transform.flip(f, True, False) for f in v] for k, v in d.items()}

    return {
        "melee": mirror(mkin(melee_scheme)),
        "ranged": mirror(mkin(ranged_scheme)),
        "boss_melee": mirror(mkin(boss_m_scheme, boss=True)),
        "boss_ranged": mirror(mkin(boss_r_scheme, boss=True)),
    }


# ---------------------------------------------------------------------------
# 道具精灵
# ---------------------------------------------------------------------------
def _build_pickups() -> Dict[str, pygame.Surface]:
    """返回道具精灵（单帧）。"""
    out: Dict[str, pygame.Surface] = {}
    s = _surf(22, 22)
    # 手榴弹
    _rect(s, (70, 74, 84), 8, 6, 8, 10)
    _rect(s, (120, 124, 132), 9, 4, 6, 3)
    _px(s, (255, 200, 60), 8, 3)
    out["grenade"] = s.copy()

    s = _surf(22, 26)
    _rect(s, (200, 205, 215), 4, 6, 14, 8)
    _rect(s, (120, 128, 140), 4, 11, 14, 4)
    _px(s, (255, 120, 50), 18, 8)
    _rect(s, (60, 64, 76), 4, 6, 2, 12)
    out["rocket"] = s.copy()

    s = _surf(20, 20)
    # 生命拾取
    _rect(s, (220, 60, 70), 8, 4, 4, 12)
    _rect(s, (220, 60, 70), 4, 8, 12, 4)
    out["hp"] = s.copy()

    s = _surf(20, 20)
    # 护盾增益
    _rect(s, (80, 200, 255), 4, 4, 12, 12)
    s = pygame.transform.smoothscale(s, (16, 16))
    out["shield"] = s.copy()
    return out


# ---------------------------------------------------------------------------
# 背景贴片（赛博朋克店铺 / 建筑 / 平台）
# ---------------------------------------------------------------------------
def _build_bg_tiles() -> Dict[str, pygame.Surface]:
    """返回背景贴片集合。"""
    tiles: Dict[str, pygame.Surface] = {}

    # 单个店铺前景（下方是卷帘门，上方发光招牌）
    def shop(neon: Color, sign_color: Color) -> pygame.Surface:
        s = _surf(96, 96)
        _rect(s, P.SHOP_SHUTTER, 4, 20, 88, 76)          # 卷帘门
        _rect(s, (52, 66, 90), 4, 20, 88, 6)
        _rect(s, (46, 60, 82), 12, 30, 72, 10)
        _rect(s, (150, 160, 175), 20, 46, 56, 40, )      # 橱窗
        _rect(s, sign_color, 22, 50, 52, 8)
        _rect(s, P.SHOP_GLOW, 6, 90, 84, 6)
        # 发光招牌条
        _rect(s, neon, 10, 10, 76, 8)
        s = pygame.transform.smoothscale(s, (96, 120))
        return s

    tiles["shop_cyan"] = shop(P.SIGN_NEON, (20, 40, 70))
    tiles["shop_pink"] = shop(P.SIGN_NEON_PINK, (70, 20, 50))
    tiles["shop_yellow"] = shop(P.SIGN_NEON_YELLOW, (70, 60, 20))

    # 远景高楼剪影
    def building(h: int, color: Color, w: int = 80) -> pygame.Surface:
        s = _surf(w, h)
        _rect(s, color, 0, 0, w, h)
        for wx in range(6, w - 6, 14):
            for wy in range(8, h - 8, 14):
                _px(s, (min(color[0] + 30, 120), min(color[1] + 30, 120), min(color[2] + 40, 160)),
                    wx, wy, 6)
        return s

    tiles["bld_a"] = building(200, P.BUILDING_FAR)
    tiles["bld_b"] = building(160, P.BUILDING_MID)

    # 屋顶平台（可站立）
    def platform(w: int = 160) -> pygame.Surface:
        s = _surf(w, 16)
        _rect(s, P.ROOF_TOP, 0, 0, w, 10)
        _rect(s, P.ROOF_EDGE, 0, 10, w, 6)
        for x in range(4, w - 4, 16):
            _px(s, (150, 140, 120), x, 4, 4)
        return s

    tiles["platform"] = platform()

    # 地面砖块
    def ground(w: int = 160) -> pygame.Surface:
        s = _surf(w, 120)
        _rect(s, P.GROUND_TOP, 0, 0, w, 8)
        _rect(s, P.GROUND_BODY, 0, 8, w, 112)
        for x in range(0, w, 24):
            _rect(s, P.GROUND_DK, x, 8, 2, 112)
            _px(s, (70, 62, 56), x + 6, 20, 4)
        return s

    tiles["ground"] = ground()
    return tiles


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------
def make_sprites() -> Dict[str, object]:
    """生成并返回全部精灵，按类别组织。

    :return: dict，包含 player/enemies/pickups/bg 四个键。
    """
    return {
        "player": _build_player(),
        "enemies": _build_enemies(),
        "pickups": _build_pickups(),
        "bg": _build_bg_tiles(),
    }
