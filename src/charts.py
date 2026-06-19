from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .brand import COLORS, PLOTLY_TEMPLATE


LABEL_OVERRIDES = {
    "udr": "UDR",
    "crm_enrolled": "Lifecycle Enrolled",
    "lead_to_contact_pct": "Lead-to-Contact %",
    "lead_to_applicant_pct": "Lead-to-Applicant %",
    "lead_to_crm_enrolled_pct": "Lead-to-Lifecycle Enrolled %",
    "lead_to_enrolled_pct": "Lead-to-Enrolled %",
    "bad_lead_rate": "Bad Lead Rate",
    "pct_to_goal": "% to Goal",
    "selected_term_actual": "Actual",
    "selected_term_goal": "Goal",
    "variance_to_goal": "Variance to Goal",
    "actual_enrollments": "Enrolled",
    "tracker_actual_enrollments": "Tracker Actual Enrolled",
    "activity_count": "Activity Count",
    "avg_talk_time": "Avg Talk Time",
    "total_talk_time": "Total Talk Time",
    "activities_per_lead": "Activities per Lead",
    "activities_per_applicant": "Activities per Applicant",
    "activities_per_enrollment": "Activities per Enrollment",
    "avg_time_to_enroll": "Avg Time to Enroll",
    "median_time_to_enroll": "Median Time to Enroll",
    "normalized_source": "Source",
    "source_mapping_status": "Source Mapping Status",
    "source_type": "Source Type",
    "term_label": "Term",
    "term_code": "Term Code",
    "raw_actual_column": "Raw Actual Column",
    "raw_goal_column": "Raw Goal Column",
    "annual_goal": "Annual Goal",
    "current_enrolled": "Current Enrolled",
    "current_starts": "Current Starts",
    "current_start_pct": "Current Start %",
    "fetched_activity_rows": "Fetched Activity Rows",
    "fetched_rows": "Fetched Rows",
}


def human_label(value: object) -> str:
    key = str(value)
    if key in LABEL_OVERRIDES:
        return LABEL_OVERRIDES[key]
    words = key.replace("_", " ").strip().split()
    rendered = []
    for word in words:
        lower = word.lower()
        if lower in {"udr", "crm", "id", "api", "qa"}:
            rendered.append(lower.upper())
        elif lower == "pct":
            rendered.append("%")
        elif lower in {"to", "per", "vs", "and", "or", "of", "in"}:
            rendered.append(lower)
        elif lower == "avg":
            rendered.append("Avg")
        else:
            rendered.append(lower.capitalize())
    return " ".join(rendered)


def _labels_for(columns: list[str]) -> dict[str, str]:
    return {column: human_label(column) for column in columns}


def apply_layout(fig: go.Figure, height: int = 380) -> go.Figure:
    title_text = fig.layout.title.text
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        height=height,
        margin={"l": 72, "r": 36, "t": 104, "b": 68},
        title={
            "text": title_text,
            "x": 0.02,
            "xanchor": "left",
            "y": 0.96,
            "yanchor": "top",
            "font": {"size": 17},
        },
    )
    fig.update_xaxes(showline=False, automargin=True, title_standoff=18)
    fig.update_yaxes(showline=False, automargin=True, title_standoff=18)
    return fig


def empty_figure(title: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text="No data available", x=0.5, y=0.5, showarrow=False, font={"color": COLORS["muted"], "size": 16})
    fig.update_layout(title=title, template=PLOTLY_TEMPLATE, height=320)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return apply_layout(fig, height=320)


def horizontal_bar(df: pd.DataFrame, x: str, y: str, title: str, limit: int = 12) -> go.Figure:
    if df.empty or x not in df or y not in df:
        return empty_figure(title)
    plot_df = df.sort_values(x, ascending=False).head(limit).sort_values(x)
    fig = px.bar(plot_df, x=x, y=y, orientation="h", title=title, text=x, labels=_labels_for([x, y]), color_discrete_sequence=[COLORS["blue"]])
    fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside", cliponaxis=False)
    return apply_layout(fig)


def goal_variance(df: pd.DataFrame, title: str) -> go.Figure:
    required = {"udr", "selected_term_actual", "selected_term_goal"}
    if df.empty or not required.issubset(df.columns):
        return empty_figure(title)
    plot_df = df.copy().head(12)
    fig = go.Figure()
    fig.add_bar(
        y=plot_df["udr"],
        x=plot_df["selected_term_goal"],
        orientation="h",
        name="Goal",
        marker_color=COLORS["pale_blue"],
    )
    fig.add_bar(
        y=plot_df["udr"],
        x=plot_df["selected_term_actual"],
        orientation="h",
        name="Actual",
        marker_color=COLORS["blue"],
    )
    fig.update_layout(title=title, barmode="group")
    fig.update_xaxes(title_text="Enrollments")
    fig.update_yaxes(title_text="UDR")
    return apply_layout(fig, height=430)


def conversion_funnel(kpis: dict[str, object]) -> go.Figure:
    labels = ["Leads", "Contacted", "Applicants", "Enrolled"]
    values = [
        kpis.get("total_leads") or 0,
        kpis.get("contacted") or 0,
        kpis.get("applicants") or 0,
        kpis.get("crm_enrolled") or 0,
    ]
    fig = go.Figure(go.Funnel(y=labels, x=values, marker={"color": [COLORS["blue"], COLORS["royal"], COLORS["green"], COLORS["navy"]]}))
    fig.update_layout(title="Lead Funnel")
    return apply_layout(fig)


def trend_line(df: pd.DataFrame, title: str) -> go.Figure:
    if df.empty or "period" not in df:
        return empty_figure(title)
    metrics = [column for column in ["leads", "contacted", "applicants", "crm_enrolled", "bad_leads"] if column in df]
    plot_df = df.melt(id_vars="period", value_vars=metrics, var_name="Metric", value_name="Count")
    plot_df["Metric"] = plot_df["Metric"].map(human_label)
    fig = px.line(plot_df, x="period", y="Count", color="Metric", title=title, markers=True)
    return apply_layout(fig)


def term_goal_chart(df: pd.DataFrame, title: str) -> go.Figure:
    if df.empty or "term_label" not in df:
        return empty_figure(title)
    fig = go.Figure()
    fig.add_bar(x=df["term_label"], y=df.get("goal"), name="Goal", marker_color=COLORS["pale_blue"])
    fig.add_bar(x=df["term_label"], y=df.get("actual"), name="Actual", marker_color=COLORS["blue"])
    fig.update_layout(title=title, barmode="group")
    return apply_layout(fig)


def scatter_metric(df: pd.DataFrame, x: str, y: str, title: str, color: str | None = None, size: str | None = None) -> go.Figure:
    if df.empty or x not in df or y not in df:
        return empty_figure(title)
    plot_df = df.copy()
    labels = _labels_for([x, y] + ([color] if color else []) + ([size] if size else []))
    fig = px.scatter(
        plot_df,
        x=x,
        y=y,
        color=color if color in plot_df else None,
        size=size if size in plot_df else None,
        hover_name="udr" if "udr" in plot_df else None,
        title=title,
        labels=labels,
        color_discrete_sequence=[COLORS["blue"], COLORS["green"], COLORS["red"], COLORS["royal"]],
    )
    if not color:
        fig.update_layout(showlegend=False)
    return apply_layout(fig)


def grouped_bar(df: pd.DataFrame, category: str, metrics: list[str], title: str, limit: int = 12) -> go.Figure:
    if df.empty or category not in df:
        return empty_figure(title)
    present_metrics = [metric for metric in metrics if metric in df]
    if not present_metrics:
        return empty_figure(title)
    plot_df = df.sort_values(present_metrics[0], ascending=False).head(limit)
    melted = plot_df.melt(id_vars=category, value_vars=present_metrics, var_name="Metric", value_name="Value")
    melted["Metric"] = melted["Metric"].map(human_label)
    fig = px.bar(melted, x=category, y="Value", color="Metric", barmode="group", title=title, labels={category: human_label(category), "Value": "Value"})
    return apply_layout(fig, height=420)


def source_funnel(df: pd.DataFrame, title: str = "Source Funnel") -> go.Figure:
    if df.empty or "normalized_source" not in df:
        return empty_figure(title)
    top = df.sort_values("leads", ascending=False).head(8)
    melted = top.melt(
        id_vars="normalized_source",
        value_vars=[column for column in ["leads", "contacted", "applicants", "actual_enrollments"] if column in top],
        var_name="Stage",
        value_name="Count",
    )
    melted["Stage"] = melted["Stage"].map(human_label)
    fig = px.bar(melted, x="normalized_source", y="Count", color="Stage", barmode="group", title=title, labels={"normalized_source": "Source"})
    return apply_layout(fig, height=430)


def starts_vs_enrolled(df: pd.DataFrame, title: str = "Starts vs Enrolled") -> go.Figure:
    if df.empty:
        return empty_figure(title)
    category = "udr" if "udr" in df else "term_label" if "term_label" in df else df.columns[0]
    return grouped_bar(df, category, ["actual_enrollments", "starts"], title)
