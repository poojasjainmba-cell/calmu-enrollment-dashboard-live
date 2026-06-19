from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import requests

from .activity_loader import enrich_activities, fetch_hubspot_activities
from .data_cleaning import COLUMN_ALIASES, normalize_contacts, slugify_column


BASE_URL = "https://api.hubapi.com"

PROPERTY_CANDIDATES = {
    "record_id": ["hs_object_id"],
    "first_name": ["firstname"],
    "last_name": ["lastname"],
    "email": ["email"],
    "phone": ["phone", "mobilephone"],
    "lead_status": ["hs_lead_status", "lead_status"],
    "lifecycle_stage": ["lifecyclestage"],
    "udr": ["hubspot_owner_id", "contact_owner", "udr"],
    "last_activity_date": ["hs_last_sales_activity_date", "notes_last_updated", "hs_last_activity_date"],
    "marketing_contact_status": ["hs_marketable_status"],
    "create_date": ["createdate"],
    "student_type": ["student_type", "studenttype"],
    "degree": ["degree", "program", "academic_program"],
    "athletics": ["athletics"],
    "event_attended": ["event_attended", "event"],
    "campus_location": ["campus_location", "campus"],
    "paid_lead_list": ["paid_lead_list"],
    "organic_lead_list": ["organic_lead_list"],
    "source": ["hs_analytics_source", "source", "lead_source"],
    "original_source": ["hs_analytics_source"],
    "latest_source": ["hs_latest_source", "latest_source"],
    "utm_source": ["utm_source"],
    "utm_medium": ["utm_medium"],
    "utm_campaign": ["utm_campaign"],
    "campaign": ["campaign", "campaign_name"],
    "term": ["term", "start_term", "enrollment_term"],
    "enrollment_status": ["enrollment_status", "actual_enrollment", "enrolled_status"],
    "enrolled_date": ["enrolled_date", "enrollment_date", "actual_enrolled_date"],
    "start_status": ["start_status", "started_status"],
    "start_date": ["start_date", "actual_start_date"],
    "revenue": ["revenue", "tuition_revenue", "amount"],
    "days_to_enroll": ["days_to_enroll"],
}

PROPERTY_KEYWORDS = [
    "student",
    "degree",
    "program",
    "athletic",
    "event",
    "campus",
    "paid",
    "organic",
    "utm",
    "campaign",
    "source",
    "term",
    "enroll",
    "start",
    "revenue",
    "budget",
    "goal",
    "owner",
]


@dataclass
class HubSpotFetchResult:
    contacts: pd.DataFrame
    activities: pd.DataFrame
    property_map: dict[str, str]
    available_properties: pd.DataFrame
    owner_map: dict[str, str]
    activity_issues: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    fetched_rows: int = 0
    fetched_activity_rows: int = 0


class HubSpotClient:
    def __init__(self, access_token: str | None, timeout: int = 30):
        self.access_token = access_token or ""
        self.timeout = timeout
        self.session = requests.Session()
        if self.access_token:
            self.session.headers.update(
                {
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                }
            )

    @property
    def has_token(self) -> bool:
        return bool(self.access_token)

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        url = f"{BASE_URL}{path}"
        for attempt in range(4):
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            if response.status_code == 429:
                wait = float(response.headers.get("Retry-After", 2 + attempt))
                time.sleep(min(wait, 12))
                continue
            if 500 <= response.status_code < 600 and attempt < 3:
                time.sleep(1 + attempt)
                continue
            if response.status_code >= 400:
                try:
                    detail = response.json()
                except ValueError:
                    detail = response.text[:500]
                raise RuntimeError(f"HubSpot API {response.status_code}: {detail}")
            return response.json()
        raise RuntimeError("HubSpot API request failed after retries.")

    def fetch_contact_properties(self) -> pd.DataFrame:
        data = self._request("GET", "/crm/v3/properties/contacts")
        rows = []
        for prop in data.get("results", []):
            rows.append(
                {
                    "name": prop.get("name", ""),
                    "label": prop.get("label", ""),
                    "type": prop.get("type", ""),
                    "fieldType": prop.get("fieldType", ""),
                    "description": prop.get("description", ""),
                    "options": prop.get("options", []),
                }
            )
        return pd.DataFrame(rows)

    def property_option_labels(self, properties: pd.DataFrame, property_name: str | None) -> dict[str, str]:
        if not property_name or properties.empty or "name" not in properties:
            return {}
        matched = properties[properties["name"].astype(str).eq(str(property_name))]
        if matched.empty:
            return {}
        options = matched.iloc[0].get("options") or []
        return {
            str(option.get("value")): str(option.get("label"))
            for option in options
            if option.get("value") is not None and option.get("label") is not None
        }

    def select_contact_properties(self, properties: pd.DataFrame) -> dict[str, str]:
        if properties.empty:
            return {key: values[0] for key, values in PROPERTY_CANDIDATES.items() if values}
        by_name = {str(row["name"]).lower(): str(row["name"]) for _, row in properties.iterrows()}
        by_label = {slugify_column(row["label"]): str(row["name"]) for _, row in properties.iterrows()}
        selected: dict[str, str] = {}

        for canonical, candidates in PROPERTY_CANDIDATES.items():
            for candidate in candidates + COLUMN_ALIASES.get(canonical, []):
                key = slugify_column(candidate)
                if candidate.lower() in by_name:
                    selected[canonical] = by_name[candidate.lower()]
                    break
                if key in by_label:
                    selected[canonical] = by_label[key]
                    break

        names_to_fetch = set(selected.values())
        for _, row in properties.iterrows():
            name = str(row["name"])
            label = str(row["label"])
            search = f"{name} {label}".lower()
            if any(keyword in search for keyword in PROPERTY_KEYWORDS):
                names_to_fetch.add(name)

        selected["_properties_to_fetch"] = ",".join(sorted(names_to_fetch))
        return selected

    def fetch_owners(self) -> tuple[dict[str, str], list[str]]:
        issues: list[str] = []
        owners: dict[str, str] = {}
        try:
            after = None
            while True:
                params = {"limit": 100}
                if after:
                    params["after"] = after
                data = self._request("GET", "/crm/v3/owners/", params=params)
                for owner in data.get("results", []):
                    first = owner.get("firstName") or ""
                    last = owner.get("lastName") or ""
                    name = " ".join([first, last]).strip() or owner.get("email") or str(owner.get("id"))
                    owners[str(owner.get("id"))] = name
                after = data.get("paging", {}).get("next", {}).get("after")
                if not after:
                    break
        except Exception as exc:
            issues.append(f"HubSpot owner lookup unavailable; showing owner IDs where needed. Detail: {exc}")
        return owners, issues

    def fetch_contacts(self, properties: list[str], max_pages: int | None = None) -> list[dict[str, Any]]:
        if max_pages:
            return self.search_contacts(properties, max_pages=max_pages)

        records: list[dict[str, Any]] = []
        after = None
        pages = 0
        while True:
            params = {
                "limit": 100,
                "properties": ",".join(sorted(set(properties))),
                "archived": "false",
            }
            if after:
                params["after"] = after
            data = self._request("GET", "/crm/v3/objects/contacts", params=params)
            for item in data.get("results", []):
                row = {"id": item.get("id"), "createdAt": item.get("createdAt"), "updatedAt": item.get("updatedAt")}
                row.update(item.get("properties") or {})
                records.append(row)
            pages += 1
            after = data.get("paging", {}).get("next", {}).get("after")
            if not after or (max_pages and pages >= max_pages):
                break
        return records

    def search_contacts(self, properties: list[str], max_pages: int) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        after = None
        pages = 0
        while True:
            payload: dict[str, Any] = {
                "limit": 100,
                "properties": sorted(set(properties)),
                "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}],
            }
            if after:
                payload["after"] = after
            data = self._request("POST", "/crm/v3/objects/contacts/search", json=payload)
            for item in data.get("results", []):
                row = {"id": item.get("id"), "createdAt": item.get("createdAt"), "updatedAt": item.get("updatedAt")}
                row.update(item.get("properties") or {})
                records.append(row)
            pages += 1
            after = data.get("paging", {}).get("next", {}).get("after")
            if not after or pages >= max_pages:
                break
        return records

    def fetch_dashboard_contacts(
        self,
        max_pages: int | None = None,
        include_activities: bool = True,
        max_activity_pages_per_object: int | None = None,
    ) -> HubSpotFetchResult:
        issues: list[str] = []
        if not self.has_token:
            return HubSpotFetchResult(
                contacts=pd.DataFrame(),
                activities=pd.DataFrame(),
                property_map={},
                available_properties=pd.DataFrame(),
                owner_map={},
                issues=["HUBSPOT_ACCESS_TOKEN is not set."],
            )

        properties = pd.DataFrame()
        property_map: dict[str, str] = {}
        try:
            properties = self.fetch_contact_properties()
            property_map = self.select_contact_properties(properties)
        except Exception as exc:
            issues.append(f"Contact property schema fetch failed; using default property names. Detail: {exc}")
            property_map = {key: values[0] for key, values in PROPERTY_CANDIDATES.items() if values}
            property_map["_properties_to_fetch"] = ",".join(sorted(set(property_map.values())))

        owner_map, owner_issues = self.fetch_owners()
        issues.extend(owner_issues)

        property_names = [name for name in property_map.get("_properties_to_fetch", "").split(",") if name]
        records = self.fetch_contacts(property_names, max_pages=max_pages)
        raw = pd.DataFrame(records)
        if raw.empty:
            return HubSpotFetchResult(
                contacts=pd.DataFrame(),
                activities=pd.DataFrame(),
                property_map=property_map,
                available_properties=properties,
                owner_map=owner_map,
                issues=issues + ["No HubSpot contacts were returned."],
                fetched_rows=0,
            )

        reverse_map = {hubspot_name: canonical for canonical, hubspot_name in property_map.items() if not canonical.startswith("_")}
        raw = raw.rename(columns=reverse_map)
        if "id" in raw.columns and "record_id" not in raw.columns:
            raw["record_id"] = raw["id"]
        if "lifecycle_stage" in raw.columns:
            lifecycle_labels = self.property_option_labels(properties, property_map.get("lifecycle_stage"))
            if lifecycle_labels:
                raw["lifecycle_stage_raw"] = raw["lifecycle_stage"]
                raw["lifecycle_stage"] = raw["lifecycle_stage"].map(
                    lambda value: value if value is None or pd.isna(value) else lifecycle_labels.get(str(value), value)
                )
        if "udr" in raw.columns and owner_map:
            raw["udr"] = raw["udr"].astype("string").map(lambda value: owner_map.get(str(value), str(value)))

        contacts = normalize_contacts(raw, source_system="HubSpot")
        activities = pd.DataFrame()
        activity_issues: list[str] = []
        fetched_activity_rows = 0
        if include_activities:
            activity_result = fetch_hubspot_activities(self, max_pages_per_object=max_activity_pages_per_object)
            activities = enrich_activities(activity_result.activities, contacts, owner_map)
            activity_issues = activity_result.issues
            fetched_activity_rows = activity_result.fetched_rows
        return HubSpotFetchResult(
            contacts=contacts,
            activities=activities,
            property_map=property_map,
            available_properties=properties,
            owner_map=owner_map,
            activity_issues=activity_issues,
            issues=issues,
            fetched_rows=len(records),
            fetched_activity_rows=fetched_activity_rows,
        )
