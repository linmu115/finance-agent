"""Isolated, raw-source-only cleaning worker. No database or evaluator answers.

The Node owner passes an ephemeral loopback credential on stdin; upstream keys
never enter Python. Evaluation reads these result files only after extraction.
"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from service.semantic import normalize_document, table_batches

CASES=[(9,1,'mixed_eps_roe'),(16,1,'segments_percentage_points'),
       (100,1,'balance_sheet'),(104,1,'income_statement'),
       (108,1,'cashflow_capex'),(173,1,'asset_movement_matrix'),
       (304,1,'post_balance_sheet_events'),(325,1,'parent_investments_continuation'),
       (78,1,'share_capital_changes'),(272,1,'subsidiary_capital_and_ownership')]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--prepared',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--mode',choices=['low','compact-low','targeted-low'],required=True)
    parser.add_argument('--cases',default='')
    args=parser.parse_args()
    runtime=json.loads(sys.stdin.readline())
    source=json.loads(Path(args.prepared).read_text(encoding='utf-8'))
    parsed=source.get('parsed',source)
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    runtime.update(force=True,processing_id='isolated-'+args.mode,
                   cleaning_effort='low',
                   compact_mappings=args.mode in {'compact-low','targeted-low'},
                   targeted_repairs=args.mode=='targeted-low')
    chosen={int(x) for x in args.cases.split(',') if x}
    for index,first,name in CASES:
        if chosen and index not in chosen:continue
        destination=output/(args.mode+'-'+name+'.json')
        if destination.exists():continue
        batch=next(b for b in table_batches(parsed) if b[0]['table']['index']==index and b[0]['rows'][0]==first)
        # Select target rows only. Retain the whole parsed source as read-only
        # evidence so continuation-header retrieval matches production exactly.
        details=[]
        print(json.dumps({'case':name,'mode':args.mode,'status':'started'}),flush=True)
        facts,report=normalize_document(parsed,'isolated-yili',runtime,lambda *_:None,lambda:False,
            lambda _:None,lambda *_:None,on_batch=lambda batch,facts,issues,detail:details.append(detail),selected_batches=[batch])
        destination.write_text(json.dumps({'mode':args.mode,'case':name,'table':index,'page':batch[0]['table']['page'],
            'source_sha256':source.get('sha256'),'report':report,'details':details,'facts':facts},ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'case':name,'mode':args.mode,'facts':len(facts),'issues':len(report['issues']),'status':'saved'}),flush=True)

if __name__=='__main__':main()
