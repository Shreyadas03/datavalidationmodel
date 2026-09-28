import pandas as pd
import pytest

from dq_platform.engine import run_checks, run_rule
from dq_platform.models import RuleSpec
from dq_platform.presets import PRESETS, build_preset_specs, match_column
from dq_platform.registry import RULE_REGISTRY


def test_registry_ids_are_unique_and_resolvable():
    assert len(RULE_REGISTRY) == len({d.rule_id for d in RULE_REGISTRY.values()})
    for definition in RULE_REGISTRY.values():
        assert callable(definition.runner)
        assert definition.dimension


def test_run_rule_reports_unknown_rule(contract_df):
    result = run_rule(contract_df, RuleSpec(rule_id="does.not.exist", columns=[]))
    assert result.status == "ERROR"
    assert "Unknown rule id" in result.error


def test_run_rule_isolates_failures(contract_df):
    result = run_rule(contract_df, RuleSpec(rule_id="completeness.null_blank", columns=["Nope"]))
    assert result.status == "ERROR"
    assert "not found" in result.error


def test_run_rule_accepts_dicts(contract_df):
    result = run_rule(contract_df, {"rule_id": "completeness.null_blank", "columns": ["Party Name"]})
    assert result.status == "FAIL"
    assert result.failed_count == 1


def test_run_checks_builds_a_report(contract_df):
    specs = [
        RuleSpec(rule_id="uniqueness.duplicate_key", columns=["Sales Doc Nbr"]),
        RuleSpec(rule_id="validity.email_domain", columns=["Email"], params={"domains": "hpe.com"}),
        RuleSpec(rule_id="completeness.null_blank", columns=["Document Type"]),
    ]
    report = run_checks(contract_df, specs, source_path="x.xlsx", sheet_name="Sheet1")

    assert report.total_checks == 3
    assert report.failed_checks == 2
    assert report.passed_checks == 1
    assert report.row_count == len(contract_df)
    assert report.missing_profile is not None
    assert not report.details_frame().empty


def test_failed_rows_are_recoverable(contract_df):
    report = run_checks(
        contract_df, [RuleSpec(rule_id="uniqueness.duplicate_key", columns=["Sales Doc Nbr"])]
    )
    rows = report.results[0].failed_rows(contract_df)
    assert list(rows["Sales Doc Nbr"]) == ["1002", "1002"]


def test_failed_rows_respect_limit(contract_df):
    report = run_checks(
        contract_df, [RuleSpec(rule_id="uniqueness.duplicate_key", columns=["Sales Doc Nbr"])]
    )
    assert len(report.results[0].failed_rows(contract_df, limit=1)) == 1


def test_match_column_is_fuzzy():
    columns = ["Sales Doc Nbr", "Hdr Start Date", "Party Name"]
    assert match_column(["sales doc nbr"], columns) == "Sales Doc Nbr"
    assert match_column(["Sales Document", "Sales Doc"], columns) == "Sales Doc Nbr"
    assert match_column(["Nothing Here"], columns) is None


def test_hpe_preset_resolves_against_real_columns(contract_df):
    specs, notes = build_preset_specs("HPE Contract QC", list(contract_df.columns))
    assert specs
    assert all(spec.rule_id in RULE_REGISTRY for spec in specs)
    # Every resolved column must exist on the sheet.
    for spec in specs:
        for column in spec.columns:
            assert column in contract_df.columns
    assert isinstance(notes, list)


def test_preset_notes_when_columns_are_missing():
    specs, notes = build_preset_specs("HPE Contract QC", ["Totally", "Unrelated"])
    assert notes
    assert all(spec.columns == [] for spec in specs)


def test_preset_end_to_end_runs_without_errors(contract_df):
    specs, notes = build_preset_specs("HPE Contract QC", list(contract_df.columns))
    report = run_checks(contract_df, specs, notes=notes)
    assert report.errored_checks == 0
    assert report.total_checks == len(specs)


def test_unknown_preset_raises():
    with pytest.raises(KeyError):
        build_preset_specs("Not A Preset", ["a"])


def test_all_presets_reference_known_rules():
    for preset in PRESETS.values():
        for entry in preset.rules:
            assert entry.rule_id in RULE_REGISTRY
