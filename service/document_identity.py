"""Source candidates for names and identifiers; no entity inference or rewriting."""
import re


def candidates(parsed):
    names, identifiers = [], []
    seen = set()
    for page in parsed['pages']:
        lines = [(m.group().strip(), m.start()) for m in re.finditer(r'[^\r\n]+', page['text']) if m.group().strip()]
        for line, start in lines:
            # Covers title, definitions and running headers. Return exact source
            # strings, including PDF word spacing, for directly usable evidence.
            match = re.search(r'([\u4e00-\u9fffA-Za-z（）()·]{2,80}(?:股份有限公司|有限责任公司|有限公司))', line)
            english = re.search(r'\b[A-Z][A-Za-z &.,()-]*(?:LIMITED|Limited|LTD\.?|Ltd\.?)\b', line)
            for found in (match, english):
                if not found: continue
                name = found.group(1) if found.lastindex else found.group()
                if name in seen: continue
                seen.add(name)
                names.append({'name': name, 'kind': 'company', 'aliases': [], 'identifiers': {}, 'evidence': {'page': page['page'], 'quote': name}})
            code = re.search(r'(?:stock\s*code|股份代[号號]|股[票份]代[码碼]|证券代码|證券代碼|股票代号)\s*[:：]?\s*(\d{4,6})', line, re.I)
            if code:
                value = {'ticker': code[1], 'evidence': {'page': page['page'], 'quote': code.group()}}
                if value not in identifiers: identifiers.append(value)
    return {'names': names, 'identifiers': identifiers,
            'instruction': 'Use exact names/quotes. Name and ticker may cite separate evidence entries. Exchange abbreviations not present in the source must be omitted, not inferred from a ticker.'}


class ProfileEvidenceError(ValueError):
    def __init__(self, code, parsed):
        super().__init__(code)
        self.details = {'candidates': candidates(parsed), 'instruction': 'Evidence may be {page,quote} or a list of such entries covering name, each alias and identifier. Omit unknown fields; do not quote an explanation for a null field.'}
