"""Rebuild the three formal-evaluation figures using only the public aggregate.

Run from any directory with the document Python environment:
  D:/anaconda/python.exe submission/report/build_result_figures.py
No participant answers, private held-out material, or runtime services are read.
"""
from pathlib import Path
from hashlib import sha256
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'data/evaluation/blind-eval-F21-formal-20261009/formal-results.json'
OUT = HERE / 'assets'
FONT = Path('C:/Windows/Fonts/simhei.ttf')
font_manager.fontManager.addfont(str(FONT))
plt.rcParams.update({
    'font.family': font_manager.FontProperties(fname=str(FONT)).get_name(),
    'axes.unicode_minus': False, 'font.size': 13, 'axes.titlesize': 14,
    'axes.labelsize': 12, 'xtick.labelsize': 12, 'ytick.labelsize': 11,
    'pdf.fonttype': 42, 'ps.fonttype': 42,
    'axes.spines.top': False, 'axes.spines.right': False,
    'axes.edgecolor': '#8593A0', 'text.color': '#18283B',
    'axes.labelcolor': '#18283B', 'savefig.facecolor': 'white',
})
D = json.loads(SOURCE.read_text(encoding='utf-8'))
SPLITS = [('development', '开发核心'), ('heldout', '封存测试集'), ('extension', '已见扩展')]
ARMS = [('original_pi', '原版组'), ('prepared', '同数据通用组'), ('financial', '金融组')]
ROUNDS = [('round1', '第一遍'), ('round2', '倒序遍')]
METRICS = [('explanation', 'R3 业绩解释'), ('adjustments', 'R4 特殊损益与口径'), ('anomalies', 'R5 异常分析')]
COLORS = ['#557F9C', '#C98B39', '#168572']
LEGEND = [Patch(facecolor=c, label=label) for c, (_, label) in zip(COLORS, ARMS)]
RECORDS = []


def value(split, rnd, arm, key):
    base = f'/splits/{split}/groups/{rnd}/{arm}'
    obj = D['splits'][split]['groups'][rnd][arm]
    for part in key.split('/'):
        obj = obj[part]
    RECORDS.append({'pointer': base + '/' + key, 'value': obj})
    return obj


def base_axes(ax, ylim, ticks):
    ax.set_ylim(0, ylim)
    ax.set_yticks(ticks)
    ax.yaxis.grid(True, color='#E4E9EE', linewidth=.7)
    ax.set_axisbelow(True)


def finish(fig, name, note):
    fig.legend(handles=LEGEND, loc='upper center', bbox_to_anchor=(.5, .994),
               ncol=3, frameon=False, fontsize=13)
    fig.text(.5, .012, note, ha='center', va='bottom', fontsize=10, color='#536577')
    for suffix in ['png', 'pdf']:
        fig.savefig(OUT / f'{name}.{suffix}', dpi=240, bbox_inches=None)
    plt.close(fig)


def quality():
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5))
    fig.subplots_adjust(top=.82, bottom=.19, left=.07, right=.98, wspace=.17)
    for ax, (rnd, label) in zip(axes, ROUNDS):
        for j, (arm, _) in enumerate(ARMS):
            vals = [value(s, rnd, arm, 'completed_without_material_defect') for s, _ in SPLITS]
            bars = ax.bar(np.arange(3)+(j-1)*.24, vals, width=.22, color=COLORS[j])
            ax.bar_label(bars, labels=[str(x) for x in vals], padding=4, fontsize=13)
        base_axes(ax, 18, [0, 6, 12, 18])
        ax.set_title(label, pad=12)
        ax.set_xticks(range(3), [label for _, label in SPLITS])
    axes[0].set_ylabel('完成且无实质缺陷的回合数（每组计划 18）')
    finish(fig, 'formal-quality', '两遍评审使用同一批运行。开发核心金融组完成 17 回合，其余组均完成 18 回合。来源：[F02]')


def depth():
    fig, axes = plt.subplots(3, 3, figsize=(12, 8))
    fig.subplots_adjust(top=.89, bottom=.1, left=.1, right=.985, hspace=.34, wspace=.14)
    for i, (split, label) in enumerate(SPLITS):
        for k, (metric, title) in enumerate(METRICS):
            ax = axes[i, k]
            if i == 0:
                ax.set_title(title, pad=12)
            if k == 0:
                ax.set_ylabel(label+'\n适用均分', fontsize=13)
            base_axes(ax, 4.55, [0, 2, 4])
            ax.set_xticks([0, 1], ['第一遍', '倒序遍'])
            for j, (arm, _) in enumerate(ARMS):
                vals = [value(split, rnd, arm, 'scores/'+metric) for rnd, _ in ROUNDS]
                for x, v in enumerate(vals):
                    if v is not None:
                        bar = ax.bar(x+(j-1)*.23, v, width=.21, color=COLORS[j])
                        ax.bar_label(bar, labels=[f'{v:.2f}'], padding=3, fontsize=10.5)
            if split == 'development' and metric == 'adjustments':
                ax.text(.5, .48, '未主考 / 无适用评分\n不作零分', transform=ax.transAxes,
                        ha='center', va='center', fontsize=13, color='#536577')
            ax.set_xlim(-.5, 1.5)
    finish(fig, 'formal-depth', '各维度为 0–4 分；仅汇总适用评分。开发核心 R3 含直接主考与模型更新辅助解释。来源：[F02]')


def cost():
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.4))
    fig.subplots_adjust(top=.89, bottom=.12, left=.08, right=.98, hspace=.43, wspace=.19)
    for c, (rnd, label) in enumerate(ROUNDS):
        for r, key in enumerate(['known_input_total', 'known_input_per_complete_clean_case']):
            ax = axes[r, c]
            for j, (arm, _) in enumerate(ARMS):
                vals = [value(s, rnd, arm, key)/1e6 for s, _ in SPLITS]
                bars = ax.bar(np.arange(3)+(j-1)*.24, vals, width=.22, color=COLORS[j])
                ax.bar_label(bars, labels=[f'{v:.2f}' for v in vals], fontsize=10.5, padding=3)
            base_axes(ax, 19 if r == 0 else 2.6, [0, 6, 12, 18] if r == 0 else [0, 1, 2])
            ax.set_xticks(range(3), [label for _, label in SPLITS])
            ax.set_title(label+(' · 已知输入总量' if r == 0 else ' · 每个完成且无实质缺陷回合'), pad=10)
            if c == 0:
                ax.set_ylabel('百万 token' if r == 0 else '百万 token / 回合')
    finish(fig, 'formal-cost', '含失败与重试的已知输入；两遍共用总量、分别取无缺陷分母。未知用量未计入此图；非费用判据。来源：[F02]')


if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    quality()
    depth()
    cost()
    evidence = {
        'source': SOURCE.relative_to(ROOT).as_posix(),
        'source_sha256': sha256(SOURCE.read_bytes()).hexdigest(),
        'font': str(FONT),
        'definitions': {
            'quality': 'completed_without_material_defect; failed cases never counted as clean',
            'depth': 'groups scores, applicable means; null is untested, never zero',
            'cost': 'known input, including cache-read and failures; same runs in both reviews',
            'cost_per_clean': 'known_input_total / completed_without_material_defect; per review',
            'display': 'raw values retained; depth and millions displayed at two decimals',
        },
        'plotted_values': RECORDS,
        'artifacts': {p.name: sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.glob('formal-*.*'))},
    }
    (HERE/'evidence'/'formal-figure-data.json').write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    print('3 figures generated; raw values and source pointers in evidence/formal-figure-data.json')
