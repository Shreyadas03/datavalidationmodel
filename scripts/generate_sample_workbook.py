"""Generate a sample contract workbook with deliberate defects, for testing the platform.

Usage:
    .venv\\Scripts\\python.exe scripts\\generate_sample_workbook.py
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

OUTPUT = Path(__file__).resolve().parents[1] / "data" / "SAMPLE AI.xlsx"
ROWS = 300
SEED = 20260818

CUSTOMERS = [
    ("CE1001", "Acme Corporation"),
    ("CE1002", "Globex Industries"),
    ("CE1003", "Initech Systems"),
    ("CE1004", "Umbrella Health"),
    ("CE1005", "Soylent Foods"),
    ("CE1006", "Vandelay Imports"),
]
DOC_TYPES = ["ZDEP", "ZCRN", "ZQTE", "ZSVC"]


def build() -> pd.DataFrame:
    random.seed(SEED)
    rows = []

    for index in range(ROWS):
        ce_id, party = random.choice(CUSTOMERS)
        start = date(2023, 1, 1) + timedelta(days=random.randint(0, 700))
        end = start + timedelta(days=random.choice([90, 180, 365, 730, 1095]))
        doc_type = random.choice(DOC_TYPES)
        surname = party.split()[0].lower()

        rows.append(
            {
                "Sales Doc Nbr": f"{4500000 + index}",
                "Document Type": doc_type,
                "CE_ID": ce_id,
                "Party Name": party,
                "Hdr Start Date": start,
                "Hdr End Date": end,
                "AMP ID": f"AMP{random.randint(10000, 99999)}",
                "Serial Nbr": f"SN{random.randint(100000, 999999)}",
                "Email": f"{surname}.contact{index}@hpe.com",
                "Phone": f"+1 650-857-{random.randint(1000, 9999)}",
                "Contract Value": round(random.uniform(5_000, 250_000), 2),
            }
        )

    df = pd.DataFrame(rows)

    # ---- plant defects so every check has something to find -------------------
    df.loc[5, "Sales Doc Nbr"] = df.loc[4, "Sales Doc Nbr"]          # duplicate key
    df.loc[11] = df.loc[10]                                          # exact duplicate row
    df.loc[17, "Hdr End Date"] = df.loc[17, "Hdr Start Date"] - timedelta(days=30)  # reversed dates
    df.loc[23, "Hdr End Date"] = df.loc[23, "Hdr Start Date"] + timedelta(days=9000)  # absurd duration
    df.loc[29, "Party Name"] = None                                  # blank customer
    df.loc[35, "Party Name"] = "  Acme Corporation  "                # stray whitespace
    df.loc[41, "Party Name"] = "ACME CORPORATION"                    # casing inconsistency
    df.loc[47, "AMP ID"] = ""                                        # missing AMP ID
    df.loc[53, "Serial Nbr"] = None                                  # missing serial
    df.loc[59, "Email"] = "personal.address@gmail.com"               # wrong domain
    df.loc[65, "Email"] = "not-an-email"                             # malformed email
    df.loc[71, "Email"] = None                                       # blank email
    df.loc[77, "Phone"] = "12345"                                    # invalid phone
    df.loc[83, "Phone"] = "call me"                                  # non-numeric phone
    df.loc[89, "Contract Value"] = 9_999_999.99                      # outlier
    df.loc[95, "Contract Value"] = -500                              # negative value
    df.loc[101, "Document Type"] = "XXXX"                            # unknown category
    df.loc[107, "Party Name"] = "Globex Industries Ltd"              # CE_ID -> two names
    df.loc[107, "CE_ID"] = "CE1002"
    df.loc[113, "Serial Nbr"] = "SN#12\u20ac45"                      # special characters

    return df


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frame = build()
    frame.to_excel(OUTPUT, sheet_name="Contracts", index=False)
    print(f"Wrote {len(frame)} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
