"""The rule catalog.

This module is the single source of truth: the widget UI, the presets and the
engine all read rule metadata from :data:`RULE_REGISTRY`.  Adding a rule here
automatically exposes it in the notebook UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

import pandas as pd

from dq_platform.rules import completeness, consistency, distribution, hygiene, uniqueness, validity
from dq_platform.rules.base import RuleOutcome

RuleRunner = Callable[[pd.DataFrame, Sequence[str], Dict[str, Any]], RuleOutcome]


@dataclass(frozen=True)
class ParamSpec:
    """Describes one configurable parameter so the UI can render a widget for it."""

    name: str
    label: str
    kind: str  # text | number | bool | choice
    default: Any = None
    choices: Optional[List[str]] = None
    help: str = ""
    placeholder: str = ""


@dataclass(frozen=True)
class RuleDefinition:
    """Metadata plus the callable that performs the check."""

    rule_id: str
    label: str
    dimension: str
    runner: RuleRunner
    description: str = ""
    # How many columns the rule needs: 1, 2, "many" or 0 for dataset level.
    arity: Any = 1
    column_labels: List[str] = field(default_factory=lambda: ["Column"])
    params: List[ParamSpec] = field(default_factory=list)

    def default_params(self) -> Dict[str, Any]:
        return {p.name: p.default for p in self.params if p.default is not None}


_ALLOW_BLANK = ParamSpec(
    name="allow_blank",
    label="Ignore blank values",
    kind="bool",
    default=True,
    help="When on, empty cells are not counted as format failures (use the blank check for those).",
)


RULE_DEFINITIONS: List[RuleDefinition] = [
    # ---------------------------------------------------------------- Completeness
    RuleDefinition(
        rule_id="completeness.null_blank",
        label="Blank / null values",
        dimension="Completeness",
        runner=completeness.null_blank,
        description="Flags rows where the column is empty, null or whitespace only.",
        arity=1,
        column_labels=["Column to check"],
        params=[
            ParamSpec(
                "treat_whitespace_as_blank",
                "Treat whitespace-only as blank",
                "bool",
                default=True,
            )
        ],
    ),
    RuleDefinition(
        rule_id="completeness.missing_summary",
        label="Missing value summary (all columns)",
        dimension="Completeness",
        runner=completeness.missing_summary,
        description="Profiles missing values across the whole sheet and flags incomplete rows.",
        arity=0,
        column_labels=[],
    ),
    RuleDefinition(
        rule_id="completeness.threshold",
        label="Row completeness threshold",
        dimension="Completeness",
        runner=completeness.completeness_threshold,
        description="Flags rows where fewer than N% of the selected columns are populated.",
        arity="many",
        column_labels=["Columns to measure"],
        params=[
            ParamSpec("min_filled_pct", "Minimum filled %", "number", default=100),
        ],
    ),
    # ------------------------------------------------------------------ Uniqueness
    RuleDefinition(
        rule_id="uniqueness.duplicate_rows",
        label="Exact duplicate rows",
        dimension="Uniqueness",
        runner=uniqueness.duplicate_rows,
        description="Finds rows that are identical across all columns (or a chosen subset).",
        arity="many",
        column_labels=["Columns (leave empty for all)"],
    ),
    RuleDefinition(
        rule_id="uniqueness.duplicate_key",
        label="Duplicate key values",
        dimension="Uniqueness",
        runner=uniqueness.duplicate_key,
        description="Finds repeated business keys such as Sales Doc Nbr.",
        arity="many",
        column_labels=["Key column(s)"],
        params=[
            ParamSpec("ignore_blanks", "Ignore rows with a blank key", "bool", default=True),
        ],
    ),
    RuleDefinition(
        rule_id="uniqueness.unique_ratio",
        label="Distinct value ratio",
        dimension="Uniqueness",
        runner=uniqueness.unique_ratio,
        description="Reports how many distinct values a column holds.",
        arity=1,
        column_labels=["Column to profile"],
        params=[
            ParamSpec("min_distinct_pct", "Minimum distinct % (0 = report only)", "number", default=0),
        ],
    ),
    # -------------------------------------------------------------------- Validity
    RuleDefinition(
        rule_id="validity.email_format",
        label="Valid email format",
        dimension="Validity",
        runner=validity.email_format,
        description="Checks that values look like real email addresses.",
        arity=1,
        column_labels=["Email column"],
        params=[_ALLOW_BLANK],
    ),
    RuleDefinition(
        rule_id="validity.email_domain",
        label="Email domain restriction (e.g. hpe.com)",
        dimension="Validity",
        runner=validity.email_domain,
        description="Checks that email addresses belong to one of the allowed domains.",
        arity=1,
        column_labels=["Email column"],
        params=[
            ParamSpec(
                "domains",
                "Allowed domains (comma separated)",
                "text",
                default="hpe.com",
                placeholder="hpe.com, hp.com",
            ),
            ParamSpec("allow_subdomains", "Allow subdomains", "bool", default=True),
            _ALLOW_BLANK,
        ],
    ),
    RuleDefinition(
        rule_id="validity.phone_number",
        label="Valid phone number",
        dimension="Validity",
        runner=validity.phone_number,
        description="Validates phone numbers, honouring '+' international prefixes.",
        arity=1,
        column_labels=["Phone column"],
        params=[
            ParamSpec(
                "region",
                "Default region for numbers without '+'",
                "text",
                default="US",
                placeholder="US, IN, GB, DE ...",
            ),
            _ALLOW_BLANK,
        ],
    ),
    RuleDefinition(
        rule_id="validity.regex_match",
        label="Pattern / regex match",
        dimension="Validity",
        runner=validity.regex_match,
        description="Checks values against a custom regular expression.",
        arity=1,
        column_labels=["Column to check"],
        params=[
            ParamSpec("pattern", "Regular expression", "text", placeholder=r"^[A-Z]{2}\d{6}$"),
            ParamSpec("should_match", "Values must match (off = must NOT match)", "bool", default=True),
            ParamSpec("case_sensitive", "Case sensitive", "bool", default=True),
            _ALLOW_BLANK,
        ],
    ),
    RuleDefinition(
        rule_id="validity.allowed_values",
        label="Allowed values (whitelist)",
        dimension="Validity",
        runner=validity.allowed_values,
        description="Checks that a categorical column only contains approved values.",
        arity=1,
        column_labels=["Column to check"],
        params=[
            ParamSpec(
                "values",
                "Allowed values (comma separated)",
                "text",
                placeholder="ZDEP, ZCRN, ZQTE",
            ),
            ParamSpec("case_sensitive", "Case sensitive", "bool", default=False),
            _ALLOW_BLANK,
        ],
    ),
    RuleDefinition(
        rule_id="validity.numeric_range",
        label="Numeric range",
        dimension="Validity",
        runner=validity.numeric_range,
        description="Checks that numbers fall inside the expected minimum and maximum.",
        arity=1,
        column_labels=["Numeric column"],
        params=[
            ParamSpec("min_value", "Minimum", "number"),
            ParamSpec("max_value", "Maximum", "number"),
            _ALLOW_BLANK,
        ],
    ),
    RuleDefinition(
        rule_id="validity.outlier_iqr",
        label="Statistical outliers (IQR)",
        dimension="Validity",
        runner=validity.outlier_iqr,
        description="Flags values far outside the interquartile range.",
        arity=1,
        column_labels=["Numeric column"],
        params=[
            ParamSpec("iqr_multiplier", "IQR multiplier", "number", default=1.5),
        ],
    ),
    RuleDefinition(
        rule_id="validity.dtype_numeric",
        label="Must be numeric",
        dimension="Validity",
        runner=validity.dtype_numeric,
        description="Flags values that cannot be parsed as numbers.",
        arity=1,
        column_labels=["Column to check"],
        params=[_ALLOW_BLANK],
    ),
    RuleDefinition(
        rule_id="validity.dtype_date",
        label="Must be a date",
        dimension="Validity",
        runner=validity.dtype_date,
        description="Flags values that cannot be parsed as dates.",
        arity=1,
        column_labels=["Column to check"],
        params=[
            ParamSpec("dayfirst", "Day comes first (DD/MM/YYYY)", "bool", default=False),
            _ALLOW_BLANK,
        ],
    ),
    # ----------------------------------------------------------------- Consistency
    RuleDefinition(
        rule_id="consistency.date_order",
        label="End date must not precede start date",
        dimension="Consistency",
        runner=consistency.date_order,
        description="Compares two date columns and flags reversed ranges.",
        arity=2,
        column_labels=["Start date column", "End date column"],
        params=[
            ParamSpec("allow_equal", "Allow equal dates", "bool", default=True),
            ParamSpec("dayfirst", "Day comes first (DD/MM/YYYY)", "bool", default=False),
        ],
    ),
    RuleDefinition(
        rule_id="consistency.duration_range",
        label="Contract duration in range",
        dimension="Consistency",
        runner=consistency.duration_range,
        description="Computes Duration_Days between two dates and flags out-of-bound contracts.",
        arity=2,
        column_labels=["Start date column", "End date column"],
        params=[
            ParamSpec("min_days", "Minimum days", "number", default=0),
            ParamSpec("max_days", "Maximum days", "number"),
            ParamSpec("dayfirst", "Day comes first (DD/MM/YYYY)", "bool", default=False),
        ],
    ),
    RuleDefinition(
        rule_id="consistency.one_to_one",
        label="Key maps to a single value (e.g. CE_ID -> Party Name)",
        dimension="Consistency",
        runner=consistency.one_to_one,
        description="Flags keys that are associated with conflicting values.",
        arity=2,
        column_labels=["Key column", "Value column"],
        params=[
            ParamSpec("case_sensitive", "Case sensitive comparison", "bool", default=False),
        ],
    ),
    RuleDefinition(
        rule_id="consistency.conditional_required",
        label="Conditionally required field",
        dimension="Consistency",
        runner=consistency.conditional_required,
        description="When the trigger column holds given values, the target column must be filled.",
        arity=2,
        column_labels=["Trigger column", "Required column"],
        params=[
            ParamSpec(
                "trigger_values",
                "Trigger values (comma separated)",
                "text",
                placeholder="ZDEP, ZCRN",
            ),
            ParamSpec("case_sensitive", "Case sensitive", "bool", default=False),
        ],
    ),
    # --------------------------------------------------------------------- Hygiene
    RuleDefinition(
        rule_id="hygiene.whitespace",
        label="Stray whitespace",
        dimension="Hygiene",
        runner=hygiene.whitespace,
        description="Flags leading, trailing or doubled internal spaces.",
        arity=1,
        column_labels=["Column to check"],
        params=[
            ParamSpec("check_inner_spaces", "Also flag doubled inner spaces", "bool", default=True),
        ],
    ),
    RuleDefinition(
        rule_id="hygiene.casing",
        label="Casing convention",
        dimension="Hygiene",
        runner=hygiene.casing,
        description="Flags values that break the chosen casing rule.",
        arity=1,
        column_labels=["Column to check"],
        params=[
            ParamSpec(
                "expected_case",
                "Expected casing",
                "choice",
                default="consistent",
                choices=["consistent", "upper", "lower", "title"],
                help="'consistent' flags values that differ from another value only by case.",
            ),
        ],
    ),
    RuleDefinition(
        rule_id="hygiene.special_characters",
        label="Unexpected special characters",
        dimension="Hygiene",
        runner=hygiene.special_characters,
        description="Flags characters outside the accepted character set.",
        arity=1,
        column_labels=["Column to check"],
        params=[
            ParamSpec(
                "disallowed_pattern",
                "Disallowed character pattern",
                "text",
                default=hygiene.DEFAULT_SPECIAL_CHARS,
            ),
        ],
    ),
    RuleDefinition(
        rule_id="hygiene.length_range",
        label="Text length in range",
        dimension="Hygiene",
        runner=hygiene.length_range,
        description="Flags values that are too short or too long.",
        arity=1,
        column_labels=["Column to check"],
        params=[
            ParamSpec("min_length", "Minimum length", "number"),
            ParamSpec("max_length", "Maximum length", "number"),
        ],
    ),
    # ---------------------------------------------------------------- Distribution
    RuleDefinition(
        rule_id="distribution.value_profile",
        label="Value distribution profile",
        dimension="Distribution",
        runner=distribution.value_profile,
        description="Reports value_counts for a column (informational).",
        arity=1,
        column_labels=["Column to profile"],
        params=[
            ParamSpec("top_n", "Show top N values", "number", default=25),
            ParamSpec("max_distinct", "Fail if distinct values exceed", "number"),
        ],
    ),
    RuleDefinition(
        rule_id="distribution.category_count",
        label="Category counts (e.g. ZDEP / ZCRN)",
        dimension="Distribution",
        runner=distribution.category_count,
        description="Counts specific category values and optionally flags anything else.",
        arity=1,
        column_labels=["Column to count"],
        params=[
            ParamSpec(
                "values",
                "Values to count (comma separated)",
                "text",
                placeholder="ZDEP, ZCRN",
            ),
            ParamSpec("case_sensitive", "Case sensitive", "bool", default=False),
            ParamSpec("flag_others", "Flag rows outside this list", "bool", default=False),
            ParamSpec("min_count", "Fail if a value occurs fewer than", "number"),
        ],
    ),
]


RULE_REGISTRY: Dict[str, RuleDefinition] = {r.rule_id: r for r in RULE_DEFINITIONS}


def get_rule(rule_id: str) -> RuleDefinition:
    try:
        return RULE_REGISTRY[rule_id]
    except KeyError as exc:
        raise KeyError(f"Unknown rule id '{rule_id}'.") from exc


def rules_by_dimension() -> Dict[str, List[RuleDefinition]]:
    grouped: Dict[str, List[RuleDefinition]] = {}
    for definition in RULE_DEFINITIONS:
        grouped.setdefault(definition.dimension, []).append(definition)
    return grouped
