from __future__ import annotations

import pandas as pd

from .data_cleaning import normalize_udr_key


def is_all_terms(selected_term: str | None) -> bool:
    return selected_term in (None, "", "All", "All Terms")


def safe_div(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if denominator is None or pd.isna(denominator):
        return None
    denominator = float(denominator)
    if denominator == 0:
        return None
    if numerator is None or pd.isna(numerator):
        numerator = 0
    return float(numerator) / denominator


def first_nonzero(*values: object) -> object | None:
    for value in values:
        if value is None or pd.isna(value):
            continue
        try:
            if float(value) == 0:
                continue
        except (TypeError, ValueError):
            pass
        return value
    return None


def _sum_bool(df: pd.DataFrame, column: str) -> int:
    if df.empty or column not in df:
        return 0
    return int(df[column].fillna(False).sum())


def _selected_goals(goals: pd.DataFrame, selected_term: str | None = None, entity_type: str = "UDR") -> pd.DataFrame:
    if goals.empty:
        return goals
    subset = goals[goals["entity_type"].eq(entity_type)].copy()
    if not is_all_terms(selected_term):
        subset = subset[subset["term_label"].eq(selected_term)]
    return subset


def contact_summary(contacts: pd.DataFrame) -> dict[str, int | float | None]:
    total_leads = int(len(contacts))
    applicants = _sum_bool(contacts, "is_applicant")
    enrolled = _sum_bool(contacts, "is_crm_enrolled")
    contacted = _sum_bool(contacts, "is_contacted")
    bad_leads = _sum_bool(contacts, "is_bad_lead")
    starts = _sum_bool(contacts, "is_started")
    return {
        "total_leads": total_leads,
        "contacted": contacted,
        "lead_to_contact_pct": safe_div(contacted, total_leads),
        "applicants": applicants,
        "lead_to_applicant_pct": safe_div(applicants, total_leads),
        "crm_enrolled": enrolled,
        "lead_to_crm_enrolled_pct": safe_div(enrolled, total_leads),
        "lead_to_enrolled_pct": safe_div(enrolled, total_leads),
        "lead_to_enrolled_basis": "Lifecycle Stage = Enrolled",
        "bad_leads": bad_leads,
        "bad_lead_rate": safe_div(bad_leads, total_leads),
        "actual_enrolled_from_contacts": enrolled,
        "starts_from_contacts": starts,
    }


def actual_enrollment_count(
    contacts: pd.DataFrame,
    enrollments: pd.DataFrame,
    goals: pd.DataFrame,
    selected_term: str | None,
    current_state: dict[str, object] | None = None,
) -> tuple[int | None, str]:
    contact_actual = _sum_bool(contacts, "is_crm_enrolled")
    if contact_actual:
        return contact_actual, "HubSpot Lifecycle Stage = Enrolled"

    if is_all_terms(selected_term) and current_state and current_state.get("current_enrolled") is not None:
        return int(float(current_state["current_enrolled"])), "Budget workbook current-state fallback"

    if not enrollments.empty:
        subset = enrollments
        if not is_all_terms(selected_term) and "term_label" in subset:
            subset = subset[subset["term_label"].eq(selected_term)]
        return int(len(subset)), "Enrollment tracker fallback"

    selected = _selected_goals(goals, selected_term, "UDR")
    if not selected.empty and selected["actual"].notna().any():
        return int(selected["actual"].fillna(0).sum()), "Budget workbook actual columns"

    return None, "Unavailable"


def starts_count(
    contacts: pd.DataFrame,
    starts: pd.DataFrame,
    selected_term: str | None,
    current_state: dict[str, object] | None = None,
) -> tuple[int | None, str]:
    contact_starts = _sum_bool(contacts, "is_started")
    if contact_starts:
        return contact_starts, "HubSpot start fields"
    if is_all_terms(selected_term) and current_state and current_state.get("current_starts") is not None:
        return int(float(current_state["current_starts"])), "Budget workbook current-state fallback"
    if not starts.empty:
        subset = starts
        if not is_all_terms(selected_term):
            subset = subset[subset["term_label"].eq(selected_term)]
        values = subset["actual"].dropna() if "actual" in subset else pd.Series(dtype=float)
        if not values.empty:
            return int(values.sum()), "Budget workbook starts rows"
    return None, "Unavailable"


def executive_kpis(
    contacts: pd.DataFrame,
    enrollments: pd.DataFrame,
    goals: pd.DataFrame,
    starts: pd.DataFrame,
    activities: pd.DataFrame,
    selected_term: str | None,
    current_state: dict[str, object] | None = None,
) -> dict[str, object]:
    summary = contact_summary(contacts)
    actual, actual_source = actual_enrollment_count(contacts, enrollments, goals, selected_term, current_state)
    start_value, starts_source = starts_count(contacts, starts, selected_term, current_state)
    selected_goal_rows = _selected_goals(goals, selected_term, "UDR")
    if is_all_terms(selected_term) and current_state and current_state.get("annual_goal") is not None:
        enrollment_goal = current_state["annual_goal"]
        enrollment_goal_source = "Budget workbook annual goal"
    else:
        enrollment_goal = selected_goal_rows["goal"].fillna(0).sum() if not selected_goal_rows.empty else None
        enrollment_goal_source = "Budget workbook UDR term goals" if enrollment_goal is not None else "Unavailable"
    total_udr_goal = selected_goal_rows["goal"].fillna(0).sum() if not selected_goal_rows.empty else None
    revenue = None
    revenue_per_enrollment = None
    avg_days_to_enroll = None

    if not enrollments.empty:
        revenue = enrollments["revenue"].sum(min_count=1) if "revenue" in enrollments else None
        avg_days_to_enroll = enrollments["days_to_enroll"].mean() if "days_to_enroll" in enrollments else None
    if revenue is None or pd.isna(revenue):
        revenue = contacts["revenue"].sum(min_count=1) if "revenue" in contacts else None
    if actual:
        revenue_per_enrollment = safe_div(revenue, actual)
    total_activities = len(activities) if not activities.empty else 0
    avg_talk_time = activities["call_duration_minutes"].mean() if not activities.empty and "call_duration_minutes" in activities else None
    total_talk_time = activities["call_duration_minutes"].sum(min_count=1) if not activities.empty and "call_duration_minutes" in activities else None

    summary.update(
        {
            "actual_enrollments": actual,
            "actual_enrollments_source": actual_source,
            "starts": start_value,
            "starts_source": starts_source,
            "start_pct": safe_div(start_value, actual),
            "enrollment_goal": enrollment_goal,
            "enrollment_goal_source": enrollment_goal_source,
            "pct_to_goal": safe_div(actual, enrollment_goal),
            "remaining_enrollments": None if enrollment_goal is None or actual is None else max(enrollment_goal - actual, 0),
            "total_udr_goal": total_udr_goal,
            "revenue": revenue,
            "revenue_per_enrollment": revenue_per_enrollment,
            "avg_days_to_enroll": avg_days_to_enroll,
            "avg_talk_time": avg_talk_time,
            "total_talk_time": total_talk_time,
            "total_activities": total_activities,
        }
    )
    return summary


def aggregate_contacts(contacts: pd.DataFrame, group_col: str) -> pd.DataFrame:
    columns = [
        group_col,
        "leads",
        "contacted",
        "applicants",
        "crm_enrolled",
        "actual_enrollments",
        "starts",
        "bad_leads",
        "lead_to_contact_pct",
        "lead_to_applicant_pct",
        "lead_to_crm_enrolled_pct",
        "lead_to_enrolled_pct",
        "bad_lead_rate",
    ]
    if contacts.empty or group_col not in contacts:
        return pd.DataFrame(columns=columns)
    grouped = (
        contacts.groupby(group_col, dropna=False)
        .agg(
            leads=("record_id", "size"),
            contacted=("is_contacted", "sum"),
            applicants=("is_applicant", "sum"),
            crm_enrolled=("is_crm_enrolled", "sum"),
            actual_enrollments=("is_crm_enrolled", "sum"),
            starts=("is_started", "sum"),
            bad_leads=("is_bad_lead", "sum"),
        )
        .reset_index()
    )
    for numerator, output in [
        ("contacted", "lead_to_contact_pct"),
        ("applicants", "lead_to_applicant_pct"),
        ("crm_enrolled", "lead_to_crm_enrolled_pct"),
        ("actual_enrollments", "lead_to_enrolled_pct"),
        ("bad_leads", "bad_lead_rate"),
    ]:
        grouped[output] = grouped.apply(lambda row: safe_div(row[numerator], row["leads"]), axis=1)
    return grouped.sort_values("leads", ascending=False)


def activity_summary(activities: pd.DataFrame, group_col: str) -> pd.DataFrame:
    columns = [
        group_col,
        "activity_count",
        "calls",
        "emails",
        "meetings",
        "tasks",
        "notes",
        "messages",
        "total_talk_time",
        "avg_talk_time",
    ]
    if activities.empty or group_col not in activities:
        return pd.DataFrame(columns=columns)
    grouped = (
        activities.groupby(group_col, dropna=False)
        .agg(
            activity_count=("activity_id", "size"),
            calls=("is_call", "sum"),
            emails=("is_email", "sum"),
            meetings=("is_meeting", "sum"),
            tasks=("is_task", "sum"),
            notes=("is_note", "sum"),
            messages=("is_message", "sum"),
            total_talk_time=("call_duration_minutes", "sum"),
            avg_talk_time=("call_duration_minutes", "mean"),
        )
        .reset_index()
    )
    return grouped


def _time_to_enroll_by_group(contacts: pd.DataFrame, enrollments: pd.DataFrame, group_col: str) -> pd.DataFrame:
    pieces = []
    if not contacts.empty and group_col in contacts:
        contact_days = contacts[[group_col, "create_date", "enrolled_date", "days_to_enroll"]].copy()
        contact_days["create_date"] = pd.to_datetime(contact_days["create_date"], errors="coerce", utc=True).dt.tz_convert(None)
        contact_days["enrolled_date"] = pd.to_datetime(contact_days["enrolled_date"], errors="coerce", utc=True).dt.tz_convert(None)
        computed = (contact_days["enrolled_date"] - contact_days["create_date"]).dt.days
        contact_days["time_to_enroll_days"] = contact_days["days_to_enroll"].fillna(computed)
        contact_days = contact_days.dropna(subset=["time_to_enroll_days"])
        if not contact_days.empty:
            pieces.append(contact_days[[group_col, "time_to_enroll_days"]])
    if not enrollments.empty and group_col in enrollments and "days_to_enroll" in enrollments:
        enrollment_days = enrollments[[group_col, "days_to_enroll"]].copy().dropna(subset=["days_to_enroll"])
        if not enrollment_days.empty:
            enrollment_days = enrollment_days.rename(columns={"days_to_enroll": "time_to_enroll_days"})
            pieces.append(enrollment_days)
    if not pieces:
        return pd.DataFrame(columns=[group_col, "avg_time_to_enroll", "median_time_to_enroll"])
    combined = pd.concat(pieces, ignore_index=True)
    return (
        combined.groupby(group_col, dropna=False)
        .agg(avg_time_to_enroll=("time_to_enroll_days", "mean"), median_time_to_enroll=("time_to_enroll_days", "median"))
        .reset_index()
    )


def _attach_activity_and_time(
    base: pd.DataFrame,
    group_col: str,
    activities: pd.DataFrame,
    contacts: pd.DataFrame,
    enrollments: pd.DataFrame,
) -> pd.DataFrame:
    out = base.copy()
    out = out.merge(activity_summary(activities, group_col), on=group_col, how="left")
    out = out.merge(_time_to_enroll_by_group(contacts, enrollments, group_col), on=group_col, how="left")
    fill_zero = ["activity_count", "calls", "emails", "meetings", "tasks", "notes", "messages", "total_talk_time"]
    for column in fill_zero:
        if column in out:
            out[column] = out[column].fillna(0)
    out["activities_per_lead"] = out.apply(lambda row: safe_div(row.get("activity_count"), row.get("leads")), axis=1)
    out["activities_per_applicant"] = out.apply(lambda row: safe_div(row.get("activity_count"), row.get("applicants")), axis=1)
    out["activities_per_enrollment"] = out.apply(
        lambda row: safe_div(
            row.get("activity_count"),
            first_nonzero(row.get("actual_enrollments"), row.get("tracker_actual_enrollments"), row.get("crm_enrolled")),
        ),
        axis=1,
    )
    return out


def _match_goal_key(activity_key: str, goal_keys: list[str]) -> str | None:
    if activity_key in goal_keys:
        return activity_key
    tokens = set(activity_key.split())
    best_key = None
    best_score = 0
    for goal_key in goal_keys:
        goal_tokens = set(goal_key.split())
        if goal_key and (goal_key in activity_key or activity_key in goal_key):
            return goal_key
        score = len(tokens & goal_tokens)
        if score > best_score and score >= 2:
            best_key = goal_key
            best_score = score
    return best_key


def udr_performance(
    contacts: pd.DataFrame,
    goals: pd.DataFrame,
    enrollments: pd.DataFrame,
    activities: pd.DataFrame,
    selected_term: str | None,
) -> pd.DataFrame:
    activity = aggregate_contacts(contacts, "udr")
    if activity.empty:
        activity = pd.DataFrame(
            columns=[
                "udr",
                "leads",
                "contacted",
                "applicants",
                "crm_enrolled",
                "actual_enrollments",
                "starts",
                "bad_leads",
                "lead_to_contact_pct",
                "lead_to_applicant_pct",
                "lead_to_crm_enrolled_pct",
                "bad_lead_rate",
            ]
        )
    activity["entity_key"] = activity["udr"].map(normalize_udr_key) if "udr" in activity else ""

    selected = _selected_goals(goals, selected_term, "UDR")
    if selected.empty:
        activity["selected_term_actual"] = pd.NA
        activity["selected_term_goal"] = pd.NA
        activity["variance_to_goal"] = pd.NA
        activity["pct_to_goal"] = pd.NA
        activity["goal_entity"] = pd.NA
    else:
        goal_summary = (
            selected.groupby(["entity_key", "entity"], dropna=False)
            .agg(selected_term_actual=("actual", "sum"), selected_term_goal=("goal", "sum"))
            .reset_index()
        )
        goal_summary["variance_to_goal"] = goal_summary["selected_term_actual"] - goal_summary["selected_term_goal"]
        goal_summary["pct_to_goal"] = goal_summary.apply(
            lambda row: safe_div(row["selected_term_actual"], row["selected_term_goal"]), axis=1
        )
        goal_keys = goal_summary["entity_key"].dropna().astype(str).tolist()
        activity["matched_goal_key"] = activity["entity_key"].map(lambda key: _match_goal_key(str(key), goal_keys))
        activity = activity.merge(
            goal_summary.rename(columns={"entity_key": "matched_goal_key", "entity": "goal_entity"}),
            on="matched_goal_key",
            how="left",
        )
        missing_activity = goal_summary[~goal_summary["entity_key"].isin(set(activity["matched_goal_key"].dropna()))].copy()
        if not missing_activity.empty:
            missing_activity = missing_activity.rename(columns={"entity": "udr", "entity_key": "matched_goal_key"})
            missing_activity["entity_key"] = missing_activity["matched_goal_key"]
            for column in ["leads", "contacted", "applicants", "crm_enrolled", "actual_enrollments", "starts", "bad_leads"]:
                missing_activity[column] = 0
            missing_activity["lead_to_contact_pct"] = pd.NA
            missing_activity["lead_to_applicant_pct"] = pd.NA
            missing_activity["lead_to_crm_enrolled_pct"] = pd.NA
            missing_activity["bad_lead_rate"] = pd.NA
            missing_activity["goal_entity"] = missing_activity["udr"]
            for column in activity.columns:
                if column not in missing_activity:
                    missing_activity[column] = pd.NA
            activity = pd.concat([activity, missing_activity[activity.columns]], ignore_index=True)

    if not enrollments.empty and "udr" in enrollments:
        enroll_subset = enrollments
        if not is_all_terms(selected_term) and "term_label" in enroll_subset:
            enroll_subset = enroll_subset[enroll_subset["term_label"].eq(selected_term)]
        enrollment_counts = enroll_subset.groupby("udr").size().rename("tracker_actual_enrollments").reset_index()
        enrollment_counts["enrollment_key"] = enrollment_counts["udr"].map(normalize_udr_key)
        enrollment_keys = enrollment_counts["enrollment_key"].dropna().astype(str).tolist()
        activity["matched_enrollment_key"] = activity["entity_key"].map(lambda key: _match_goal_key(str(key), enrollment_keys))
        activity = activity.merge(
            enrollment_counts.drop(columns=["udr"]).rename(columns={"enrollment_key": "matched_enrollment_key"}),
            on="matched_enrollment_key",
            how="left",
        )
    else:
        activity["tracker_actual_enrollments"] = pd.NA

    activity["actual_enrollments"] = activity["actual_enrollments"].fillna(0)
    if "tracker_actual_enrollments" in activity:
        activity["actual_enrollments"] = activity["actual_enrollments"].where(
            activity["actual_enrollments"].gt(0), activity["tracker_actual_enrollments"]
        )
    activity = _attach_activity_and_time(activity, "udr", activities, contacts, enrollments)
    if not enrollments.empty and {"udr", "days_to_enroll"}.issubset(enrollments.columns):
        tracker_time = enrollments.dropna(subset=["days_to_enroll"]).copy()
        if not tracker_time.empty:
            tracker_time["time_key"] = tracker_time["udr"].map(normalize_udr_key)
            time_summary = (
                tracker_time.groupby("time_key")
                .agg(
                    tracker_avg_time_to_enroll=("days_to_enroll", "mean"),
                    tracker_median_time_to_enroll=("days_to_enroll", "median"),
                )
                .reset_index()
            )
            time_keys = time_summary["time_key"].dropna().astype(str).tolist()
            activity["matched_time_key"] = activity["entity_key"].map(lambda key: _match_goal_key(str(key), time_keys))
            activity = activity.merge(
                time_summary.rename(columns={"time_key": "matched_time_key"}),
                on="matched_time_key",
                how="left",
            )
            activity["avg_time_to_enroll"] = activity["avg_time_to_enroll"].fillna(activity["tracker_avg_time_to_enroll"])
            activity["median_time_to_enroll"] = activity["median_time_to_enroll"].fillna(activity["tracker_median_time_to_enroll"])
    activity["start_pct"] = activity.apply(lambda row: safe_div(row.get("starts"), row.get("actual_enrollments")), axis=1)
    activity["flag_below_goal"] = activity["selected_term_goal"].notna() & (activity["selected_term_actual"].fillna(0) < activity["selected_term_goal"].fillna(0))
    activity["flag_missing_goal"] = activity["selected_term_goal"].isna()
    activity["flag_missing_live_activity"] = activity["leads"].fillna(0).eq(0) & activity["selected_term_goal"].fillna(0).gt(0)
    activity["flag_high_volume_low_applicant_conversion"] = activity["leads"].fillna(0).ge(100) & activity["lead_to_applicant_pct"].fillna(0).lt(0.03)
    activity["flag_high_activity_low_conversion"] = activity["activity_count"].fillna(0).ge(activity["activity_count"].fillna(0).median()) & activity["lead_to_applicant_pct"].fillna(0).lt(0.03)
    activity["flag_low_activity_strong_conversion"] = activity["activity_count"].fillna(0).le(activity["activity_count"].fillna(0).median()) & activity["lead_to_applicant_pct"].fillna(0).ge(0.03)
    activity["flag_below_goal_low_activity"] = activity["flag_below_goal"] & activity["activity_count"].fillna(0).le(activity["activity_count"].fillna(0).median())
    activity["flag_below_goal_high_activity"] = activity["flag_below_goal"] & activity["activity_count"].fillna(0).gt(activity["activity_count"].fillna(0).median())
    activity["flags"] = activity.apply(_flag_text, axis=1)
    return activity.sort_values(["selected_term_goal", "leads"], ascending=False, na_position="last")


def _flag_text(row: pd.Series) -> str:
    flags = []
    if row.get("flag_high_volume_low_applicant_conversion"):
        flags.append("High volume / low applicant conversion")
    if row.get("flag_below_goal"):
        flags.append("Below goal")
    if row.get("flag_missing_goal"):
        flags.append("Missing goal")
    if row.get("flag_missing_live_activity"):
        flags.append("No live activity")
    if row.get("flag_high_activity_low_conversion"):
        flags.append("High activity / low conversion")
    if row.get("flag_low_activity_strong_conversion"):
        flags.append("Low activity / strong conversion")
    if row.get("flag_below_goal_low_activity"):
        flags.append("Below goal / low activity")
    if row.get("flag_below_goal_high_activity"):
        flags.append("Below goal despite high activity")
    return "; ".join(flags)


def source_performance(contacts: pd.DataFrame, enrollments: pd.DataFrame, activities: pd.DataFrame) -> pd.DataFrame:
    base = aggregate_contacts(contacts, "normalized_source")
    if not enrollments.empty and "normalized_source" in enrollments:
        actuals = enrollments.groupby("normalized_source").size().rename("tracker_actual_enrollments").reset_index()
        base = base.merge(actuals, on="normalized_source", how="outer")
        base["actual_enrollments"] = base["actual_enrollments"].where(base["actual_enrollments"].fillna(0).gt(0), base["tracker_actual_enrollments"])
    return _attach_activity_and_time(base, "normalized_source", activities, contacts, enrollments).sort_values("leads", ascending=False, na_position="last")


def program_mix(contacts: pd.DataFrame, enrollments: pd.DataFrame, activities: pd.DataFrame) -> pd.DataFrame:
    contacts_by_program = aggregate_contacts(contacts, "program")
    if not enrollments.empty and "program" in enrollments:
        actuals = enrollments.groupby("program").agg(tracker_actual_enrollments=("student", "size"), revenue=("revenue", "sum")).reset_index()
        contacts_by_program = contacts_by_program.merge(actuals, on="program", how="outer")
        contacts_by_program["actual_enrollments"] = contacts_by_program["actual_enrollments"].where(
            contacts_by_program["actual_enrollments"].fillna(0).gt(0), contacts_by_program["tracker_actual_enrollments"]
        )
    out = _attach_activity_and_time(contacts_by_program, "program", activities, contacts, enrollments)
    return out.fillna({"program": "Unmapped"}).sort_values("leads", ascending=False, na_position="last")


def term_performance(contacts: pd.DataFrame, enrollments: pd.DataFrame, goals: pd.DataFrame, starts: pd.DataFrame) -> pd.DataFrame:
    pieces = []
    if not goals.empty:
        goal_terms = (
            goals[goals["entity_type"].eq("UDR")]
            .groupby(["term_code", "term_label", "sort_order"], dropna=False)
            .agg(actual=("actual", "sum"), goal=("goal", "sum"))
            .reset_index()
        )
        pieces.append(goal_terms)
    base = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame(columns=["term_code", "term_label", "sort_order", "actual", "goal"])
    if not enrollments.empty and "term_label" in enrollments:
        actuals = enrollments.groupby("term_label").size().rename("enrolled").reset_index()
        base = base.merge(actuals, on="term_label", how="outer")
    if not contacts.empty and "term_label" in contacts:
        contact_terms = (
            contacts.groupby("term_label", dropna=False)
            .agg(leads=("record_id", "size"), applicants=("is_applicant", "sum"), crm_enrolled=("is_crm_enrolled", "sum"))
            .reset_index()
        )
        base = base.merge(contact_terms, on="term_label", how="outer")
    if not starts.empty:
        start_terms = starts.groupby("term_label").agg(starts=("actual", "sum")).reset_index()
        base = base.merge(start_terms, on="term_label", how="outer")
    base["variance"] = base.get("actual", 0).fillna(0) - base.get("goal", 0).fillna(0)
    base["pct_to_goal"] = base.apply(lambda row: safe_div(row.get("actual"), row.get("goal")), axis=1)
    base["start_pct"] = base.apply(lambda row: safe_div(row.get("starts"), first_nonzero(row.get("enrolled"), row.get("actual"))), axis=1)
    return base.sort_values(["sort_order", "term_label"], na_position="last")


def trends(contacts: pd.DataFrame, grain: str = "W") -> pd.DataFrame:
    if contacts.empty or "create_date" not in contacts:
        return pd.DataFrame()
    dates = contacts.dropna(subset=["create_date"]).copy()
    if dates.empty:
        return pd.DataFrame()
    dates["period"] = dates["create_date"].dt.to_period(grain).dt.start_time
    return (
        dates.groupby("period")
        .agg(
            leads=("record_id", "size"),
            contacted=("is_contacted", "sum"),
            applicants=("is_applicant", "sum"),
            crm_enrolled=("is_crm_enrolled", "sum"),
            bad_leads=("is_bad_lead", "sum"),
        )
        .reset_index()
        .sort_values("period")
    )
