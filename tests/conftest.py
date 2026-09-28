import pandas as pd
import pytest


@pytest.fixture
def contract_df() -> pd.DataFrame:
    """A small contract-like frame with one planted defect per check."""
    return pd.DataFrame(
        {
            "Sales Doc Nbr": ["1001", "1002", "1002", "1003", "1004", None],
            "Party Name": ["Acme Corp", "Globex", "Globex Ltd", "  Initech  ", None, "Umbrella"],
            "Document Type": ["ZDEP", "ZCRN", "ZCRN", "ZDEP", "ZQTE", "ZDEP"],
            "Hdr Start Date": [
                "2024-01-01",
                "2024-02-01",
                "2024-02-01",
                "2024-03-01",
                "2024-04-01",
                "2024-05-01",
            ],
            "Hdr End Date": [
                "2024-12-31",
                "2024-01-15",  # ends before it starts
                "2025-02-01",
                "2024-03-15",
                "2025-04-01",
                "2025-05-01",
            ],
            "CE_ID": ["CE1", "CE2", "CE2", "CE3", "CE4", "CE5"],
            "AMP ID": ["A1", "A2", "A3", "", "A5", "A6"],
            "Serial Nbr": ["S1", "S2", None, "S4", "S5", "S6"],
            "Email": [
                "a.user@hpe.com",
                "b.user@gmail.com",
                "not-an-email",
                "c.user@sub.hpe.com",
                None,
                "d.user@hpe.com",
            ],
            "Phone": [
                "+1 650-857-1501",
                "1234",
                "+44 20 7946 0958",
                None,
                "+91 80 2808 0808",
                "abc",
            ],
            "Amount": [100, 250, 250, 300, 1_000_000, None],
        }
    )
