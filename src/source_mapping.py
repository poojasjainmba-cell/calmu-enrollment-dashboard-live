from __future__ import annotations

import re
from typing import Any

import pandas as pd


KNOWN_SOURCE_ALIASES = {
    "eddie": "Eddie Leads",
    "eddie leads": "Eddie Leads",
    "ebg": "EBG",
    "hiregi": "HireGI",
    "hire gi": "HireGI",
    "kara": "Kara Leads",
    "kara leads": "Kara Leads",
    "karyl": "Karyl Leads",
    "karyl leads": "Karyl Leads",
    "nathen": "Nathen",
    "nathan": "Nathen",
    "referral": "Referral",
    "website": "Website",
    "web": "Website",
    "alumni": "Alumni",
    "event": "Event",
    "archer": "Archer",
    "atra": "ATRA",
    "clearance jobs": "Clearance Jobs",
    "add3": "Add3",
    "agent": "Agent",
}


def _clean(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_source_value(value: Any) -> tuple[str, str]:
    text = _clean(value)
    if not text:
        return "Unmapped", "missing"
    key = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    if key in KNOWN_SOURCE_ALIASES:
        return KNOWN_SOURCE_ALIASES[key], "mapped"
    for alias, canonical in KNOWN_SOURCE_ALIASES.items():
        if alias and alias in key:
            return canonical, "mapped_partial"
    return text, "unmapped"


def source_from_row(row: pd.Series) -> tuple[str, str, str]:
    candidates = [
        "paid_lead_list",
        "organic_lead_list",
        "source",
        "original_source",
        "latest_source",
        "utm_source",
        "campaign",
        "event_attended",
    ]
    for column in candidates:
        value = row.get(column)
        normalized, status = normalize_source_value(value)
        if status != "missing":
            source_type = "Paid" if column == "paid_lead_list" else "Organic" if column == "organic_lead_list" else "Other"
            return normalized, status, source_type
    return "Unmapped", "missing", "Unknown"


def add_source_fields(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        for column in ("normalized_source", "source_mapping_status", "source_type"):
            df[column] = pd.Series(dtype="object")
        return df
    rows = df.apply(source_from_row, axis=1, result_type="expand")
    rows.columns = ["normalized_source", "source_mapping_status", "source_type"]
    return pd.concat([df.reset_index(drop=True), rows.reset_index(drop=True)], axis=1)
