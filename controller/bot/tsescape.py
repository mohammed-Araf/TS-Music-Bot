import re

_TO_ESC = [("\\", "\\\\"), ("/", "\\/"), (" ", "\\s"), ("|", "\\p"),
           ("\a", "\\a"), ("\b", "\\b"), ("\f", "\\f"), ("\n", "\\n"),
           ("\r", "\\r"), ("\t", "\\t"), ("\v", "\\v")]
_FROM_ESC = {"\\": "\\", "/": "/", "s": " ", "p": "|", "a": "\a", "b": "\b",
             "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}

def escape(s: str) -> str:
    for raw, esc in _TO_ESC:          # backslash first, order matters
        s = s.replace(raw, esc)
    return s

def unescape(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s) and s[i + 1] in _FROM_ESC:
            out.append(_FROM_ESC[s[i + 1]]); i += 2
        else:
            out.append(c); i += 1
    return "".join(out)

def parse_line(line: str):
    """'notifytextmessage a=b c=d' -> ('notifytextmessage', {'a': 'b', 'c': 'd'})"""
    parts = line.strip().split(" ")
    name, fields = parts[0], {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            fields[k] = unescape(v)
        else:
            fields[p] = ""
    return name, fields

_BBCODE = re.compile(r"\[/?(?:URL|B|I|U|S|COLOR|SIZE|CODE|QUOTE)(?:=[^\]]*)?\]", re.I)

def strip_bbcode(s: str) -> str:
    return _BBCODE.sub("", s).strip()
