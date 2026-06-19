from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

import pandas as pd


TERM_LABELS = {
    "SP": "Spring",
    "SU": "Summer",
    "FA": "Fall",
    "SP1": "Spring 1",
    "SP2": "Spring 2",
    "SU1": "Summer 1",
    "SU2": "Summer 2",
    "FA1": "Fall 1",
    "FA2": "Fall 2",
}

TERM_ORDER = {
    "SP": 10,
    "SP1": 11,
    "SP2": 12,
    "SU": 20,
    "SU1": 21,
    "SU2": 22,
    "FA": 30,
    "FA1": 31,
    "FA2": 32,
}


@dataclass(frozen=True)
class ParsedTermMetric:
    term_code: str
    term_label: str
    metric: str
    raw_header: str
    sort_order: int


def clean_token(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).replace("\xa0", " ").strip().upper()
    return re.sub(r"[^A-Z0-9]", "", text)


def parse_term_metric_header(value: object) -> ParsedTermMetric | None:
    token = clean_token(value)
    if not token:
        return None
    match = re.match(r"^(SP|SU|FA)([12]?)([AG])$", token)
    if not match:
        return None
    season, number, metric = match.groups()
    term_code = f"{season}{number}" if number else season
    return ParsedTermMetric(
        term_code=term_code,
        term_label=TERM_LABELS.get(term_code, term_code),
        metric="actual" if metric == "A" else "goal",
        raw_header=str(value).strip(),
        sort_order=TERM_ORDER.get(term_code, 999),
    )


def normalize_term_value(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).replace("\xa0", " ").strip()
    token = clean_token(text)
    if token in TERM_LABELS:
        return TERM_LABELS[token]
    for code, label in TERM_LABELS.items():
        if token.startswith(code) and code in ("SP1", "SP2", "SU1", "SU2", "FA1", "FA2"):
            return label
    lowered = text.lower()
    for code, label in sorted(TERM_LABELS.items(), key=lambda item: len(item[1]), reverse=True):
        if label.lower() in lowered:
            return label
    date_value = pd.to_datetime(value, errors="coerce")
    if pd.notna(date_value):
        month = int(date_value.month)
        if month <= 4:
            return "Spring"
        if month <= 8:
            return "Summer"
        return "Fall"
    return text


def term_code_from_label(label: object) -> str:
    normalized = normalize_term_value(label)
    for code, term_label in TERM_LABELS.items():
        if normalized == term_label:
            return code
    return clean_token(label)


def sorted_terms(values: Iterable[object]) -> list[str]:
    labels = {normalize_term_value(value) for value in values if normalize_term_value(value)}

    def key(label: str) -> tuple[int, str]:
        code = term_code_from_label(label)
        return TERM_ORDER.get(code, 999), label

    return sorted(labels, key=key)
