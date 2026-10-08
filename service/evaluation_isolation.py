"""Trusted MCP run scope. No key means the existing project-wide product view."""
from contextvars import ContextVar

isolation_key = ContextVar('evaluation_isolation_key', default=None)


def visible(value):
    key = isolation_key.get()
    return key is None or value.get('isolation_key') == key


def stamp(value):
    # Caller content cannot choose ownership. Unscoped writes remain ordinary assets.
    value = {k:v for k,v in value.items() if k != 'isolation_key'}
    key = isolation_key.get()
    return {**value, 'isolation_key':key} if key is not None else value
