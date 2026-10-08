"""Persistent per-table scheduling at Pi's native settle boundary."""
from .store import utcnow
from .table_identity import table_index


def runnable_tables(state, document):
    pending=set(document['tables'])-set(document['completed_tables'])
    deferred=document.get('deferred_tables',{})
    if state.get('repair_phase'):
        return {i for i in pending if str(i) in deferred and not deferred[str(i)].get('repair_attempted')}
    return pending-{int(i) for i in deferred}


def record_attempt(state, document_id, results, reopenings=()):
    document=next(d for d in state['documents'] if d['document_id']==document_id)
    attempts=document.setdefault('round_attempts',{})
    for item in results:
        attempts[str(item['index'])]=[i for i in item['issues'] if i.get('severity')!='review']
    for issue in reopenings:
        bucket=attempts.setdefault(str(issue['table']),[])
        if issue not in bucket:bucket.append(issue)


def submitted_table(document, index):
    document['offered_tables']=[i for i in document.get('offered_tables',[]) if i!=index]
    document.get('round_attempts',{}).pop(str(index),None)
    document.get('deferred_tables',{}).pop(str(index),None)


def settle_tables(state, sources, tool_errors=()):
    """An offered/attempted table gets one round, unrelated work stays runnable."""
    newly=[]
    for document in state['documents']:
        did=document['document_id'];done=set(document['completed_tables'])
        deferred=document.setdefault('deferred_tables',{})
        for key in list(deferred):
            if int(key) in done:deferred.pop(key)
        attempts=document.pop('round_attempts',{})
        offered=set(document.pop('offered_tables',[]))|{int(i) for i in attempts}
        tables={t['index']:t for t in sources[did]['tables']}
        for index in sorted(offered-done):
            table=tables[index];errors=[]
            for error in tool_errors:
                if error.get('processing_id') not in {None,state['processing_id']}:continue
                if error.get('document_id') not in {None,did}:continue
                target=table_index(error.get('table_id'),did)
                if target is not None and target!=index:continue
                errors.append(error)
            issues=attempts.get(str(index)) or document.get('validation_issues',{}).get(str(index)) or []
            reason=issues[0]['reason'] if issues else 'tool_error_without_submission' if errors else 'no_submission_in_round'
            previous=deferred.get(str(index))
            deferred[str(index)]={'table':index,'table_id':f'{did}:t{index}','page':table['page'],
                'reason':reason,'issues':issues,'tool_errors':errors,'source_heading':table['rows'][:2],
                'deferred_at':utcnow(),'repair_attempted':bool(state.get('repair_phase')),
                **({'initial_failure':previous.get('initial_failure',previous)} if previous else {})}
            newly.append({'document_id':did,**deferred[str(index)]})
    if not any(runnable_tables(state,d) for d in state['documents']) and not state.get('repair_phase'):
        # Exactly one final sweep, restricted to the deferred set. Completion
        # counts remain unchanged; a deferred table is never a success receipt.
        if any(d.get('deferred_tables') for d in state['documents']):state['repair_phase']=True
    return newly
