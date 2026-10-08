"""Describe dimension roles from source identity; never erase business slices."""
from collections import defaultdict
from decimal import Decimal
from .standard_metrics import exact_standard_metric, workpaper_concepts


def metadata(record):
    return record.get('source_ref', record.get('source', {})).get('normalization', {})


def classify_dimensions(table, facts, context=None):
    from .metric_context import source_metric_context
    from .metric_normalization import source_metric
    groups = defaultdict(list)
    for fact in facts:
        n = metadata(fact)
        key = tuple(fact.get(k) for k in ('company', 'scope', 'metric', 'period', 'currency')) + (n.get('restatement', 'unspecified'),)
        groups[key].append(fact)
    for group in groups.values():
        values = {Decimal(str(f['value'])) for f in group if f['value'] is not None}
        for fact in group:
            n = metadata(fact); dims = n.get('dimensions', {})
            if not dims:
                continue
            roles = {}
            if dims.get('version') in {'original', 'restated'} and dims['version'] == n.get('restatement'):
                roles['version'] = 'comparison_version'
            if 'financial_item' in dims:
                row = fact['source']['row']
                label = table['rows'][row - 1][0]
                semantic_context = source_metric_context(table, row, context)
                metric, evidence = source_metric(table, fact, context)
                same = metric == fact['metric'] or bool(set(workpaper_concepts(metric)) & set(workpaper_concepts(fact['metric'])))
                item = dims['financial_item']
                item_metric = exact_standard_metric(item, context=semantic_context) or item
                matches_item = item_metric == metric or bool(set(workpaper_concepts(item_metric)) & set(workpaper_concepts(metric)))
                if metric and same and matches_item and len(values) == 1:
                    roles['financial_item'] = 'descriptive'
            if roles:
                n['dimension_roles'] = roles
            else:
                n.pop('dimension_roles', None)


def dimensions_ok(record):
    n = metadata(record)
    dims = record.get('dimensions') or n.get('dimensions', {})
    roles = n.get('dimension_roles', {})
    return all(key == 'source_table' or roles.get(key) in {'descriptive', 'comparison_version'} for key in dims)


def preferred_version(records):
    restated = [r for r in records if metadata(r).get('restatement') in ('restated', 'adjusted')]
    return restated or records
