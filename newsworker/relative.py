"""Relative publication dates ("3 hours ago", "вчера в 14:30") in eight languages.

Listing pages often print recent items relative to now. Each language contributes
words for now/today/yesterday and an "N <unit> ago" phrase with its unit names;
an optional clock time after today/yesterday is honoured.
"""

from __future__ import annotations

import datetime as dt
import re
from re import Pattern
from zoneinfo import ZoneInfo

MINUTE, HOUR, DAY, WEEK = 60, 3600, 86400, 604800
MONTH, YEAR = 30 * DAY, 365 * DAY

# unit word (lower-case, accents kept) -> seconds
_UNITS: dict[str, dict[str, int]] = {
    "en": {
        "second": 1,
        "seconds": 1,
        "sec": 1,
        "secs": 1,
        "minute": MINUTE,
        "minutes": MINUTE,
        "min": MINUTE,
        "mins": MINUTE,
        "hour": HOUR,
        "hours": HOUR,
        "hr": HOUR,
        "hrs": HOUR,
        "day": DAY,
        "days": DAY,
        "week": WEEK,
        "weeks": WEEK,
        "month": MONTH,
        "months": MONTH,
        "year": YEAR,
        "years": YEAR,
    },
    "ru": {
        "секунду": 1,
        "секунды": 1,
        "секунд": 1,
        "сек": 1,
        "минуту": MINUTE,
        "минуты": MINUTE,
        "минут": MINUTE,
        "мин": MINUTE,
        "час": HOUR,
        "часа": HOUR,
        "часов": HOUR,
        "ч": HOUR,
        "день": DAY,
        "дня": DAY,
        "дней": DAY,
        "неделю": WEEK,
        "недели": WEEK,
        "недель": WEEK,
        "месяц": MONTH,
        "месяца": MONTH,
        "месяцев": MONTH,
        "год": YEAR,
        "года": YEAR,
        "лет": YEAR,
    },
    "uk": {
        "секунду": 1,
        "секунди": 1,
        "секунд": 1,
        "хвилину": MINUTE,
        "хвилини": MINUTE,
        "хвилин": MINUTE,
        "хв": MINUTE,
        "годину": HOUR,
        "години": HOUR,
        "годин": HOUR,
        "день": DAY,
        "дні": DAY,
        "днів": DAY,
        "тиждень": WEEK,
        "тижні": WEEK,
        "тижнів": WEEK,
        "місяць": MONTH,
        "місяці": MONTH,
        "місяців": MONTH,
        "рік": YEAR,
        "роки": YEAR,
        "років": YEAR,
    },
    "de": {
        "sekunde": 1,
        "sekunden": 1,
        "minute": MINUTE,
        "minuten": MINUTE,
        "min": MINUTE,
        "stunde": HOUR,
        "stunden": HOUR,
        "std": HOUR,
        "tag": DAY,
        "tagen": DAY,
        "woche": WEEK,
        "wochen": WEEK,
        "monat": MONTH,
        "monaten": MONTH,
        "jahr": YEAR,
        "jahren": YEAR,
    },
    "fr": {
        "seconde": 1,
        "secondes": 1,
        "minute": MINUTE,
        "minutes": MINUTE,
        "min": MINUTE,
        "heure": HOUR,
        "heures": HOUR,
        "h": HOUR,
        "jour": DAY,
        "jours": DAY,
        "semaine": WEEK,
        "semaines": WEEK,
        "mois": MONTH,
        "an": YEAR,
        "ans": YEAR,
        "année": YEAR,
        "années": YEAR,
    },
    "es": {
        "segundo": 1,
        "segundos": 1,
        "minuto": MINUTE,
        "minutos": MINUTE,
        "min": MINUTE,
        "hora": HOUR,
        "horas": HOUR,
        "día": DAY,
        "días": DAY,
        "dia": DAY,
        "dias": DAY,
        "semana": WEEK,
        "semanas": WEEK,
        "mes": MONTH,
        "meses": MONTH,
        "año": YEAR,
        "años": YEAR,
    },
    "it": {
        "secondo": 1,
        "secondi": 1,
        "minuto": MINUTE,
        "minuti": MINUTE,
        "min": MINUTE,
        "ora": HOUR,
        "ore": HOUR,
        "giorno": DAY,
        "giorni": DAY,
        "settimana": WEEK,
        "settimane": WEEK,
        "mese": MONTH,
        "mesi": MONTH,
        "anno": YEAR,
        "anni": YEAR,
    },
    "pt": {
        "segundo": 1,
        "segundos": 1,
        "minuto": MINUTE,
        "minutos": MINUTE,
        "min": MINUTE,
        "hora": HOUR,
        "horas": HOUR,
        "dia": DAY,
        "dias": DAY,
        "semana": WEEK,
        "semanas": WEEK,
        "mês": MONTH,
        "mes": MONTH,
        "meses": MONTH,
        "ano": YEAR,
        "anos": YEAR,
    },
}

# Phrase shapes: (prefix, suffix) around "<number> <unit>".
_AGO_SHAPES: dict[str, list[tuple[str, str]]] = {
    "en": [("", r"ago")],
    "ru": [("", r"назад")],
    "uk": [("", r"тому")],
    "de": [(r"vor", "")],
    "fr": [(r"il y a", "")],
    "es": [(r"hace", "")],
    "it": [("", r"fa")],
    "pt": [(r"há", ""), ("", r"atrás")],
}

# day offset keywords: word -> days before today (0 = today / now)
_DAY_WORDS: dict[str, int] = {
    # en
    "just now": 0,
    "now": 0,
    "moments ago": 0,
    "a moment ago": 0,
    "today": 0,
    "yesterday": 1,
    # ru
    "только что": 0,
    "сегодня": 0,
    "вчера": 1,
    "позавчера": 2,
    # uk
    "щойно": 0,
    "сьогодні": 0,
    "вчора": 1,
    "учора": 1,
    "позавчора": 2,
    # de
    "gerade eben": 0,
    "soeben": 0,
    "heute": 0,
    "gestern": 1,
    "vorgestern": 2,
    # fr
    "à l'instant": 0,
    "à l’instant": 0,
    "aujourd'hui": 0,
    "aujourd’hui": 0,
    "hier": 1,
    "avant-hier": 2,
    # es
    "ahora mismo": 0,
    "hoy": 0,
    "ayer": 1,
    "anteayer": 2,
    # it
    "proprio ora": 0,
    "adesso": 0,
    "oggi": 0,
    "ieri": 1,
    "l'altro ieri": 2,
    # pt
    "agora mesmo": 0,
    "hoje": 0,
    "ontem": 1,
    "anteontem": 2,
}

# Words that stand in for "1" ("an hour ago", "una hora", "год назад" = 1 year).
_ONE = r"a|an|one|un|une|una|uno|um|uma|ein|eine|einem|einer"

_TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3])[:.h]([0-5]\d)(?!\d)")
_EDGE_PUNCT = " \t\r\n.,;:-–—()[]«»\"'|·•"


def _build_ago_patterns() -> list[tuple[Pattern[str], dict[str, int]]]:
    patterns = []
    for lang, shapes in _AGO_SHAPES.items():
        units = _UNITS[lang]
        unit_alt = "|".join(sorted((re.escape(u) for u in units), key=len, reverse=True))
        for prefix, suffix in shapes:
            body = rf"(?P<n>\d+|{_ONE})?\s*(?P<unit>{unit_alt})\.?"
            text = (rf"{prefix}\s+" if prefix else "") + body + (rf"\s+{suffix}" if suffix else "")
            patterns.append((re.compile(rf"(?<!\w){text}(?!\w)", re.IGNORECASE), units))
    return patterns


_AGO_PATTERNS = _build_ago_patterns()
_DAY_WORD_RE = re.compile(
    r"^(?P<word>"
    + "|".join(sorted((re.escape(w) for w in _DAY_WORDS), key=len, reverse=True))
    + r")(?!\w)",
    re.IGNORECASE,
)
_KEYWORDS = tuple(_DAY_WORDS) + tuple(
    word for shapes in _AGO_SHAPES.values() for pair in shapes for word in pair if word
)


def looks_relative(text: str | None) -> bool:
    """Cheap pre-filter: does ``text`` contain a relative-date keyword?"""
    if not text:
        return False
    low = text.lower()
    return any(keyword in low for keyword in _KEYWORDS)


def parse_relative(
    text: str | None, now: dt.datetime | None = None, default_timezone: str = "UTC"
) -> dt.datetime | None:
    """Resolve a relative date expression to an aware datetime, or ``None``."""
    if not text:
        return None
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)
    cleaned = " ".join(text.split()).strip(_EDGE_PUNCT)
    low = cleaned.lower()
    for pattern, units in _AGO_PATTERNS:
        match = pattern.search(low)
        if match is None:
            continue
        raw = match.group("n")
        amount = int(raw) if raw and raw.isdigit() else 1
        seconds = units.get(match.group("unit").lower().rstrip("."))
        if seconds is None:
            continue
        return now - dt.timedelta(seconds=amount * seconds)
    match = _DAY_WORD_RE.match(low)
    if match is None:
        return None
    rest = low[match.end() :]
    days = _DAY_WORDS[match.group("word")]
    clock = _TIME_RE.search(rest)
    # The rest may carry a clock time ("вчера в 14:30") but nothing else of
    # substance; "today's agenda" is not a date.
    leftover = _TIME_RE.sub("", rest)
    if re.search(r"[^\W\d_]{4,}", leftover):
        return None
    if clock is None:
        # Same clock time N days back keeps the calendar date right in the
        # site's timezone and orders items as before.
        return now - dt.timedelta(days=days)
    zone = ZoneInfo(default_timezone)
    local_now = now.astimezone(zone)
    day = local_now.date() - dt.timedelta(days=days)
    hour, minute = int(clock.group(1)), int(clock.group(2))
    return dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone).astimezone(
        dt.timezone.utc
    )
