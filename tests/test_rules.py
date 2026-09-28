import pandas as pd

from dq_platform.rules import completeness, consistency, distribution, hygiene, uniqueness, validity


def failed(outcome):
    return set(outcome.failed_index)


# ------------------------------------------------------------------ completeness


def test_null_blank_flags_nulls_and_whitespace():
    df = pd.DataFrame({"c": ["a", None, "   ", "b", ""]})
    result = completeness.null_blank(df, ["c"], {})
    assert failed(result) == {1, 2, 4}


def test_null_blank_can_ignore_whitespace():
    df = pd.DataFrame({"c": ["a", None, "   "]})
    result = completeness.null_blank(df, ["c"], {"treat_whitespace_as_blank": False})
    assert failed(result) == {1}


def test_missing_summary_profiles_all_columns(contract_df):
    result = completeness.missing_summary(contract_df, [], {})
    assert result.detail_table is not None
    assert set(result.detail_table.columns) == {"Column", "Missing_Count", "Missing_Pct"}
    assert result.detail_table["Missing_Count"].sum() > 0


def test_completeness_threshold():
    df = pd.DataFrame({"a": ["x", None, "y"], "b": ["1", None, None]})
    result = completeness.completeness_threshold(df, ["a", "b"], {"min_filled_pct": 100})
    assert failed(result) == {1, 2}


def test_empty_frame_is_handled():
    df = pd.DataFrame({"c": pd.Series(dtype="object")})
    assert failed(completeness.null_blank(df, ["c"], {})) == set()


# -------------------------------------------------------------------- uniqueness


def test_duplicate_rows_flags_every_copy():
    df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    result = uniqueness.duplicate_rows(df, [], {})
    assert failed(result) == {0, 1}


def test_duplicate_key_flags_repeats_and_skips_blanks(contract_df):
    result = uniqueness.duplicate_key(contract_df, ["Sales Doc Nbr"], {})
    assert failed(result) == {1, 2}


def test_duplicate_key_can_include_blanks():
    df = pd.DataFrame({"k": [None, None, "a"]})
    result = uniqueness.duplicate_key(df, ["k"], {"ignore_blanks": False})
    assert failed(result) == {0, 1}


def test_unique_ratio_reports_without_row_failures(contract_df):
    result = uniqueness.unique_ratio(contract_df, ["Document Type"], {})
    assert failed(result) == set()
    assert result.rule_failed is False


# ---------------------------------------------------------------------- validity


def test_email_format(contract_df):
    result = validity.email_format(contract_df, ["Email"], {})
    assert failed(result) == {2}


def test_email_format_can_require_a_value(contract_df):
    result = validity.email_format(contract_df, ["Email"], {"allow_blank": False})
    assert failed(result) == {2, 4}


def test_email_domain_hpe_only(contract_df):
    result = validity.email_domain(contract_df, ["Email"], {"domains": "hpe.com"})
    assert failed(result) == {1, 2}


def test_email_domain_without_subdomains(contract_df):
    result = validity.email_domain(
        contract_df, ["Email"], {"domains": "hpe.com", "allow_subdomains": False}
    )
    assert failed(result) == {1, 2, 3}


def test_phone_number(contract_df):
    result = validity.phone_number(contract_df, ["Phone"], {"region": "US"})
    assert failed(result) == {1, 5}


def test_regex_match():
    df = pd.DataFrame({"code": ["AB123456", "bad", None]})
    result = validity.regex_match(df, ["code"], {"pattern": r"^[A-Z]{2}\d{6}$"})
    assert failed(result) == {1}


def test_regex_must_not_match():
    df = pd.DataFrame({"code": ["AB123456", "bad"]})
    result = validity.regex_match(
        df, ["code"], {"pattern": r"^[A-Z]{2}\d{6}$", "should_match": False}
    )
    assert failed(result) == {0}


def test_allowed_values(contract_df):
    result = validity.allowed_values(contract_df, ["Document Type"], {"values": "ZDEP, ZCRN"})
    assert failed(result) == {4}
    assert result.detail_table is not None


def test_numeric_range(contract_df):
    result = validity.numeric_range(contract_df, ["Amount"], {"min_value": 0, "max_value": 1000})
    assert failed(result) == {4}


def test_numeric_range_flags_non_numeric():
    df = pd.DataFrame({"n": ["10", "abc", None]})
    result = validity.numeric_range(df, ["n"], {})
    assert failed(result) == {1}


def test_outlier_iqr(contract_df):
    result = validity.outlier_iqr(contract_df, ["Amount"], {})
    assert 4 in failed(result)


def test_dtype_date_flags_unparseable():
    df = pd.DataFrame({"d": ["2024-01-01", "not a date", None]})
    result = validity.dtype_date(df, ["d"], {})
    assert failed(result) == {1}
    assert result.derived is not None


# ------------------------------------------------------------------- consistency


def test_date_order(contract_df):
    result = consistency.date_order(
        contract_df, ["Hdr Start Date", "Hdr End Date"], {}
    )
    assert failed(result) == {1}


def test_duration_range_produces_derived_column(contract_df):
    result = consistency.duration_range(
        contract_df, ["Hdr Start Date", "Hdr End Date"], {"min_days": 0}
    )
    assert failed(result) == {1}
    assert result.derived is not None
    assert result.derived.name == "Duration_Days"


def test_one_to_one_detects_conflicting_names(contract_df):
    result = consistency.one_to_one(contract_df, ["CE_ID", "Party Name"], {})
    assert failed(result) == {1, 2}


def test_conditional_required(contract_df):
    result = consistency.conditional_required(
        contract_df, ["Document Type", "AMP ID"], {"trigger_values": "ZDEP"}
    )
    assert failed(result) == {3}


# ----------------------------------------------------------------------- hygiene


def test_whitespace(contract_df):
    result = hygiene.whitespace(contract_df, ["Party Name"], {})
    assert failed(result) == {3}


def test_casing_upper():
    df = pd.DataFrame({"c": ["ABC", "Abc", None]})
    result = hygiene.casing(df, ["c"], {"expected_case": "upper"})
    assert failed(result) == {1}


def test_casing_consistent():
    df = pd.DataFrame({"c": ["Acme", "ACME", "Globex"]})
    result = hygiene.casing(df, ["c"], {"expected_case": "consistent"})
    assert failed(result) == {0, 1}


def test_special_characters():
    df = pd.DataFrame({"c": ["Fine name", "Bad\u2122 name", None]})
    result = hygiene.special_characters(df, ["c"], {})
    assert failed(result) == {1}


def test_length_range():
    df = pd.DataFrame({"c": ["ab", "abcdef", None]})
    result = hygiene.length_range(df, ["c"], {"min_length": 3})
    assert failed(result) == {0}


# ------------------------------------------------------------------ distribution


def test_value_profile(contract_df):
    result = distribution.value_profile(contract_df, ["Document Type"], {})
    assert result.detail_table is not None
    assert set(result.detail_table.columns) == {"Value", "Count", "Percent"}


def test_value_profile_max_distinct(contract_df):
    result = distribution.value_profile(contract_df, ["Sales Doc Nbr"], {"max_distinct": 2})
    assert result.rule_failed is True


def test_category_count(contract_df):
    result = distribution.category_count(contract_df, ["Document Type"], {"values": "ZDEP, ZCRN"})
    counts = dict(zip(result.detail_table["Value"], result.detail_table["Count"]))
    assert counts == {"ZDEP": 3, "ZCRN": 2}
    assert failed(result) == set()


def test_category_count_flag_others(contract_df):
    result = distribution.category_count(
        contract_df, ["Document Type"], {"values": "ZDEP, ZCRN", "flag_others": True}
    )
    assert failed(result) == {4}


def test_category_count_min_count(contract_df):
    result = distribution.category_count(
        contract_df, ["Document Type"], {"values": "ZDEP, ZCRN", "min_count": 5}
    )
    assert result.rule_failed is True
