"""Use only invented fixtures in the extracted package; no production database."""
import copy
import itertools
import json
from unittest.mock import patch
from uuid import UUID
from service.tests.test_research_ingestion import ResearchIngestionTests

def inspect(force_id_collision):
    counter=itertools.count(1)
    def identity():return UUID('fcff'+format(next(counter),'028x'))
    context=patch('uuid.uuid4',side_effect=identity) if force_id_collision else patch('builtins.print')
    with context:
        f=ResearchIngestionTests();f.setUp()
        try:
            f.source_row_label('Free cash flow to firm')
            payload=copy.deepcopy(f.payload)
            payload['tables'][0]['rows'][0]['attributes'].update(metric='free_cash_flow_firm',label='Free cash flow to firm')
            f.commit(payload=payload)
            result=f.s.query_research_records('p',{'query':'FCFF','record_type':'observation'})['data']
            return {'forced_uuid_collision':force_id_collision,'total':result['total'],
                    'metrics':[r['metric'] for r in result['items']],
                    'query_terms':result['query_terms']}
        finally:f.tearDown()

print(json.dumps([inspect(False),inspect(True)],ensure_ascii=False))
