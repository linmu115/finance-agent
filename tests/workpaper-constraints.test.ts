import test from 'node:test';
import assert from 'node:assert/strict';
import {registerWorkpaperConstraints,workpaperConstraintIssues} from '../server/workpaper-constraints.js';

test('N4 restrictions attach to exact cells; qualified references and known parent cells remain usable',()=>{
 const registry:any={};
 registerWorkpaperConstraints(registry,{answer_constraints:[{id:'unknown',subject:{table:'versions',row_key:'v1',columns:['previous']},
  prohibited_uses:['label_as_parent_profit','same_basis_error'],message:'前值利润归属未明；只能作限定参照。'}]});
 assert.equal(workpaperConstraintIssues('归母净利润为 {{versions.v1.previous}}。',registry).length,1);
 assert.equal(workpaperConstraintIssues('预测误差为 {{versions.v1.previous}}。',registry).length,1);
 for(const body of ['不能将 {{versions.v1.previous}} 称为归母净利润。','归母净利润为 {{versions.v1.current}}。',
  '归属不明的披露利润为 {{versions.v1.previous}}。','{{versions.v1.previous}} 不构成预测误差。'])assert.equal(workpaperConstraintIssues(body,registry).length,0,body);
 assert.equal(workpaperConstraintIssues('不能视为归母净利润。归母净利润为 {{versions.v1.previous}}。',registry).length,1);
 registerWorkpaperConstraints(registry,{numeric_tables:{versions:{}},answer_constraints:[]});assert.deepEqual(registry,{});
});

test('pipeline namespace constraints and finite row sets preserve their boundaries',()=>{
 const registry:any={};registerWorkpaperConstraints(registry,{context:{comparability_constraints:[{id:'basis',affected_refs:['comparison_growth.revenue.delta'],forbidden_claims:['same_basis_comparison'],required_qualification:'收入边界未齐'}]}});
 assert.equal(workpaperConstraintIssues('同口径增长为 {{comparison_growth.revenue.delta}}。',registry).length,1);
 assert.equal(workpaperConstraintIssues('同口径增长为 {{comparison_growth.profit.delta}}。',registry).length,0);
 registerWorkpaperConstraints(registry,{answer_constraints:[{id:'finite',subject:{table:'x',row_key:'*',row_keys:['a','b'],columns:['delta']},prohibited_uses:['beat_miss_conclusion'],message:'口径未齐'}]});
 assert.equal(workpaperConstraintIssues('{{x.a.delta}} 表明超预期。',registry).length,1);
 assert.equal(workpaperConstraintIssues('{{x.c.delta}} 表明超预期。',registry).length,0);
});
