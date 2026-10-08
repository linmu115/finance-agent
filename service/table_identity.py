"""Table aliases remain confined to the explicitly selected document."""
import re


def table_index(value, document_id=None):
    text=str(value).strip()
    if document_id and text.startswith(document_id+':'):text=text[len(document_id)+1:]
    match=re.fullmatch(r'[tT]?(\d+)',text)
    return int(match[1]) if match else None


def table_id(value, document_id):
    index=table_index(value,document_id)
    return f'{document_id}:t{index}' if index is not None else str(value)
