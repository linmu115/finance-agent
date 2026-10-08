"""Trusted MCP run scope. No key means the existing project-wide product view."""
from contextvars import ContextVar

isolation_key = ContextVar('evaluation_isolation_key', default=None)
evaluation_profile = ContextVar('evaluation_profile', default=None)
analysis_only = ContextVar('evaluation_analysis_only', default=False)


def original_pi():
    return evaluation_profile.get() == 'original_pi'


def raw_source(ref):
    return not any(ref.get(key) is not None for key in ('research_record_id','fact_id','record_id','normalization','data_kind'))


def raw_source_clause(alias=''):
    prefix = alias + '.' if alias else ''
    return ''.join(f" AND json_extract({prefix}source_json,'$.{key}') IS NULL"
                   for key in ('research_record_id','fact_id','record_id','normalization','data_kind'))


def visible(value):
    key = isolation_key.get()
    return key is None or value.get('isolation_key') == key


def stamp(value):
    # Caller content cannot choose ownership. Unscoped writes remain ordinary assets.
    value = {k:v for k,v in value.items() if k != 'isolation_key'}
    key = isolation_key.get()
    return {**value, 'isolation_key':key} if key is not None else value
