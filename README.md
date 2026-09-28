# Data Quality Reporting Platform

Point it at an Excel file, pick the validations you want, get an Excel workbook and an
HTML dashboard back.

## Documentation

| Doc | Read it for |
| --- | --- |
| [How to operate](docs/01-how-to-operate.md) | Setup, every control in the UI, reading the output, the full validation catalog, troubleshooting. |
| [Architecture](docs/02-architecture.md) | How the pieces fit together, the rule contract, design decisions. |
| [Creating presets](docs/03-creating-presets.md) | Adding your own check bundles, and adding new rules. |
| [Next steps](docs/04-next-steps-databricks.md) | Proposed design for Databricks deployment and multi-source support. |

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
.\.venv\Scripts\python.exe -m ipykernel install --user --name dq-platform --display-name "Python (dq-platform)"
```

## Use it

Open [notebooks/Revenue_Validation_App.ipynb](notebooks/Revenue_Validation_App.ipynb), select the
**Python (dq-platform)** kernel, and run the first cell. It now hosts both notebook flows in one
runtime, with a toggle for **Data Quality** vs **Revenue Validation**.

1. Choose **Data Quality** for the single-source profiling/check flow, or
   **Revenue Validation** for the old-vs-new renewal comparison flow.
2. In either flow, **SQL** mode is selected by default. Switch to **Excel** when needed.
3. For **Excel** mode, click **Browse…** to pick your `.xlsx` (or paste the path), then click
   **Load file** — sheet names and column dropdowns are read from the header row.
4. For **SQL** mode, define your SQL Server connection in
   [src/dq_platform/connection.py](src/dq_platform/connection.py). Table names auto-populate when
   you switch to SQL mode, and **Refresh tables** lets you reload the latest list manually.
   Then pick the required table(s) and load.
   - If you hit `Cannot generate SSPI context` / domain-controller auth errors, switch from
     Windows auth to SQL auth by setting:
     `DQ_SQL_TRUSTED_CONNECTION=false`, `DQ_SQL_USERNAME=<user>`, `DQ_SQL_PASSWORD=<password>`.
     Optionally set `DQ_SQL_AUTHENTICATION` (example: `ActiveDirectoryPassword`) if your server needs it.
5. In **Data Quality**, click **Add preset checks** for a ready-made bundle, or add checks one at
   a time (validation → column(s) → parameters → **Add this check**). In the hybrid flow, use
   **Next: Revenue Validation** instead of running here.
6. In **Revenue Validation**, when using SQL mode for old/new sources, pick both tables and click
   the single **Load selected data** button (it shows loading state and then **Data loaded**), then
   choose validation columns from searchable dropdowns and run the comparison. It enforces this
   rule on the new file: if `Channel profile` is `indirect`, `Tier 2 reseller` must be non-empty.
   It also filters rows by selected `Document type` value (default `ZDEL`), compares old vs new totals
   using the configured `Revenue column`, reports the difference, and flags an error when the difference
   exceeds the configured threshold (default 5%).
   It also checks both old and new sources for renewal completeness: for rows where selected
   `Renewal status value` (default `Renewed`) matches, `Renewal Quote Nbr` and
   `Renewal Contract Doc Nbr` must both be non-blank; missing % is calculated only over matching rows
   and flagged when either source exceeds the configured threshold (default 5%).
   You can configure `Document type column name`, `Document type`, `ZDEL threshold %`,
   `Renewal status column`, `Renewal status value`, `Renewal quote column`,
   `Renewal contract doc column`, and `Renewal threshold %` in the UI.
7. In the hybrid flow, click **Run both and generate combined report** from the Revenue Validation
   step. It creates one combined Excel and one combined HTML report containing both Data Quality
   and Revenue Validation output. The combined HTML is ordered as: Data Quality summary, Revenue
   Validation summary, visualizations (Data Quality + Revenue charts), then details.
8. Reports land in `reports/`.

### AI Insights (optional)

The combined HTML report includes a single **AI Insights: Dashboard Summary** section (after
Data Quality and Validation, before Recommended Solutions) that never modifies or recomputes any
existing validation/rule logic. It combines:

- A whole-dashboard, business-friendly overview covering Data Quality, Revenue Validation and
  Business Case validation results, plus a short "Key Risks" list.
- Current-vs-previous-refresh changes and a rolling 3-month trend for the headline metrics
  ("Change from Previous Refresh", "3-Month Trend", "Key Observations", "Areas to Investigate").
  A lightweight local history log (`dq_history.json`) is created alongside each report's output
  folder to power the trend analysis - no other configuration is required for the calculations
  themselves.

The section's wording can optionally be generated by an AI model. The default backend is
**Azure OpenAI Service** - no public/open-source AI API is called by default, and the
`openai_compatible` provider (a generic OpenAI-style Chat Completions endpoint) is strictly
opt-in and requires an explicit base URL. Configure the backend via environment variables -
never hardcode a credential in source:

| Variable | Purpose | Default |
| --- | --- | --- |
| `DQ_AI_PROVIDER` | `azure_openai` or `openai_compatible`. | `azure_openai` |
| `DQ_AI_API_KEY` | Credential value for the selected endpoint. Unset = AI disabled. | *(none)* |
| `DQ_AI_AZURE_ENDPOINT` | Azure OpenAI resource endpoint, e.g. `https://<resource>.openai.azure.com`. Required for `azure_openai`. | *(none)* |
| `DQ_AI_AZURE_DEPLOYMENT` | Azure OpenAI deployment name. Required for `azure_openai`. | *(none)* |
| `DQ_AI_AZURE_API_VERSION` | Azure OpenAI REST API version. | `2024-06-01` |
| `DQ_AI_BASE_URL` | Base URL of an `openai_compatible` Chat Completions endpoint. Only used when `DQ_AI_PROVIDER=openai_compatible`; there is no public default. | *(none)* |
| `DQ_AI_MODEL` | Model name to request (used by the `openai_compatible` provider). | `gpt-4o-mini` |

If the AI backend is unconfigured (no credential/endpoint), or a request fails/times out, the
section falls back to a deterministic, template-built summary derived from the same calculated
statistics - the report never blocks on AI availability. The AI is only ever asked to interpret
pre-computed numbers; it is instructed to never invent figures or root causes.

If you only want the dedicated quality-only notebook, [notebooks/Data_Quality_Report.ipynb](notebooks/Data_Quality_Report.ipynb)
still works unchanged.

Want a file to try it on first?

```powershell
.\.venv\Scripts\python.exe scripts\generate_sample_workbook.py
```

This writes `data/SAMPLE AI.xlsx` with one planted defect per check.

## Scripted use

```python
from dq_platform import (
    RuleSpec, build_preset_specs, load_dataframe, read_header_columns,
    run_checks, write_excel_report, write_html_report,
)

path = r"data/SAMPLE AI.xlsx"
df = load_dataframe(path, "Contracts")

specs, notes = build_preset_specs("HPE Contract QC", read_header_columns(path, "Contracts"))
specs += [
    RuleSpec("validity.email_domain", ["Email"], {"domains": "hpe.com"}),
    RuleSpec("validity.phone_number", ["Phone"], {"region": "US"}),
]

report = run_checks(df, specs, source_path=path, sheet_name="Contracts", notes=notes)
write_excel_report(report, df, "reports/Quality_Report.xlsx")
write_html_report(report, df, "reports/Quality_Report.html")
```

## Validation catalog

| Dimension | Checks |
| --- | --- |
| Completeness | blank/null values, missing-value summary across all columns, row completeness threshold |
| Uniqueness | exact duplicate rows, duplicate business keys, distinct value ratio |
| Validity | email format, email domain (e.g. `hpe.com`), phone numbers, regex, allowed values, numeric range, IQR outliers, numeric/date type conformity |
| Consistency | end-date-before-start-date, contract duration range, key→value consistency (CE_ID → Party Name), conditionally required fields |
| Hygiene | stray whitespace, casing convention, unexpected special characters, text length |
| Distribution | value distribution profile, category counts (ZDEP/ZCRN) |

Presets: **HPE Contract QC** and **Contact Data QC**. Both are plain data in
[src/dq_platform/presets.py](src/dq_platform/presets.py) — edit them freely; they resolve
against whatever columns your sheet actually has and report anything they had to skip.

## Layout

```
notebooks/     thin widget UI
src/dq_platform/
  registry.py  the rule catalog (drives the UI, presets and engine)
  rules/       one module per quality dimension
  engine.py    runs specs, isolates failures
  presets.py   named check bundles with fuzzy column matching
  report/      Excel and HTML writers
  ai_insights/ AI narrative & 3-month trend analysis layer (history log, stats, optional AI call)
  ui/          ipywidgets front end
scripts/       sample data generator
tests/         pytest suite
```

Adding a rule: implement a runner in the matching `rules/*.py` module and register it in
`registry.py`. It appears in the notebook UI automatically.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```
