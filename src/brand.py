from __future__ import annotations

import streamlit as st


COLORS = {
    "blue": "#2938D5",
    "lime": "#EDFF81",
    "navy": "#1E2944",
    "royal": "#3D59D9",
    "white": "#FFFFFF",
    "pale_blue": "#ABCCE3",
    "green": "#1A5347",
    "slate_green": "#657874",
    "sage": "#ABBEB3",
    "mist": "#C4CDD3",
    "red": "#CD1141",
    "maroon": "#8F0028",
    "background": "#F7F9FC",
    "border": "#DDE5EE",
    "muted": "#657874",
}

PLOTLY_TEMPLATE = {
    "layout": {
        "font": {"family": "Inter, Arial, sans-serif", "color": COLORS["navy"]},
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "colorway": [
            COLORS["blue"],
            COLORS["green"],
            COLORS["royal"],
            COLORS["red"],
            COLORS["pale_blue"],
            COLORS["slate_green"],
            COLORS["maroon"],
        ],
        "margin": {"l": 24, "r": 24, "t": 52, "b": 40},
        "xaxis": {"gridcolor": "#E8EEF5", "zerolinecolor": "#DDE5EE"},
        "yaxis": {"gridcolor": "#E8EEF5", "zerolinecolor": "#DDE5EE"},
        "legend": {"orientation": "h", "yanchor": "bottom", "y": 1.02},
    }
}


def apply_brand_style() -> None:
    st.markdown(
        f"""
        <style>
        :root {{
            --calmu-blue: {COLORS["blue"]};
            --calmu-lime: {COLORS["lime"]};
            --calmu-navy: {COLORS["navy"]};
            --calmu-green: {COLORS["green"]};
            --calmu-border: {COLORS["border"]};
            --calmu-muted: {COLORS["muted"]};
            --calmu-bg: {COLORS["background"]};
        }}
        .stApp {{
            background: var(--calmu-bg);
            color: var(--calmu-navy);
        }}
        [data-testid="stSidebar"] {{
            background: #FFFFFF;
            border-right: 1px solid var(--calmu-border);
        }}
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] label {{
            color: var(--calmu-navy);
        }}
        .block-container {{
            padding-top: 1.6rem;
            padding-bottom: 2.5rem;
            max-width: 1500px;
        }}
        h1, h2, h3 {{
            color: var(--calmu-navy);
            letter-spacing: 0;
        }}
        div[data-testid="stMetric"] {{
            background: #FFFFFF;
            border: 1px solid var(--calmu-border);
            border-left: 4px solid var(--calmu-blue);
            border-radius: 8px;
            padding: 14px 16px;
            min-height: 114px;
            box-shadow: 0 8px 18px rgba(30, 41, 68, 0.05);
        }}
        div[data-testid="stMetric"] label {{
            color: var(--calmu-muted);
            font-size: 0.82rem;
            text-transform: uppercase;
            letter-spacing: 0;
        }}
        div[data-testid="stMetricValue"] {{
            color: var(--calmu-navy);
            font-weight: 750;
        }}
        div[data-testid="stDataFrame"] {{
            border: 1px solid var(--calmu-border);
            border-radius: 8px;
            overflow: hidden;
            background: #FFFFFF;
        }}
        .calmu-page-kicker {{
            color: var(--calmu-blue);
            font-weight: 700;
            font-size: 0.82rem;
            text-transform: uppercase;
            letter-spacing: 0;
            margin-bottom: 0.2rem;
        }}
        .calmu-page-title {{
            font-size: 2rem;
            font-weight: 760;
            line-height: 1.1;
            margin: 0;
            color: var(--calmu-navy);
        }}
        .calmu-status {{
            border: 1px solid var(--calmu-border);
            border-left: 4px solid var(--calmu-green);
            background: #FFFFFF;
            padding: 0.85rem 1rem;
            border-radius: 8px;
            color: var(--calmu-navy);
        }}
        .calmu-warning {{
            border-left-color: {COLORS["red"]};
        }}
        .calmu-note {{
            color: var(--calmu-muted);
            font-size: 0.92rem;
        }}
        section[data-testid="stTabs"] button p {{
            font-weight: 650;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, kicker: str = "California Miramar University") -> None:
    st.markdown(
        f"""
        <div class="calmu-page-kicker">{kicker}</div>
        <h1 class="calmu-page-title">{title}</h1>
        """,
        unsafe_allow_html=True,
    )


def status_box(message: str, warning: bool = False) -> None:
    class_name = "calmu-status calmu-warning" if warning else "calmu-status"
    st.markdown(f'<div class="{class_name}">{message}</div>', unsafe_allow_html=True)

