from __future__ import annotations

import pandas as pd

from .data_cleaning import normalize_udr_key


def _row(check: str, status: str, detail: str, severity: str = "Info") -> dict[str, str]:
    return {"Check": check, "Status": status, "Severity": severity, "Detail": detail}


def run_qa_checks(
    contacts: pd.DataFrame,
    enrollments: pd.DataFrame,
    goals: pd.DataFrame,
    starts: pd.DataFrame,
    activities: pd.DataFrame,
    current_state: dict[str, object],
    parsed_term_columns: list[str],
    token_present: bool,
    api_issues: list[str],
    activity_issues: list[str],
    parse_issues: list[str],
    live_mode: bool,
) -> pd.DataFrame:
    checks: list[dict[str, str]] = []
    checks.append(_row("HubSpot token present", "Pass" if token_present else "Warning", "Token found." if token_present else "HUBSPOT_ACCESS_TOKEN is not set.", "Warning" if not token_present else "Info"))
    checks.append(_row("HubSpot API fetch", "Warning" if api_issues else "Pass", "; ".join(api_issues) if api_issues else "No fetch issues reported.", "Warning" if api_issues else "Info"))
    checks.append(_row("HubSpot activity data", "Warning" if activity_issues or activities.empty else "Pass", "; ".join(activity_issues) if activity_issues else f"{len(activities):,} activity rows loaded.", "Warning" if activity_issues or activities.empty else "Info"))
    checks.append(_row("Data mode", "Pass" if live_mode else "Warning", "Live HubSpot data in use." if live_mode else "Fallback/static reference data in use.", "Warning" if not live_mode else "Info"))

    if contacts.empty:
        checks.append(_row("Contacts loaded", "Warning", "No contact rows are available for metrics.", "Warning"))
    else:
        dup_ids = contacts["record_id"].astype("string").replace("", pd.NA).dropna().duplicated().sum() if "record_id" in contacts else 0
        dup_emails = contacts["email"].astype("string").replace("", pd.NA).dropna().duplicated().sum() if "email" in contacts else 0
        checks.append(_row("Duplicate Record IDs", "Pass" if dup_ids == 0 else "Fail", f"{int(dup_ids):,} duplicate Record IDs after dedupe.", "High" if dup_ids else "Info"))
        checks.append(_row("Duplicate emails", "Pass" if dup_emails == 0 else "Warning", f"{int(dup_emails):,} duplicate emails after dedupe.", "Warning" if dup_emails else "Info"))
        for column, label in [
            ("email", "Missing email"),
            ("udr", "Missing contact owner"),
            ("lead_status", "Missing lead status"),
            ("lifecycle_stage", "Missing lifecycle stage"),
            ("create_date", "Missing create date"),
            ("program", "Missing Degree"),
            ("normalized_source", "Missing source"),
            ("term_label", "Missing term"),
            ("enrolled_date", "Missing enrollment date"),
            ("start_status", "Missing start status"),
        ]:
            if column in contacts:
                missing = contacts[column].isna() | contacts[column].astype("string").str.strip().eq("")
                count = int(missing.sum())
                checks.append(_row(label, "Pass" if count == 0 else "Warning", f"{count:,} of {len(contacts):,} contacts missing.", "Warning" if count else "Info"))
        if "create_date" in contacts:
            invalid_dates = int(contacts["create_date"].isna().sum())
            checks.append(_row("Invalid dates", "Pass" if invalid_dates == 0 else "Warning", f"{invalid_dates:,} contacts have invalid or blank create dates.", "Warning" if invalid_dates else "Info"))

    if not enrollments.empty and "days_to_enroll" in enrollments:
        negative = int((enrollments["days_to_enroll"].dropna() < 0).sum())
        checks.append(_row("Negative days to enroll", "Pass" if negative == 0 else "Fail", f"{negative:,} enrollment rows have negative days to enroll.", "High" if negative else "Info"))

    crm_enrolled = int(contacts.get("is_crm_enrolled", pd.Series(dtype=bool)).fillna(False).sum()) if not contacts.empty else 0
    actual_enrolled = len(enrollments) if not enrollments.empty else int(contacts.get("is_actual_enrolled", pd.Series(dtype=bool)).fillna(False).sum()) if not contacts.empty else 0
    if crm_enrolled and actual_enrolled:
        checks.append(_row("CRM enrolled vs actual enrollment count", "Pass" if crm_enrolled >= actual_enrolled else "Warning", f"CRM enrolled: {crm_enrolled:,}; actual enrollments: {actual_enrolled:,}.", "Warning" if crm_enrolled < actual_enrolled else "Info"))

    start_count = int(starts["actual"].dropna().sum()) if not starts.empty and "actual" in starts else 0
    if actual_enrolled and start_count:
        checks.append(_row("Enrolled count vs starts count", "Pass" if start_count <= actual_enrolled else "Warning", f"Actual enrollments: {actual_enrolled:,}; starts: {start_count:,}.", "Warning" if start_count > actual_enrolled else "Info"))

    if not goals.empty:
        goal_udrs = set(goals.loc[goals["entity_type"].eq("UDR"), "entity_key"].dropna())
        live_udrs = set(contacts["udr"].map(normalize_udr_key).dropna()) if not contacts.empty and "udr" in contacts else set()
        missing_goal = live_udrs - goal_udrs
        missing_activity = goal_udrs - live_udrs
        checks.append(_row("UDR in HubSpot but missing UDR goal", "Pass" if not missing_goal else "Warning", ", ".join(sorted(missing_goal))[:400] or "All live UDRs matched a parsed goal.", "Warning" if missing_goal else "Info"))
        checks.append(_row("UDR goal exists but no HubSpot activity", "Pass" if not missing_activity else "Warning", ", ".join(sorted(missing_activity))[:400] or "All parsed UDR goals have live activity.", "Warning" if missing_activity else "Info"))
        unpaired = goals[(goals["actual"].isna()) | (goals["goal"].isna())]
        checks.append(_row("Actual/goal columns paired correctly", "Pass" if unpaired.empty else "Warning", f"{len(unpaired):,} parsed rows have missing actual or goal values.", "Warning" if not unpaired.empty else "Info"))
        expected_terms = {"SP-1 A", "SP1-G", "SP2-A", "SP2-G", "SU1-A", "SU1-G", "SU2 -A", "SU2- G", "FA1- A", "FA1 -G", "FA2 -A", "FA2 -G"}
        missing_terms = expected_terms - set(parsed_term_columns)
        checks.append(_row("Term columns parsed successfully", "Pass" if not missing_terms else "Warning", ", ".join(sorted(missing_terms)) if missing_terms else "All expected actual/goal columns parsed.", "Warning" if missing_terms else "Info"))
    else:
        checks.append(_row("UDR goals parsed", "Warning", "No UDR goal rows are available.", "Warning"))

    goal = current_state.get("annual_goal")
    enrolled = current_state.get("current_enrolled")
    start_value = current_state.get("current_starts")
    checks.append(_row("Reference annual goal 858", "Pass" if goal is not None and round(float(goal)) == 858 else "Warning", f"Parsed annual goal: {goal}.", "Warning" if goal is None or round(float(goal or 0)) != 858 else "Info"))
    checks.append(_row("Reference current enrolled 411", "Pass" if enrolled is not None and round(float(enrolled)) == 411 else "Warning", f"Parsed current enrolled: {enrolled}.", "Warning" if enrolled is None or round(float(enrolled or 0)) != 411 else "Info"))
    checks.append(_row("Reference starts 318", "Pass" if start_value is not None and round(float(start_value)) == 318 else "Warning", f"Parsed starts: {start_value}.", "Warning" if start_value is None or round(float(start_value or 0)) != 318 else "Info"))

    if activities.empty:
        checks.append(_row("Missing activity data", "Warning", "No calls/emails/meetings/tasks/notes were available. Activity impact charts will be blank.", "Warning"))
        checks.append(_row("Missing talk time", "Warning", "No call duration rows are available.", "Warning"))
    else:
        talk_missing = int(activities.get("call_duration_minutes", pd.Series(dtype=float)).dropna().empty)
        checks.append(_row("Missing talk time", "Warning" if talk_missing else "Pass", "No call duration rows available." if talk_missing else "Call duration data is available.", "Warning" if talk_missing else "Info"))

    for issue in parse_issues:
        checks.append(_row("Reference parse issue", "Warning", issue, "Warning"))

    if live_mode and not contacts.empty and "create_date" in contacts:
        latest = contacts["create_date"].max()
        if pd.notna(latest):
            days_old = (pd.Timestamp.now(tz=None) - latest.tz_localize(None) if getattr(latest, "tzinfo", None) else pd.Timestamp.now() - latest).days
            checks.append(_row("Stale data warning", "Pass" if days_old <= 7 else "Warning", f"Latest create date is {days_old} days old.", "Warning" if days_old > 7 else "Info"))

    return pd.DataFrame(checks)
