# Expense: cash flow from bank exports

A Streamlit app (`finance_cash.py`) that reads the CSV exports from the bank for a
Visa card and a current account. It:

- codes each transaction from a mapping spreadsheet and keyword rules;
- reconciles both accounts to their balances;
- shows monthly cash movement by category, with a drill-down and charts.

Since the bank only exports the last 24 months, the app now works from **a fixed
start date**, so the opening balances stop moving. Every export ever downloaded
is kept, and the app rebuilds one continuous history from all of them.

```bash
pip install -r requirements.txt
streamlit run finance_cash.py
pytest test_finance.py            # 9 tests: stitching, checks, the app end to end
```

The sidebar's **Use sample data** box switches to the made-up data in
`sample_data/`. It is ticked automatically when your own Finance folder isn't
found, so the app runs anywhere.

| File | What it is |
|---|---|
| `finance_cash.py` | the app |
| `bank_exports.py` | reads the exports, works out which account each is, stitches the overlapping downloads together, and runs the coverage and balance checks |
| `generate_sample_data.py` | writes `sample_data/`: three years of made-up transactions, saved as eight overlapping downloads in the bank's CSV layout, plus a coding mapping and config |
| `test_finance.py` | pytest suite |

## Your data folder

Nothing personal goes in this repo. It is **public** (GitHub Pages), and
`.gitignore` blocks CSVs, spreadsheets and `finance_config.json` everywhere
except `sample_data/`. The app reads your data from
`C:/Users/Darragh/Documents/Finance` (`MY_DATA_DIR` at the top of the script):

```
Finance/
├── exports/              every Transaction_Export_*.csv you download, Visa and current account
│                         together. The app tells them apart by their columns.
│                         Never edit or delete them.
├── coding_mapping.xlsx   unchanged: Sheet1 Description -> Coding, Sheet2 Coding -> Alt_Coding
└── finance_config.json   start date, opening balances at that date, latest Visa balance
```

`finance_config.json` (copy `sample_data/finance_config.json` and edit it):

```json
{
  "start_date": "2024-09-28",
  "opening_balances": {
    "Visa": 0.00,
    "Current_Account": 0.00
  },
  "visa_closing_balance": 0.00
}
```

`start_date` and `opening_balances` are set once and never touched again.
`visa_closing_balance` is the Visa balance from the app or website on the day
you download; you can also just type it into the app.

## A fixed starting point

### The problem

Each export reaches back 24 months from the day you download it, so the first
date moves every visit. The opening balances have to move with it, and they are
the one number you can't read off the export.

### The fix: freeze the downloads, not the dates

An export you have already downloaded never changes. Keep every one, and
history the bank no longer shows is still on your disk. The app reads all of
them and keeps each transaction once, from the fixed start date onwards. The
opening balances at that date never change, because the transactions after it
never change.

You don't need to plan date ranges when you download. Overlap is expected and
handled, and a download that overlaps the last one is the safest kind.

### One-time setup

1. **Gather every export you still have** into `Finance/exports/`, old ones
   included. Your script mentions exports from 1 Dec 2025 (current account) and
   19 Jan 2026 (Visa). Those were run when the bank still allowed earlier start
   dates, so they hold days the bank won't give you any more. The **Bank Exports
   Used** table shows how far back each file goes.
2. **Pick the start date.** It can't be earlier than the first date *both*
   accounts' exports cover; the app warns if it is. If you can, make it the
   day after a Visa statement date, so the Visa opening balance is printed on a
   statement.
3. **Set the opening balances**, as at the *start* of that day (before its
   transactions). Put in your best guess, run the app, then:
   - **Current account:** the bank prints a running balance, so if the guess is
     wrong the app shows the opening balance the bank's figures imply. Copy
     that in.
   - **Visa:** there's no balance column. Enter today's Visa balance; if the
     reconciliation fails, it shows the opening balance that would make it
     agree. Once the coverage checks are clean, that is the opening balance.
     Copy it in. A statement balance at the start date does the same job.
4. Never change them again. From now on, every run proves the history is
   complete, because the fixed opening balance plus every transaction has to
   land on the bank's balance today.

### Each visit to the bank

1. Download both exports. The full 24 months is easiest.
2. Drop them in `Finance/exports/` as they are. Don't rename them, edit them or
   delete the old ones.
3. Update `visa_closing_balance` in `finance_config.json`, or type it in the
   app.
4. Run the app and check: no warnings under **Bank Exports Used**, and two ✅
   under **Reconciliation**.

Download at least once every 23 months, or there will be a gap the bank can no
longer fill. Monthly or quarterly is plenty.

**Back up `Finance/exports/`** (OneDrive or similar). It is now the only copy of
anything older than 24 months.

### How the stitching works (`bank_exports.stitch`)

Two downloads that both cover a day list that day's transactions the same way,
so the obvious fix is to drop repeated rows. That would be wrong: a day can
genuinely contain two identical transactions, such as two €4.50 coffees in the
same café. The sample data has 170 such rows.

So each row is first numbered by how many times that same transaction (date,
description, amounts) has already appeared in its own file: 0, 1, 2 and so on.
Duplicates are then dropped on transaction plus number:

- the second coffee is number 1 in every download that has it, so it is kept;
- the overlap between downloads is counted once;
- a download made at lunchtime is missing that afternoon's transactions, and
  the next download fills them in.

The Balance column is left out of the match. The bank prints it on the last
transaction of a day, and in a lunchtime download that is a different row than
it is the next day.

Tests 1 to 4 check this, test 1 against the full generated history: stitching
all eight sample downloads rebuilds it exactly, row for row and in order.

### Other ways of doing it

- **A master spreadsheet you paste new rows into.** It's the same idea done by
  hand, and it's easy to paste a day twice or miss a partial one. Keeping the
  raw downloads means the record is exactly what the bank gave you, and the app
  can always rebuild from it.
- **Downloading only "since last time".** It works, and the stitcher handles
  it, but full downloads overlap. That overlap is a free cross-check, and it
  fills in the partial last day of the previous download.

## Checks the app runs

| Check | Catches |
|---|---|
| Exports table | a file that isn't a Visa or current account export (skipped, and listed) |
| Start date covered | exports that don't reach back to the start date, so the opening balance can't hold |
| Coverage gaps | a stretch no download covers (you left it more than 24 months) |
| End dates line up | Visa and current account downloaded on different days, so the last months only have one account |
| Sum preservation + row count | the coding merge duplicating rows |
| Reconciliation, per account | opening + transactions ≠ closing, for each account separately so errors can't cancel out |
| Daily current account balance | the bank prints a balance every day; the first day that disagrees is where a transaction is missing or doubled |

## Review notes on the original script

Found by running it on the sample data.

**Fixed**

1. **Balance with thousand separators crashed it.** Commas were stripped from
   Debit/Credit but not from Balance, so `"3,129.53"` stayed text and the
   closing balance sum raised `TypeError`. Your exports evidently don't put
   commas in Balance, or you'd have seen this; the fix makes it safe either way.
2. **The monthly table left out uncoded transactions.** `pivot_table` drops rows
   with a blank Coding, so Net Cash Movement and every Closing Balance in that
   table missed whatever wasn't coded yet. On the sample data the final Closing
   Balance was €9,675.10 out: exactly the 72 uncoded rows. They now appear as an
   `Uncoded` row, and the table ties to the reconciliation (tested).
3. **No common start date.** Visa and current account came from separate files
   with their own windows, and nothing tied their dates together. From the file
   names in the script, the Visa data ran to 28 Sep 2026 but the current account
   only to 1 Aug 2026, so Aug and Sep 2026 had Visa spending and no current
   account. Both accounts are now trimmed to the same start date, and the app
   warns if their end dates differ.
4. **Closing balance row.** The script took the first row after sorting by date
   descending. If the bank prints a balance on several rows in a day, that sort
   doesn't preserve their order, so it could pick a mid-day balance. Now it uses
   the last balance the bank printed, in the file's own order.
5. **The reconciliation only checked the net of both accounts**, where an error
   in one could hide behind the other. It is now per account, plus the daily
   current account check.
6. `use_container_width` is deprecated (its announced removal date was
   2025-12-31) and replaced with `width='stretch'`, which needs Streamlit 1.51
   or later. If you see an error about `width`, run `pip install -U streamlit`.
7. Sheet2 was read twice; once is enough. A row-count check now sits next to
   the sum-preservation test.

**Not changed (your call)**

- **Keyword rules match anywhere in the description**, and the first match
  wins. `'car'` codes `HALLMARK CARDS` as Car (in the sample data), and would
  do the same to anything containing "card", "scar" or "Carrolls". `'gas'` is
  just as loose ("Vegas", "gastro"), and so is `'sv'`. `' car '` adds nothing,
  because `'car'` right after it catches the same rows with the same coding.
  `'symths'` looks like a typo of `'smyths'`.
  `'jewellers'` gives `'Present'` while `'blooming'` gives `'Presents'`, which
  makes two categories. Matching whole words (`re.search(rf'\b{re.escape(k)}\b',
  desc)`) would fix the first group but could stop some intended matches,
  so check the drill-down after any change.
- **The expense charts treat every category except 'Salary' / 'Salary (Income)'
  as spending, and take `.abs()`**. So other income (Child Benefit in the
  sample, refunds) and transfers (Visa repayments, Revolut top-ups) show up as
  spend bars. Adding those codings next to `'Salary (Income)', 'Salary'` where
  `expense_df` and `expense_categories_ordered_filtered` are built would take
  them out.
- `get_close_matches` is imported but not used.
- The keyword rules contain family names, and the repo is public.
