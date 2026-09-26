"""Scope the approved reference workspace CSS under the R4 Studio root.

Relative specificity/ordering is preserved (every selector gets exactly one
extra `.rs-studio` class), so the reference's successive overrides resolve to
the same final computed values inside the Studio and never leak outside it.
"""
import re, sys

ROOT = '.rs-studio'
ID_MAP = {'#app': '.rs-app', '#modal-root': '.rs-modal-root', '#toast': '.rs-toast',
          '#storefront-preview': '#r4PreviewFrame'}
KEYFRAMES = {'spin': 'rs-spin', 'progress': 'rs-progress'}

def split_top(s, sep=','):
    out, depth, cur = [], 0, ''
    for ch in s:
        if ch in '([': depth += 1
        elif ch in ')]': depth -= 1
        if ch == sep and depth == 0:
            out.append(cur); cur = ''
        else:
            cur += ch
    out.append(cur)
    return out

def scope_selector(sel):
    sel = sel.strip()
    if not sel:
        return []
    for k, v in ID_MAP.items():
        sel = re.sub(re.escape(k) + r'(?![\w-])', v, sel)
    if sel in (':root', 'html', 'body'):
        return [ROOT]
    if sel == '*':
        return [ROOT, ROOT + ' *']
    m = re.match(r'^(html|body)(?=[\s.:\[#>~+]|$)(.*)$', sel)
    if m:
        rest = m.group(2)
        return [ROOT + rest] if rest else [ROOT]
    return [ROOT + ' ' + sel]

def scope_block(css):
    out, i, n = [], 0, len(css)
    while i < n:
        j = css.find('{', i)
        if j == -1:
            out.append(css[i:]); break
        head = css[i:j]
        # find matching close
        depth, k = 1, j + 1
        while k < n and depth:
            if css[k] == '{': depth += 1
            elif css[k] == '}': depth -= 1
            k += 1
        body = css[j + 1:k - 1]
        h = head.strip()
        if h.startswith('@media') or h.startswith('@supports'):
            out.append(h + '{' + scope_block(body) + '}')
        elif h.startswith('@keyframes'):
            name = h.split()[1]
            out.append('@keyframes ' + KEYFRAMES.get(name, name) + '{' + body + '}')
        elif h.startswith('@'):
            out.append(h + '{' + body + '}')
        else:
            sels = []
            for s in split_top(h):
                sels.extend(scope_selector(s))
            for old, new in KEYFRAMES.items():
                body = re.sub(r'(animation(?:-name)?\s*:[^;]*?)\b' + old + r'\b', r'\1' + new, body)
            out.append(','.join(dict.fromkeys(sels)) + '{' + body + '}')
        i = k
    return ''.join(out)

css = open(sys.argv[1], encoding='utf-8').read()
css = re.sub(r'/\*[\s\S]*?\*/', '', css)
print(scope_block(css))
