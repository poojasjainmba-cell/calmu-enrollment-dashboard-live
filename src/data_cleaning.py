from __future__ import annotations

import re
from typing import Iterable

import pandas as pd

from .source_mapping import add_source_fields
from .term_mapping import normalize_term_value


BAD_LEAD_STATUSES = {
    "dead lead",
    "do not contact",
    "duplicate lead",
    "app submitted - unqualified",
}

CONTACTED_STATUSES = {
    "outreach attempt 1",
    "outreach attempt 2",
    "outreach attempt 3",
    "outreach attempt 4",
    "responded",
    "warm lead",
    "hot lead",
    "cold lead",
    "qualified meeting set",
    "interviewed - app ready",
    "interviewed - not ready",
    "app submitted - qualified",
    "app submitted - unqualified",
    "future applicant",
    "enrolled",
}

COLUMN_ALIASES = {
    "record_id": ["record id", "hs_object_id", "object id", "vid", "id"],
    "first_name": ["first name", "firstname"],
    "last_name": ["last name", "lastname"],
    "email": ["email", "email address"],
    "phone": ["phone number", "phone", "mobile phone number"],
    "lead_status": ["lead status", "hs_lead_status"],
    "lifecycle_stage": ["lifecycle stage", "lifecyclestage"],
    "udr": ["contact owner", "hubspot owner id", "owner", "udr"],
    "last_activity_date": [
        "last activity date",
        "hs_last_activity_date",
        "notes last updated",
        "notes_last_updated",
        "hs_last_sales_activity_date",
    ],
    "marketing_contact_status": ["marketing contact status", "hs_marketable_status"],
    "create_date": ["create date", "createdate", "created at"],
    "student_type": ["student type", "student_type"],
    "degree": ["degree", "program", "academic program"],
    "athletics": ["athletics"],
    "paid_lead_list": ["paid lead list", "paid_lead_list"],
    "organic_lead_list": ["organic lead list", "organic_lead_list"],
    "event_attended": ["event attended", "event_attended"],
    "campus_location": ["campus location", "campus_location"],
    "source": ["source", "lead source", "original source", "hs_analytics_source"],
    "original_source": ["original source", "hs_analytics_source"],
    "latest_source": ["latest source", "hs_latest_source"],
    "utm_source": ["utm source", "utm_source"],
    "utm_medium": ["utm medium", "utm_medium"],
    "utm_campaign": ["utm campaign", "utm_campaign"],
    "campaign": ["campaign", "campaign name"],
    "term": ["term", "start term", "enrollment term"],
    "enrollment_status": ["enrollment status", "actual enrollment", "enrolled status"],
    "enrolled_date": ["enrolled date", "enrollment date", "actual enrolled date"],
    "start_status": ["start status", "started status"],
    "start_date": ["start date", "actual start date"],
    "revenue": ["revenue", "rev", "tuition revenue", "amount"],
    "days_to_enroll": ["days to enroll", "days_to_enroll"],
}


def slugify_column(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\xa0", " ").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def normalize_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def lower_text(value: object) -> str:
    return normalize_text(value).lower()


def canonicalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    clean = df.copy()
    clean.columns = [slugify_column(column) for column in clean.columns]
    clean = clean.loc[:, [column for column in clean.columns if column]]
    return clean


def _alias_lookup(columns: Iterable[str]) -> dict[str, str]:
    by_slug = {slugify_column(column): column for column in columns}
    lookup: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            slug = slugify_column(alias)
            if slug in by_slug:
                lookup[canonical] = by_slug[slug]
                break
    return lookup


def coalesce_aliases(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=list(COLUMN_ALIASES.keys()))
    clean = canonicalize_columns(df)
    lookup = _alias_lookup(clean.columns)
    output = pd.DataFrame(index=clean.index)
    for canonical in COLUMN_ALIASES:
        source = lookup.get(canonical)
        output[canonical] = clean[source] if source else pd.NA
    passthrough = [column for column in clean.columns if column not in set(lookup.values())]
    for column in passthrough:
        output[column] = clean[column]
    return output


def normalize_udr(value: object) -> str:
    text = normalize_text(value)
    if not text:
        return "Unassigned"
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_udr_key(value: object) -> str:
    text = normalize_udr(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return text


def normalize_contacts(df: pd.DataFrame, source_system: str = "HubSpot") -> pd.DataFrame:
    contacts = coalesce_aliases(df)
    if contacts.empty:
        return contacts

    text_columns = [
        "record_id",
        "first_name",
        "last_name",
        "email",
        "lead_status",
        "lifecycle_stage",
        "udr",
        "marketing_contact_status",
        "student_type",
        "degree",
        "athletics",
        "paid_lead_list",
        "organic_lead_list",
        "event_attended",
        "campus_location",
        "source",
        "original_source",
        "latest_source",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "campaign",
        "term",
        "enrollment_status",
        "start_status",
    ]
    for column in text_columns:
        if column in contacts:
            contacts[column] = contacts[column].map(normalize_text)

    contacts["email"] = contacts["email"].str.lower()
    contacts["udr"] = contacts["udr"].map(normalize_udr)
    contacts["program"] = contacts["degree"].map(normalize_text)
    contacts["term_label"] = contacts["term"].map(normalize_term_value)

    date_columns = ["last_activity_date", "create_date", "enrolled_date", "start_date"]
    for column in date_columns:
        contacts[column] = pd.to_datetime(contacts[column], errors="coerce", utc=True).dt.tz_convert(None)

    numeric_columns = ["revenue", "days_to_enroll"]
    for column in numeric_columns:
        contacts[column] = pd.to_numeric(contacts[column], errors="coerce")

    contacts["source_system"] = source_system
    contacts = add_source_fields(contacts)
    contacts = add_contact_flags(contacts)
    contacts = dedupe_contacts(contacts)
    return contacts.reset_index(drop=True)


def add_contact_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    lifecycle = out["lifecycle_stage"].map(lower_text)
    lead_status = out["lead_status"].map(lower_text)
    enrollment_status = out["enrollment_status"].map(lower_text)
    start_status = out["start_status"].map(lower_text)

    out["is_applicant"] = lifecycle.eq("applicant")
    out["is_crm_enrolled"] = lifecycle.eq("enrolled")
    out["is_bad_lead"] = lifecycle.eq("not a lead") | lead_status.isin(BAD_LEAD_STATUSES)
    out["is_contacted"] = out["last_activity_date"].notna() | lead_status.isin(CONTACTED_STATUSES)
    out["is_actual_enrolled"] = (
        enrollment_status.str.contains("enroll|active|confirmed", na=False)
        | out["enrolled_date"].notna()
    )
    out["is_started"] = (
        start_status.str.contains("started|active|attended", na=False)
        | out["start_date"].notna()
    )
    out.loc[out["is_bad_lead"], "is_contacted"] = False
    return out


def dedupe_contacts(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["_record_id_key"] = out["record_id"].astype("string").str.strip().replace("", pd.NA)
    out["_email_key"] = out["email"].astype("string").str.lower().str.strip().replace("", pd.NA)
    with_id = out[out["_record_id_key"].notna()].drop_duplicates("_record_id_key", keep="last")
    without_id = out[out["_record_id_key"].isna()]
    combined = pd.concat([with_id, without_id], ignore_index=True)
    with_email = combined[combined["_email_key"].notna()].drop_duplicates("_email_key", keep="last")
    without_email = combined[combined["_email_key"].isna()]
    final = pd.concat([with_email, without_email], ignore_index=True)
    return final.drop(columns=["_record_id_key", "_email_key"], errors="ignore")


def normalize_enrollments(df: pd.DataFrame, source_system: str = "Enrollment tracker") -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    enrollments = canonicalize_columns(df)
    rename = {
        "student": "student",
        "udr": "udr",
        "program": "program",
        "modality": "modality",
        "enrolled_date": "enrolled_date",
        "student_type": "student_type",
        "payment": "payment",
        "new_roll": "new_roll",
        "term": "term",
        "source": "source",
        "days_to_enroll": "days_to_enroll",
        "rev": "revenue",
        "revenue": "revenue",
        "notes": "notes",
    }
    enrollments = enrollments.rename(columns={old: new for old, new in rename.items() if old in enrollments.columns})
    for column in ["student", "udr", "program", "modality", "student_type", "payment", "new_roll", "source", "notes"]:
        if column not in enrollments:
            enrollments[column] = ""
        enrollments[column] = enrollments[column].map(normalize_text)
    if "enrolled_date" in enrollments:
        enrollments["enrolled_date"] = pd.to_datetime(enrollments["enrolled_date"], errors="coerce", utc=True).dt.tz_convert(None)
    else:
        enrollments["enrolled_date"] = pd.NaT
    enrollments["term_label"] = enrollments.get("term", pd.Series(index=enrollments.index)).map(normalize_term_value)
    enrollments["revenue"] = pd.to_numeric(enrollments.get("revenue"), errors="coerce")
    enrollments["days_to_enroll"] = pd.to_numeric(enrollments.get("days_to_enroll"), errors="coerce")
    enrollments["source_system"] = source_system
    normalized_sources = enrollments.apply(
        lambda row: pd.Series(add_source_fields(pd.DataFrame([{"source": row.get("source")}])).iloc[0][["normalized_source", "source_mapping_status", "source_type"]]),
        axis=1,
    )
    enrollments[["normalized_source", "source_mapping_status", "source_type"]] = normalized_sources
    enrollments = enrollments[enrollments["student"].astype(str).str.len().gt(0)]
    return enrollments.reset_index(drop=True)


def mask_email(value: object) -> str:
    email = normalize_text(value)
    if "@" not in email:
        return ""
    name, domain = email.split("@", 1)
    if len(name) <= 2:
        masked = name[:1] + "*"
    else:
        masked = name[:2] + "*" * min(6, max(1, len(name) - 2))
    return f"{masked}@{domain}"
