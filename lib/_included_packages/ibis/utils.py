# coding=utf-8

import ast
import re
import keyword


# Splits a string on instances of a delimiter character. Ignores quoted delimiters.
def splitc(s, delimiter, strip=False, discard_empty=False, maxsplit=-1):

    tokens, buf, expecting, escaped = [], [], None, False

    for index, char in enumerate(s):
        if expecting:
            buf.append(char)
            if char == expecting and not escaped:
                expecting = None
        else:
            if char == delimiter:
                tokens.append(''.join(buf))
                buf = []
                if len(tokens) == maxsplit:
                    buf.append(s[index+1:])
                    break
            else:
                buf.append(char)
                if char in ('"', "'"):
                    expecting = char
        escaped = not escaped if char == '\\' else False

    tokens.append(''.join(buf))

    if strip:
        tokens = [t.strip() for t in tokens]

    if discard_empty:
        tokens = [t for t in tokens if t]

    return tokens


# Splits a string on blocks of whitespace. Strips leading and trailing whitespace.
# Ignores quoted whitespace.
def splitws(s, maxsplit=-1):
    tokens, buf, expecting, escaped, wsrun = [], [], None, False, False

    for index, char in enumerate(s.strip()):
        if expecting:
            buf.append(char)
            if char == expecting and not escaped:
                expecting = None
        else:
            if char.isspace():
                if wsrun:
                    continue
                tokens.append(''.join(buf))
                buf = []
                wsrun = True
                if len(tokens) == maxsplit:
                    buf.append(s[index+1:].lstrip())
                    break
            else:
                buf.append(char)
                wsrun = False
                if char in ('"', "'"):
                    expecting = char
        escaped = not escaped if char == '\\' else False

    tokens.append(''.join(buf))
    return tokens


# Splits a string using a list of regular expression patterns. Ignores quoted delimiter matches.
def splitre(s, delimiters, keep_delimiters=False):
    tokens, buf = [], []
    end_last_match = 0

    pattern = r'''"(?:[^\\"]|\\.)*"|'(?:[^\\']|\\.)*'|%s'''
    pattern %= '|'.join(delimiters)

    for match in re.finditer(pattern, s):
        if match.group()[0] in ["'", '"']:
            buf.append(s[end_last_match:match.end()])
            end_last_match = match.end()
            continue
        buf.append(s[end_last_match:match.start()])
        tokens.append(''.join(buf))
        buf = []
        end_last_match = match.end()
        if keep_delimiters:
            tokens.append(match.group())

    buf.append(s[end_last_match:])
    tokens.append(''.join(buf))

    return tokens


ISIDENTIFIER_RE = re.compile(r'^[a-z_][a-z0-9_]*$', re.I)


def isidentifier(s):
    try:
        return s.isidentifier()
    except AttributeError:
        if s in keyword.kwlist:
            return False
        return ISIDENTIFIER_RE.match(s) is not None


try:
    # Python 3.8+ uses ast.Constant for all literal values
    Constant = ast.Constant
except AttributeError:
    # Python 2.7-3.7 use separate types for different literals
    # Create a tuple so isinstance() works with multiple types
    _constant_types = [ast.Num]
    if hasattr(ast, 'Str'):
        _constant_types.append(ast.Str)
    if hasattr(ast, 'Bytes'):
        _constant_types.append(ast.Bytes)
    if hasattr(ast, 'NameConstant'):  # True, False, None in Python 3.0-3.7
        _constant_types.append(ast.NameConstant)
    Constant = tuple(_constant_types)
