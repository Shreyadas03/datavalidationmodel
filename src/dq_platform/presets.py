"""Named presets: ready-made check bundles that auto-map to the sheet's columns.

Presets are plain data built from the generic rules in the registry, so they can
be edited here without touching any rule implementation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from dq_platform.models import RuleSpec


@dataclass(frozen=True)
class PresetRule:
    """One entry of a preset: a rule plus candidate column names for each role."""

    rule_id: str
    # One list of candidate names per column the rule needs.
    column_candidates: List[List[str]] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)
    label: Optional[str] = None
    # Dataset-level rules need no columns.
    dataset_level: bool = False


@dataclass(frozen=True)
class Preset:
    name: str
    description: str
    rules: List[PresetRule]


def _normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def match_column(candidates: Sequence[str], columns: Sequence[str]) -> Optional[str]:
    """Find the best matching column for a list of candidate names."""
    normalised = {_normalise(c): c for c in columns}

    for candidate in candidates:
        key = _normalise(candidate)
        if key in normalised:
            return normalised[key]

    for candidate in candidates:
        key = _normalise(candidate)
        for norm_col, original in normalised.items():
            if key and (key in norm_col or norm_col in key):
                return original
    return None


HPE_CONTRACT_QC = Preset(
    name="HPE Contract QC",
    description=(
        "The standard HPE contract sheet checks: duplicate sales documents, date order, "
        "contract duration, blank customer names, document type counts (ZDEP/ZCRN), "
        "mandatory AMP ID and Serial Number, and CE_ID to customer-name consistency."
    ),
    rules=[
        PresetRule(
            rule_id="completeness.missing_summary",
            dataset_level=True,
            label="Missing value summary",
        ),
        PresetRule(
            rule_id="uniqueness.duplicate_rows",
            dataset_level=True,
            label="Exact duplicate rows",
        ),
        PresetRule(
            rule_id="uniqueness.duplicate_key",
            column_candidates=[["Sales Doc Nbr", "Sales Document", "Sales Doc Number", "Sales Doc"]],
            label="Duplicate Sales Doc Nbr",
        ),
        PresetRule(
            rule_id="consistency.date_order",
            column_candidates=[
                ["Hdr Start Date", "Header Start Date", "Start Date"],
                ["Hdr End Date", "Header End Date", "End Date"],
            ],
            label="End date before start date",
        ),
        PresetRule(
            rule_id="consistency.duration_range",
            column_candidates=[
                ["Hdr Start Date", "Header Start Date", "Start Date"],
                ["Hdr End Date", "Header End Date", "End Date"],
            ],
            params={"min_days": 0},
            label="Contract duration (days)",
        ),
        PresetRule(
            rule_id="completeness.null_blank",
            column_candidates=[["Party Name", "Customer Name", "Sold To Name"]],
            label="Blank customer name",
        ),
        PresetRule(
            rule_id="distribution.value_profile",
            column_candidates=[["Document Type", "Doc Type", "Sales Doc Type"]],
            label="Document type distribution",
        ),
        PresetRule(
            rule_id="distribution.category_count",
            column_candidates=[["Document Type", "Doc Type", "Sales Doc Type"]],
            params={"values": "ZDEP, ZCRN"},
            label="ZDEP / ZCRN counts",
        ),
        PresetRule(
            rule_id="completeness.null_blank",
            column_candidates=[["AMP ID", "AMPID", "AMP Identifier"]],
            label="Missing AMP ID",
        ),
        PresetRule(
            rule_id="completeness.null_blank",
            column_candidates=[["Serial Nbr", "Serial Number", "Serial No", "SerialNbr"]],
            label="Missing Serial Number",
        ),
        PresetRule(
            rule_id="consistency.one_to_one",
            column_candidates=[
                ["CE_ID", "CE ID", "CEID"],
                ["Party Name", "Customer Name", "Sold To Name"],
            ],
            label="CE_ID to customer name consistency",
        ),
    ],
)


DATA_HYGIENE_QC = Preset(
    name="Contact Data QC",
    description=(
        "Contact-detail focused checks: valid email format, hpe.com domain, valid phone "
        "numbers, and whitespace hygiene on name columns."
    ),
    rules=[
        PresetRule(
            rule_id="validity.email_format",
            column_candidates=[["Email", "Email Address", "E-mail", "Contact Email"]],
            label="Valid email format",
        ),
        PresetRule(
            rule_id="validity.email_domain",
            column_candidates=[["Email", "Email Address", "E-mail", "Contact Email"]],
            params={"domains": "hpe.com"},
            label="Email on hpe.com",
        ),
        PresetRule(
            rule_id="validity.phone_number",
            column_candidates=[["Phone", "Phone Number", "Telephone", "Contact Number", "Mobile"]],
            params={"region": "US"},
            label="Valid phone number",
        ),
        PresetRule(
            rule_id="hygiene.whitespace",
            column_candidates=[["Party Name", "Customer Name", "Contact Name", "Name"]],
            label="Stray whitespace in name",
        ),
    ],
)


PRESETS: Dict[str, Preset] = {
    HPE_CONTRACT_QC.name: HPE_CONTRACT_QC,
    DATA_HYGIENE_QC.name: DATA_HYGIENE_QC,
}


def build_preset_specs(
    preset_name: str, columns: Sequence[str]
) -> Tuple[List[RuleSpec], List[str]]:
    """Resolve a preset against the sheet's real columns.

    Returns the runnable specs plus notes describing any rule that was skipped
    because its columns are not present.
    """
    try:
        preset = PRESETS[preset_name]
    except KeyError as exc:
        raise KeyError(f"Unknown preset '{preset_name}'. Available: {', '.join(PRESETS)}") from exc

    specs: List[RuleSpec] = []
    notes: List[str] = []

    for entry in preset.rules:
        if entry.dataset_level:
            specs.append(RuleSpec(rule_id=entry.rule_id, columns=[], params=dict(entry.params), label=entry.label))
            continue

        resolved: List[str] = []
        missing: List[str] = []
        for candidates in entry.column_candidates:
            match = match_column(candidates, columns)
            if match is None:
                missing.append(candidates[0])
            else:
                resolved.append(match)

        if missing:
            notes.append(
                f"Skipped '{entry.label or entry.rule_id}': no column matching "
                f"{' / '.join(missing)} was found."
            )
            continue

        specs.append(
            RuleSpec(
                rule_id=entry.rule_id,
                columns=resolved,
                params=dict(entry.params),
                label=entry.label,
            )
        )

    return specs, notes
