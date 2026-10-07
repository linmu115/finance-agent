"""Text edits with Python-token equivalence for whitespace/quote-only differences."""
import ast
import difflib
import io
import tokenize


class AnalysisEditError(ValueError):
    def __init__(self, code, index, matches, candidates=()):
        super().__init__(code)
        self.details = {'edit_index': index, 'matches': matches, 'candidates': list(candidates),
                        'hint': 'Use the returned exact lines with enough surrounding context; replace_all=true replaces every match. To rerun unchanged code, omit edits.'}


def tokens(code):
    lines = code.splitlines(keepends=True); offsets = [0]
    for line in lines: offsets.append(offsets[-1] + len(line))
    result = []
    stream = tokenize.generate_tokens(io.StringIO(code).readline)
    try:
        for item in stream:
            if item.type in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT, tokenize.ENDMARKER): continue
            value = item.string
            if item.type == tokenize.STRING:
                try: value = repr(ast.literal_eval(value))
                except (ValueError, SyntaxError): pass  # f-strings are kept literally.
            result.append(((item.type, value), offsets[item.start[0]-1]+item.start[1], offsets[item.end[0]-1]+item.end[1]))
    except (tokenize.TokenError, IndentationError):
        # An edit fragment can end inside an open bracket. Keep its actual tokens.
        pass
    return result


def apply_edits(code, edits):
    for index, edit in enumerate(edits or [], 1):
        before, after = edit['before'], edit['after']
        spans=[]; pos=0
        while before and (start := code.find(before, pos)) >= 0:
            spans.append((start,start+len(before))); pos=start+len(before)
        if not spans and before:
            haystack=tokens(code); needle=[t[0] for t in tokens(before)]
            if needle:
                spans=[(haystack[i][1],haystack[i+len(needle)-1][2]) for i in range(len(haystack)-len(needle)+1)
                       if [t[0] for t in haystack[i:i+len(needle)]]==needle]
        count=len(spans)
        if not count or count!=1 and not edit.get('replace_all'):
            lines=code.splitlines()
            if spans:
                candidates=[{'line':code[:start].count('\n')+1,'text':code[start:end]} for start,end in spans]
            else:
                near=difflib.get_close_matches(before,lines,n=3,cutoff=.2)
                candidates=[{'line':lines.index(line)+1,'text':line} for line in near]
            error=AnalysisEditError('edit_must_match_once',index,count,candidates)
            if not count: error.details['source_code']=code
            raise error
        if before==after:raise AnalysisEditError('edit_makes_no_change',index,count)
        for start,end in reversed(spans):code=code[:start]+after+code[end:]
    return code
