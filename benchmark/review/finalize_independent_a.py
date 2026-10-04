"""Decimal evaluation of independently authored formulas; no legacy labels or predictions."""
import ast
from datetime import datetime,timezone
from decimal import Decimal,localcontext
import hashlib,json
from pathlib import Path

here=Path(__file__).resolve().parent
def evaluate(formula):
    def walk(node):
        if isinstance(node,ast.Constant) and isinstance(node.value,(int,float)):
            return Decimal(ast.get_source_segment(formula,node))
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,ast.USub):return -walk(node.operand)
        if isinstance(node,ast.BinOp):
            a,b=walk(node.left),walk(node.right)
            if isinstance(node.op,ast.Add):return a+b
            if isinstance(node.op,ast.Sub):return a-b
            if isinstance(node.op,ast.Mult):return a*b
            if isinstance(node.op,ast.Div):return a/b
        raise ValueError('Unsupported formula node')
    with localcontext() as context:
        context.prec=50
        return format(walk(ast.parse(formula,mode='eval').body),'f')

if __name__=='__main__':
    source=here/'acceptance_a_independent_source.json'
    data=json.loads(source.read_text(encoding='utf-8'))
    assert len(data['items'])==40
    root=here.parent/'agent_input'
    cases={c['id']:c for c in [json.loads(s) for s in (root/'cases.jsonl').read_text(encoding='utf-8').splitlines()]}
    for item in data['items']:
        original=root/cases[item['id']]['allowed_assets'][0]
        content=json.loads(original.read_text(encoding='utf-8'))
        locators={e['id'] for section in ('text','table') for e in content[section]}
        assert all(ref in locators for group in item['evidence_sets'] for ref in group)
        assert all(ref in locators for ref in item['valid_context_citations'])
        item['question']=cases[item['id']]['question']
        item['input_sha256']=hashlib.sha256(original.read_bytes()).hexdigest()
        item['canonical_answer']=evaluate(item['formula']) if item['formula'] else None
        item['abs_tolerance']='0.000001'
        for answer in item.get('conditioned_answers',[]):
            if answer.get('formula') and 'canonical_answer' not in answer:
                answer['canonical_answer']=evaluate(answer['formula'])
    data.update(completed_at=datetime.now(timezone.utc).isoformat(),reviewer='Codex independent source-review agent /root/financial_service',scope='Acceptance FinQA sorted by case ID, first 40 of 80',legacy_labels_accessed=False,model_predictions_accessed=False,source_review_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    target=here/'acceptance_a_independent_answers.json'
    target.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Independent solution frozen',hashlib.sha256(target.read_bytes()).hexdigest())
    for i,r in enumerate(data['items']):print(i,r['id'],r['canonical_answer'],r['answer_unit'],r['independent_status'])
