"""Read-only project research inventory. No model calls or new ingestion path."""
from __future__ import annotations
import json
from .research_ingestion import envelope, norm


class AssetDashboardMixin:
    def get_asset_catalog(self, project_id, entity_key=None):
        self.store.project(project_id)
        current = " FROM research_records r LEFT JOIN document_profiles p USING(document_id) WHERE r.project_id=? AND r.is_current=1 AND (r.profile_revision IS NULL OR r.profile_revision=p.revision_id)"
        with self.store.connect() as db:
            # One SQLite snapshot keeps cards and facet counts consistent with a batch commit.
            db.execute('BEGIN')
            fact_groups = [dict(row) for row in db.execute(
                'SELECT company,count(*) count FROM current_financial_facts WHERE project_id=? GROUP BY company', (project_id,))]
            research_groups = [dict(row) for row in db.execute(
                'SELECT r.entity_id,r.record_type,r.data_kind,count(*) count'+current+' GROUP BY r.entity_id,r.record_type,r.data_kind', (project_id,))]
            entities = []
            for row in db.execute("""SELECT e.* FROM research_entities e WHERE e.project_id=? AND
                (EXISTS(SELECT 1 FROM research_document_entities de JOIN document_profiles dp
                ON dp.document_id=de.document_id AND dp.revision_id=de.profile_revision WHERE de.entity_id=e.entity_id)
                OR EXISTS(SELECT 1 FROM research_records r LEFT JOIN document_profiles p USING(document_id)
                WHERE r.entity_id=e.entity_id AND r.is_current=1 AND (r.profile_revision IS NULL OR r.profile_revision=p.revision_id)))
                ORDER BY e.kind,e.name""", (project_id,)):
                item = dict(row)
                aliases = json.loads(item['aliases_json'])
                names = {norm(value) for value in [item['name'], *aliases]}
                entities.append({'key': item['entity_id'], 'entity_id': item['entity_id'], 'kind': item['kind'],
                    'name': item['name'], 'aliases': aliases, 'identifiers': json.loads(item['identifiers_json']),
                    'companies': [f['company'] for f in fact_groups if norm(f['company']) in names]})
            mapped = {name for e in entities for name in e['companies']}
            for f in fact_groups:
                if f['company'] not in mapped:
                    entities.append({'key': 'company:'+f['company'], 'kind': 'company', 'name': f['company'],
                                     'aliases': [], 'identifiers': {}, 'companies': [f['company']]})
            for entity in entities:
                groups = [r for r in research_groups if r['entity_id'] == entity.get('entity_id')]
                entity['facts'] = sum(f['count'] for f in fact_groups if f['company'] in entity['companies'])
                entity['records'] = sum(r['count'] for r in groups)
                entity['forecasts'] = sum(r['count'] for r in groups if r['record_type']=='observation' and r['data_kind'] in ('analyst_forecast','company_guidance'))
                entity['claims'] = sum(r['count'] for r in groups if r['record_type']=='claim')
            selected = next((e for e in entities if e['key']==entity_key), None)
            if entity_key and selected is None:
                raise ValueError('asset_entity_not_found')
            record_where, record_args = current, [project_id]
            fact_where, fact_args = ' FROM current_financial_facts WHERE project_id=?', [project_id]
            if selected:
                record_where += ' AND r.entity_id=?'
                record_args.append(selected.get('entity_id', ''))
                fact_where += ' AND company IN ('+','.join('?' for _ in selected['companies'])+')' if selected['companies'] else ' AND 0'
                fact_args.extend(selected['companies'])
            records_by_kind = [dict(r) for r in db.execute('SELECT r.record_type,r.data_kind,count(*) count'+record_where+' GROUP BY r.record_type,r.data_kind', record_args)]
            metrics = [dict(r) for r in db.execute("SELECT r.metric,COALESCE(json_extract(r.record_json,'$.label'),r.metric) label,count(*) count"+record_where+" AND r.record_type='observation' GROUP BY r.metric,label ORDER BY label", record_args)]
            publishers = [r[0] for r in db.execute('SELECT DISTINCT r.publisher'+record_where+' AND r.publisher IS NOT NULL ORDER BY r.publisher', record_args)]
            periods = [r[0] for r in db.execute('SELECT DISTINCT r.period'+record_where+' AND r.period IS NOT NULL ORDER BY r.period', record_args)]
            selected_docs = {r[0] for r in db.execute('SELECT DISTINCT document_id'+fact_where, fact_args)}
            selected_docs.update(r[0] for r in db.execute('SELECT DISTINCT r.document_id'+record_where, record_args))
            documents = []
            for row in db.execute('SELECT d.*,p.profile_json FROM documents d LEFT JOIN document_profiles p USING(document_id) WHERE d.project_id=? ORDER BY d.created_at DESC', (project_id,)):
                doc = dict(row)
                profile = json.loads(doc['profile_json']) if doc['profile_json'] else {}
                entity_ids = [r[0] for r in db.execute('SELECT de.entity_id FROM research_document_entities de JOIN document_profiles p ON p.document_id=de.document_id AND p.revision_id=de.profile_revision WHERE de.document_id=?', (doc['document_id'],))]
                if selected and doc['document_id'] not in selected_docs and selected.get('entity_id') not in entity_ids:
                    continue
                documents.append({'document_id': doc['document_id'], 'name': doc['original_name'], 'state': doc['state'],
                    'page_count': doc['page_count'], 'kind': profile.get('kind', 'unclassified'),
                    'title': profile.get('title') or doc['original_name'], 'publisher': profile.get('publisher'),
                    'published_at': profile.get('published_at'), 'authors': profile.get('authors', []), 'entity_ids': entity_ids})
            count = lambda kinds, record_type: sum(r['count'] for r in records_by_kind if r['record_type']==record_type and (kinds is None or r['data_kind'] in kinds))
            summary = {'documents': len(documents), 'facts': db.execute('SELECT count(*)'+fact_where, fact_args).fetchone()[0],
                'records': sum(r['count'] for r in records_by_kind), 'claims': count(None, 'claim'),
                'forecasts': count({'analyst_forecast','company_guidance'}, 'observation'),
                'observations': count(None, 'observation'),
                'needs_review': db.execute("SELECT count(*)"+record_where+" AND json_extract(r.record_json,'$.quality')='needs_review'", record_args).fetchone()[0]}
        return envelope({'entities': entities, 'selected': selected, 'summary': summary, 'documents': documents,
                         'metrics': metrics, 'publishers': publishers, 'periods': periods, 'record_kinds': records_by_kind})
