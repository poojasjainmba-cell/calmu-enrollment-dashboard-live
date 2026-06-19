from __future__ import annotations

import json
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import BinaryIO

import pandas as pd

from .data_cleaning import dedupe_contacts, normalize_contacts, normalize_enrollments
from .goal_loader import GoalParseResult, load_goal_workbook
from .term_mapping import normalize_term_value


REFERENCE_NAMES = {
    "budget": "2026Budget.xlsx",
    "udr_conversions": "UDRConversionsJune11.xlsx",
    "paid_leads": "PaidleadsJune11.xlsx",
    "enrollment_tracker": "Summer2tracker.xlsx",
    "weekly_email": "Summer 2 Enrollment Update – Week 6 June 8-12.eml",
}

STATIC_GOAL_DIR = Path(__file__).resolve().parents[1] / "data" / "static"


@dataclass
class ReferenceBundle:
    contacts: pd.DataFrame
    enrollments: pd.DataFrame
    goals: pd.DataFrame
    starts: pd.DataFrame
    current_state: dict[str, object]
    parsed_term_columns: list[str]
    source_rows: dict[str, int]
    notes: list[str]
    parse_issues: list[str]


def _candidate_dirs() -> list[Path]:
    dirs = [Path("data/reference"), Path.home() / "Downloads"]
    return [path for path in dirs if path.exists()]


def find_reference_files(reference_dir: str | Path | None = None) -> dict[str, Path]:
    dirs = []
    if reference_dir:
        dirs.append(Path(reference_dir))
    dirs.extend(_candidate_dirs())
    found: dict[str, Path] = {}
    for key, filename in REFERENCE_NAMES.items():
        for directory in dirs:
            candidate = directory / filename
            if candidate.exists():
                found[key] = candidate
                break
    return found


def _read_excel_sheets(source: str | Path | BinaryIO) -> dict[str, pd.DataFrame]:
    try:
        return pd.read_excel(source, sheet_name=None, dtype=object)
    except Exception:
        return {}


def _contact_sheets(source: str | Path | BinaryIO, source_system: str) -> tuple[list[pd.DataFrame], dict[str, int]]:
    frames: list[pd.DataFrame] = []
    source_rows: dict[str, int] = {}
    for sheet_name, df in _read_excel_sheets(source).items():
        lowered = {str(col).strip().lower() for col in df.columns}
        if "record id" in lowered and "email" in lowered:
            normalized = normalize_contacts(df, source_system=source_system)
            frames.append(normalized)
            source_rows[f"{source_system}:{sheet_name}"] = len(normalized)
    return frames, source_rows


def _enrollment_sheet(source: str | Path | BinaryIO) -> pd.DataFrame:
    sheets = _read_excel_sheets(source)
    if not sheets:
        return pd.DataFrame()
    for sheet_name in sheets:
        if sheet_name.lower().startswith("enroll"):
            title_rows = pd.read_excel(source, sheet_name=sheet_name, header=None, nrows=2, dtype=object)
            title_values = [normalize_term_value(value) for value in title_rows.to_numpy().flatten()]
            default_term = next((value for value in title_values if value in {"Spring 1", "Spring 2", "Summer 1", "Summer 2", "Fall 1", "Fall 2"}), "")
            df = pd.read_excel(source, sheet_name=sheet_name, header=1, dtype=object)
            normalized = normalize_enrollments(df)
            if default_term and not normalized.empty:
                normalized["term_label"] = default_term
                normalized["reference_term_label"] = default_term
            return normalized
    return pd.DataFrame()


def _email_note(source: str | Path | BinaryIO) -> str:
    try:
        if hasattr(source, "read"):
            raw = source.read()
            if hasattr(source, "seek"):
                source.seek(0)
        else:
            raw = Path(source).read_bytes()
        msg = BytesParser(policy=policy.default).parsebytes(raw)
        subject = msg.get("subject", "Weekly enrollment update")
        date = msg.get("date", "date unavailable")
        return f"Weekly update reference loaded: {subject} ({date})."
    except Exception as exc:
        return f"Weekly update email could not be parsed: {exc}"


def _read_static_goals() -> GoalParseResult:
    goals_path = STATIC_GOAL_DIR / "2026_goals.csv"
    starts_path = STATIC_GOAL_DIR / "2026_starts.csv"
    current_state_path = STATIC_GOAL_DIR / "2026_current_state.json"
    if not goals_path.exists() or not current_state_path.exists():
        return GoalParseResult(pd.DataFrame(), pd.DataFrame(), {}, [], ["No budget workbook provided."])

    goals = pd.read_csv(goals_path)
    starts = pd.read_csv(starts_path) if starts_path.exists() else pd.DataFrame()
    metadata = json.loads(current_state_path.read_text())
    numeric_columns = ["budget_total", "variance", "pct_to_goal", "sort_order", "actual", "goal"]
    for frame in [goals, starts]:
        for column in numeric_columns:
            if column in frame:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return GoalParseResult(
        goals=goals,
        starts=starts,
        current_state=metadata.get("current_state", {}),
        parsed_term_columns=metadata.get("parsed_term_columns", []),
        parse_issues=metadata.get("parse_issues", []),
    )


def load_reference_bundle(paths: dict[str, str | Path | BinaryIO]) -> ReferenceBundle:
    contact_frames: list[pd.DataFrame] = []
    source_rows: dict[str, int] = {}
    notes: list[str] = []
    parse_issues: list[str] = []

    for key in ("paid_leads", "udr_conversions"):
        source = paths.get(key)
        if not source:
            continue
        frames, rows = _contact_sheets(source, source_system=key.replace("_", " ").title())
        contact_frames.extend(frames)
        source_rows.update(rows)

    contacts = pd.concat(contact_frames, ignore_index=True) if contact_frames else pd.DataFrame()
    if not contacts.empty:
        contacts = dedupe_contacts(contacts)

    enrollments = pd.DataFrame()
    if paths.get("enrollment_tracker"):
        enrollments = _enrollment_sheet(paths["enrollment_tracker"])
        source_rows["Enrollment tracker"] = len(enrollments)

    if paths.get("budget"):
        goal_result = load_goal_workbook(paths["budget"])
        source_rows["Budget workbook goals"] = len(goal_result.goals)
        parse_issues.extend(goal_result.parse_issues)
    else:
        goal_result = _read_static_goals()
        if not goal_result.goals.empty:
            source_rows["Static 2026 budget goals"] = len(goal_result.goals)
        parse_issues.extend(goal_result.parse_issues)

    if paths.get("weekly_email"):
        notes.append(_email_note(paths["weekly_email"]))

    return ReferenceBundle(
        contacts=contacts,
        enrollments=enrollments,
        goals=goal_result.goals,
        starts=goal_result.starts,
        current_state=goal_result.current_state,
        parsed_term_columns=goal_result.parsed_term_columns,
        source_rows=source_rows,
        notes=notes,
        parse_issues=parse_issues,
    )
