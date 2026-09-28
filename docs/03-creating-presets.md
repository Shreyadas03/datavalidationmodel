# 3. How to Create New Presets

A preset is a named bundle of checks that maps itself onto whatever sheet you
point it at. Adding one is a data edit in a single file —
[src/dq_platform/presets.py](../src/dq_platform/presets.py) — with no changes to
the UI, the engine or any rule.

---

## 3.1 The two building blocks

```python
@dataclass(frozen=True)
class PresetRule:
    rule_id: str                          # which check, from the registry
    column_candidates: List[List[str]]    # one list of aliases per column role
    params: Dict[str, Any]                # parameter overrides
    label: Optional[str]                  # what it is called in the report
    dataset_level: bool                   # True for rules that need no columns


@dataclass(frozen=True)
class Preset:
    name: str          # what appears in the UI dropdown
    description: str   # the help text under it
    rules: List[PresetRule]
```

`column_candidates` is a **list of lists**. The outer list has one entry per
column the rule needs; the inner list holds the alias names to try for that
role, best guess first.

```python
# one column
column_candidates=[["Serial Nbr", "Serial Number", "Serial No"]]

# two columns: start date, then end date
column_candidates=[
    ["Hdr Start Date", "Header Start Date", "Start Date"],
    ["Hdr End Date",   "Header End Date",   "End Date"],
]
```

---

## 3.2 How column matching works

`match_column()` normalises every name to lowercase alphanumeric — spaces,
underscores, hyphens and punctuation are stripped — then makes two passes:

1. **Exact match** on the normalised name, trying each candidate in order.
2. **Substring match** in either direction, again in candidate order.

So a single candidate `"Sales Doc Nbr"` matches all of:

```
Sales Doc Nbr    SALES DOC NBR    sales_doc_nbr    Sales-Doc-Nbr    salesdocnbr
```

The substring pass is what makes `"Serial Nbr"` match a column literally named
`Serial Nbr (Primary)`. It is also why **candidate order matters**: put the most
specific alias first. A candidate list of `["Date", "Hdr Start Date"]` would
match `Hdr End Date` via the substring pass before ever reaching the specific
alias.

If no candidate matches, the check is skipped and a note is recorded. The rest
of the preset still runs.

---

## 3.3 Building a preset — worked example

Say you want a **Renewals QC** preset for a renewals extract.

### Step 1 — Find the rule IDs you need

Run the last cell of the notebook to print the catalog, or see the tables in
[How to Operate](01-how-to-operate.md#16-the-validation-catalog). Pick the
generic rules that express your intent:

| Intent | Rule ID |
| --- | --- |
| Renewal ID must be unique | `uniqueness.duplicate_key` |
| Renewal date must be a real date | `validity.dtype_date` |
| Status must be one of a known set | `validity.allowed_values` |
| Renewal value must be positive | `validity.numeric_range` |
| If status is "Won", close date is required | `consistency.conditional_required` |
| Account owner email must be hpe.com | `validity.email_domain` |

### Step 2 — Write the preset

Add this to `presets.py`, above the `PRESETS` dictionary:

```python
RENEWALS_QC = Preset(
    name="Renewals QC",
    description=(
        "Renewal pipeline checks: unique renewal IDs, valid dates and statuses, "
        "positive contract value, mandatory close date on won deals, and internal "
        "owner emails."
    ),
    rules=[
        PresetRule(
            rule_id="completeness.missing_summary",
            dataset_level=True,
            label="Missing value summary",
        ),
        PresetRule(
            rule_id="uniqueness.duplicate_key",
            column_candidates=[["Renewal ID", "Renewal Nbr", "Renewal Number"]],
            label="Duplicate Renewal ID",
        ),
        PresetRule(
            rule_id="validity.dtype_date",
            column_candidates=[["Renewal Date", "Renewal Dt"]],
            label="Renewal date is a valid date",
        ),
        PresetRule(
            rule_id="validity.allowed_values",
            column_candidates=[["Status", "Renewal Status", "Opportunity Status"]],
            params={"values": "Open, Won, Lost, Cancelled"},
            label="Status is a known value",
        ),
        PresetRule(
            rule_id="validity.numeric_range",
            column_candidates=[["Renewal Value", "Contract Value", "TCV"]],
            params={"min_value": 0},
            label="Renewal value is not negative",
        ),
        PresetRule(
            rule_id="consistency.conditional_required",
            column_candidates=[
                ["Status", "Renewal Status"],      # the trigger column
                ["Close Date", "Closed Date"],     # the column that becomes required
            ],
            params={"trigger_values": "Won"},
            label="Won deals must have a close date",
        ),
        PresetRule(
            rule_id="validity.email_domain",
            column_candidates=[["Owner Email", "Account Owner Email", "Email"]],
            params={"domains": "hpe.com"},
            label="Owner email is internal",
        ),
    ],
)
```

### Step 3 — Register it

```python
PRESETS: Dict[str, Preset] = {
    HPE_CONTRACT_QC.name: HPE_CONTRACT_QC,
    DATA_HYGIENE_QC.name: DATA_HYGIENE_QC,
    RENEWALS_QC.name: RENEWALS_QC,          # <-- add this line
}
```

That is the whole change. The UI reads `PRESETS` when it builds the dropdown, so
**Renewals QC** appears the next time the app is created.

### Step 4 — Verify it resolves

Restart the kernel, re-run the app cell, load your sheet and click **Add preset
checks**. Or check it headlessly:

```python
from dq_platform import build_preset_specs, read_header_columns

columns = read_header_columns("data/renewals.xlsx", "Sheet1")
specs, notes = build_preset_specs("Renewals QC", columns)

for spec in specs:
    print(f"{spec.label:45} -> {spec.columns}")
print("\nSkipped:")
for note in notes:
    print(" ", note)
```

**An empty `notes` list means every candidate resolved.** If something was
skipped, the note names the check and the column it could not find — either add
the real column name to that candidate list, or accept the skip.

---

## 3.4 Recipes

### A dataset-level rule (no columns)

```python
PresetRule(
    rule_id="uniqueness.duplicate_rows",
    dataset_level=True,
    label="Exact duplicate rows",
)
```

Set `dataset_level=True` and omit `column_candidates` entirely.

### The same rule twice on different columns

Perfectly normal — give each a distinct label so the report is readable:

```python
PresetRule(rule_id="completeness.null_blank",
           column_candidates=[["AMP ID", "AMPID"]],
           label="Missing AMP ID"),
PresetRule(rule_id="completeness.null_blank",
           column_candidates=[["Serial Nbr", "Serial Number"]],
           label="Missing Serial Number"),
```

### Expected category counts

```python
PresetRule(
    rule_id="distribution.category_count",
    column_candidates=[["Document Type", "Doc Type"]],
    params={"values": "ZDEP, ZCRN", "min_count": 50},
    label="ZDEP / ZCRN counts",
)
```

With `min_count`, the check fails at the dataset level if a category falls short
— it reports the shortfall without flagging individual rows.

### A regex rule for a house format

```python
PresetRule(
    rule_id="validity.regex_match",
    column_candidates=[["Contract Nbr", "Contract Number"]],
    params={"pattern": r"^HPE-\d{8}$"},
    label="Contract number format",
)
```

### List-valued parameters

Anything that takes a list is written as a comma-separated string:

```python
params={"values": "Open, Won, Lost"}
params={"domains": "hpe.com, hpe.co.uk"}
```

---

## 3.5 Guidelines

| Do | Why |
| --- | --- |
| Order candidates most-specific first | The substring pass will otherwise match the wrong column. |
| Write labels as a business statement | "Won deals must have a close date" reads better in a report than "Conditionally required field". |
| Include the aliases you have actually seen | Two or three real variants beat ten invented ones. |
| Set `params` for anything not at its default | Presets should be runnable with zero configuration. |
| Verify against a real extract and check `notes` is empty | Silent skips are the main failure mode. |

| Avoid | Why |
| --- | --- |
| Generic candidates like `["Date"]` or `["ID"]` | They substring-match almost anything. |
| Bundling 40 checks into one preset | Reports become unreadable. Split by concern and add two presets. |
| Creating a new rule when a generic one plus params will do | `validity.regex_match` and `validity.allowed_values` cover most bespoke formats. |

---

## 3.6 When you need a genuinely new rule

If no registry rule expresses the check, add one. It is three steps.

### Step 1 — Write the runner

In the relevant `src/dq_platform/rules/*.py`:

```python
def checksum_valid(df, columns, params):
    """Flags IDs whose trailing check digit does not match."""
    column = require_columns(df, columns, count=1)[0]
    allow_blank = bool(get_param(params, "allow_blank", True))

    series = df[column].astype("string")
    blanks = blank_mask(series)

    def is_valid(value: str) -> bool:
        digits = [int(c) for c in value if c.isdigit()]
        return bool(digits) and sum(digits[:-1]) % 10 == digits[-1]

    mask = ~series.fillna("").map(is_valid)
    if allow_blank:
        mask = mask & ~blanks

    return outcome(mask, message=f"{int(mask.sum())} invalid checksum(s) in '{column}'.")
```

The contract: take `(df, columns, params)`, return `outcome(mask, message=...)`
where `True` in the mask means *this row failed*. Raise `ValueError` for bad
configuration — the engine turns it into an `ERROR` row rather than crashing.

### Step 2 — Register it

In `registry.py`, add to `RULE_DEFINITIONS`:

```python
RuleDefinition(
    rule_id="validity.checksum",
    label="Valid check digit",
    dimension="Validity",
    runner=validity.checksum_valid,
    description="Verifies the trailing check digit of an identifier.",
    arity=1,
    column_labels=["Identifier column"],
    params=[_ALLOW_BLANK],
),
```

It now appears in the UI dropdown with the right column picker and parameter
widgets. No UI code changes.

### Step 3 — Test it

Add a case to `tests/test_rules.py`:

```python
def test_checksum_flags_bad_check_digit():
    df = pd.DataFrame({"ID": ["1231", "1232"]})
    result = run_rule(df, RuleSpec("validity.checksum", ["ID"]))
    assert result.failed_count == 1
```

Then use it in a preset like any other rule.

---

## 3.7 Checklist

- [ ] Rule IDs exist in the registry (confirm with the catalog cell)
- [ ] One inner candidate list per column the rule needs, in the right order
- [ ] Most-specific alias first in each list
- [ ] `dataset_level=True` set on rules that take no columns
- [ ] Non-default parameters supplied
- [ ] Labels read as business statements
- [ ] Preset added to the `PRESETS` dict
- [ ] `build_preset_specs()` verified against a real extract with empty `notes`
- [ ] Kernel restarted so the UI picks up the change
