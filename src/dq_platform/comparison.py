"""Two-workbook revenue comparison with conditional validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from dq_platform.io_utils import list_sheets, load_dataframe, resolve_path
from dq_platform.presets import match_column
from dq_platform.rules import consistency


@dataclass
class RevenueComparisonReport:
    old_path: str
    new_path: str
    old_sheet: str
    new_sheet: str
    revenue_column_old: str
    revenue_column_new: str
    channel_profile_column: str
    tier2_reseller_column: str
    old_row_count: int
    new_row_count: int
    row_count_delta: int
    old_revenue_sum: float
    new_revenue_sum: float
    revenue_delta: float
    old_non_numeric_revenue_count: int
    new_non_numeric_revenue_count: int
    indirect_row_count: int
    indirect_missing_tier2_count: int
    conditional_message: str
    zdel_document_type_column_old: str
    zdel_document_type_column_new: str
    zdel_document_type_value: str
    zdel_threshold_pct: float
    zdel_check_applied: bool
    zdel_old_sum: float
    zdel_new_sum: float
    zdel_delta: float
    zdel_delta_pct: Optional[float]
    zdel_threshold_exceeded: bool
    zdel_threshold_message: str
    renewal_status_column_old: str
    renewal_status_column_new: str
    renewal_status_value: str
    renewal_quote_number_column_old: str
    renewal_quote_number_column_new: str
    renewal_contract_doc_number_column_old: str
    renewal_contract_doc_number_column_new: str
    renewal_threshold_pct: float
    renewal_old_filtered_count: int
    renewal_old_missing_count: int
    renewal_old_missing_pct: float
    renewal_new_filtered_count: int
    renewal_new_missing_count: int
    renewal_new_missing_pct: float
    renewal_threshold_exceeded: bool
    renewal_threshold_message: str
    subregion_column_used: Optional[str] = None
    tier2_missing_by_geography: pd.DataFrame = field(default_factory=pd.DataFrame)
    tier2_top_geography: Optional[str] = None
    tier2_missing_pct: float = 0.0
    tier2_impact_revenue_pct: Optional[float] = None
    tier2_severity: str = "Low"
    invalid_rows: pd.DataFrame = field(default_factory=pd.DataFrame)
    generated_at: datetime = field(default_factory=datetime.now)

    def summary_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                ("Old workbook", self.old_path),
                ("Old sheet", self.old_sheet),
                ("New workbook", self.new_path),
                ("New sheet", self.new_sheet),
                ("Old rows", self.old_row_count),
                ("New rows", self.new_row_count),
                ("Row count delta (new - old)", self.row_count_delta),
                ("Old revenue column", self.revenue_column_old),
                ("New revenue column", self.revenue_column_new),
                ("Old revenue total", round(self.old_revenue_sum, 2)),
                ("New revenue total", round(self.new_revenue_sum, 2)),
                ("Revenue delta (new - old)", round(self.revenue_delta, 2)),
                ("Old non-numeric revenue values", self.old_non_numeric_revenue_count),
                ("New non-numeric revenue values", self.new_non_numeric_revenue_count),
                ("Channel profile column", self.channel_profile_column),
                ("Tier 2 reseller column", self.tier2_reseller_column),
                ("Rows with indirect channel profile", self.indirect_row_count),
                ("Indirect rows missing Tier 2 reseller", self.indirect_missing_tier2_count),
                ("Conditional validation message", self.conditional_message),
                ("Subregion column used", self.subregion_column_used or "N/A"),
                ("Tier 2 top geography (most missing)", self.tier2_top_geography or "N/A"),
                ("Tier 2 missing % (of indirect rows)", round(self.tier2_missing_pct, 2)),
                (
                    "Tier 2 revenue impact %",
                    round(self.tier2_impact_revenue_pct, 2)
                    if self.tier2_impact_revenue_pct is not None
                    else "N/A",
                ),
                ("Tier 2 severity", self.tier2_severity),
                ("ZDEL document type column (old)", self.zdel_document_type_column_old),
                ("ZDEL document type column (new)", self.zdel_document_type_column_new),
                ("Document type value", self.zdel_document_type_value),
                ("ZDEL threshold %", round(self.zdel_threshold_pct, 2)),
                ("ZDEL check applied", "Yes" if self.zdel_check_applied else "No"),
                ("Old revenue total for selected document type", round(self.zdel_old_sum, 2)),
                ("New revenue total for selected document type", round(self.zdel_new_sum, 2)),
                ("Revenue delta for selected document type (new - old)", round(self.zdel_delta, 2)),
                (
                    "Revenue delta % of old for selected document type",
                    round(self.zdel_delta_pct, 2) if self.zdel_delta_pct is not None else "N/A",
                ),
                (
                    f"ZDEL threshold exceeded (>{round(self.zdel_threshold_pct, 2)}%)",
                    "Yes" if self.zdel_threshold_exceeded else "No",
                ),
                ("ZDEL threshold message", self.zdel_threshold_message),
                ("Renewal status column (old)", self.renewal_status_column_old),
                ("Renewal status column (new)", self.renewal_status_column_new),
                ("Renewal status value", self.renewal_status_value),
                ("Renewal quote nbr column (old)", self.renewal_quote_number_column_old),
                ("Renewal quote nbr column (new)", self.renewal_quote_number_column_new),
                (
                    "Renewal contract doc nbr column (old)",
                    self.renewal_contract_doc_number_column_old,
                ),
                (
                    "Renewal contract doc nbr column (new)",
                    self.renewal_contract_doc_number_column_new,
                ),
                ("Renewal threshold %", round(self.renewal_threshold_pct, 2)),
                ("Old rows with selected renewal status", self.renewal_old_filtered_count),
                ("Old rows missing renewal quote/contract", self.renewal_old_missing_count),
                ("Old missing % for selected renewal status", round(self.renewal_old_missing_pct, 2)),
                ("New rows with selected renewal status", self.renewal_new_filtered_count),
                ("New rows missing renewal quote/contract", self.renewal_new_missing_count),
                ("New missing % for selected renewal status", round(self.renewal_new_missing_pct, 2)),
                (
                    f"Renewal threshold exceeded (>{round(self.renewal_threshold_pct, 2)}%)",
                    "Yes" if self.renewal_threshold_exceeded else "No",
                ),
                ("Renewal threshold message", self.renewal_threshold_message),
                ("Generated at", self.generated_at.strftime("%Y-%m-%d %H:%M:%S")),
            ],
            columns=["Metric", "Value"],
        )


def _resolve_sheet(path: Path, sheet_name: Optional[str]) -> str:
    if sheet_name and str(sheet_name).strip():
        return str(sheet_name)
    sheets = list_sheets(path)
    if not sheets:
        raise ValueError(f"No sheets found in workbook: {path}")
    return sheets[0]


def _resolve_column(
    columns: Sequence[str],
    provided_name: Optional[str],
    default_name: str,
    field_label: str,
    file_label: str,
) -> str:
    available = [str(col) for col in columns]
    requested = str(provided_name).strip() if provided_name is not None else ""

    if requested:
        match = match_column([requested], available)
        if match is None:
            raise ValueError(
                f"{field_label} column '{requested}' was not found in {file_label}. "
                f"Available columns: {', '.join(available)}"
            )
        return match

    fallback = match_column([default_name], available)
    if fallback is None:
        raise ValueError(
            f"{field_label} column was not provided and default '{default_name}' "
            f"was not found in {file_label}. Available columns: {', '.join(available)}"
        )
    return fallback


def _sum_revenue(series: pd.Series) -> tuple[float, int]:
    numeric = pd.to_numeric(series, errors="coerce")
    non_null = int(series.notna().sum())
    numeric_count = int(numeric.notna().sum())
    non_numeric = max(0, non_null - numeric_count)
    return float(numeric.sum(skipna=True)), non_numeric


def _blank_mask(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip()
    return text.isna() | text.eq("")


def _build_zdel_check(
    old_df: pd.DataFrame,
    new_df: pd.DataFrame,
    *,
    old_source_label: str,
    new_source_label: str,
    document_type_column: Optional[str],
    document_type_value: Optional[str],
    old_revenue_column: str,
    new_revenue_column: str,
    threshold_pct: float,
) -> tuple[str, str, str, bool, float, float, float, Optional[float], bool, str]:
    document_type_old = _resolve_column(
        old_df.columns,
        document_type_column,
        "Document type",
        "Document type",
        old_source_label,
    )
    document_type_new = _resolve_column(
        new_df.columns,
        document_type_column,
        "Document type",
        "Document type",
        new_source_label,
    )
    selected_document_type = str(document_type_value).strip() if document_type_value is not None else ""
    if not selected_document_type:
        selected_document_type = "ZDEL"

    old_doc_text = old_df[document_type_old].astype("string").str.strip().str.upper()
    new_doc_text = new_df[document_type_new].astype("string").str.strip().str.upper()
    selected_document_type_text = selected_document_type.upper()
    old_zdel_sum, _old_non_numeric = _sum_revenue(
        old_df.loc[old_doc_text.eq(selected_document_type_text), old_revenue_column]
    )
    new_zdel_sum, _new_non_numeric = _sum_revenue(
        new_df.loc[new_doc_text.eq(selected_document_type_text), new_revenue_column]
    )
    zdel_delta = new_zdel_sum - old_zdel_sum

    if old_zdel_sum == 0:
        if new_zdel_sum == 0:
            zdel_delta_pct = 0.0
        else:
            zdel_delta_pct = None
    else:
        zdel_delta_pct = (abs(zdel_delta) / abs(old_zdel_sum)) * 100

    exceeds = False
    if zdel_delta_pct is None:
        exceeds = new_zdel_sum != 0
    else:
        exceeds = zdel_delta_pct > threshold_pct

    if exceeds:
        delta_pct_text = f"{round(zdel_delta_pct, 2)}%" if zdel_delta_pct is not None else "N/A"
        message = (
            f"{selected_document_type} revenue delta of {delta_pct_text} exceeds the "
            f"{round(threshold_pct, 2)}% threshold (old: {round(old_zdel_sum, 2)}, "
            f"new: {round(new_zdel_sum, 2)}, diff: {round(zdel_delta, 2)})."
        )
    else:
        message = (
            f"{selected_document_type} revenue total is within the "
            f"{round(threshold_pct, 2)}% threshold."
        )

    return (
        document_type_old,
        document_type_new,
        selected_document_type,
        True,
        old_zdel_sum,
        new_zdel_sum,
        zdel_delta,
        zdel_delta_pct,
        exceeds,
        message,
    )


def _build_renewal_check(
    old_df: pd.DataFrame,
    new_df: pd.DataFrame,
    *,
    old_source_label: str,
    new_source_label: str,
    renewal_status_column: Optional[str],
    renewal_status_value: Optional[str],
    renewal_quote_number_column: Optional[str],
    renewal_contract_doc_number_column: Optional[str],
    threshold_pct: float,
) -> tuple[str, str, str, str, str, str, str, int, int, float, int, int, float, bool, str]:
    status_column_old = _resolve_column(
        old_df.columns,
        renewal_status_column,
        "Renewal Status",
        "Renewal status",
        old_source_label,
    )
    status_column_new = _resolve_column(
        new_df.columns,
        renewal_status_column,
        "Renewal Status",
        "Renewal status",
        new_source_label,
    )
    quote_column_old = _resolve_column(
        old_df.columns,
        renewal_quote_number_column,
        "Renewal Quote Nbr",
        "Renewal quote nbr",
        old_source_label,
    )
    quote_column_new = _resolve_column(
        new_df.columns,
        renewal_quote_number_column,
        "Renewal Quote Nbr",
        "Renewal quote nbr",
        new_source_label,
    )
    contract_column_old = _resolve_column(
        old_df.columns,
        renewal_contract_doc_number_column,
        "Renewal Contract Doc Nbr",
        "Renewal contract doc nbr",
        old_source_label,
    )
    contract_column_new = _resolve_column(
        new_df.columns,
        renewal_contract_doc_number_column,
        "Renewal Contract Doc Nbr",
        "Renewal contract doc nbr",
        new_source_label,
    )

    selected_status = str(renewal_status_value).strip() if renewal_status_value is not None else ""
    if not selected_status:
        selected_status = "Renewed"
    selected_status_key = selected_status.upper()

    def _compute(frame: pd.DataFrame, status_col: str, quote_col: str, contract_col: str) -> tuple[int, int, float]:
        status_text = frame[status_col].astype("string").str.strip().str.upper()
        status_mask = status_text.eq(selected_status_key).fillna(False)
        filtered_count = int(status_mask.sum())
        missing_mask = status_mask & (_blank_mask(frame[quote_col]) | _blank_mask(frame[contract_col]))
        missing_count = int(missing_mask.sum())
        if filtered_count == 0:
            return filtered_count, missing_count, 0.0
        return filtered_count, missing_count, (missing_count / filtered_count) * 100

    old_filtered_count, old_missing_count, old_missing_pct = _compute(
        old_df,
        status_column_old,
        quote_column_old,
        contract_column_old,
    )
    new_filtered_count, new_missing_count, new_missing_pct = _compute(
        new_df,
        status_column_new,
        quote_column_new,
        contract_column_new,
    )

    exceeds = old_missing_pct > threshold_pct or new_missing_pct > threshold_pct
    if exceeds:
        message = (
            f'Renewal completeness exceeds {round(threshold_pct, 2)}% '
            f'(old: {round(old_missing_pct, 2)}%, new: {round(new_missing_pct, 2)}%).'
        )
    else:
        message = (
            f"Renewal completeness is within the {round(threshold_pct, 2)}% threshold "
            f"(old: {round(old_missing_pct, 2)}%, new: {round(new_missing_pct, 2)}%)."
        )

    return (
        status_column_old,
        status_column_new,
        selected_status,
        quote_column_old,
        quote_column_new,
        contract_column_old,
        contract_column_new,
        old_filtered_count,
        old_missing_count,
        old_missing_pct,
        new_filtered_count,
        new_missing_count,
        new_missing_pct,
        exceeds,
        message,
    )


def build_revenue_comparison_report_from_dataframes(
    old_df: pd.DataFrame,
    new_df: pd.DataFrame,
    *,
    old_source_label: str,
    new_source_label: str,
    old_selection_label: str,
    new_selection_label: str,
    revenue_column: Optional[str] = "Total Net Value Global",
    channel_profile_column: Optional[str] = "Sales Channel Route Name",
    tier2_reseller_column: Optional[str] = "Tier 2 Reseller Id",
    zdel_document_type_column: Optional[str] = "Document type",
    zdel_document_type_value: Optional[str] = "ZDEL",
    zdel_threshold_pct: float = 5.0,
    renewal_status_column: Optional[str] = "Renewal Status",
    renewal_status_value: Optional[str] = "Renewed",
    renewal_quote_number_column: Optional[str] = "Renewal Quote Nbr",
    renewal_contract_doc_number_column: Optional[str] = "Renewal Contract Doc Nbr",
    renewal_threshold_pct: float = 5.0,
    subregion_column: Optional[str] = None,
) -> RevenueComparisonReport:
    """Compare row/revenue deltas for already-loaded DataFrames."""
    old_revenue_col = _resolve_column(
        old_df.columns,
        revenue_column,
        "Total Net Value Global",
        "Revenue",
        old_source_label,
    )
    new_revenue_col = _resolve_column(
        new_df.columns,
        revenue_column,
        "Total Net Value Global",
        "Revenue",
        new_source_label,
    )
    channel_col = _resolve_column(
        new_df.columns,
        channel_profile_column,
        "Sales Channel Route Name",
        "Channel profile",
        new_source_label,
    )
    tier2_col = _resolve_column(
        new_df.columns,
        tier2_reseller_column,
        "Tier 2 Reseller Id",
        "Tier 2 reseller",
        new_source_label,
    )

    old_revenue_sum, old_non_numeric = _sum_revenue(old_df[old_revenue_col])
    new_revenue_sum, new_non_numeric = _sum_revenue(new_df[new_revenue_col])
    threshold_pct = float(zdel_threshold_pct)
    if threshold_pct <= 0:
        raise ValueError("ZDEL threshold percent must be greater than 0.")
    renewal_threshold = float(renewal_threshold_pct)
    if renewal_threshold <= 0:
        raise ValueError("Renewal threshold percent must be greater than 0.")

    rule_outcome = consistency.conditional_required(
        new_df,
        [channel_col, tier2_col],
        {"trigger_values": "indirect", "case_sensitive": False},
    )
    bad_index = pd.Index(rule_outcome.failed_index)
    invalid_rows = new_df.loc[bad_index[bad_index.isin(new_df.index)]].copy()
    if not invalid_rows.empty:
        invalid_rows.insert(
            0,
            "Source Row",
            [new_df.index.get_loc(index_value) + 2 for index_value in invalid_rows.index],
        )
        invalid_rows = invalid_rows.reset_index(drop=True)

    channel_text = new_df[channel_col].astype("string").str.strip().str.upper()
    indirect_count = int(channel_text.eq("INDIRECT").fillna(False).sum())
    missing_tier2_count = int(len(invalid_rows))

    subregion_column_used: Optional[str] = None
    tier2_missing_by_geography = pd.DataFrame(columns=["Geography", "Missing Count"])
    tier2_top_geography: Optional[str] = None
    tier2_missing_pct = (missing_tier2_count / indirect_count * 100) if indirect_count else 0.0
    tier2_impact_revenue_pct: Optional[float] = None
    if not invalid_rows.empty and new_revenue_col in invalid_rows.columns:
        invalid_revenue_sum, _ = _sum_revenue(invalid_rows[new_revenue_col])
        tier2_impact_revenue_pct = (
            (invalid_revenue_sum / new_revenue_sum * 100) if new_revenue_sum else None
        )

    subregion_requested = str(subregion_column).strip() if subregion_column is not None else ""
    if subregion_requested:
        resolved_subregion = match_column([subregion_requested], [str(c) for c in new_df.columns])
        if resolved_subregion is not None:
            subregion_column_used = resolved_subregion
            if not invalid_rows.empty and resolved_subregion in invalid_rows.columns:
                geo_series = invalid_rows[resolved_subregion].astype("string").str.strip()
                geo_series = geo_series.mask(geo_series.eq(""), "(Blank)").fillna("(Blank)")
                counts = geo_series.value_counts()
                tier2_missing_by_geography = (
                    pd.DataFrame({"Geography": counts.index, "Missing Count": counts.values})
                    .sort_values("Missing Count", ascending=False)
                    .reset_index(drop=True)
                )
                if not tier2_missing_by_geography.empty:
                    tier2_top_geography = str(tier2_missing_by_geography.iloc[0]["Geography"])

    if tier2_missing_pct > 20:
        tier2_severity = "High"
    elif tier2_missing_pct > 10:
        tier2_severity = "Medium"
    else:
        tier2_severity = "Low"

    (
        zdel_document_type_column_old,
        zdel_document_type_column_new,
        selected_document_type,
        zdel_check_applied,
        zdel_old_sum,
        zdel_new_sum,
        zdel_delta,
        zdel_delta_pct,
        zdel_threshold_exceeded,
        zdel_threshold_message,
    ) = _build_zdel_check(
        old_df,
        new_df,
        old_source_label=old_source_label,
        new_source_label=new_source_label,
        document_type_column=zdel_document_type_column,
        document_type_value=zdel_document_type_value,
        old_revenue_column=old_revenue_col,
        new_revenue_column=new_revenue_col,
        threshold_pct=threshold_pct,
    )
    (
        renewal_status_column_old,
        renewal_status_column_new,
        selected_renewal_status,
        renewal_quote_number_column_old,
        renewal_quote_number_column_new,
        renewal_contract_doc_number_column_old,
        renewal_contract_doc_number_column_new,
        renewal_old_filtered_count,
        renewal_old_missing_count,
        renewal_old_missing_pct,
        renewal_new_filtered_count,
        renewal_new_missing_count,
        renewal_new_missing_pct,
        renewal_threshold_exceeded,
        renewal_threshold_message,
    ) = _build_renewal_check(
        old_df,
        new_df,
        old_source_label=old_source_label,
        new_source_label=new_source_label,
        renewal_status_column=renewal_status_column,
        renewal_status_value=renewal_status_value,
        renewal_quote_number_column=renewal_quote_number_column,
        renewal_contract_doc_number_column=renewal_contract_doc_number_column,
        threshold_pct=renewal_threshold,
    )

    return RevenueComparisonReport(
        old_path=old_source_label,
        new_path=new_source_label,
        old_sheet=old_selection_label,
        new_sheet=new_selection_label,
        revenue_column_old=old_revenue_col,
        revenue_column_new=new_revenue_col,
        channel_profile_column=channel_col,
        tier2_reseller_column=tier2_col,
        old_row_count=len(old_df),
        new_row_count=len(new_df),
        row_count_delta=len(new_df) - len(old_df),
        old_revenue_sum=old_revenue_sum,
        new_revenue_sum=new_revenue_sum,
        revenue_delta=new_revenue_sum - old_revenue_sum,
        old_non_numeric_revenue_count=old_non_numeric,
        new_non_numeric_revenue_count=new_non_numeric,
        indirect_row_count=indirect_count,
        indirect_missing_tier2_count=int(len(invalid_rows)),
        conditional_message=rule_outcome.message,
        zdel_document_type_column_old=zdel_document_type_column_old,
        zdel_document_type_column_new=zdel_document_type_column_new,
        zdel_document_type_value=selected_document_type,
        zdel_threshold_pct=threshold_pct,
        zdel_check_applied=zdel_check_applied,
        zdel_old_sum=zdel_old_sum,
        zdel_new_sum=zdel_new_sum,
        zdel_delta=zdel_delta,
        zdel_delta_pct=zdel_delta_pct,
        zdel_threshold_exceeded=zdel_threshold_exceeded,
        zdel_threshold_message=zdel_threshold_message,
        renewal_status_column_old=renewal_status_column_old,
        renewal_status_column_new=renewal_status_column_new,
        renewal_status_value=selected_renewal_status,
        renewal_quote_number_column_old=renewal_quote_number_column_old,
        renewal_quote_number_column_new=renewal_quote_number_column_new,
        renewal_contract_doc_number_column_old=renewal_contract_doc_number_column_old,
        renewal_contract_doc_number_column_new=renewal_contract_doc_number_column_new,
        renewal_threshold_pct=renewal_threshold,
        renewal_old_filtered_count=renewal_old_filtered_count,
        renewal_old_missing_count=renewal_old_missing_count,
        renewal_old_missing_pct=renewal_old_missing_pct,
        renewal_new_filtered_count=renewal_new_filtered_count,
        renewal_new_missing_count=renewal_new_missing_count,
        renewal_new_missing_pct=renewal_new_missing_pct,
        renewal_threshold_exceeded=renewal_threshold_exceeded,
        renewal_threshold_message=renewal_threshold_message,
        subregion_column_used=subregion_column_used,
        tier2_missing_by_geography=tier2_missing_by_geography,
        tier2_top_geography=tier2_top_geography,
        tier2_missing_pct=tier2_missing_pct,
        tier2_impact_revenue_pct=tier2_impact_revenue_pct,
        tier2_severity=tier2_severity,
        invalid_rows=invalid_rows,
    )


def build_revenue_comparison_report(
    old_workbook_path: str | Path,
    new_workbook_path: str | Path,
    old_sheet_name: Optional[str] = None,
    new_sheet_name: Optional[str] = None,
    revenue_column: Optional[str] = "Total Net Value Global",
    channel_profile_column: Optional[str] = "Sales Channel Route Name",
    tier2_reseller_column: Optional[str] = "Tier 2 Reseller Id",
    zdel_document_type_column: Optional[str] = "Document type",
    zdel_document_type_value: Optional[str] = "ZDEL",
    zdel_threshold_pct: float = 5.0,
    renewal_status_column: Optional[str] = "Renewal Status",
    renewal_status_value: Optional[str] = "Renewed",
    renewal_quote_number_column: Optional[str] = "Renewal Quote Nbr",
    renewal_contract_doc_number_column: Optional[str] = "Renewal Contract Doc Nbr",
    renewal_threshold_pct: float = 5.0,
    subregion_column: Optional[str] = None,
) -> RevenueComparisonReport:
    """Compare row/revenue deltas and enforce indirect->Tier 2 reseller completeness."""
    old_path = resolve_path(old_workbook_path)
    new_path = resolve_path(new_workbook_path)

    old_sheet = _resolve_sheet(old_path, old_sheet_name)
    new_sheet = _resolve_sheet(new_path, new_sheet_name)

    old_df = load_dataframe(old_path, old_sheet)
    new_df = load_dataframe(new_path, new_sheet)

    return build_revenue_comparison_report_from_dataframes(
        old_df,
        new_df,
        old_source_label=str(old_path),
        new_source_label=str(new_path),
        old_selection_label=old_sheet,
        new_selection_label=new_sheet,
        revenue_column=revenue_column,
        channel_profile_column=channel_profile_column,
        tier2_reseller_column=tier2_reseller_column,
        zdel_document_type_column=zdel_document_type_column,
        zdel_document_type_value=zdel_document_type_value,
        zdel_threshold_pct=zdel_threshold_pct,
        renewal_status_column=renewal_status_column,
        renewal_status_value=renewal_status_value,
        renewal_quote_number_column=renewal_quote_number_column,
        renewal_contract_doc_number_column=renewal_contract_doc_number_column,
        renewal_threshold_pct=renewal_threshold_pct,
        subregion_column=subregion_column,
    )
