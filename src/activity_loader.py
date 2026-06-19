from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from .data_cleaning import normalize_udr_key


ACTIVITY_OBJECTS = {
    "calls": {
        "label": "Calls",
        "properties": [
            "hs_timestamp",
            "hubspot_owner_id",
            "hs_call_duration",
            "hs_call_status",
            "hs_call_title",
            "hs_activity_type",
        ],
    },
    "emails": {
        "label": "Emails",
        "properties": ["hs_timestamp", "hubspot_owner_id", "hs_email_status", "hs_email_subject"],
    },
    "meetings": {
        "label": "Meetings",
        "properties": ["hs_timestamp", "hubspot_owner_id", "hs_meeting_title", "hs_meeting_outcome"],
    },
    "tasks": {
        "label": "Tasks",
        "properties": ["hs_timestamp", "hubspot_owner_id", "hs_task_status", "hs_task_subject"],
    },
    "notes": {
        "label": "Notes",
        "properties": ["hs_timestamp", "hubspot_owner_id", "hs_note_body"],
    },
    "communications": {
        "label": "Messages",
        "properties": ["hs_timestamp", "hubspot_owner_id", "hs_communication_channel_type", "hs_communication_body"],
    },
}


@dataclass
class ActivityFetchResult:
    activities: pd.DataFrame
    issues: list[str] = field(default_factory=list)
    fetched_rows: int = 0


def _association_contact_id(item: dict[str, Any]) -> str:
    contacts = (item.get("associations") or {}).get("contacts", {}).get("results", [])
    if not contacts:
        return ""
    return str(contacts[0].get("id") or "")


def _activity_rows(client, object_name: str, config: dict[str, object], max_pages: int | None) -> tuple[list[dict[str, object]], list[str]]:
    rows: list[dict[str, object]] = []
    issues: list[str] = []
    after = None
    pages = 0
    while True:
        params = {
            "limit": 100,
            "archived": "false",
            "properties": ",".join(config["properties"]),
            "associations": "contacts",
        }
        if after:
            params["after"] = after
        try:
            data = client._request("GET", f"/crm/v3/objects/{object_name}", params=params)
        except Exception as exc:
            issues.append(f"{config['label']} unavailable or missing scope: {exc}")
            break
        for item in data.get("results", []):
            props = item.get("properties") or {}
            rows.append(
                {
                    "activity_id": item.get("id"),
                    "activity_object": object_name,
                    "activity_type": config["label"],
                    "activity_timestamp": pd.to_datetime(props.get("hs_timestamp"), errors="coerce", utc=True).tz_convert(None),
                    "activity_owner_id": str(props.get("hubspot_owner_id") or ""),
                    "associated_contact_id": _association_contact_id(item),
                    "call_duration_ms": pd.to_numeric(props.get("hs_call_duration"), errors="coerce"),
                    "raw_status": props.get("hs_call_status")
                    or props.get("hs_email_status")
                    or props.get("hs_meeting_outcome")
                    or props.get("hs_task_status")
                    or "",
                    "raw_subject": props.get("hs_call_title")
                    or props.get("hs_email_subject")
                    or props.get("hs_meeting_title")
                    or props.get("hs_task_subject")
                    or "",
                }
            )
        pages += 1
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after or (max_pages and pages >= max_pages):
            break
    return rows, issues


def fetch_hubspot_activities(client, max_pages_per_object: int | None = None) -> ActivityFetchResult:
    all_rows: list[dict[str, object]] = []
    issues: list[str] = []
    if not client.has_token:
        return ActivityFetchResult(pd.DataFrame(), ["HUBSPOT_ACCESS_TOKEN is not set."])
    for object_name, config in ACTIVITY_OBJECTS.items():
        rows, object_issues = _activity_rows(client, object_name, config, max_pages_per_object)
        all_rows.extend(rows)
        issues.extend(object_issues)
    activities = pd.DataFrame(all_rows)
    if activities.empty:
        return ActivityFetchResult(activities, issues + ["No HubSpot activity rows were returned."], 0)
    activities["call_duration_minutes"] = pd.to_numeric(activities["call_duration_ms"], errors="coerce") / 60000
    activities["is_call"] = activities["activity_object"].eq("calls")
    activities["is_email"] = activities["activity_object"].eq("emails")
    activities["is_meeting"] = activities["activity_object"].eq("meetings")
    activities["is_task"] = activities["activity_object"].eq("tasks")
    activities["is_note"] = activities["activity_object"].eq("notes")
    activities["is_message"] = activities["activity_object"].eq("communications")
    return ActivityFetchResult(activities, issues, len(activities))


def enrich_activities(activities: pd.DataFrame, contacts: pd.DataFrame, owner_map: dict[str, str]) -> pd.DataFrame:
    if activities.empty:
        return activities
    enriched = activities.copy()
    if owner_map:
        enriched["activity_owner"] = enriched["activity_owner_id"].map(lambda value: owner_map.get(str(value), str(value)))
    else:
        enriched["activity_owner"] = enriched["activity_owner_id"]

    if not contacts.empty and "record_id" in contacts:
        contact_fields = [
            "record_id",
            "udr",
            "program",
            "normalized_source",
            "source_type",
            "is_applicant",
            "is_crm_enrolled",
            "is_actual_enrolled",
            "is_started",
        ]
        contact_lookup = contacts[[column for column in contact_fields if column in contacts]].copy()
        contact_lookup["record_id"] = contact_lookup["record_id"].astype(str)
        enriched = enriched.merge(
            contact_lookup,
            left_on="associated_contact_id",
            right_on="record_id",
            how="left",
        )
    if "udr" not in enriched:
        enriched["udr"] = ""
    enriched["udr"] = enriched["udr"].fillna(enriched["activity_owner"]).replace("", pd.NA).fillna(enriched["activity_owner"])
    enriched["entity_key"] = enriched["udr"].map(normalize_udr_key)
    return enriched
