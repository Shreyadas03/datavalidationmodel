# 1. How to Operate

Everything you need to run a data quality assessment on an Excel workbook.

---

## 1.1 One-time setup

From the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
.\.venv\Scripts\python.exe -m ipykernel install --user --name dq-platform --display-name "Python (dq-platform)"
```

The last line registers a Jupyter kernel so the notebook uses the virtual
environment rather than your system Python. You only do this once.

Verify the install:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

You should see all tests pass.

Need a file to practise on? This writes `data/SAMPLE AI.xlsx` with one planted
defect per check:

```powershell
.\.venv\Scripts\python.exe scripts\generate_sample_workbook.py
```

---

## 1.2 Running a report (the normal way)

1. Open [notebooks/Data_Quality_Report.ipynb](../notebooks/Data_Quality_Report.ipynb).
2. In the top-right kernel picker, select **Python (dq-platform)**.
3. Run the second cell (`app = dq_platform.build_ui(...)`). The interactive
   control panel appears below it.

Everything after this is point-and-click. The panel has five sections.

### Section 1 — Source workbook

| Control | What it does |
| --- | --- |
| **Browse…** | Opens the file picker. Picking a file fills the path and loads it immediately. |
| Excel file path | Accepts a typed or pasted path. Surrounding quotes are stripped for you. |
| **Load file** | Loads the path currently in the box. |
| Sheet | Lists every worksheet. Changing it reloads the data. |

Only the header row is read first, so the column dropdowns populate instantly
even on large workbooks. Accepted formats: `.xlsx`, `.xlsm`, `.xltx`, `.xltm`, `.xls`.

If the kernel is running somewhere without a desktop session (a remote server,
a container, WSL without an X server), **Browse…** falls back to an inline
folder browser rendered in the notebook: click a folder to open it, **Up one
folder** to go back, click a workbook then **Use this file**.

The green confirmation line tells you how many rows and columns were loaded.
If something is wrong (file missing, wrong extension), a red message explains
what happened and nothing else changes.

### Section 2 — Quick start with a preset

Pick a preset and click **Add preset checks** to load a whole bundle at once.

| Preset | Covers |
| --- | --- |
| **HPE Contract QC** | Missing-value summary, exact duplicate rows, duplicate Sales Doc Nbr, end-date-before-start-date, contract duration, blank customer name, document type distribution, ZDEP/ZCRN counts, missing AMP ID, missing Serial Number, CE_ID → customer name consistency. |
| **Contact Data QC** | Valid email format, hpe.com domain restriction, valid phone number, stray whitespace in names. |

Presets match themselves to your sheet's real column names, so
`Sales Doc Nbr`, `Sales Document` and `sales_doc_number` all resolve to the same
check. If a column genuinely is not present, that one check is skipped and a
note is recorded — the rest still run, and the note appears in both reports.

You can add a preset and then keep adding individual checks on top.

### Section 3 — Add individual validations

This is where you assemble checks one at a time.

1. **Validation** — a single dropdown grouped by dimension
   (`Completeness • Blank / null values`, `Validity • Valid email format`, …).
   A one-line description appears underneath.
2. **Column(s)** — the picker changes shape to match the rule:
   - most rules ask for one column,
   - comparison rules (date order, duration, CE_ID mapping) ask for two,
   - some rules take many columns via a multi-select with a filter box,
   - dataset-level rules (missing summary) ask for none.

   Single/dual pickers are type-to-search: start typing and the list narrows.
3. **Parameters** — only the parameters that rule supports are shown, pre-filled
   with sensible defaults (for example `domains = hpe.com`, `region = US`).
   Leave a numeric parameter blank to mean "no limit".
4. **Add this check** — validates your input and adds it to the list. Bad input
   (unknown column, `abc` in a number field) produces a message and adds nothing.

### Section 4 — Selected checks

A numbered list of everything queued up, each with a **✕** to remove it, plus
**Clear all**. Adding the same rule twice on different columns is fine and
expected.

### Section 5 — Generate the report

| Control | Meaning |
| --- | --- |
| Output folder | Created if it does not exist. Defaults to `../reports/` (parent-level `reports` folder). |
| Max flagged rows/sheet | Caps how many offending rows are written per detail sheet (default 5000) so a badly broken file cannot produce a 500 MB workbook. |
| **Run quality checks** | Runs everything and writes both reports. |

When it finishes you get a summary table plus links to the two generated files.

### Revenue comparison app (two files)

Use this when you need to compare an old and new Excel file for renewal reporting.

1. Open [notebooks/Revenue_Validation_App.ipynb](../notebooks/Revenue_Validation_App.ipynb).
2. Run the app cell (`app = dq_platform.build_revenue_validation_ui(...)`).
3. Use **Browse…** or paste paths, then load the old workbook and new workbook and choose sheets.
4. Keep default columns (`Total Net Value Global`, `Sales Channel Route Name`, `Tier 2 Reseller Id`) or override.
5. Click **Run revenue validation**.

Outputs (Excel + HTML) include:
- old/new row counts and row-count delta,
- old/new revenue totals and revenue delta,
- failing rows where `Channel profile = indirect` and `Tier 2 reseller` is blank/null.

If the notebook cannot open a desktop file picker (remote/headless kernel), it
automatically falls back to the inline folder browser.

---

## 1.3 Reading the output

Two files are written per run, timestamped so nothing is overwritten:

```
reports/Quality_Report_20260818_143512.xlsx
reports/Quality_Report_20260818_143512.html
```

### The Excel workbook

| Sheet | Contents |
| --- | --- |
| `Summary` | Source file, sheet, timestamp, row/column counts, checks run/passed/failed/errored, total flagged rows. |
| `Notes` | Only present when a preset skipped something. Explains exactly which check and which missing column. |
| `Rule_Details` | One row per check: status, rows checked, failed rows, failed %, message, and a link to that check's detail sheet. Status is colour-coded — red FAIL, green PASS, amber ERROR. |
| `Missing_Values` | Missing count and percentage per column, worst first. |
| `Column_Profile` | Dtype, non-null count, null count and distinct count per column — the `df.info()` equivalent. |
| `D1_…`, `D2_…` | Detail tables produced by profiling rules (value distributions, category counts). |
| `F1_…`, `F2_…` | The actual flagged rows for each failing check, with a **Source Row** column giving the Excel row number in your original file. |

The **Source Row** column is the one to hand back to a data owner — it points
straight at the row to fix.

### The HTML dashboard

A single self-contained file (charts are embedded, no internet needed). Open it
in any browser or attach it to an email. It shows headline pass/fail counts, a
chart per dimension, and a collapsible section per check with a preview of the
first 200 flagged rows.

---

## 1.4 Digging deeper in the notebook

The app keeps the last run in memory, so you can carry on in pandas:

```python
app.df           # the loaded sheet
app.report       # the QualityReport object
app.specs        # the checks that were run
app.excel_path   # Path to the generated workbook
app.html_path    # Path to the generated dashboard

app.report.details_frame()                 # the Rule_Details table
failing = [r for r in app.report.results if r.status == "FAIL"]
failing[0].failed_rows(app.df).head(20)    # the offending rows
```

---

## 1.5 Running it as a script

For a repeatable, schedulable run with no widgets — this is the last code cell
in the notebook, and works equally well as a `.py` file:

```python
from dq_platform import (
    RuleSpec, build_preset_specs, load_dataframe, read_header_columns,
    run_checks, write_excel_report, write_html_report,
)

EXCEL_PATH = r"data/SAMPLE AI.xlsx"
SHEET = "Contracts"

columns = read_header_columns(EXCEL_PATH, SHEET)
df = load_dataframe(EXCEL_PATH, SHEET)

specs, notes = build_preset_specs("HPE Contract QC", columns)
specs += [
    RuleSpec("validity.email_domain", ["Email"], {"domains": "hpe.com"}),
    RuleSpec("validity.phone_number", ["Phone"], {"region": "US"}),
]

report = run_checks(df, specs, source_path=EXCEL_PATH, sheet_name=SHEET, notes=notes)
write_excel_report(report, df, "reports/Quality_Report.xlsx")
write_html_report(report, df, "reports/Quality_Report.html")

print(f"{report.passed_checks} passed, {report.failed_checks} failed")
```

A `RuleSpec` is always `(rule_id, [columns], {params})`. Run the last notebook
cell to print the full catalog of rule IDs and their parameters.

---

## 1.6 The validation catalog

25 rules across six dimensions. All are selectable in the UI and usable via `RuleSpec`.

### Completeness

| Rule ID | Columns | Parameters |
| --- | --- | --- |
| `completeness.null_blank` | 1 | `treat_whitespace_as_blank` |
| `completeness.missing_summary` | none | — |
| `completeness.threshold` | many | `min_filled_pct` |

### Uniqueness

| Rule ID | Columns | Parameters |
| --- | --- | --- |
| `uniqueness.duplicate_rows` | many (empty = all) | — |
| `uniqueness.duplicate_key` | many | `ignore_blanks` |
| `uniqueness.unique_ratio` | 1 | `min_distinct_pct` |

### Validity

| Rule ID | Columns | Parameters |
| --- | --- | --- |
| `validity.email_format` | 1 | `allow_blank` |
| `validity.email_domain` | 1 | `domains`, `allow_subdomains`, `allow_blank` |
| `validity.phone_number` | 1 | `region`, `allow_blank` |
| `validity.regex_match` | 1 | `pattern`, `should_match`, `case_sensitive`, `allow_blank` |
| `validity.allowed_values` | 1 | `values`, `case_sensitive`, `allow_blank` |
| `validity.numeric_range` | 1 | `min_value`, `max_value`, `allow_blank` |
| `validity.outlier_iqr` | 1 | `iqr_multiplier` |
| `validity.dtype_numeric` | 1 | `allow_blank` |
| `validity.dtype_date` | 1 | `dayfirst`, `allow_blank` |

### Consistency

| Rule ID | Columns | Parameters |
| --- | --- | --- |
| `consistency.date_order` | 2 (start, end) | `allow_equal`, `dayfirst` |
| `consistency.duration_range` | 2 (start, end) | `min_days`, `max_days`, `dayfirst` |
| `consistency.one_to_one` | 2 (key, value) | `case_sensitive` |
| `consistency.conditional_required` | 2 (trigger, required) | `trigger_values`, `case_sensitive` |

### Hygiene

| Rule ID | Columns | Parameters |
| --- | --- | --- |
| `hygiene.whitespace` | 1 | `check_inner_spaces` |
| `hygiene.casing` | 1 | `expected_case` |
| `hygiene.special_characters` | 1 | `disallowed_pattern` |
| `hygiene.length_range` | 1 | `min_length`, `max_length` |

### Distribution

| Rule ID | Columns | Parameters |
| --- | --- | --- |
| `distribution.value_profile` | 1 | `top_n`, `max_distinct` |
| `distribution.category_count` | 1 | `values`, `case_sensitive`, `flag_others`, `min_count` |

---

## 1.7 Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `ModuleNotFoundError: dq_platform` | Wrong kernel. Select **Python (dq-platform)**. If it is missing, re-run the `ipykernel install` command. |
| Nothing renders where the app should be | ipywidgets not active in the frontend. Restart the kernel and re-run the cell. |
| `File not found` on a valid path | OneDrive paths with spaces — use **Browse…** rather than typing. |
| `Unsupported file type '.csv'` | Only Excel formats are supported today. See [Next Steps](04-next-steps-databricks.md). |
| A check shows **ERROR** | The rule raised on your data — the reason is in the Details column. One bad rule never aborts the run. |
| A preset check is missing from the output | Its column is not in your sheet. The `Notes` sheet names it. Add the check manually in section 3 against the equivalent column. |
| The Excel file is huge | Lower **Max flagged rows/sheet**. |
