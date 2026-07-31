# YouTube Reconciliation — Fixture & Test Report

**Date:** 2026-07-31 (updated same day with the bug-fix pass)
**Scope:** `yt_reconciliation_clean.py` tested end-to-end with synthetic
fixtures via `streamlit.testing.v1.AppTest`, then the 11 review findings
from the first pass were **fixed in the script** (see "Fixes applied"
below). The original Windows source paths are untouched.

## Contents of this folder

| File | Purpose |
|---|---|
| `yt_reconciliation_clean.py` | The app, original Windows paths intact, 11 review findings fixed (change log in the module docstring) |
| `generate_fixtures.py` | Deterministic synthetic-fixture generator (seeded) |
| `fixtures/` | Small fixture set (~1,300 CSV rows total, ~90 KB) + `expected_totals.json` |
| `test_app.py` | AppTest suite (`python test_app.py` or `pytest test_app.py`) |

`test_app.py` never edits the delivered script: it writes a **temporary
copy** with the ten path lines re-pointed at `fixtures/` and runs AppTest
on that copy, so the committed file keeps the production paths.

## Test environment

The full suite passes on two version matrices:

- Python 3.11.15, streamlit **1.60.0**, pandas **3.0.5**, numpy 2.4.6
- Python 3.11.15, streamlit **1.44.1**, pandas **2.2.3**, numpy 2.1.x

so the script works on both the current pandas 3 / new-Streamlit stack and
the older 2.x-era stack it was written against.

## Fixes applied (the 11 findings from the first pass)

Items marked **[output change]** can alter visible numbers/tables on real
data; the others only change error handling, robustness, or presentation.

1. **Payment-summary column guard moved earlier.** The
   `required_payment_columns` check now runs before `Revenue Type` is
   first indexed, so a malformed payment file raises the intended
   "missing required columns" message instead of a raw `KeyError`.
   *Tested:* a payment file with a wrong column name produces exactly that
   message (`check_malformed_payment_summary`).

2. **`Asset Labels` fallback restored** **[output change]**. `load_csv`
   gained `optional_usecols`: columns loaded when present, skipped
   silently when absent. red_rawdata and rev_views request
   `['Asset Labels']`, so rows whose Custom ID and Asset Title are both
   blank can again take their Custom ID from Asset Labels — behaviour the
   usecols optimisation had silently disabled. *Tested:* two fixture rows
   with only an Asset Labels value merge to their master shows instead of
   landing in the missing review; rev_views (no such column) exercises the
   optional-absent path.

3. **Season extraction restricted to free-text columns** **[output
   change]**. Stage B1 now searches only Custom ID / Asset Title /
   Video Title / Asset Labels rather than every column, so an incidental
   `S12`-style token in an Asset ID, Video ID, `data_source`, etc. can no
   longer donate a season. *Tested:* the `wwtr_weird_waters_s05` Custom ID
   still yields season 05.

4. **Custom ID matches anchored to word boundaries** **[output change]**.
   Rule 3 patterns now require the match to start at the beginning of the
   id or straight after a space/underscore (`(?<![0-9a-z])`), so `az_` no
   longer fires inside `topaz_…`, `gb_` inside `songb_…`, etc. *Tested:* a
   `topaz_collection_001` row that the old rule mapped to ARTZ now
   correctly stays in the missing review. Note the *end* of a match is
   still unanchored (`fait` would still match `faithful_…`) — tail
   anchoring would break intentionally-prefix keys like `dtnb`.

5. **Shorts merge is now a left join** **[output change, review table
   only]**. Subs-only Video IDs no longer create phantom NaN-revenue rows
   under `YT Shorts Ads Revenue` (their real revenue arrives via the subs
   source), and the `_merge` indicator column is gone from combo. Totals
   are unaffected because those rows carried no revenue.

6. **Blank User Codes surfaced** **[output change, warning table only]**.
   Revenue whose rows never received a New Show still appears in the Final
   Output under a blank User Code, but that row is now also listed in the
   unmatched-codes warning (previously filtered out by `notna()`), with
   the warning text explaining what a blank code means. *Tested:* the
   warning lists the blank code (319.46 — exactly the Missing New Show
   Review total) alongside the deliberate WWTR05.

7. **`Film` treated like Other in the grouped allocation** **[output
   change]**. Multi-row shows now fold a Film row into their real seasons,
   matching what the single-grouped-row rule already did — previously a
   show with rows {01, Film} kept a `SHOWFilm` User Code that could never
   match the List of Codes. *Tested:* a GARF `Film` master season folds
   into GARF01; no `GARFFilm` row appears.

8. **Exact show equality in consolidations** **[output change only for
   pathological codes]**. SCMX 05→03, KRMA →01 and the invalid-season
   family lookup now use `.eq()` like the ARTH consolidation, instead of
   `str.contains`, so a future code merely containing "SCMX"/"KRMA"/"DTNB"
   cannot be swept in. *Tested:* all consolidations still fire on the
   exact codes.

9. **Dotless-ı normalisation in the master** — `clean_master_file` now
   applies the same `ı → i` replacement as `clean_custom_id`, so such
   master Custom IDs can match their source counterparts.

10. **Accounting negatives in the payment summary** — `"(1,234.56)"`
    parses as `-1234.56`. *Tested:* the fixture ADJ file is net-negative
    and its payment-summary line is written as `"(70.19)"`; the
    reconciliation still matches to the cent.

11. **Version-adaptive full-width tables.** Every table renders through a
    small `show_dataframe()` helper that tries `width="stretch"` (the
    replacement for `use_container_width`, which Streamlit removes after
    2025-12-31) and falls back to `use_container_width=True` when the
    installed Streamlit only accepts an integer width. *Tested on both
    Streamlit 1.60.0 and 1.44.1* — the first release raised
    `TypeError: 'str' object cannot be interpreted as an integer` on the
    initial substitution-only version of this fix.

## Feature added after the fix pass: Asset Labels keyword rule

- `rev_views` (like `red_rawdata`) loads **`Asset Labels`** whenever the
  file carries it (the `optional_usecols` mechanism from fix 2 — no error
  if a future file drops the column).
- A new **Rule 3** applies `ASSET_TITLE_SHOW_KEYWORDS` to `Asset Labels`
  (case-insensitive, mirroring the Video Title rule) for rows still
  missing a New Show. It runs after the Video Title rule and before the
  Custom ID / Asset Title substring mappings, which are now Rules 4 and 5.
- *Tested:* a rev_views fixture row whose title (`Untitled Upload 77`) and
  Custom ID match nothing, but whose lower-case label contains
  `science max`, is tagged SCMX by the new rule — it stays out of the
  missing review (count still asserted at 57) and its revenue lands in
  SCMX03. Verified on both version matrices.

## Feature added: Territory (CA / INTL) in the Final Output

- The Final Output by Title now carries a **Territory** column: `CA`
  where the row's `Country` is CA, `INTL` for everything else — one row
  per User Code per territory, with the GRAND TOTAL unchanged.
- This is deliberately simpler than the pipeline's internal per-row
  Territory column (no `9SUSA` / peep rules), which is left untouched.
- **Rows with no Country value are classified INTL and flagged**: a
  warning plus a review table grouped by data source (row count +
  revenue) appears under the Final Output, so missing country data can
  be investigated. In the fixtures this flags exactly the two sources
  that genuinely have no Country column: `YT Shorts Ads Revenue` and
  `Transactions Revenue: Others`.
- **Territory is preserved end-to-end.** The classification is stamped on
  detail rows before the season allocation, and both grouped allocation
  steps (Other/Film/missing seasons, invalid-season families) were
  restructured to split each source row across the recipient seasons
  *within its own territory* — per-season totals match the pre-territory
  behaviour, and the CA total in the final output equals the CA-country
  revenue in the source files exactly. A new conservation guard covers
  the restructured Other/missing allocation.
- The unmatched-codes warning stays at User Code granularity (summed
  across territories).
- *Tested:* Territory only ever shows CA/INTL; CA total ties to the
  fixture's CA-country revenue to the cent; the no-country table lists
  exactly the expected sources and revenue. Verified on both version
  matrices.

## Test results after the fix pass (all passing)

- No exceptions, no `st.error` output.
- Reconciliation: all 6 revenue types match to the cent, including the
  parenthesised negative dispute line.
- Final Output GRAND TOTAL = 16,916.34 = the exact sum of every revenue
  cell across all seven source files (revenue conserved through B2
  allocation, Other/Film/missing allocation, DTNB-12 invalid-season
  reallocation, and the SCMX/ARTH/KRMA consolidations).
- Unmatched-codes warning lists exactly `WWTR05` + the blank code.
- Missing New Show Review holds exactly the 57 intended rows.
- Malformed payment file fails with the intended clear message.
- Caching: first run ~0.5s pipeline, second run 0.00s (on both version
  matrices above).
- Large fixture (200k-row / 12.6 MB red_rawdata, regenerated in a scratch
  dir with `--red-rows 200000`, not committed): first run 3.6s pipeline /
  3.9s wall, cached rerun 0.0s, all assertions pass.

### Rule-path coverage (unchanged from the first pass, plus the new cases)

Rule 1 keywords (Fugget / Science Max / Garfield / Karma's World), Rule 2
lower-case Video Title match (`wheels on the bus sing along` → WOTB),
Rule 3 boundary-anchored Custom ID matches (`dtnb_movie_special`,
`d7mst_tivfg`, `wwtr_`), master `ANNE01` split, `spec`→Other, Film→01
fold, DTNB >2-season allocation, DTNB-12 reallocation, SCMX 05→03,
ARTH 16/17→01 + 18/19→02, KRMA→01, single-grouped-row rule (FUGT / WOTB /
MSBC), RKMS special-case asserts, find_header on row 3, all four
skip-first-row metadata headers, `Net Partner Revenue (Post revshare)`,
`Channel Name`/`Earnings (USD)`, Asset Labels fallback (present and
absent), shorts left-join Custom ID pickup.

## Remaining caveats (known, deliberate)

- Custom ID keys are still unanchored at the tail (see fix 4) — that is
  the conservative choice; add explicit keys if a tail collision ever
  shows up in the review table.
- Stage B2's "existing seasons" count still includes `Film` seasons when
  deciding the >2-season eligibility; the grouped stage reallocates the
  Film bucket afterwards, so totals are unaffected.
- A revenue type present on only one side of the reconciliation with a
  ~0.00 total would still show `matches=True` (visible via
  `match_status` = left_only/right_only in the table).

## How to re-run

```bash
pip install streamlit pandas numpy openpyxl
cd yt
python generate_fixtures.py   # regenerates fixtures/ deterministically
python test_app.py            # runs all assertions, prints timings
```
