import unittest
from decimal import Decimal
from service.analysis_parameters import parameter_inventory, override_parameters, apply_operator
from service.analysis_comparison import differences

class ParameterTests(unittest.TestCase):
    def test_static_decimal_constructors_and_elementwise_updates_without_execution(self):
        code="from decimal import Decimal\nD=Decimal\nfcf=list(map(D,['288','512']))\nw=D('0.122'); g=D('.02')\nx={'2024':D('1.2')}\nunsafe=__import__('os').system('must never run')\n"
        self.assertNotIn('unsafe',parameter_inventory(code))
        new,changes=override_parameters(code,{'w':{'+':.005},'fcf':{'*':.9}},['w','fcf'])
        self.assertEqual(parameter_inventory(new)['fcf'],['259.2','460.8'])
        self.assertIn("w=D('0.127')",new)
        self.assertEqual(changes['w'],{'old':'0.122','new':'0.127'})
        self.assertEqual(apply_operator({'year':Decimal('1.1')},{'*':'0.9'}),{'year':Decimal('.99')})
        with self.assertRaisesRegex(ValueError,'可覆盖参数.*fcf'):override_parameters(code,{'WACC':.1})
        with self.assertRaisesRegex(ValueError,'恰好'):override_parameters(code,{'w':.1},['g'])

    def test_unicode_offsets_and_no_false_mutation_of_literals_in_strings(self):
        code="标题='中文'; w=0.122; fcf={2024:288,2025:512}\ntext='w=0.122'\n"
        new,_=override_parameters(code,{'w':{'+':'.005'},'fcf':{'*':'.9'}})
        self.assertIn("标题='中文'; w=0.127",new);self.assertIn("text='w=0.122'",new)
        self.assertEqual(parameter_inventory(new)['fcf'][2024],'259.2')

    def test_changes_align_rows_and_convert_units_and_percentage_points(self):
        old={'t':{'columns':{'rate':{'unit':'%'},'v':{'unit':'人民币百万元','currency':'CNY'}},'row_keys':['A'],'rows':[{'rate':'12.2','v':'1234'}]}}
        new={'t':{'columns':{'rate':{'unit':'%'},'v':{'unit':'亿元','currency':'CNY'}},'row_keys':['A'],'rows':[{'rate':'12.7','v':'13'}]}}
        table,skipped=differences(old,new);self.assertEqual(skipped,[])
        self.assertEqual(table['rows'][0]['delta'],'0.5');self.assertEqual(table['cell_units'][0]['delta']['unit'],'个百分点')
        self.assertEqual(table['rows'][1]['delta'],'0.66')

if __name__=='__main__':unittest.main()
