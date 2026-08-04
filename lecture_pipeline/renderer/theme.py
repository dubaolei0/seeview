"""
主题配置：颜色、字体、尺寸、间距

基于 templates.tex 抽取。所有视觉常量统一在此定义。
详细设计见 ../docs/能力地图.md 的"视觉语言"章节。
"""

from __future__ import annotations

from dataclasses import dataclass


# =====================================================================
# 调色板（方向 B · 浅色加深版 · 教辅书风）
# =====================================================================

MAIN_BLUE = "#1E40AF"     # 深宝石蓝：顶栏、卡片标题、重要结论
BG_BLUE = "#D6DEF5"       # 浅宝石蓝背景：bluebox（思考框）
BG_YELLOW = "#E8DDB5"     # 米黄背景：yellowbox（公式/结论框），对比主背景更明显
BG_ANCHOR = "#EDE8DC"     # 浅驼灰：已知栏卡片底，低调
MAIN_PINK = "#B91C1C"     # 深朱红：警告框标签、强调
EYE_WHITE = "#F7F3EB"     # 羊皮纸米白：全局主背景（比之前深，更有纸感）

TEXT_DARK = "#1F2937"     # 墨石色正文
TEXT_MUTED = "#6B7280"    # 次要文字（如"已知"前缀）
RULE_GREY = "#9CA3AF"     # 细线分隔色

EMPHASIS_RED = "#B91C1C"  # 重点强调
INSIGHT_GOLD = "#B45309"  # wow_formula 沉稳琥珀金

SHADOW_COLOR = "#1F2937"  # 假阴影色（配 8-10% 透明度）


# =====================================================================
# 字体
# =====================================================================
# 统一用 FONT_SONG（宋体）+ FONT_KAI（楷体）两种主字体。
# 过渡期用 Windows 自带 SimSun / KaiTi；装了思源后只改这两个常量即可。
#
# 换成思源时把值改成：
#   FONT_SONG = "Source Han Serif SC"
#   FONT_KAI = "Source Han Serif SC"   # 楷体用思源宋体 Regular 过渡，或者装思源楷体
# 其中思源官方无楷体，保留 KaiTi 作为楷体也 OK。

# 字体全部来自 renderer/font_config.py（改字体只动那个文件）。下面只是把"角色"映射成
# 渲染各处要用的值：family 名（给 create_mixed_tex 的 font=）或系统字体名（给 manim Text）。
from .font_config import role_family, family_system_name

# 角色 -> family 名（create_mixed_tex 用）
FONT_STATEMENT = role_family("statement")   # 题干
FONT_STEP = role_family("step")             # 步骤
FONT_WOW = role_family("wow")               # wow 强调汉字
FONT_TAKEAWAY = role_family("takeaway")     # 心法

# 给 manim Text(Pango) 用的系统字体名
FONT_SONG = family_system_name("song")      # 宋体（思源宋体）
FONT_KAI = family_system_name("kai")        # 楷体
FONT_TITLE = family_system_name(role_family("title"))   # 标题

# 兼容旧代码的别名
FONT_DEFAULT = FONT_TITLE
FONT_KAITI = FONT_KAI
FONT_HEITI = FONT_SONG


# =====================================================================
# 字号（Manim font_size 单位）
# =====================================================================

FONT_SIZE_COVER_TITLE = 56             # 开场大标题
FONT_SIZE_COVER_STATEMENT = 36         # 开场题干

FONT_SIZE_HEADER_TITLE = 22            # 顶栏文字（22pt，不加粗，更精致）
FONT_SIZE_STATEMENT_INLINE = 26        # 讲题阶段题干字号（兼容旧名，等同 FONT_SIZE_TEACH_STATEMENT）
FONT_SIZE_TEACH_STATEMENT = 26         # 讲题阶段题干字号（布局 A/B/C/D 顶部）

FONT_SIZE_KEYPOINT_LABEL = 20          # 锚点栏"已知"前缀
FONT_SIZE_KEYPOINT_ITEM = 24           # 锚点栏条目

FONT_SIZE_STEP = 30                    # 推导 step（正文基准）
FONT_SIZE_KNOWLEDGE_TITLE = 32         # 知识卡标题（略大于 step）
FONT_SIZE_KNOWLEDGE_BODY = 28          # 知识卡正文（略小于 step）
FONT_SIZE_ANSWER = 34                  # 答案框（比 step 大一档，但不夸张）
FONT_SIZE_WOW = 60                     # 顿悟公式（显著更大）
FONT_SIZE_WOW_CAPTION = 24             # 顿悟公式下方小字
FONT_SIZE_WARNING = 26                 # 警告框正文

FONT_SIZE_TAKEAWAY = 34                # 升华心法条
FONT_SIZE_MINDMAP = 26                 # 思维导图节点


# =====================================================================
# 屏幕尺寸（Manim 单位，默认 1920x1080 对应 14.2x8 Manim 单位）
# =====================================================================

SCREEN_WIDTH = 14.22                   # 1920 像素对应
SCREEN_HEIGHT = 8.0                    # 1080 像素对应

# 3D 几何整体下移的 z 偏移（让顶部不溢出顶栏区域）
GEOMETRY3D_Y_OFFSET = 1.5              # 在 -z 方向偏移多少 manim 单位

# 3D 几何默认目标尺寸：整组缩放到 max(world dx, dy, dz) ≤ 这个值
# 相机角度 phi=70, theta=-30 下，世界尺寸 3.0 投影后约占屏幕高 4 单位
GEOMETRY3D_DEFAULT_MAX_SIZE = 3.0

# 3D 几何默认整体位移：让它落到屏幕右侧（与 FIGURE_BOX 对齐的概念）
# 注意：默认相机 phi=70, theta=-30 下：
#   +x 世界方向 → 屏幕右下；+y → 屏幕右上；+z → 屏幕上
# 经验：(2.5, -1.0, +0.5) 大致到屏幕右侧偏中
GEOMETRY3D_DEFAULT_SHIFT = (4.5, -0.5, 1.2)

# 3D 几何自旋速率（弧度/秒），camera_rotate=true 时启用物体自旋
GEOMETRY3D_SPIN_RATE = 0.4

# 3D 相机焦距：manim 默认 20，透视较强；图被推到屏幕右侧（离光轴远）时，
# 竖直物体（圆柱/棱柱中轴）会因透视 keystone 而"往外倒、看着歪"。
# 把焦距拉大到 200 接近正交投影，离轴竖直线仍保持竖直，同时保留椭圆收缩的立体感。
# （实测：20 明显歪、60 仍微歪、200 完全竖直且立体感不丢。）
GEOMETRY3D_FOCAL_DISTANCE = 200.0


# =====================================================================
# Region 位置和尺寸
# =====================================================================

@dataclass
class RegionBox:
    """一个区域的矩形框"""
    x: float       # 左上角 x（Manim 坐标）
    y: float       # 左上角 y
    width: float
    height: float


# 顶栏（Header）
HEADER_BOX = RegionBox(
    x=-SCREEN_WIDTH / 2,
    y=SCREEN_HEIGHT / 2 - 0.3,   # 整体下移 0.3 单位，留呼吸空间
    width=SCREEN_WIDTH,
    height=0.8,
)

# 顶栏下方细线的位置（单一事实源，header.py 与题干卡片都引用，保证对齐）
HEADER_RULE_INSET = 0.3                                  # 细线两端相对顶栏左右缘内缩
HEADER_RULE_DROP = 0.55                                  # 细线相对顶栏顶的下移
HEADER_RULE_Y = HEADER_BOX.y - HEADER_RULE_DROP          # = 3.15
HEADER_RULE_X_LEFT = HEADER_BOX.x + HEADER_RULE_INSET    # = -6.81
HEADER_RULE_X_RIGHT = HEADER_BOX.x + HEADER_BOX.width - HEADER_RULE_INSET  # = +6.81
HEADER_RULE_WIDTH = HEADER_RULE_X_RIGHT - HEADER_RULE_X_LEFT               # = 13.62

# 布局 A：整体左移 2 单位，留出更安全的右侧边距
# 推导：x ∈ [-6.81, +0.85] 宽 7.66
# 已知：x ∈ [+1.55, +4.40] 宽 2.85
# 留白：0.70 单位（推导→已知之间），右侧安全边距 2.71 单位
BOARD_BOX_A = RegionBox(
    x=-SCREEN_WIDTH / 2 + 0.3,            # 左缘 -6.81
    y=SCREEN_HEIGHT / 2 - 1.3,
    width=7.66,                           # 到 +0.85
    height=SCREEN_HEIGHT - 1.8,
)
ANCHOR_BOX = RegionBox(
    x=2.55,                               # 左缘 +2.55
    y=SCREEN_HEIGHT / 2 - 1.3,
    width=2.85,                           # 右缘 +5.40
    height=SCREEN_HEIGHT - 1.8,
)

# 布局 B：推导主区全宽 + 题干在顶栏下一行
BOARD_B_FLOW_WIDTH_RATIO = 0.90             # B 布局左对齐板书流使用主区宽度的 90%
BOARD_BOX_B = RegionBox(
    x=-SCREEN_WIDTH / 2 + 0.3,
    y=SCREEN_HEIGHT / 2 - 2.4,          # 默认值；实际会按题干高度动态下压/上提
    width=SCREEN_WIDTH - 0.6,
    height=SCREEN_HEIGHT - 2.8,
)
STATEMENT_INLINE_Y = SCREEN_HEIGHT / 2 - 1.7  # 题干横条位置（再下移 0.1 拉开与蓝线间距）

# 布局 C/D（改版）：图栏在左、推导（讲解步骤）主区在右。
# 比例 图栏 40% : 推导 60%（按可用宽度分）——讲解区更宽以容多步推导/长公式。
# 两栏外边距相等、中间留缝。
_COL_OUTER = 0.40                                  # 左右外边距
_COL_GAP = 0.50                                    # 两栏间缝
_USABLE_W = SCREEN_WIDTH - 2 * _COL_OUTER - _COL_GAP   # 可用总宽 ≈ 12.92
_FIG_W = _USABLE_W * 0.40                           # 图栏 40% ≈ 5.17
_BOARD_W = _USABLE_W * 0.60                         # 推导 60% ≈ 7.75
_LEFT_X = -SCREEN_WIDTH / 2 + _COL_OUTER            # 左栏左缘 ≈ -6.71
_BOARD_X = _LEFT_X + _FIG_W + _COL_GAP             # 右栏左缘 ≈ -2.33（右缘对齐 +6.71）
FIGURE_BOX = RegionBox(
    x=_LEFT_X,
    y=SCREEN_HEIGHT / 2 - 1.3,
    width=_FIG_W,
    height=SCREEN_HEIGHT - 1.8,
)
BOARD_BOX_C = RegionBox(
    x=_BOARD_X,
    y=SCREEN_HEIGHT / 2 - 1.3,
    width=_BOARD_W,
    height=SCREEN_HEIGHT - 1.8,
)

# 布局 D：左栏（条件在上、图在下）与 C 图栏同列同宽（30%），右侧推导主区同 C（70%）
BOARD_BOX_D = BOARD_BOX_C
CONDITIONS_BOX = RegionBox(
    x=_LEFT_X,
    y=ANCHOR_BOX.y,                       # 与锚点栏同顶
    width=_FIG_W,
    height=2.0,
)
FIGURE_BOX_D = RegionBox(
    x=_LEFT_X,
    y=ANCHOR_BOX.y - 2.0 - 0.2,          # 条件区下方 + 0.2 间距
    width=_FIG_W,
    height=4.0,
)

# 讲题阶段题干（C/D 布局，可被 --no-statement 关闭）。纯文本、无底框、左对齐、固定字号。
# 题干与下方"图栏+讲解区"整块同宽、左缘对齐；题干越长往下多铺几行，下方据其底沿联动下移。
STATEMENT_TOP_GAP = 0.18                            # 题干上沿相对顶栏细线的下移（留点缝，不顶着线）
STATEMENT_TO_CONTENT_GAP = 0.30                    # 题干底沿到下方图栏/主区顶部的间距

# 题干字号（FONT_SIZE_TEACH_STATEMENT=26）下，minipage 一行填满时"屏幕单位/cm"的换算系数。
# 实测填满文本 13.42 屏宽对应 minipage 17.59cm（10.24/13.42≈0.763）。用于把"想要的屏幕宽"换成
# minipage 的 cm（cm = 屏宽 / 该系数）。仅在含 \choices 的题干里按题干实际宽度反推分列宽时用到。
# ⚠️ 若改了 FONT_SIZE_TEACH_STATEMENT 需重新实测此值。
STATEMENT_SCREEN_PER_CM = 0.763


def shift_box_top_to(box: RegionBox, new_top: float) -> RegionBox:
    """把矩形顶部下压到 new_top（底部不动，高度相应缩短）。new_top 不低于原顶时原样返回。"""
    delta = box.y - new_top
    if delta <= 0:
        return box
    return RegionBox(box.x, new_top, box.width, box.height - delta)


def compute_c_layout(board_ratio: float = 0.60, figure_side: str = "left") -> tuple[RegionBox, RegionBox]:
    """按自定义比例和方向计算布局 C 的 (FIGURE_BOX, BOARD_BOX_C)。

    board_ratio: 推导主区（步骤）占可用宽度的比例，图栏 = 1 - board_ratio。
    figure_side: "left" 图在左、步骤在右；"right" 步骤在左、图在右。
    """
    usable_w = SCREEN_WIDTH - 2 * _COL_OUTER - _COL_GAP
    board_w = usable_w * board_ratio
    fig_w = usable_w * (1.0 - board_ratio)
    left_x = -SCREEN_WIDTH / 2 + _COL_OUTER
    y_top = SCREEN_HEIGHT / 2 - 1.3
    h = SCREEN_HEIGHT - 1.8

    if figure_side == "right":
        board_x = left_x
        fig_x = left_x + board_w + _COL_GAP
    else:
        fig_x = left_x
        board_x = left_x + fig_w + _COL_GAP

    fig_box = RegionBox(fig_x, y_top, fig_w, h)
    brd_box = RegionBox(board_x, y_top, board_w, h)
    return fig_box, brd_box


# =====================================================================
# 开场（读题阶段）尺寸
# =====================================================================

COVER_TITLE_Y = 2.5                    # 开场大标题位置
COVER_STATEMENT_BOX = RegionBox(
    x=-6.3,                            # 比之前收一点，左右各留约 0.8 缝隙
    y=1.0,
    width=12.6,
    height=6.0,
)


# =====================================================================
# 边距 & 间距
# =====================================================================

BLOCK_SPACING = 0.55                   # 推导主区内 block 之间的垂直间距（放大到呼吸感）
CARD_INNER_PADDING = 0.4               # 卡片内边距（多留白）
CARD_CORNER_RADIUS = 0.18              # 圆角半径（更柔和）

HEADER_RULE_THICKNESS = 0.04           # 顶栏下方细线厚度

# 阴影配置
SHADOW_OFFSET = (0.05, -0.05, 0)       # 阴影偏移（右下）
SHADOW_OPACITY = 0.08                  # 阴影透明度（隐约的层次感）

# 边框配置
CARD_BORDER_WIDTH = 1.5                # 卡片边框笔画宽度


# =====================================================================
# 动画时长（秒）
# =====================================================================

DEFAULT_RUN_TIME = 1.0                 # 默认动画时长
FAST_RUN_TIME = 0.5
SLOW_RUN_TIME = 1.5
DEFAULT_REPLACE_TIME = 1.2             # TransformMatchingTex 替换默认时长（略长，眼睛跟得上）

COVER_TO_TEACH_RUN_TIME = 1.0          # cover_to_teach 的 run_time 参数
TEACH_TO_SUMMARY_RUN_TIME = 0.8        # teach_to_summary 的 run_time 参数
ACT_SOFT_TRANSITION = 0.6              # Act 软转场
ACT_HARD_TRANSITION = 1.0              # Act 硬切（含空白）

BEAT_GAP = 0.4                         # 两 beat 之间的默认静音时长（音频上）
INTRO_SILENCE = 1.2                    # 视频开头静音
OUTRO_WAIT = 1.5                       # 视频结尾等待


# =====================================================================
# 分式线厚度
# =====================================================================

DFRAC_THICKNESS = 0.6                   # pt，对应 LaTeX \\genfrac 的线宽


# =====================================================================
# 辅助函数
# =====================================================================

def color_hex_to_manim(hex_str: str):
    """
    把 '#RRGGBB' 形式的颜色转成 Manim 可用的颜色字符串。
    Manim 直接接受 hex 字符串，所以这里就是 identity（留作扩展点）。
    """
    return hex_str


if __name__ == "__main__":
    print("=== Theme 配置 ===")
    print(f"主题色：{MAIN_BLUE}")
    print(f"背景色：{EYE_WHITE}")
    print(f"屏幕尺寸：{SCREEN_WIDTH} x {SCREEN_HEIGHT} Manim 单位")
    print(f"Header: {HEADER_BOX}")
    print(f"Board A: {BOARD_BOX_A}")
    print(f"Anchor: {ANCHOR_BOX}")
