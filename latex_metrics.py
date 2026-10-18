"""LaTeX normalization and scoring shared by newEvaluate.py and train_texteller.py.

Both scripts must score predictions the same way, or "baseline" numbers from one
can't be compared with checkpoint numbers from the other.
"""
import re

TOKEN_RE = re.compile(r"\\[a-zA-Z]+|\\.|\S")
# Commands that change spacing or sizing but not the math itself.
NOISE_RE = re.compile(r"\\(?:displaystyle|textstyle|left|right|quad|qquad)(?![a-zA-Z])|\\[,;:! ]")
FRAC_RE = re.compile(r"\\[dt]frac(?![a-zA-Z])")
DELIMITERS = (("$$", "$$"), ("\\[", "\\]"), ("\\(", "\\)"), ("$", "$"))


def strip_delims(s: str) -> str:
    """Remove one pair of surrounding math delimiters, e.g. \\[ ... \\] or $ ... $."""
    s = s.strip()
    for left, right in DELIMITERS:
        if s.startswith(left) and s.endswith(right) and len(s) > len(left) + len(right):
            return s[len(left):-len(right)].strip()
    return s


def normalize(s: str) -> str:
    return FRAC_RE.sub(r"\\frac", NOISE_RE.sub(" ", strip_delims(s)))


def tokens(s: str) -> list[str]:
    """Normalized LaTeX tokens: \\commands, escaped characters, and single characters."""
    return TOKEN_RE.findall(normalize(s))


def edit_distance(a: list, b: list) -> int:
    """Levenshtein distance between two token lists."""
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]
