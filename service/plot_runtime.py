"""Shared plot defaults and renderer diagnostics for every sandbox profile."""
import json
from pathlib import Path

_DIAGNOSTICS = {}


def luminance(rgb):
    linear = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in rgb[:3]]
    return sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))


def contrast(a,b):
    x,y = sorted((luminance(a),luminance(b)))
    return (y+.05)/(x+.05)


def _texts(fig,renderer):
    from matplotlib.text import Text
    import numpy as np
    texts=[]
    undrawn_ticks=set()
    for ax in fig.axes:
        for axis in (ax.xaxis,ax.yaxis):
            all_ticks=axis.get_major_ticks()+axis.get_minor_ticks()
            drawn=set(axis._update_ticks())  # Same view-interval selection as Axis.draw.
            undrawn_ticks.update(label for tick in all_ticks if tick not in drawn for label in (tick.label1,tick.label2))
    for text in fig.findobj(Text):
        if text in undrawn_ticks or not text.get_visible() or not text.get_text().strip():continue
        box=text.get_window_extent(renderer)
        if box.width<=0 or box.height<=0 or not np.isfinite(box.extents).all():continue
        clip=text.get_clip_box() if text.get_clip_on() else None
        if clip is not None and not box.overlaps(clip):continue
        texts.append((text,box))
    return texts


def _element(fig,text,index):
    return {'id':f'text:{index}','text':text.get_text(),'axes':fig.axes.index(text.axes) if text.axes in fig.axes else None}


def _overlap(a,b):
    from matplotlib.transforms import Bbox
    intersection=Bbox.intersection(a,b)
    return 0. if intersection is None else float(max(0,intersection.width)*max(0,intersection.height))


def overlaps(fig,renderer):
    """Renderer bounding-box intersections in save-DPI pixels, not semantic guesses."""
    texts=_texts(fig,renderer);issues=[]
    for i,(a,box_a) in enumerate(texts):
        for j in range(i+1,len(texts)):
            b,box_b=texts[j];area=_overlap(box_a,box_b)
            if area>0:
                issues.append({'kind':'text_overlap','a':_element(fig,a,i),'b':_element(fig,b,j),
                               'area_px2':round(area,3),'bbox_a':list(map(float,box_a.extents)),'bbox_b':list(map(float,box_b.extents))})
    for i,bar in enumerate(fig.axes):
        if not hasattr(bar,'_colorbar'):continue
        for j,ax in enumerate(fig.axes):
            if ax is bar or hasattr(ax,'_colorbar') or not ax.get_visible():continue
            a,b=bar.get_tightbbox(renderer),ax.get_tightbbox(renderer)
            if a is None or b is None:continue
            area=_overlap(a,b)
            if area>0:
                issues.append({'kind':'colorbar_subplot_overlap','a':{'id':f'axes:{i}','role':'colorbar'},
                               'b':{'id':f'axes:{j}','role':'subplot','title':ax.get_title()},'area_px2':round(area,3),
                               'bbox_a':list(map(float,a.extents)),'bbox_b':list(map(float,b.extents))})
    return issues


def _on_data_artist(ax,point,renderer):
    from matplotlib.collections import QuadMesh
    from matplotlib.container import BarContainer
    if ax is None or not ax.bbox.contains(*point):return False
    for im in ax.images:
        if im.get_visible() and im.get_window_extent(renderer).contains(*point):return True
    for mesh in ax.collections:
        if isinstance(mesh,QuadMesh) and mesh.get_visible():
            local=mesh.get_transform().inverted().transform(point)
            if any(path.contains_point(local) for path in mesh.get_paths()):return True
    for container in ax.containers:
        if isinstance(container,BarContainer):
            if any(patch.get_visible() and patch.contains_point(point) for patch in container.patches):return True
    return False


def repair_contrast(fig,renderer):
    """Sample the rendered background with text hidden; handles alpha and colormaps."""
    import numpy as np
    from matplotlib.colors import to_rgba
    texts=_texts(fig,renderer)
    targets=[(i,t,b) for i,(t,b) in enumerate(texts) if _on_data_artist(t.axes,((b.x0+b.x1)/2,(b.y0+b.y1)/2),renderer)]
    if not targets:return []
    engine=fig.get_layout_engine()
    fig.set_layout_engine('none')
    for text,_ in texts:text.set_visible(False)
    try:
        fig.canvas.draw()
        pixels=np.asarray(fig.canvas.buffer_rgba()).copy()
    finally:
        for text,_ in texts:text.set_visible(True)
        fig.set_layout_engine(engine)
    height,width=pixels.shape[:2];changes=[]
    for index,text,box in targets:
        x,y=(box.x0+box.x1)/2,(box.y0+box.y1)/2
        # A grid line often crosses the label's exact centre. The median of a
        # small regular sample over the label area estimates the cell/bar fill.
        samples=[pixels[min(height-1,max(0,height-1-int(y+dy*box.height))),
                        min(width-1,max(0,int(x+dx*box.width))),:3]
                 for dx in (-.35,-.175,0,.175,.35) for dy in (-.35,-.175,0,.175,.35)]
        bg=np.median(samples,axis=0)/255.
        if text.get_bbox_patch() is not None:
            patch=text.get_bbox_patch().get_facecolor();bg=np.array(patch[:3])*patch[3]+bg*(1-patch[3])
        fg=to_rgba(text.get_color(),text.get_alpha());visible=np.array(fg[:3])*fg[3]+bg*(1-fg[3])
        before=contrast(visible,bg)
        if before>=3:continue
        candidates=[('black',(0.,0.,0.)),('white',(1.,1.,1.))]
        color,rgb=max(candidates,key=lambda c:contrast(np.array(c[1])*fg[3]+bg*(1-fg[3]),bg))
        text.set_color(color)
        changes.append({'element':_element(fig,text,index),'old_color':list(fg),'new_color':color,
                        'background':bg.tolist(),'contrast_before':round(before,4),
                        'contrast_after':round(contrast(np.array(rgb)*fg[3]+bg*(1-fg[3]),bg),4)})
    fig.canvas.draw()
    return changes


def _tight_layout(self, *, pad=1.08, h_pad=None, w_pad=None, rect=None):
    """Keep legacy tight_layout calls compatible with already-created colorbars."""
    from matplotlib.layout_engine import ConstrainedLayoutEngine
    import matplotlib as mpl
    engine=self.get_layout_engine()
    if not isinstance(engine,ConstrainedLayoutEngine):
        return self._finance_original_tight_layout(pad=pad,h_pad=h_pad,w_pad=w_pad,rect=rect)
    font_inches=mpl.rcParams['font.size']/72
    settings={'h_pad':(h_pad if h_pad is not None else pad)*font_inches,
              'w_pad':(w_pad if w_pad is not None else pad)*font_inches}
    if rect:
        left,bottom,right,top=rect
        settings['rect']=(left or 0,bottom or 0,(right if right is not None else 1)-(left or 0),(top if top is not None else 1)-(bottom or 0))
    engine.set(**settings)
    engine.execute(self)


def repair_negative_bar_labels(fig,renderer):
    """Move numeric bar-end labels off spines/zero lines without changing axes.

    Only unstacked negative bars and labels matching their displayed values are
    eligible. Keep ticks, limits, bar data and palette exactly as supplied.
    """
    import re
    from decimal import Decimal
    from matplotlib.container import BarContainer
    from matplotlib.text import Annotation
    from matplotlib.transforms import ScaledTranslation
    changes=[];pad=3*fig.dpi/72
    for ax in fig.axes:
        bars=[p for c in ax.containers if isinstance(c,BarContainer) and c.orientation=='vertical' for p in c.patches if p.get_height()<0 and p.get_y()==0]
        for text in ax.texts:
            label=text.get_text().strip().replace(',','').replace('−','-')
            if not re.fullmatch(r'-\d+(?:\.\d+)?',label):continue
            displayed=Decimal(label);tolerance=Decimal(1).scaleb(displayed.as_tuple().exponent)/2
            anchor=text.xy if isinstance(text,Annotation) and text.xycoords=='data' else text.get_position() if text.get_transform()==ax.transData else None
            if anchor is None:continue
            candidates=[bar for bar in bars if abs(anchor[0]-(bar.get_x()+bar.get_width()/2))<abs(bar.get_width())/2 and abs(Decimal(str(bar.get_height()))-displayed)<=tolerance]
            if len(candidates)!=1:continue
            bar=candidates[0];box=text.get_window_extent(renderer)
            lines=[spine.get_window_extent(renderer) for spine in ax.spines.values() if spine.get_visible()]
            for line in ax.lines:
                xy=line.get_xydata()
                if line.get_visible() and len(xy)>1 and all(y==0 for _,y in xy):lines.append(line.get_window_extent(renderer))
            crosses=any(box.x1>b.x0 and box.x0<b.x1 and box.y1>b.y0-pad/2 and box.y0<b.y1+pad/2 for b in lines)
            if not crosses and box.y0>=ax.bbox.y0+pad/2:continue
            x=bar.get_x()+bar.get_width()/2;y=bar.get_y()+bar.get_height()
            old=list(box.bounds)
            text.set_ha('center');text.set_va('top')
            if isinstance(text,Annotation):
                text.xy=(x,y);text.xycoords='data';text.set_anncoords('offset points');text.set_position((0,-3))
            else:
                text.set_position((x,y));text.set_transform(ax.transData+ScaledTranslation(0,-3/72,fig.dpi_scale_trans))
            new=text.get_window_extent(renderer)
            # If the model's fixed limits leave too little room below the bar,
            # use its right side at the bar end, inside the existing plot bounds.
            if new.y0<ax.bbox.y0+pad:
                px,py=ax.transData.transform((x,y));right=bar.get_window_extent(renderer).x1
                dx=(right+pad-px)*72/fig.dpi;dy=(max(py,ax.bbox.y0+pad+new.height/2)-py)*72/fig.dpi
                text.set_ha('left');text.set_va('center')
                if isinstance(text,Annotation):text.set_position((dx,dy))
                else:text.set_transform(ax.transData+ScaledTranslation(dx/72,dy/72,fig.dpi_scale_trans))
            changes.append({'axes':fig.axes.index(ax),'text':text.get_text(),'bar_value':bar.get_height(),
                            'old_bbox':old,'new_bbox':list(text.get_window_extent(renderer).bounds),
                            'reason':'negative bar label crossed axis/spine or bottom boundary'})
    return changes


def _savefig(self,fname,*args,**kwargs):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.layout_engine import ConstrainedLayoutEngine
    import matplotlib as mpl
    original_canvas,original_dpi=self.canvas,self.dpi
    dpi=kwargs.get('dpi',mpl.rcParams['savefig.dpi'])
    if dpi!='figure':self.set_dpi(dpi)
    # Agg provides a pixel renderer even if a script selected PDF/SVG as its canvas.
    canvas=FigureCanvasAgg(self)
    try:
        canvas.draw();before=overlaps(self,canvas.get_renderer());layout=None
        if before:
            engine=self.get_layout_engine()
            if engine is None:
                self.set_layout_engine('constrained');engine=self.get_layout_engine()
            if isinstance(engine,ConstrainedLayoutEngine):
                engine.execute(self);canvas.draw();layout='constrained'
            else:
                # A tight-created gridspec colorbar cannot be switched after creation.
                # Run its current engine; report unresolved intersections explicitly.
                engine.execute(self);canvas.draw();layout=type(engine).__name__
        label_changes=repair_negative_bar_labels(self,canvas.get_renderer())
        if label_changes:canvas.draw()
        changes=repair_contrast(self,canvas.get_renderer())
        remaining=overlaps(self,canvas.get_renderer())
        # bbox_inches='tight' changes figure coordinates during the actual print.
        # Capture its final renderer, including explicitly positioned suptitles.
        def saved_draw(event):
            nonlocal remaining
            remaining=overlaps(self,event.renderer)
        callback=canvas.mpl_connect('draw_event',saved_draw)
        try:
            result=self._finance_original_savefig(fname,*args,**kwargs)
        finally:
            canvas.mpl_disconnect(callback)
        filename=str(fname) if isinstance(fname,(str,Path)) else getattr(fname,'name','<stream>')
        entry={'file':filename,'dpi':self.dpi,'overlap_before':before,'layout_repair':layout,
               'contrast_changes':changes,'negative_label_changes':label_changes,'remaining_overlaps':remaining,
               'remaining_low_contrast':[c for c in changes if c['contrast_after']<3]}
        _DIAGNOSTICS[filename]=entry
        destination=Path(filename).parent/'plot_diagnostics.json' if filename!='<stream>' else None
        if destination:
            destination.write_text(json.dumps({'schema_version':1,'mode':'automatic_layout_and_contrast',
                'coordinate_unit':'save_dpi_pixel','files':list(_DIAGNOSTICS.values())},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return result
    finally:
        self.set_canvas(original_canvas);self.set_dpi(original_dpi)


def setup():
    import matplotlib as mpl
    from matplotlib import font_manager
    installed={font.name for font in font_manager.fontManager.ttflist}
    fonts=[name for name in ('Noto Sans CJK SC','Noto Sans CJK JP','Microsoft YaHei','SimHei') if name in installed]
    mpl.rcParams.update({'font.family':'sans-serif','font.sans-serif':fonts+['DejaVu Sans'],
        'axes.unicode_minus':False,'savefig.bbox':'tight','savefig.pad_inches':0.2,
        'figure.autolayout':False,'figure.constrained_layout.use':True})
    from matplotlib.figure import Figure
    if not hasattr(Figure,'_finance_original_savefig'):
        Figure._finance_original_savefig=Figure.savefig
        Figure._finance_original_tight_layout=Figure.tight_layout
        Figure.savefig=_savefig
        Figure.tight_layout=_tight_layout
    if not fonts:
        import warnings
        warnings.warn('没有可用的中文字体；中文图表可能缺字。',RuntimeWarning)


def deliver_models():
    import json, shutil, zipfile
    from pathlib import Path
    root=Path('/input')
    if not json.loads((root/'models.json').read_text(encoding='utf-8')):return
    shutil.copyfile(root/'model_bundle.zip','/output/model_bundle.zip')
    # Make already-calculated tables available as direct downloads as well.
    with zipfile.ZipFile(root/'model_bundle.zip') as z:
        for name in z.namelist():
            if name.endswith(('.csv','.json')):
                (Path('/output')/name).write_bytes(z.read(name))


LAUNCH = '''import runpy, shutil, sys
from pathlib import Path
sys.path.insert(0, '/input')
from plot_runtime import setup
setup()
try:
    runpy.run_path('/input/analysis.py', run_name='__main__')
    if Path('/input/analysis_report.json').exists() or Path('/output/analysis_report.json').exists():
        from analysis_report import deliver
        deliver()
    if Path('/input/parameter_comparison.json').exists():
        from analysis_comparison import deliver_parameter_comparison
        deliver_parameter_comparison()
finally:
    shutil.copyfile('/input/analysis.py', '/output/executed_script.py')
'''

# Same scientific runtime/font setup and executable-script delivery; no report SDK.
ORIGINAL_PI_LAUNCH = '''import runpy, shutil, sys
sys.path.insert(0, '/input')
from plot_runtime import setup
setup()
try:
    runpy.run_path('/input/analysis.py', run_name='__main__')
finally:
    shutil.copyfile('/input/analysis.py', '/output/executed_script.py')
'''
