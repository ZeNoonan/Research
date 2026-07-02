# Shop Accounts (Hedgerows)

Streamlit app that turns raw bank and visa transaction exports into a set of
accounts: coded transaction listing, summary by account, filing accounts
table (with year-on-year comparatives), and a trial balance.

## Running

```bash
streamlit run shop/hedgerows.py
```

## Data files

All data files sit in this `shop/` folder alongside the script:

| File | Contents | Required columns |
|---|---|---|
| `bank_<year>.xlsx` | Bank account export | `Posted Transactions Date`, `Description1`, `Debit Amount`, `Credit Amount` |
| `visa_<year>.xlsx` | Visa card export | `Processed`, `Description`, `Paid out`, `Paid in` |
| `mapping.xlsx` | Description → account mapping (Sheet1) and account groupings (Sheet2) | Sheet1: `Description`, `Account Description`. Sheet2: `Account Description`, `Stats_Group`, `PL_BS`, `Sorting` |

Years are discovered automatically from the file names. If a file's columns
don't match, the app stops with a message listing what it expected versus
what it found.

## Adding a new year (e.g. 2025)

1. Drop `bank_2025.xlsx` and `visa_2025.xlsx` into this folder — the year is
   picked up automatically and appears as a new column in the filing table.
2. Check the **Unmapped Transactions** section and add any new payees to
   `mapping.xlsx` until nothing is unmapped.
3. Opening balances for the 2025 trial balance (stock, bank, other loans,
   fixed assets) are carried forward automatically from the 2024 closing
   trial balance — nothing to configure.
4. If a one-off VAT payment needs recoding to Revenue Commissioners, add its
   amount under the year in `REVENUE_COMMISSIONERS_VAT_AMOUNTS` at the top of
   `hedgerows.py`.

The earliest year of accounts is the only one that needs opening balances
typed in by hand — see `SEED_PRIOR_BALANCES` in `hedgerows.py` (currently
seeded for 2024).
