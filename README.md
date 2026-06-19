# CalMU Enrollment Dashboard

Streamlit leadership dashboard for California Miramar University enrollment, UDR, source, program, activity, and goal performance.

The app is live-first when `HUBSPOT_ACCESS_TOKEN` is configured. Excel workbooks are treated as reference, fallback, and validation sources, especially for budget/current-state goals.

## Main Pages

- Executive Overview
- UDR Performance
- Source & Program Performance
- Data Quality / Assumptions

Related detail is handled with tabs and expanders inside those four pages.

## Key Reference Validation

The budget workbook parser validates:

- Annual goal: `858`
- Current enrolled fallback: `411`
- Current starts fallback: `318`
- Start rate fallback: about `77.37%`
- Term actual/goal columns including `SP-1 A`, `SP1-G`, `SP2-A`, `SP2-G`, `SU1-A`, `SU1-G`, `SU2 -A`, `SU2- G`, `FA1- A`, `FA1 -G`, `FA2 -A`, `FA2 -G`

HubSpot verified enrollment/start fields take priority when available. The workbook values are labeled as fallback/reference when used.

## HubSpot Scopes

Required contact scopes:

- `crm.objects.contacts.read`
- `crm.schemas.contacts.read`
- `crm.lists.read` if list membership is needed

Recommended activity scopes:

- calls read
- emails read
- meetings read
- tasks read
- notes read
- communications/messages read if available

If activity scopes are missing, the dashboard remains usable and QA shows which activity objects were unavailable.

## Secrets

For Streamlit Community Cloud, add:

```toml
HUBSPOT_ACCESS_TOKEN = "your-hubspot-private-app-token"
```

Optional development caps for very large portals:

```toml
HUBSPOT_MAX_CONTACT_PAGES = "50"
HUBSPOT_MAX_ACTIVITY_PAGES_PER_OBJECT = "20"
```

Leave those blank in production to fetch all available pages.

## Local Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The app also supports `.env` for local development.

## Streamlit Community Cloud Deployment

Deploy from this GitHub repository with:

- Branch: `main`
- Main file path: `app.py`
- Python: Streamlit Cloud default, currently Python 3.12

In Advanced settings, paste the `HUBSPOT_ACCESS_TOKEN` entry into the Secrets field. Do not commit `.streamlit/secrets.toml`.

## Definitions

- Applicant = Lifecycle Stage equals `Applicant`.
- CRM Enrolled = Lifecycle Stage equals `Enrolled`.
- Actual Enrolled = verified enrollment field/status from HubSpot if available; otherwise fallback/reference only.
- Starts = students who actually started and did not drop before starting.
- Bad Lead = Lifecycle Stage equals `Not a Lead` or Lead Status is `Dead Lead`, `Do Not Contact`, `Duplicate Lead`, or `App Submitted - Unqualified`.
- Lead-to-contact = contacted/progressed leads divided by total leads.
- Lead-to-applicant = applicants divided by total leads.
- Lead-to-enrolled = actual enrolled divided by total leads when actual is available; otherwise CRM enrolled divided by total leads and labeled CRM-only.
- Start % = starts divided by enrolled.
- Time to enroll = enrollment date minus contact create date, or tracker days-to-enroll fallback.
- Avg talk time = average HubSpot call duration for associated calls.

## Privacy

- Read-only analytics mode.
- No HubSpot writes.
- No emails sent.
- No source data deletion.
- Executive pages avoid student/contact-level PII.
- Optional audit data masks email by default.

## Brand

The dashboard uses the CalMU 2025 brand palette and restrained institutional styling: CalMU blue, navy, pale blue, green, and limited red alert accents.
