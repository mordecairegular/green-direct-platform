# -*- coding: utf-8 -*-
"""成果报告与 PPT 附图。用法：python3 figs.py <输出目录>"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch, Polygon

font_manager.fontManager.addfont("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")
plt.rcParams["font.family"] = "WenQuanYi Zen Hei"
import logging
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

OUT = sys.argv[1] if len(sys.argv) > 1 else "."
os.makedirs(OUT, exist_ok=True)

INK = "#1f2933"
MUTED = "#52606d"
BLUE_F, BLUE_E = "#e8eef7", "#3e5c86"
CORE_F, CORE_E = "#f4f6f8", "#7b8794"
AI_F, AI_E = "#fdf3e7", "#b06a1c"
GREEN_F, GREEN_E = "#e9f3ec", "#3f7d56"
WHITE = "#ffffff"


def canvas(w, h, xmax=100, ymax=None):
    ymax = ymax or xmax * h / w
    fig, ax = plt.subplots(figsize=(w, h), dpi=200)
    ax.set_xlim(0, xmax)
    ax.set_ylim(0, ymax)
    ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, text, fc=CORE_F, ec=CORE_E, size=10, weight="normal", lw=1.2,
        ls="-", align="center", color=INK, rounding=0.8):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0.2,rounding_size={rounding}",
                                fc=fc, ec=ec, lw=lw, ls=ls))
    if text:
        if align == "center":
            ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size,
                    color=color, weight=weight, linespacing=1.45)
        else:
            ax.text(x + 1.2, y + h / 2, text, ha="left", va="center", fontsize=size,
                    color=color, weight=weight, linespacing=1.45)


def arrow(ax, x1, y1, x2, y2, text=None, tx=0.8, ty=0.0, ls="-", color=MUTED, size=8.5,
          rad=0.0, ha="left"):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=1.1, mutation_scale=11,
                                linestyle=ls, connectionstyle=f"arc3,rad={rad}"))
    if text:
        ax.text((x1 + x2) / 2 + tx, (y1 + y2) / 2 + ty, text, fontsize=size, color=color,
                va="center", ha=ha)


def line(ax, xs, ys, color=MUTED, ls="-"):
    ax.plot(xs, ys, color=color, lw=1.1, ls=ls, solid_capstyle="round")


def diamond(ax, cx, cy, w, h, text, fc=WHITE, ec=BLUE_E, size=10):
    ax.add_patch(Polygon([(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2), (cx - w / 2, cy)],
                         closed=True, fc=fc, ec=ec, lw=1.3))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=size, color=INK, linespacing=1.4)


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path, bbox_inches="tight", facecolor="white", pad_inches=0.12)
    plt.close(fig)
    print(path)


# ---------------------------------------------------------------- 图1 总体技术架构
def fig_arch():
    fig, ax = canvas(8.4, 6.6, 100, 76)

    def layer_label(y, h, text):
        ax.text(2, y + h / 2, text, ha="center", va="center", fontsize=10, color=MUTED,
                rotation=90, weight="bold")

    layer_label(65, 9, "交互层")
    box(ax, 8, 66, 40, 7, "网页工作台\n启动 · 仿真 · 经济 · 推荐 · 图表 · 导出", BLUE_F, BLUE_E, 9.5)
    box(ax, 56, 66, 40, 7, "AI 方案策划助手\n需求理解 · 参数识别 · 缺失项提示", AI_F, AI_E, 9.5)
    layer_label(53, 8, "服务层")
    box(ax, 8, 54, 88, 6.5, "服务编排：技术仿真 / 经济性测算 / 方案推荐统一入口；项目库与结果存储", BLUE_F, BLUE_E, 9.8)
    arrow(ax, 28, 66, 28, 60.8)
    arrow(ax, 76, 66, 76, 60.8, "函数调用", 1.0)
    layer_label(31, 19.5, "计算层")
    ax.add_patch(FancyBboxPatch((8, 31), 88, 19.5, boxstyle="round,pad=0.3,rounding_size=1.2",
                                fc="#fbfcfd", ec=CORE_E, lw=1.0, ls=(0, (4, 3))))
    ax.text(52, 48, "技术经济测算引擎（全部工程指标的唯一来源，AI 不介入计算）", ha="center",
            va="center", fontsize=10, color=CORE_E, weight="bold")
    arrow(ax, 52, 54, 52, 50.2)
    steps = ["数据读取\n与校验", "候选方案\n批量生成", "逐时能量平衡\n储能SOC滚动", "政策达标\n筛选",
             "多视角\n经济性测算", "代表方案\n推荐"]
    w, g, x0 = 12.4, 2.12, 10
    for i, t in enumerate(steps):
        x = x0 + i * (w + g)
        box(ax, x, 34, w, 9.5, t, CORE_F, CORE_E, 9.2)
        if i < len(steps) - 1:
            arrow(ax, x + w + 0.15, 38.75, x + w + g - 0.15, 38.75)
    layer_label(21.5, 5.5, "结果层")
    box(ax, 8, 21.5, 88, 5.5, "计算结果：方案汇总 · 逐小时明细 · 年度现金流 · 推荐组合", WHITE, CORE_E, 9.8)
    arrow(ax, 52, 31, 52, 27.3)
    layer_label(6, 12, "应用层")
    box(ax, 8, 6, 26, 9, "可视化\n能量流 · 典型日 · 价格对比", BLUE_F, BLUE_E, 9.5)
    box(ax, 38, 6, 26, 9, "报告与导出\nWord 报告 · 图表包 · 明细", BLUE_F, BLUE_E, 9.5)
    box(ax, 68, 6, 28, 9, "AI 结果诊断与解释\n只读计算结果，不做计算", AI_F, AI_E, 9.5)
    arrow(ax, 21, 21.5, 21, 15.3)
    arrow(ax, 51, 21.5, 51, 15.3)
    arrow(ax, 82, 21.5, 82, 15.3, "只读", 0.8)
    ax.text(52, 1.2, "数据单向流动：输入 → 技术经济测算 → 计算结果 → 展示、报告与解释", ha="center",
            fontsize=9, color=MUTED)
    save(fig, "fig1_arch.png")


# ---------------------------------------------------------------- 图2 逐时能量平衡与储能调度
def fig_dispatch():
    fig, ax = canvas(8.6, 7.6, 100, 88)
    # 输入
    box(ax, 22, 79, 56, 7.2,
        "第 t 小时输入\n负荷  ·  风光净出力（扣除站用电）  ·  上一时段末储能 SOC", BLUE_F, BLUE_E, 9.8)
    arrow(ax, 50, 79, 50, 74.6)
    diamond(ax, 50, 69.5, 30, 9.5, "净新能源 ≥ 负荷？", size=10.5)
    # 分支线
    line(ax, [35, 25, 25], [69.5, 69.5, 64.6])
    line(ax, [65, 75, 75], [69.5, 69.5, 64.6])
    ax.annotate("", xy=(25, 64.2), xytext=(25, 64.8), arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1.1, mutation_scale=11))
    ax.annotate("", xy=(75, 64.2), xytext=(75, 64.8), arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1.1, mutation_scale=11))
    ax.text(29.5, 71.2, "是：新能源富余", fontsize=9, color=GREEN_E, ha="center")
    ax.text(70.5, 71.2, "否：新能源不足", fontsize=9, color=AI_E, ha="center")

    left = [
        ("① 新能源直接供负荷", None),
        ("② 富余电量为储能充电", "受充电功率、SOC 上限、充电效率约束"),
        ("③ 剩余电量上网", "受年度上网剩余额度、交换功率上限约束"),
        ("④ 仍有剩余则弃电", "记录弃电原因"),
    ]
    right = [
        ("① 新能源全部供负荷", None),
        ("② 储能放电补足缺口", "受放电功率、SOC 下限、放电效率约束"),
        ("③ 剩余缺口由电网供电", "受交换功率上限约束"),
        ("④ 仍不足记为供电缺口", "方案判为不达标"),
    ]
    ys = [56.5, 46.5, 36.5, 26.5]
    for (t, sub), y in zip(left, ys):
        text = t if sub is None else f"{t}\n{sub}"
        box(ax, 6, y, 38, 7.4 if sub else 5.6, text, GREEN_F, GREEN_E, 9.4)
    for (t, sub), y in zip(right, ys):
        text = t if sub is None else f"{t}\n{sub}"
        box(ax, 56, y, 38, 7.4 if sub else 5.6, text, AI_F, AI_E, 9.4)
    for col in (25, 75):
        arrow(ax, col, 56.5, col, 54.2)
        arrow(ax, col, 46.5, col, 44.2)
        arrow(ax, col, 36.5, col, 34.2)
    # 汇合
    line(ax, [25, 25, 75, 75], [26.5, 21.5, 21.5, 26.5])
    arrow(ax, 50, 21.5, 50, 18.9)
    box(ax, 22, 11.5, 56, 7.2, "记录第 t 小时能量台账\n供负荷 · 充放电 · 上网 · 弃电 · 下网 · SOC · 小时工况", BLUE_F, BLUE_E, 9.6)
    # 循环
    line(ax, [78.2, 98, 98, 78.2], [15.1, 15.1, 82.6, 82.6], ls=(0, (4, 3)))
    ax.annotate("", xy=(78.4, 82.6), xytext=(80, 82.6), arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1.1, mutation_scale=11))
    ax.text(96.8, 48.5, "SOC 滚动至 t+1，逐时循环至全年", fontsize=8.8, color=MUTED, rotation=90,
            va="center", ha="center")
    arrow(ax, 50, 11.5, 50, 8.2)
    box(ax, 22, 2.2, 56, 5.6, "全年汇总 → 自发自用率、绿电占比、上网比例、弃电率", WHITE, CORE_E, 9.6)
    # 约束说明
    ax.text(50, -1.2, "储能运行规则：仅由富余新能源充电，不从电网充电；同一小时不同时充放电；不放电上网",
            fontsize=8.8, color=MUTED, ha="center", va="top")
    save(fig, "fig2_dispatch.png")


# ---------------------------------------------------------------- 图3 多视角经济性测算
def fig_economy():
    fig, ax = canvas(9.2, 7.2, 100, 78)
    box(ax, 4, 66.5, 44, 9,
        "技术仿真结果（只读）\n容量配置 · 自发自用电量 · 上网电量\n储能年等效循环次数 · 逐时明细", BLUE_F, BLUE_E, 9.4)
    box(ax, 52, 66.5, 44, 9,
        "经济参数\n造价 · 运维 · 税率 · 绿电结算价 · 上网电价\n电费单科目 或 8760 小时下网电价曲线", BLUE_F, BLUE_E, 9.4)
    line(ax, [26, 26, 74, 74], [66.5, 62.5, 62.5, 66.5])
    arrow(ax, 50, 62.5, 50, 60.3)
    box(ax, 4, 54, 92, 6, "共性处理：价税分离 · 储能更换（循环寿命与日历寿命先到者）· 逐时电量与逐时电价匹配结算",
        CORE_F, CORE_E, 9.4)
    cols = [
        (4, "电源侧", "项目投资现金流",
         "收入：上网售电、绿电结算\n成本：建设投资、运维、储能更换\n税费：增值税及附加、所得税、折旧",
         "年度现金流 · FNPV · FIRR\n静态 / 动态投资回收期"),
        (35.3, "同一主体", "税前增量现金流",
         "收益：自发自用购电节费\n（扣除自用绿电仍需缴纳的\n输配电价、政府基金及附加）\n成本：建设投资、运维、储能更换",
         "税前年度现金流 · FIRR"),
        (66.6, "负荷侧", "年度用能收益",
         "收益 ＝ 自发自用电量 ×\n（可减少的购网费用单价\n－ 绿电结算价）\n可选计入环境价值",
         "负荷侧年度收益"),
    ]
    w = 29.4
    for x, name, sub, body, out in cols:
        arrow(ax, x + w / 2, 54, x + w / 2, 51.7)
        box(ax, x, 45.5, w, 6, f"{name}\n{sub}", WHITE, BLUE_E, 9.8, weight="bold")
        box(ax, x, 30.5, w, 13.3, body, WHITE, CORE_E, 9.0)
        box(ax, x, 22.2, w, 6.5, out, GREEN_F, GREEN_E, 9.2)
        arrow(ax, x + w / 2, 45.5, x + w / 2, 44.0)
        arrow(ax, x + w / 2, 30.5, x + w / 2, 28.9)
    seats = [(4, "电源侧 FIRR 最优"), (35.3, "同一主体 FIRR 最优"), (66.6, "负荷侧可成交收益最优")]
    for x, t in seats:
        arrow(ax, x + w / 2, 22.2, x + w / 2, 18.4)
        box(ax, x, 12.2, w, 6.0, t, AI_F, AI_E, 9.6, weight="bold")
    # 门槛：从电源侧席位下方绕行至负荷侧席位
    dash = (0, (4, 3))
    line(ax, [18.7, 18.7, 81.3], [12.0, 8.2, 8.2], color=AI_E, ls=dash)
    ax.annotate("", xy=(81.3, 11.9), xytext=(81.3, 8.2),
                arrowprops=dict(arrowstyle="-|>", color=AI_E, lw=1.1, mutation_scale=11, ls=dash))
    ax.text(50, 8.2, " 电源侧最低可接受 FIRR 作为门槛 ", fontsize=8.8, color=AI_E, ha="center",
            va="center", bbox=dict(fc="white", ec="none", pad=1.5))
    ax.text(50, 3.6, "负荷侧席位先满足电源侧收益门槛，再比较负荷侧收益，保证推荐方案对双方均可成交",
            fontsize=8.8, color=AI_E, ha="center")
    ax.text(50, 0.4, "FIRR 求解：扫描净现值曲线定位根，仅在存在唯一稳定解时输出，可正确处理储能更换造成的现金流多次变号",
            fontsize=8.6, color=MUTED, ha="center")
    save(fig, "fig3_economy.png")


# ---------------------------------------------------------------- 图4 代表方案推荐
def fig_recommend():
    fig, ax = canvas(9.6, 2.7, 100, 27.5)
    stages = [
        ("候选方案池", "风光储容量组合\n批量生成并逐时仿真", BLUE_F, BLUE_E),
        ("政策达标筛选", "自发自用率 · 绿电占比\n上网比例；列明原因", BLUE_F, BLUE_E),
        ("多视角排序", "同一主体 · 电源侧\n负荷侧可成交 · 工程代表", BLUE_F, BLUE_E),
        ("合并与说明", "多席位命中则合并\n无候选显示待定及原因", BLUE_F, BLUE_E),
        ("推荐组合", "容量 · 指标 · 推荐理由\n可追溯明细与现金流", GREEN_F, GREEN_E),
    ]
    n = len(stages)
    w, g, x0, y, h = 17.4, 2.6, 0.8, 3.0, 19.0
    for i, (title, body, fc, ec) in enumerate(stages):
        x = x0 + i * (w + g)
        box(ax, x, y, w, h, "", fc, ec)
        ax.text(x + w / 2, y + h - 4.6, title, ha="center", va="center", fontsize=10.5, weight="bold", color=INK)
        ax.text(x + w / 2, y + h / 2 - 2.6, body, ha="center", va="center", fontsize=8.6, color=INK, linespacing=1.55)
        if i < n - 1:
            arrow(ax, x + w + 0.2, y + h / 2, x + w + g - 0.2, y + h / 2)
    labels = ["数百至数千个", "达标方案", "四个推荐席位", "去重合并", "少数代表方案"]
    for i, t in enumerate(labels):
        x = x0 + i * (w + g)
        ax.text(x + w / 2, y + h + 2.6, t, ha="center", va="center", fontsize=8.6, color=MUTED)
    save(fig, "fig4_recommend.png")


# ---------------------------------------------------------------- 图5 AI 方案策划助手
def fig_ai():
    fig, ax = canvas(9.6, 5.2, 100, 54)
    lanes = [("工程人员", 37, BLUE_E), ("AI 助手", 19.5, AI_E), ("平台服务\n与测算引擎", 2, MUTED)]
    for name, y, c in lanes:
        ax.add_patch(FancyBboxPatch((0.5, y), 99, 15.5, boxstyle="round,pad=0.1,rounding_size=0.6",
                                    fc="#fafbfc", ec="#d9dee4", lw=0.8))
        ax.text(3.2, y + 7.75, name, fontsize=9.2, color=c, weight="bold", va="center", ha="center",
                rotation=90, linespacing=1.2)
    W, H = 16.5, 8.6
    cols = [7.5, 25.8, 44.1, 62.4, 80.7]
    lane_y = {"u": 40.2, "a": 22.7, "p": 5.2}
    spec = {
        "u1": (0, "u", "① 提出需求\n自然语言或项目数据", BLUE_F, BLUE_E),
        "a1": (0, "a", "② 意图与参数识别\n结构化 JSON 输出", AI_F, AI_E),
        "a2": (1, "a", "③ 参数校验\n提示缺失项", AI_F, AI_E),
        "u2": (1, "u", "补充或确认参数", BLUE_F, BLUE_E),
        "a3": (2, "a", "④ 选择计算功能\n函数调用", AI_F, AI_E),
        "p1": (2, "p", "⑤ 技术仿真、经济性\n测算、方案推荐", WHITE, CORE_E),
        "p2": (3, "p", "⑥ 返回真实结果\n汇总 · 明细 · 现金流", WHITE, CORE_E),
        "a4": (3, "a", "⑦ 结果诊断与解释\n报告分析与建议段落", AI_F, AI_E),
        "u3": (4, "u", "⑧ 复核并采纳\n形成方案报告", BLUE_F, BLUE_E),
    }
    pos = {}
    for k, (ci, lane, t, fc, ec) in spec.items():
        x, y = cols[ci], lane_y[lane]
        pos[k] = (x, y)
        box(ax, x, y, W, H, t, fc, ec, 8.7)

    def cx(k):
        return pos[k][0] + W / 2

    def top(k):
        return pos[k][1] + H

    def bot(k):
        return pos[k][1]

    def mid(k):
        return pos[k][1] + H / 2

    arrow(ax, cx("u1"), bot("u1"), cx("a1"), top("a1") + 0.1)
    arrow(ax, pos["a1"][0] + W, mid("a1"), pos["a2"][0], mid("a2"))
    ax.annotate("", xy=(cx("u2"), bot("u2")), xytext=(cx("a2"), top("a2")),
                arrowprops=dict(arrowstyle="<|-|>", color=MUTED, lw=1.1, mutation_scale=11))
    arrow(ax, pos["a2"][0] + W, mid("a2"), pos["a3"][0], mid("a3"))
    arrow(ax, cx("a3"), bot("a3"), cx("p1"), top("p1") + 0.1)
    arrow(ax, pos["p1"][0] + W, mid("p1"), pos["p2"][0], mid("p2"))
    arrow(ax, cx("p2"), top("p2"), cx("a4"), bot("a4") - 0.1)
    line(ax, [pos["a4"][0] + W, cx("u3")], [mid("a4"), mid("a4")])
    arrow(ax, cx("u3"), mid("a4"), cx("u3"), bot("u3") - 0.1)
    ax.text(50, -1.0, "边界：能量平衡、政策指标和财务指标全部由程序计算；AI 只负责理解需求、调用功能和解释结果",
            fontsize=8.8, color=MUTED, ha="center", va="top")
    save(fig, "fig5_ai.png")


if __name__ == "__main__":
    fig_arch()
    fig_dispatch()
    fig_economy()
    fig_recommend()
    fig_ai()
