"""Persisted, bounded splitting of audited output-limit failures.

Successful children keep their original owners. Only a typed Pi output-limit
response permits splitting; authentication, balance and transport errors escape.
"""
from .definition_model import output_limit_evidence
from .review_cache import shared_result,result_hash,accept_result


def bounded_temporal_result(store,part,phase,key_for,infer,validate,cancelled,progress,provenance,depth=0):
    key=key_for(part)
    # A plan is not an accepted model response. Its separate identity makes a
    # restarted owner skip the already proven oversized request.
    plan_key=key_for({'split_plan':'output-limit-1','parent':key})
    def read_plan():
        import json
        with store.connect() as db:row=db.execute('SELECT result_json FROM temporal_review_cache WHERE cache_key=?',(plan_key,)).fetchone()
        return json.loads(row[0]) if row else None
    def compute():
        plan=read_plan();spent=0
        if plan is None:
            try:return infer(part)
            except Exception as error:
                evidence=output_limit_evidence(error)
                if evidence is None or cancelled():raise
                spent=getattr(error,'temporal_requests',1)
                plan={'kind':'output_limit_split_plan','parent_cache_key':key,'limit':evidence,'source_provenance':provenance}
                with store.connect(write=True) as db:plan,_=accept_result(db,'temporal_review_cache',{'cache_key':plan_key},plan)
        if len(part)>1 and depth<2:
            middle=(len(part)+1)//2;children=[];requests=spent;audits=[];source_audits={}
            progress(f"本批输出达到上限，拆为 {middle} + {len(part)-middle} 项继续；已完成批次保留")
            for child in (part[:middle],part[middle:]):
                value,cached,count=bounded_temporal_result(store,child,phase,key_for,infer,validate,cancelled,progress,provenance,depth+1)
                children.append(value);requests+=count
                audit={'cache_key':key_for(child),'result_hash':result_hash(value),'source_provenance':value.get('_review_provenance'),'cache_hit':cached}
                audits.append(audit)
                if phase!='profiles':
                    for correction in value.get('corrections',[]):
                        source=correction['source_key'];source_audits[source]=value.get('source_audits',{}).get(source,audit)
            fields=('candidates','reviewed_group_ids') if phase=='profiles' else ('corrections','unresolved')
            result={field:[item for child in children for item in child.get(field,[])] for field in fields}
            if phase=='profiles':result['reviewed_count']=len(part)
            result.update(extractions=[],requests=requests,_review_provenance=provenance,
                          split_children=audits,source_audits=source_audits,output_limit=evidence_from_plan(plan),
                          deferred_group_ids=[i for child in children for i in child.get('deferred_group_ids',[])])
            return result,requests
        # At most two subdivisions. Further failure routes profile decisions to
        # explicit high source review, or keeps source dates visibly unresolved.
        reason='本批请求达到输出上限；'+('转原文 high 复核，未假定当前期间正确' if phase=='profiles' else '保留原数据并标为待核验')
        if phase=='profiles':
            result={'reviewed_count':len(part),'reviewed_group_ids':[p['group_id'] for p in part],
                    'candidates':[{'group_id':p['group_id'],'reason':reason} for p in part],
                    'deferred_group_ids':[p['group_id'] for p in part]}
        else:result={'corrections':[],'unresolved':[{'source_key':p['source_key'],'reason':reason} for p in part]}
        result.update(extractions=[],requests=spent,_review_provenance=provenance,output_limit=evidence_from_plan(plan),program_fallback=True)
        return result,spent
    return shared_result(store,'temporal_review_cache',{'cache_key':key},compute,cancelled,lambda result:validate(part,result))


def evidence_from_plan(plan):
    return {'bridge_error':plan['limit'],'source_provenance':plan['source_provenance']}
