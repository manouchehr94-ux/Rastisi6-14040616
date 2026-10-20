"""RS-09 — ONE Persian-aware search normaliser for product search.

Owner repro: «کتانی رانینگ مسابقه‌ای مشکی-سفید» returned 0 while «… مشکی سفید» returned 1 — a hyphen, a ZWNJ or an
Arabic ي/ك variant must never decide whether a product is found.

Both sides go through the SAME mapping: the query is normalised in Python; the searched text (name + brand + category + SKU)
is normalised *inside the database* with ``Replace`` — so no business data is rewritten and no extra column/migration is
needed. A query is split into tokens (whitespace, hyphens/dashes, slashes and other punctuation separate tokens) and a
product matches when EVERY token occurs in the normalised haystack; the ZWNJ is dropped on both sides so «مسابقه‌ای»,
«مسابقه ای» and «مسابقهای» are the same search. All user input travels as bound parameters (no SQL/ORM injection, LIKE
wildcards are escaped by Django's ``contains``)."""

import re
import unicodedata

from django.db.models import CharField, F, Q, Value
from django.db.models.functions import Coalesce, Concat, Lower, Replace

MAX_QUERY_LENGTH = 120
MAX_TOKENS = 8

#: (from, to) character replacements applied identically to the query and to the DB text.
_CHAR_MAP = (
    ("ي", "ی"), ("ى", "ی"), ("ئ", "ی"), ("ك", "ک"), ("ة", "ه"), ("ۀ", "ه"), ("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ؤ", "و"),
    ("‌", ""), ("‍", ""), ("‎", ""), ("‏", ""), ("ـ", ""),  # ZWNJ, ZWJ, LRM/RLM, tatweel
    ("‐", " "), ("‑", " "), ("‒", " "), ("–", " "), ("—", " "), ("−", " "), ("-", " "), ("_", " "), ("/", " "), ("\\", " "),
    ("،", " "), ("؛", " "), (",", " "), (".", " "), ("(", " "), (")", " "), ("[", " "), ("]", " "), ("«", " "), ("»", " "),
    ("ً", ""), ("ٌ", ""), ("ٍ", ""), ("َ", ""), ("ُ", ""), ("ِ", ""), ("ّ", ""), ("ْ", ""),
    *((p, str(i)) for i, p in enumerate("۰۱۲۳۴۵۶۷۸۹")),
    *((a, str(i)) for i, a in enumerate("٠١٢٣٤٥٦٧٨٩")),
)
_PUNCT_SPLIT = re.compile(r"[\s ]+")


def normalize_search_text(text: str) -> str:
    """Canonical form used for matching (NFKC, the character map above, lower-case, single spaces)."""
    value = unicodedata.normalize("NFKC", str(text or ""))
    for src, dst in _CHAR_MAP:
        value = value.replace(src, dst)
    return " ".join(_PUNCT_SPLIT.split(value.lower())).strip()


def search_tokens(query: str) -> list[str]:
    value = normalize_search_text(str(query or "")[:MAX_QUERY_LENGTH])
    seen, tokens = set(), []
    for token in value.split():
        if token not in seen:
            seen.add(token)
            tokens.append(token)
    return tokens[:MAX_TOKENS]


#: The subset of ``_CHAR_MAP`` that must be applied to the searched TEXT inside the database. Separators and digits are NOT
#: needed there: tokens never contain separators (so they match inside a hyphenated word), and digits are matched through
#: query-side spelling variants (below) — which keeps the SQL expression shallow (SQLite's parser stack is small).
_DB_CHAR_MAP = tuple(
    pair for pair in _CHAR_MAP
    if pair[0] in "يىئكةۀأإآؤ\u200c\u200d\u200e\u200f\u0640"
)

_DIGIT_SPELLINGS = (
    str.maketrans({str(i): c for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")}),
    str.maketrans({str(i): c for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}),
)


def _normalized(expression):
    """``_DB_CHAR_MAP`` expressed as nested ``Replace`` (applied inside the database, never stored)."""
    expr = Lower(expression)
    for src, dst in _DB_CHAR_MAP:
        expr = Replace(expr, Value(src), Value(dst))
    return expr


def _token_spellings(token: str) -> list[str]:
    """A token with digits may be stored with Latin, Persian or Arabic-Indic digits."""
    spellings = [token]
    if any(ch.isdigit() for ch in token):
        for table in _DIGIT_SPELLINGS:
            variant = token.translate(table)
            if variant not in spellings:
                spellings.append(variant)
    return spellings


def annotate_search_fields(queryset, *, fields):
    """One normalised alias per searched field (kept separate: a SINGLE concatenated expression would nest far too deep for
    SQLite's parser). A token may be found in ANY field; every token must be found somewhere."""
    return queryset.annotate(**{
        f"_s_{index}": _normalized(Coalesce(F(field), Value(""), output_field=CharField()))
        for index, field in enumerate(fields)
    })


def apply_text_search(queryset, query: str, *, fields):
    """Filter ANY queryset by ``query`` over the given text ``fields`` (same normaliser, AND of tokens)."""
    tokens = search_tokens(query)
    if not tokens:
        return queryset
    queryset = annotate_search_fields(queryset, fields=fields)
    for token in tokens:
        condition = Q()
        for spelling in _token_spellings(token):
            for index in range(len(fields)):
                condition |= Q(**{f"_s_{index}__contains": spelling})
        queryset = queryset.filter(condition)
    return queryset


def apply_product_search(queryset, query: str, *, fields=("name", "sku", "brand__name", "category__name")):
    """Product search (name + SKU + brand + category); an empty / punctuation-only query leaves it untouched."""
    return apply_text_search(queryset, query, fields=fields)
