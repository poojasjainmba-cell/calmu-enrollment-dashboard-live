from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from src.brand import apply_brand_style, page_header, status_box
from src.charts import (
    conversion_funnel,
    goal_variance,
    grouped_bar,
    human_label,
    horizontal_bar,
    scatter_metric,
    source_funnel,
    starts_vs_enrolled,
)
from src.data_cleaning import mask_email
from src.hubspot_client import HubSpotClient, HubSpotFetchResult
from src.metrics import (
    executive_kpis,
    is_all_terms,
    program_mix,
    source_performance,
    udr_performance,
)
from src.qa_checks import run_qa_checks
from src.reference_loader import ReferenceBundle, find_reference_files, load_reference_bundle


load_dotenv()

st.set_page_config(
    page_title="CalMU Enrollment Dashboard",
    page_icon="CMU",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_brand_style()


PAGES = [
    "Executive Overview",
    "UDR Performance",
    "Source & Program Performance",
    "Data Quality / Assumptions",
]

TERM_OPTIONS = ["All Terms", "Spring 1", "Spring 2", "Summer 1", "Summer 2", "Fall 1", "Fall 2"]
STATIC_REFERENCE_VERSION = "2026-static-goals-v1"


def secret_or_env(key: str, default: str = "") -> str:
    value = os.getenv(key)
    if value:
        return value
    try:
        return str(st.secrets.get(key, default))
    except Exception:
        return default


def empty_hubspot_result(issue: str = "") -> HubSpotFetchResult:
    return HubSpotFetchResult(
        contacts=pd.DataFrame(),
        activities=pd.DataFrame(),
        property_map={},
        available_properties=pd.DataFrame(),
        owner_map={},
        activity_issues=[],
        issues=[issue] if issue else [],
        fetched_rows=0,
        fetched_activity_rows=0,
    )


@st.cache_data(show_spinner=False, ttl=900)
def fetch_hubspot_data(
    access_token: str,
    refresh_key: int,
    contact_max_pages: int | None,
    activity_max_pages: int | None,
) -> HubSpotFetchResult:
    del refresh_key
    client = HubSpotClient(access_token)
    return client.fetch_dashboard_contacts(
        max_pages=contact_max_pages,
        include_activities=True,
        max_activity_pages_per_object=activity_max_pages,
    )


@st.cache_data(show_spinner=False)
def load_local_reference_bundle(reference_dir: str | None, static_reference_version: str) -> ReferenceBundle:
    del static_reference_version
    return load_reference_bundle(find_reference_files(reference_dir))


def uploaded_reference_bundle() -> ReferenceBundle | None:
    with st.sidebar.expander("Reference files", expanded=False):
        budget = st.file_uploader("Budget workbook", type=["xlsx"], key="budget_upload")
        paid = st.file_uploader("Paid leads workbook", type=["xlsx"], key="paid_upload")
        udr = st.file_uploader("UDR conversion workbook", type=["xlsx"], key="udr_upload")
        tracker = st.file_uploader("Enrollment tracker workbook", type=["xlsx"], key="tracker_upload")
        email = st.file_uploader("Weekly update email", type=["eml"], key="email_upload")
    uploads = {
        "budget": budget,
        "paid_leads": paid,
        "udr_conversions": udr,
        "enrollment_tracker": tracker,
        "weekly_email": email,
    }
    uploads = {key: value for key, value in uploads.items() if value is not None}
    return load_reference_bundle(uploads) if uploads else None


def combine_reference_bundles(primary: ReferenceBundle, uploaded: ReferenceBundle | None) -> ReferenceBundle:
    if uploaded is None:
        return primary
    return ReferenceBundle(
        contacts=uploaded.contacts if not uploaded.contacts.empty else primary.contacts,
        enrollments=uploaded.enrollments if not uploaded.enrollments.empty else primary.enrollments,
        goals=uploaded.goals if not uploaded.goals.empty else primary.goals,
        starts=uploaded.starts if not uploaded.starts.empty else primary.starts,
        current_state=uploaded.current_state or primary.current_state,
        parsed_term_columns=uploaded.parsed_term_columns or primary.parsed_term_columns,
        source_rows={**primary.source_rows, **uploaded.source_rows},
        notes=primary.notes + uploaded.notes,
        parse_issues=primary.parse_issues + uploaded.parse_issues,
    )


def init_sidebar() -> tuple[str, str, str, int]:
    st.sidebar.title("CalMU Dashboard")
    data_mode = st.sidebar.radio("Data source", ["Auto", "Live HubSpot", "Reference fallback"], index=0)
    if "refresh_key" not in st.session_state:
        st.session_state.refresh_key = 0
    if st.sidebar.button("Refresh data", type="primary", width="stretch"):
        st.session_state.refresh_key += 1
        fetch_hubspot_data.clear()
    page = st.sidebar.selectbox("Page", PAGES)
    selected_term = st.sidebar.selectbox("Term", TERM_OPTIONS, index=0)
    return data_mode, page, selected_term, st.session_state.refresh_key


def _optional_int_secret(key: str) -> int | None:
    value = secret_or_env(key, "").strip()
    if not value:
        return None
    return int(value)


def load_data(data_mode: str, refresh_key: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, HubSpotFetchResult, ReferenceBundle, bool, str]:
    token = secret_or_env("HUBSPOT_ACCESS_TOKEN")
    reference_dir = secret_or_env("REFERENCE_DIR", "")
    bundle = combine_reference_bundles(
        load_local_reference_bundle(reference_dir or None, STATIC_REFERENCE_VERSION),
        uploaded_reference_bundle(),
    )

    hubspot_result = empty_hubspot_result()
    live_requested = data_mode in {"Auto", "Live HubSpot"}
    if live_requested and token:
        with st.spinner("Fetching read-only HubSpot contacts and activities..."):
            try:
                hubspot_result = fetch_hubspot_data(
                    token,
                    refresh_key,
                    _optional_int_secret("HUBSPOT_MAX_CONTACT_PAGES"),
                    _optional_int_secret("HUBSPOT_MAX_ACTIVITY_PAGES_PER_OBJECT"),
                )
            except Exception as exc:
                hubspot_result = empty_hubspot_result(f"HubSpot fetch failed: {exc}")
    elif live_requested:
        hubspot_result = empty_hubspot_result("HUBSPOT_ACCESS_TOKEN is not set.")

    use_live = data_mode == "Live HubSpot" or (data_mode == "Auto" and not hubspot_result.contacts.empty)
    contacts = hubspot_result.contacts if use_live else bundle.contacts
    activities = hubspot_result.activities if use_live else pd.DataFrame()
    source_label = "Live HubSpot" if use_live else "Reference fallback"
    return contacts, bundle.enrollments, bundle.goals, bundle.starts, activities, hubspot_result, bundle, use_live, source_label


def fmt_int(value: object) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):,.0f}"


def fmt_money(value: object) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"${float(value):,.0f}"


def fmt_pct(value: object) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):.1%}"


def styled_dataframe(df: pd.DataFrame, height: int | None = None) -> None:
    display = df.copy()
    display.columns = [human_label(column) for column in display.columns]
    kwargs = {"width": "stretch", "hide_index": True}
    if height is not None:
        kwargs["height"] = height
    st.dataframe(display, **kwargs)


def apply_filters(contacts: pd.DataFrame, selected_term: str) -> pd.DataFrame:
    filtered = contacts.copy()
    if filtered.empty:
        return filtered

    if "create_date" in filtered:
        date_min = filtered["create_date"].min()
        date_max = filtered["create_date"].max()
        if pd.notna(date_min) and pd.notna(date_max):
            selected_dates = st.sidebar.date_input(
                "Date range",
                value=(date_min.date(), date_max.date()),
                min_value=date_min.date(),
                max_value=date_max.date(),
            )
            if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
                start, end = selected_dates
                filtered = filtered[filtered["create_date"].dt.date.between(start, end, inclusive="both")]

    if not is_all_terms(selected_term) and "term_label" in filtered:
        filtered = filtered[filtered["term_label"].eq(selected_term) | filtered["term_label"].eq("")]

    for column, label in [
        ("normalized_source", "Source"),
        ("source_type", "Paid / organic"),
        ("udr", "UDR"),
        ("program", "Program/Degree"),
        ("student_type", "Student type"),
        ("campus_location", "Campus location"),
        ("lead_status", "Lead status"),
        ("lifecycle_stage", "Lifecycle stage"),
        ("campaign", "Campaign"),
        ("event_attended", "Event attended"),
    ]:
        if column not in filtered:
            continue
        series = filtered.loc[:, column]
        if isinstance(series, pd.DataFrame):
            series = series.iloc[:, -1]
        options = sorted([value for value in series.dropna().astype(str).unique() if value])
        selected = st.sidebar.multiselect(label, options=options, default=[]) if options else []
        if selected:
            filtered = filtered[series.astype(str).isin(selected)]
    return filtered


def metric_grid(kpis: dict[str, object]) -> None:
    row1 = st.columns(6)
    row1[0].metric("Total leads", fmt_int(kpis["total_leads"]))
    row1[1].metric("Contacted", fmt_int(kpis["contacted"]), fmt_pct(kpis["lead_to_contact_pct"]))
    row1[2].metric("Applicants", fmt_int(kpis["applicants"]), fmt_pct(kpis["lead_to_applicant_pct"]))
    row1[3].metric("Lifecycle enrolled", fmt_int(kpis["crm_enrolled"]), fmt_pct(kpis["lead_to_crm_enrolled_pct"]))
    row1[4].metric("Enrolled", fmt_int(kpis["actual_enrollments"]))
    row1[5].metric("Starts", fmt_int(kpis["starts"]), fmt_pct(kpis["start_pct"]))

    row2 = st.columns(6)
    row2[0].metric("Goal", fmt_int(kpis["enrollment_goal"]), fmt_pct(kpis["pct_to_goal"]))
    row2[1].metric("Remaining", fmt_int(kpis["remaining_enrollments"]))
    row2[2].metric("Bad leads", fmt_int(kpis["bad_leads"]), fmt_pct(kpis["bad_lead_rate"]))
    row2[3].metric("L2E", fmt_pct(kpis["lead_to_enrolled_pct"]), str(kpis["lead_to_enrolled_basis"]))
    row2[4].metric("Avg days to enroll", fmt_int(kpis["avg_days_to_enroll"]))
    row2[5].metric("Revenue", fmt_money(kpis["revenue"]))

    row3 = st.columns(3)
    row3[0].metric("Total activities", fmt_int(kpis["total_activities"]))
    row3[1].metric("Avg talk time", fmt_int(kpis["avg_talk_time"]))
    row3[2].metric("Total talk time", fmt_int(kpis["total_talk_time"]))


def page_executive(contacts: pd.DataFrame, enrollments: pd.DataFrame, goals: pd.DataFrame, starts: pd.DataFrame, activities: pd.DataFrame, selected_term: str, source_label: str, refreshed_at: datetime, current_state: dict[str, object]) -> None:
    page_header("Executive Overview")
    status_box(
        f"Data source: {source_label}. Last refresh: {refreshed_at.strftime('%Y-%m-%d %I:%M %p')}. Selected term: {selected_term}."
    )
    kpis = executive_kpis(contacts, enrollments, goals, starts, activities, selected_term, current_state)
    metric_grid(kpis)
    st.caption(
        f"Enrolled: {kpis['actual_enrollments_source']}. Starts: {kpis['starts_source']}. Goal: {kpis['enrollment_goal_source']}."
    )

    udr = udr_performance(contacts, goals, enrollments, activities, selected_term)
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(conversion_funnel(kpis), width="stretch")
    with c2:
        st.plotly_chart(goal_variance(udr, "UDR Actual vs Goal"), width="stretch")

    c3, c4 = st.columns(2)
    with c3:
        st.plotly_chart(starts_vs_enrolled(pd.DataFrame([{"term_label": selected_term, "actual_enrollments": kpis["actual_enrollments"], "starts": kpis["starts"]}]), "Starts vs Enrolled"), width="stretch")
    with c4:
        st.plotly_chart(scatter_metric(udr, "activity_count", "actual_enrollments", "Activity Count vs Enrollments", size="leads"), width="stretch")

    st.subheader("Actionable UDR Watchlist")
    watch = udr[udr["flags"].astype(str).str.len().gt(0)].copy()
    styled_dataframe(watch[["udr", "leads", "applicants", "actual_enrollments", "selected_term_goal", "pct_to_goal", "activity_count", "avg_talk_time", "flags"]].head(20))


def page_udr(contacts: pd.DataFrame, enrollments: pd.DataFrame, goals: pd.DataFrame, starts: pd.DataFrame, activities: pd.DataFrame, selected_term: str) -> None:
    page_header("UDR Performance")
    df = udr_performance(contacts, goals, enrollments, activities, selected_term)
    chart_tab, table_tab, impact_tab, time_tab = st.tabs(["Goal View", "Performance Table", "Activity Impact", "Time To Enroll"])

    with chart_tab:
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(goal_variance(df, f"{selected_term} Actual vs Goal"), width="stretch")
        with c2:
            st.plotly_chart(grouped_bar(df, "udr", ["actual_enrollments", "starts"], "UDR Starts vs Enrolled"), width="stretch")

    with table_tab:
        columns = [
            "udr",
            "leads",
            "contacted",
            "applicants",
            "crm_enrolled",
            "actual_enrollments",
            "starts",
            "selected_term_goal",
            "selected_term_actual",
            "variance_to_goal",
            "pct_to_goal",
            "start_pct",
            "lead_to_contact_pct",
            "lead_to_applicant_pct",
            "lead_to_enrolled_pct",
            "activity_count",
            "calls",
            "emails",
            "meetings",
            "tasks",
            "avg_talk_time",
            "total_talk_time",
            "activities_per_lead",
            "activities_per_applicant",
            "activities_per_enrollment",
            "avg_time_to_enroll",
            "median_time_to_enroll",
            "flags",
        ]
        styled_dataframe(df[[column for column in columns if column in df]], height=620)

    with impact_tab:
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(scatter_metric(df, "activity_count", "actual_enrollments", "UDR Activity Count vs Enrollments", size="leads"), width="stretch")
        with c2:
            st.plotly_chart(scatter_metric(df, "avg_talk_time", "actual_enrollments", "Avg Talk Time vs Enrollments", size="calls"), width="stretch")
        st.plotly_chart(horizontal_bar(df, "lead_to_applicant_pct", "udr", "Lead-to-Applicant Conversion by UDR"), width="stretch")

    with time_tab:
        st.plotly_chart(horizontal_bar(df, "avg_time_to_enroll", "udr", "Average Time To Enroll by UDR"), width="stretch")
        styled_dataframe(df[["udr", "avg_time_to_enroll", "median_time_to_enroll", "activity_count", "activities_per_enrollment", "flags"]], height=420)


def page_source_program(contacts: pd.DataFrame, enrollments: pd.DataFrame, activities: pd.DataFrame) -> None:
    page_header("Source & Program Performance")
    source_df = source_performance(contacts, enrollments, activities)
    program_df = program_mix(contacts, enrollments, activities)
    source_tab, program_tab = st.tabs(["Source Performance", "Program Performance"])

    with source_tab:
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(source_funnel(source_df), width="stretch")
        with c2:
            st.plotly_chart(horizontal_bar(source_df, "bad_lead_rate", "normalized_source", "Source Bad Lead Rate"), width="stretch")
        styled_dataframe(source_df, height=540)

    with program_tab:
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(horizontal_bar(program_df, "leads", "program", "Program Mix"), width="stretch")
        with c2:
            st.plotly_chart(horizontal_bar(program_df, "lead_to_applicant_pct", "program", "Program Conversion"), width="stretch")
        styled_dataframe(program_df, height=540)


def page_quality(contacts: pd.DataFrame, enrollments: pd.DataFrame, goals: pd.DataFrame, starts: pd.DataFrame, activities: pd.DataFrame, qa: pd.DataFrame, hubspot_result: HubSpotFetchResult, bundle: ReferenceBundle, source_label: str) -> None:
    page_header("Data Quality / Assumptions")
    status_box(f"Current mode: {source_label}. Confirmed data is separated from fallback/reference interpretation.")
    styled_dataframe(qa, height=540)

    budget_tab, hubspot_tab, assumptions_tab, audit_tab = st.tabs(["Budget Validation", "HubSpot Fields", "Definitions", "Masked Audit"])
    with budget_tab:
        st.subheader("Reference Current State")
        current_state = pd.DataFrame([bundle.current_state]) if bundle.current_state else pd.DataFrame()
        styled_dataframe(current_state)
        st.subheader("Parsed Term Columns")
        styled_dataframe(pd.DataFrame({"Parsed term columns": bundle.parsed_term_columns}))
        st.subheader("UDR Goal Rows")
        styled_dataframe(goals[goals["entity_type"].eq("UDR")].head(250), height=420)

    with hubspot_tab:
        st.subheader("API Status")
        status_rows = [
            {"Area": "Contacts", "Rows": hubspot_result.fetched_rows, "Issues": "; ".join(hubspot_result.issues)},
            {"Area": "Activities", "Rows": hubspot_result.fetched_activity_rows, "Issues": "; ".join(hubspot_result.activity_issues)},
        ]
        styled_dataframe(pd.DataFrame(status_rows))
        mapping = pd.DataFrame(
            [{"Canonical field": key, "HubSpot property": value} for key, value in hubspot_result.property_map.items() if not key.startswith("_")]
        )
        styled_dataframe(mapping, height=420)

    with assumptions_tab:
        st.markdown(
            """
            - Applicant = Lifecycle Stage equals Applicant.
            - Enrolled = Lifecycle Stage equals Enrolled.
            - Starts = students who actually started and did not drop before starting.
            - Bad Lead = Lifecycle Stage equals Not a Lead or requested bad lead statuses.
            - Lead-to-contact uses Last Activity Date or the requested progressed lead-status fallback.
            - Lead-to-enrolled uses Lifecycle Stage equals Enrolled divided by total leads.
            - Time to enroll = enrollment date minus contact create date, or reference tracker days-to-enroll when HubSpot date is unavailable.
            - Avg talk time = average HubSpot call duration for associated calls.
            """
        )
        for note in bundle.notes:
            st.info(note)
        for issue in bundle.parse_issues:
            st.warning(issue)

    with audit_tab:
        if contacts.empty:
            status_box("No contact rows are loaded.", warning=True)
            return
        audit = contacts.copy()
        audit["email"] = audit["email"].map(mask_email) if "email" in audit else ""
        audit = audit.drop(columns=["phone", "first_name", "last_name"], errors="ignore")
        columns = [
            "record_id",
            "email",
            "lead_status",
            "lifecycle_stage",
            "udr",
            "create_date",
            "program",
            "term_label",
            "normalized_source",
            "source_mapping_status",
            "source_type",
            "student_type",
            "campus_location",
            "source_system",
        ]
        styled_dataframe(audit[[column for column in columns if column in audit]], height=520)


def main() -> None:
    data_mode, page, selected_term, refresh_key = init_sidebar()
    contacts, enrollments, goals, starts, activities, hubspot_result, bundle, live_mode, source_label = load_data(data_mode, refresh_key)
    filtered_contacts = apply_filters(contacts, selected_term)
    refreshed_at = datetime.now()
    qa = run_qa_checks(
        filtered_contacts,
        enrollments,
        goals,
        starts,
        activities,
        bundle.current_state,
        bundle.parsed_term_columns,
        token_present=bool(secret_or_env("HUBSPOT_ACCESS_TOKEN")),
        api_issues=hubspot_result.issues,
        activity_issues=hubspot_result.activity_issues,
        parse_issues=bundle.parse_issues,
        live_mode=live_mode,
    )

    if contacts.empty:
        status_box("No contact data is loaded. Use HubSpot live data or upload reference workbooks.", warning=True)

    if page == "Executive Overview":
        page_executive(filtered_contacts, enrollments, goals, starts, activities, selected_term, source_label, refreshed_at, bundle.current_state)
    elif page == "UDR Performance":
        page_udr(filtered_contacts, enrollments, goals, starts, activities, selected_term)
    elif page == "Source & Program Performance":
        page_source_program(filtered_contacts, enrollments, activities)
    elif page == "Data Quality / Assumptions":
        page_quality(filtered_contacts, enrollments, goals, starts, activities, qa, hubspot_result, bundle, source_label)


if __name__ == "__main__":
    main()
