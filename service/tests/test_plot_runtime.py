import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HAS_MPL=importlib.util.find_spec('matplotlib') is not None


@unittest.skipUnless(HAS_MPL,'Matplotlib tests run in the plot environment / Docker image')
class PlotRuntimeTests(unittest.TestCase):
    def setUp(self):
        import matplotlib
        matplotlib.use('Agg')
        from service import plot_runtime
        import matplotlib.pyplot as plt
        self.runtime=plot_runtime;self.plt=plt
        plot_runtime._DIAGNOSTICS.clear();plot_runtime.setup()
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.addCleanup(plt.close,'all')

    def save(self,fig):
        path=Path(self.tmp.name)/'plot.png';fig.savefig(path,dpi=120)
        self.assertTrue(path.is_file())
        return json.loads(path.with_name('plot_diagnostics.json').read_text(encoding='utf-8'))['files'][-1]

    def test_default_and_legacy_colorbar_tight_layout(self):
        import numpy as np
        fig,axes=self.plt.subplots(1,2,figsize=(8,4))
        self.assertTrue(fig.get_constrained_layout())
        for ax in axes:
            im=ax.imshow(np.arange(9).reshape(3,3));ax.set_title('sensitivity')
        fig.colorbar(im,ax=list(axes));fig.suptitle('two scenarios')
        fig.tight_layout(rect=[0,.05,1,.95])
        data=self.save(fig)
        self.assertFalse(data['remaining_overlaps'])

    def test_negative_bar_label_clears_bottom_spine_without_changing_axes_or_values(self):
        import numpy as np
        for annotation in (True,False):
            fig,ax=self.plt.subplots(figsize=(7,4));bars=ax.bar([0,1],[-18.7,955.2],color=['navy','orange'])
            ax.set_ylim(-70,1050);ax.axhline(0,color='gray');ax.set_xticks([0,1],['cash','income'])
            if annotation:text=ax.annotate('-18.7',(0,-18.7),xytext=(0,-14),textcoords='offset points',ha='center',va='top')
            else:text=ax.text(0,-65,'-18.7',ha='center',va='top')
            ylim=ax.get_ylim();ticks=ax.get_yticks().copy();colors=[b.get_facecolor() for b in bars]
            result=self.save(fig);self.assertEqual(len(result['negative_label_changes']),1)
            box=text.get_window_extent(fig.canvas.get_renderer());self.assertGreater(box.y0,ax.bbox.y0)
            self.assertEqual(ax.get_ylim(),ylim);self.assertTrue(np.array_equal(ticks,ax.get_yticks()))
            self.assertEqual([b.get_height() for b in bars],[-18.7,955.2]);self.assertEqual([b.get_facecolor() for b in bars],colors)
            self.assertEqual([t.get_text() for t in ax.get_xticklabels()],['cash','income'])

    def test_negative_label_requires_bar_and_matching_number(self):
        fig,ax=self.plt.subplots();ax.bar([0],[-5]);label=ax.text(0,0,'-9.0')
        before=label.get_position();result=self.save(fig)
        self.assertEqual(result['negative_label_changes'],[]);self.assertEqual(label.get_position(),before)

    def test_heatmap_recolors_dark_cells_only_and_keeps_data_ticks_palette(self):
        import numpy as np
        fig,ax=self.plt.subplots();values=np.array([[0,1],[2,3]])
        im=ax.imshow(values,cmap='viridis');ax.set_xticks([0,1],['base','new'])
        labels=[ax.text(j,i,str(values[i,j]),ha='center',va='center',color='black') for i in range(2) for j in range(2)]
        xlim,ylim=ax.get_xlim(),ax.get_ylim();data=self.save(fig)
        self.assertTrue(data['contrast_changes']);self.assertEqual(labels[0].get_color(),'white')
        self.assertEqual(labels[-1].get_color(),'black');self.assertFalse(data['remaining_low_contrast'])
        self.assertTrue(np.array_equal(im.get_array(),values));self.assertEqual(im.get_cmap().name,'viridis')
        self.assertEqual(ax.get_xlim(),xlim);self.assertEqual(ax.get_ylim(),ylim)
        self.assertEqual([t.get_text() for t in ax.get_xticklabels()],['base','new'])

    def test_grid_crossing_label_centre_is_not_mistaken_for_cell_fill(self):
        fig,ax=self.plt.subplots();ax.imshow([[0,1],[2,3]],cmap='YlGnBu')
        ax.set_xticks([0,1]);ax.set_yticks([0,1]);ax.grid(color='white',linewidth=1)
        text=ax.text(1,1,'dark',color='black',ha='center',va='center')
        data=self.save(fig)
        self.assertEqual(text.get_color(),'white');self.assertTrue(data['contrast_changes'])

    def test_quadmesh_and_bar_labels(self):
        fig,axes=self.plt.subplots(1,2)
        axes[0].pcolormesh([[0,1],[2,3]],cmap='viridis')
        q=axes[0].text(.5,.5,'mesh',ha='center',va='center',color='black')
        bars=axes[1].bar([0],[10],color='#111111')
        b=axes[1].text(0,5,'bar',ha='center',va='center',color='black')
        old=bars[0].get_facecolor();data=self.save(fig)
        self.assertEqual(q.get_color(),'white');self.assertEqual(b.get_color(),'white')
        self.assertEqual(bars[0].get_facecolor(),old);self.assertGreaterEqual(len(data['contrast_changes']),2)

    def test_unresolved_text_collision_reported_with_elements_and_area(self):
        fig,ax=self.plt.subplots()
        ax.text(.5,.5,'alpha',transform=ax.transAxes);ax.text(.5,.5,'beta',transform=ax.transAxes)
        data=self.save(fig)
        pair=next(x for x in data['remaining_overlaps'] if {x['a'].get('text'),x['b'].get('text')}=={'alpha','beta'})
        self.assertGreater(pair['area_px2'],0);self.assertIn('bbox_a',pair)
        self.assertTrue(data['file'].endswith('plot.png'));self.assertEqual(data['layout_repair'],'constrained')

    def test_manual_colorbar_collision_reported_without_changing_limits(self):
        fig,ax=self.plt.subplots();im=ax.imshow([[0,1],[2,3]])
        cb=fig.add_axes([.4,.3,.04,.4]);fig.colorbar(im,cax=cb)
        data=self.save(fig)
        self.assertTrue(any(x['kind']=='colorbar_subplot_overlap' for x in data['remaining_overlaps']))

    def test_repeated_setup_is_idempotent_and_stream_save_works(self):
        import io
        self.runtime.setup();fig,ax=self.plt.subplots();ax.plot([1,2])
        output=io.BytesIO();fig.savefig(output,format='png')
        self.assertTrue(output.getvalue().startswith(b'\x89PNG'))
        self.assertEqual(len(self.runtime._DIAGNOSTICS),1)

    def test_final_save_reports_fixed_suptitle_and_ignores_off_axis_ticks(self):
        fig,axes=self.plt.subplots(1,2,figsize=(6,3))
        for ax in axes:ax.set_title('a wide subplot heading')
        fig.suptitle('explicit figure heading',y=.98)
        data=self.save(fig)
        self.assertTrue(any('explicit figure heading' in (x['a'].get('text'),x['b'].get('text')) for x in data['remaining_overlaps']))
        self.assertTrue(any('a wide subplot heading' in (x['a'].get('text'),x['b'].get('text')) for x in data['remaining_overlaps']))
        fig,ax=self.plt.subplots();ax.set_ylim(0,1);ax.set_yticks([-1,0,.5,1,2]);ax.set_ylim(0,1)
        fig.canvas.draw()
        labels=[t.get_text() for t,b in self.runtime._texts(fig,fig.canvas.get_renderer())]
        self.assertNotIn('-1.0',labels);self.assertNotIn('2.0',labels)

    def test_contrast_threshold_and_alpha_are_retained(self):
        fig,ax=self.plt.subplots();ax.imshow([[0]],cmap='gray',vmin=0,vmax=1)
        text=ax.text(0,0,'dim',ha='center',va='center',color='black',alpha=.1)
        data=self.save(fig)
        self.assertEqual(text.get_alpha(),.1);self.assertTrue(data['remaining_low_contrast'])
        self.assertEqual(self.runtime.contrast((0,0,0),(1,1,1)),21)


if __name__=='__main__':unittest.main()
