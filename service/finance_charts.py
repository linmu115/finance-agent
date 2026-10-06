"""Optional Matplotlib house styles for scripts running inside the analysis sandbox.

The agent still chooses data, chart types, layout and annotations. This module
does not calculate financial results or decide whether a value is a forecast.
It is copied as a read-only input; the host service never imports Matplotlib.
"""
from contextlib import contextmanager


VERSION = "finance-charts-1.2"
PALETTES = {
    "analysis": {
        "main": "#35658e", "secondary": "#438478", "negative": "#b57d58",
        "neutral": "#6d7f8b", "background": "#ffffff", "panel": "#f2f5f6",
        "text": "#233645", "muted": "#61717d", "grid": "#dce4e8",
    },
    "report": {
        "main": "#315447", "secondary": "#608976", "negative": "#ae7455",
        "neutral": "#748079", "background": "#fdfcf9", "panel": "#fdfcf9",
        "text": "#28372f", "muted": "#637269", "grid": "#e2e6df",
    },
}


@contextmanager
def theme(name="analysis"):
    """Use 'analysis' for chat, 'report' for formal exports; yield named colors.

Keep creation, labels and savefig inside the context. Standard Matplotlib APIs
remain available, including custom layouts and user-requested style overrides.
"""
    if name not in PALETTES:
        raise ValueError("Unknown chart theme; choose analysis or report")
    import matplotlib as mpl
    from matplotlib import font_manager
    from cycler import cycler

    colors = dict(PALETTES[name])
    installed = {font.name for font in font_manager.fontManager.ttflist}
    candidates = ["Noto Sans CJK SC", "Noto Sans CJK JP", "Microsoft YaHei", "SimHei", "DejaVu Sans"]
    fonts = [font for font in candidates if font in installed] or ["DejaVu Sans"]
    title_candidates = ["Noto Serif CJK SC", "Noto Serif CJK JP", "SimSun"]
    colors["title_font"] = next((font for font in title_candidates if font in installed), fonts[0]) if name == "report" else fonts[0]
    settings = {
        "font.family": fonts,
        "font.size": 11,
        "text.color": colors["text"],
        "axes.unicode_minus": False,
        "axes.facecolor": colors["panel"],
        "axes.edgecolor": colors["grid"],
        "axes.labelcolor": colors["muted"],
        "axes.labelsize": 10,
        "axes.titlesize": 12,
        "axes.titleweight": "semibold",
        "axes.titlelocation": "left",
        "axes.titlepad": 14,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "axes.axisbelow": True,
        "axes.prop_cycle": cycler(color=[colors["main"], colors["secondary"], colors["negative"], colors["neutral"]]),
        "grid.color": colors["grid"],
        "grid.linewidth": 0.6,
        "xtick.color": colors["muted"],
        "ytick.color": colors["muted"],
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "xtick.major.size": 0,
        "ytick.major.size": 0,
        "lines.linewidth": 2,
        "lines.markersize": 5,
        "legend.frameon": False,
        "legend.fontsize": 10,
        "figure.facecolor": colors["background"],
        "savefig.facecolor": colors["background"],
        "savefig.dpi": 180,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.2,
        "pdf.fonttype": 42,
    }
    with mpl.rc_context(settings):
        yield colors


def configure(name="analysis"):
    """Apply a theme for the whole script; a short-lived with block cannot undo it."""
    import matplotlib as mpl
    with theme(name) as colors:
        settings=dict(mpl.rcParams)
    mpl.rcParams.update(settings)
    return colors


def amount_values(values, amount_scale, display_unit="亿元"):
    """Convert model amounts and return the matching axis unit together."""
    from decimal import Decimal
    units={"元":1,"千元":1000,"万元":10000,"百万元":1000000,"亿元":100000000,"十亿元":1000000000,"千亿元":100000000000}
    scale=Decimal(str(amount_scale))/Decimal(units[display_unit])
    return [None if value is None else float(Decimal(str(value))*scale) for value in values],display_unit


def plot_amounts(ax, x, values, *, amount_scale, display_unit="亿元", currency="CNY", kind="plot", **style):
    """Plot original amounts and set the matching axis label in one operation.

    Database normalized money uses amount_scale=1; a source table uses its
    declared scale; saved model results use model['spec']['amount_scale'].
    The caller controls layout, line styles and all ordinary Matplotlib options.
    """
    plotted,unit=amount_values(values,amount_scale,display_unit)
    artists=getattr(ax,kind)(x,plotted,**style)
    if kind=="barh":ax.set_xlabel(currency+" "+unit)
    else:ax.set_ylabel(currency+" "+unit)
    return artists


def record_values(records, display_unit="亿元"):
    """Normalized database amounts are already base currency, not raw_unit.

    Returns plot values, currency-qualified unit, and exact chart-data records.
    Raw cell unit never causes a second multiplication or division.
    """
    currencies={r['currency'] for r in records}
    if len(currencies)!=1:raise ValueError('Plot series requires one currency/unit')
    currency=next(iter(currencies))
    monetary=currency in {'CNY','HKD','USD','EUR','GBP','JPY'}
    if monetary:values,unit=amount_values([r['value'] for r in records],1,display_unit)
    elif currency in {'percent','percentage_points','multiple','shares','count'}:
        values=[None if r['value'] is None else float(r['value']) for r in records]
        unit={'percent':'%','percentage_points':'个百分点','multiple':'倍','shares':'股','count':'个'}[currency]
    else:raise ValueError('Unsupported display currency/unit: '+currency)
    label=currency+' '+unit if monetary else unit
    data=[{k:r[k] for k in ('fact_id','record_id','metric','label','value','currency','normalized_unit','period','scope','data_kind','quality','dimensions','source_ref') if k in r} for r in records]
    return values,label,data


def model_values(model, values, display_unit="亿元"):
    """Amounts from a saved model carry that model's declared amount_scale."""
    plotted,unit=amount_values(values,model['spec']['amount_scale'],display_unit)
    return plotted,model['spec']['currency']+' '+unit


def waterfall(start, changes, *, end=None, title='', unit='', ax=None, source=None):
    """Signed changes start from the preceding cumulative value, including losses.

    An explicit end different from start+changes is shown as an unexplained
    residual, never silently balanced into a named economic contribution.
    """
    from decimal import Decimal
    import matplotlib.pyplot as plt
    if ax is None:fig,ax=plt.subplots(figsize=(max(7,len(changes)*1.3),4.8),layout='constrained')
    else:fig=ax.figure
    initial=Decimal(str(start));current=initial;steps=[]
    for label,change in changes.items():
        value=Decimal(str(change));steps.append((label,current,value));current+=value
    if end is not None and Decimal(str(end))!=current:
        steps.append(('未解释差额',current,Decimal(str(end))-current));current=Decimal(str(end))
    labels=['起点',*[s[0] for s in steps],'终点']
    series=[initial,*[s[2] for s in steps],current]
    bases=[min(initial,0),*[min(before,before+delta) for _,before,delta in steps],min(current,0)]
    colors=['#637269',*['#608976' if value>=0 else '#ae7455' for value in series[1:-1]],'#637269']
    bars=ax.bar(range(len(series)),[float(abs(v)) for v in series],bottom=[float(b) for b in bases],color=colors,width=.62)
    for i,(bar,value,base) in enumerate(zip(bars,series,bases)):
        top=float(base+abs(value));label=f'{float(value):+,.2f}' if 0<i<len(series)-1 else f'{float(value):,.2f}'
        ax.annotate(label,(bar.get_x()+bar.get_width()/2,top),xytext=(0,5),textcoords='offset points',ha='center',va='bottom',fontsize=9)
    for i,(_,before,delta) in enumerate(steps,1):
        ax.plot([i+.31,i+.69],[float(before+delta)]*2,color='#8a968f',linewidth=.7)
    ax.set_xticks(range(len(labels)),labels);ax.set(title=title,ylabel=unit);ax.axhline(0,color='#748079',linewidth=.7);ax.margins(y=.18)
    if source:fig.supxlabel(source,fontsize=9,color='#637269')
    return fig,ax


def comparison_heatmaps(models):
    """Plot saved DCF results on common WACC/growth axes and one shared color scale.

    models maps panel titles to run_financial_model result objects. Script authors
    remain free to modify the returned figure/axes before saving.
    """
    import numpy as np
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize
    if len({result['units']['value_per_share'] for result in models.values()})>1:
        raise ValueError('Sensitivity panels require the same currency per share')
    rows=[(title,result['tables']['sensitivity']) for title,result in models.items()]
    wacc=sorted({float(row['wacc']) for _,table in rows for row in table})
    growth=sorted({float(row['growth']) for _,table in rows for row in table})
    matrices=[]
    for title,table in rows:
        cells={(float(row['wacc']),float(row['growth'])):float(row['value_per_share']) for row in table if row['status']=='ok'}
        matrices.append((title,np.array([[cells.get((w,g),np.nan) for g in growth] for w in wacc])))
    finite=np.concatenate([matrix[np.isfinite(matrix)] for _,matrix in matrices])
    if not len(finite):raise ValueError('No valid sensitivity values to plot')
    norm=Normalize(vmin=finite.min(),vmax=finite.max());fig,axes=plt.subplots(1,len(matrices),figsize=(6*len(matrices),5),squeeze=False,layout='constrained')
    for ax,(title,matrix) in zip(axes[0],matrices):
        im=ax.imshow(np.ma.masked_invalid(matrix),cmap='YlGnBu',norm=norm,aspect='auto')
        ax.set(title=title,xlabel='永续增长率 g',ylabel='WACC');ax.grid(False)
        ax.set_xticks(range(len(growth)),[f'{v:.1%}' for v in growth]);ax.set_yticks(range(len(wacc)),[f'{v:.1%}' for v in wacc])
        for (i,j),value in np.ndenumerate(matrix):
            if np.isfinite(value):
                rgb=im.cmap(norm(value))[:3]
                linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb]
                luminance=sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))
                ax.text(j,i,f'{value:.2f}',ha='center',va='center',color='white' if luminance<.179 else '#111111')
    fig.colorbar(im,ax=list(axes[0]),label=next(iter(models.values()))['units']['value_per_share'])
    return fig,axes[0]
