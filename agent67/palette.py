"""赛博朋克风调色板。

统一的颜色常量，供精灵生成和界面绘制使用。
"""

from __future__ import annotations

# 主角（蓝发 + 红白装甲，参考角色设计稿）
PLAYER_HAIR = (64, 160, 255)        # 亮蓝头发
PLAYER_HAIR_DK = (40, 96, 200)      # 头发阴影
PLAYER_SKIN = (240, 210, 170)       # 皮肤
PLAYER_ARMOR_RED = (210, 46, 60)    # 装甲红
PLAYER_ARMOR_WHITE = (238, 240, 246)  # 装甲白
PLAYER_ARMOR_DK = (120, 120, 136)   # 装甲暗部
PLAYER_CHEST = (70, 220, 255)       # 胸口能量核心
PLAYER_BELT = (150, 110, 40)        # 腰带
PLAYER_PANTS = (40, 44, 70)         # 裤子
PLAYER_BOOT = (200, 50, 55)         # 靴子

# 敌人（牛仔机器人配色）
ENEMY_BODY = (110, 70, 40)          # 躯干古铜
ENEMY_BODY_DK = (70, 44, 26)
ENEMY_METAL = (168, 140, 96)        # 金属部件
ENEMY_METAL_DK = (104, 84, 56)
ENEMY_BANDANA = (200, 40, 40)       # 红头巾
ENEMY_HAT = (88, 70, 44)            # 帽子
ENEMY_PANTS = (42, 78, 150)         # 蓝牛仔裤
ENEMY_SCARF = (206, 60, 60)         # 围巾

# 第敌人 Boss 变体接近主角色，用于区分远程 Boss
BOSS_MELEE = (150, 60, 40)
BOSS_RANGED = (60, 150, 120)

# 背景（赛博朋克街景）
SKY_TOP = (40, 30, 80)
SKY_BOTTOM = (120, 70, 160)
CLOUD = (150, 120, 180)
BUILDING_FAR = (60, 48, 100)
BUILDING_MID = (40, 32, 72)
SIGN_NEON = (60, 220, 255)
SIGN_NEON_PINK = (255, 80, 180)
SIGN_NEON_YELLOW = (255, 210, 60)
SHOP_SHUTTER = (70, 90, 120)
SHOP_GLOW = (90, 200, 230)
ROOF_TOP = (110, 100, 90)
ROOF_EDGE = (60, 50, 40)
GROUND_TOP = (90, 80, 70)
GROUND_BODY = (55, 48, 44)
GROUND_DK = (38, 34, 32)

# 界面
UI_TEXT = (235, 238, 245)
UI_DIM = (150, 155, 170)
UI_PANEL = (20, 22, 36)
UI_PANEL_EDGE = (90, 200, 230)
UI_ACCENT = (60, 220, 255)
UI_ACCENT_PINK = (255, 80, 180)
UI_DANGER = (220, 60, 60)
UI_GOOD = (80, 220, 130)
UI_WARN = (240, 200, 60)

# 通用
WHITE = (255, 255, 255)
BLACK = (10, 10, 14)
TRANSPARENT = (0, 0, 0, 0)

# 技能特效
ENERGY = (70, 220, 255)
ENERGY_CORE = (180, 250, 255)
BOMB = (255, 120, 40)
BOMB_CORE = (255, 230, 130)
FIRE = (255, 140, 40)
EXPLOSION = (255, 210, 80)
SWORD = (120, 220, 255)
SHIELD = (80, 200, 255)

# 汇总字典便于外部按名取色
COLORS = {
    "player_hair": PLAYER_HAIR,
    "player_armor_red": PLAYER_ARMOR_RED,
    "enemy_body": ENEMY_BODY,
    "sky_top": SKY_TOP,
    "ui_accent": UI_ACCENT,
}
