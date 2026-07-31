# YouTube Reconciliation — Fixture & Test Report

**Date:** 2026-07-31
**Scope:** `yt_reconciliation_clean.py` tested end-to-end with synthetic
fixtures via `streamlit.testing.v1.AppTest`. No business logic, rule
ordering, mappings, or output tables were changed. The delivered script is
**byte-identical to the file as supplied** (md5 `61aab99281d20414ed40998e5ca77b2f`)
— the original Windows paths are exactly as delivered.

## Contents of this folder

| File | Purpose |
|---|---|
| `yt_reconciliation_clean.py` | The app, unmodified, original Windows paths intact |
| `generate_fixtures.py` | Deterministic synthetic-fixture generator (seeded) |
| `fixtures/` | Small fixture set (~1,300 CSV rows total, ~80 KB) + `expected_totals.json` |
| `test_app.py` | AppTest suite (`python test_app.py` or `pytest test_app.py`) |

Rather than editing the path block and restoring it afterwards, `test_app.py`
writes a **temporary copy** of the script with the ten path lines re-pointed
at `fixtures/` and runs AppTest on that copy. The committed script is never
touched, so "restore original paths" is satisfied by construction.

## Test environment

Python 3.11.15, streamlit 1.60.0, pandas 3.0.5, numpy 2.4.6, openpyxl 3.1.5.
Notably the script ran **unmodified on pandas 3.0** (a major-version jump
from the 2.x era it was presumably written against) with no errors.

## What passed (everything)

1. **No exceptions, no `st.error` output** on a full run.
2. **Reconciliation:** all 6 revenue types `matches == True`, `match_status`
   = `both` for every row, and each `combo_youtube_total` equals the
   per-source fixture totals to the cent. The payment summary is built FROM
   the fixture totals using the original payment-summary labels (the
   `PAYMENT_SUMMARY_REVENUE_TYPE_MAPPING` keys, plus `Ads Revenue` and
   `Ads Revenue: Dispute Resolution` as-is, plus a `Total` row), so this
   passes by construction — the test proves the mapping and truncation logic
   round-trips correctly.
3. **Final Output GRAND TOTAL** = 16,976.71 = the fixture grand total
   (sum of every revenue cell across all seven source files), i.e. revenue
   is conserved through allocation, reallocation, and consolidation.
4. **Unmatched-codes warning** fires with exactly the deliberately
   unmatched code `WWTR05` (and nothing else).
5. **Caching:** second `AppTest.run()` reports `Pipeline time this run: 0.0s`
   (first run 0.40s). Wall times 1.08s → 0.20s.
6. **Header quirks all exercised:** `skip_first_row` metadata rows on
   red_rawdata / red_music_video / shorts-subs / ecommerce; `find_header`
   located the ADJ header on physical row 3 beneath two junk rows;
   `Channel Name`/`Earnings (USD)`; `Net Partner Revenue (Post revshare)`;
   `'New Show '` with trailing space; the Video Title → Asset Title fallback.

### Rule-path coverage confirmed by inspecting the rendered tables

- **Rule 1** (Asset Title keyword, case-sensitive): `Fugget`, `Science Max`,
  `Garfield`, `Karma's World` rows → FUGT/SCMX/GARF/KRMA.
- **Rule 2** (Video Title, case-insensitive): lower-case
  `"wheels on the bus sing along"` → WOTB (Rule 1 correctly misses it).
- **Rule 3** (Custom ID substrings): `dtnb_movie_special` → DTNB,
  `d7mst_tivfg` → MSBC, `wwtr_weird_waters_s05` → WWTR.
- **Rows staying missing:** 56 rows (zzz_unknown assets, `Nine Story
  Extras` channel, `Random Shorts Mix` shorts) appear in the Missing New
  Show Review; their 278.23 total re-appears as the blank-User-Code row in
  the Final Output — conserved.
- **Season extraction:** `s05` inside a Custom ID → season 05 (→ `WWTR05`).
- **Stage B2 allocation (>2 seasons):** DTNB missing-season revenue split
  across its 4 existing seasons (01/02/03/12).
- **Grouped Other/missing allocation:** GARF `spec`→`Other` (master
  correction 1) and keyword rows with no season folded into GARF01;
  SCMX missing-season row spread across 03/05.
- **Invalid-season family:** DTNB season 12 removed and spread equally
  across DTNB01/02/03 (visible as exact thirds in the final output).
- **Consolidations:** SCMX 05→03; ARTH 16/17→01 and 18/19→02 (regrouped);
  KRMA 02→01.
- **Master corrections:** `ANNE01` split into ANNE + season 01;
  `spec`→`Other`; `RKMS` special-case asserts in the code-mapping split ran.
- **Single grouped-row rule:** FUGT/WOTB/MSBC missing seasons → `01`.
- **Shorts outer merge:** shared Video IDs picked up Custom IDs from the
  subs file; ads-only rows fell back to Video Title; subs-only IDs produced
  the expected right-side rows.

## Large-fixture timing (optional task 5)

One larger set with a **200,007-row red_rawdata (12.6 MB)** was generated in
a scratch directory (not committed; recreate with
`python generate_fixtures.py --outdir <dir> --red-rows 200000`):

- First run: **3.0s wall / 2.4s pipeline**; all assertions still pass,
  grand total 4,060,363.23 matches.
- Cached rerun: 0.23s wall / 0.0s pipeline.

Extrapolating, the 500 MB production file will be dominated by
`pd.read_csv` parse time; the usecols optimisation in `load_csv` is doing
its job.

## What failed

Nothing. All assertions passed on both the small and large fixture sets.

## Suspected bugs / observations (reported, NOT fixed)

1. **Payment-summary column guard runs too late** (`build_combo`): the code
   indexes `payment_summary_df["Revenue Type"]` to build
   `Original Revenue Type` *before* the `required_payment_columns` check.
   A payment file missing `Revenue Type` raises a raw `KeyError` instead of
   the intended friendly message. (Missing `Partner Revenue (USD)` is
   caught correctly.)

2. **The `Asset Labels` fallback is dead code in this build.** `load_csv`
   is called with `usecols` lists that never include `Asset Labels`, so the
   `use_asset_label=True` branch in `clean_custom_id` can never fire. If
   the pre-optimisation build loaded all columns, rows whose Custom ID and
   Asset Title are both blank but Asset Labels populated would previously
   have merged via the label and now become `"nan"` Custom IDs — a silent
   behaviour change vs. older revisions worth verifying against a real month.

3. **Stage B1 season extraction scans every column.** The regex runs over
   all columns concatenated (IDs, titles, `data_source`, `Territory`,
   `Show_Season`, the `_merge` indicator …), and the first `S##` match in
   column order wins. An incidental token like `GS05X` in an Asset ID, or
   an `S12` inside a title, will assign a season to a missing-season row.

4. **`CUSTOM_ID_SHOW_MAPPING` matches unanchored substrings.** Short keys
   such as `gb_`, `az_`, `lbb`, `dtnb`, `fait` match *anywhere* in the
   cleaned Custom ID: e.g. any id containing `topaz_…` would map to ARTZ
   via `az_`, and `fait` would hit ids containing "faith…". Because rules
   only fill still-missing rows, damage is bounded, but false positives are
   plausible as new content appears.

5. **Shorts outer merge creates phantom "ads" rows.** Subs-only Video IDs
   become rows labelled `YT Shorts Ads Revenue` with NaN Partner Revenue
   (harmless for totals, but they can surface in the Missing New Show
   Review with blank revenue if unmapped). The `_merge` indicator column
   also rides along into the cached combo frame.

6. **Missing-New-Show revenue is invisible in the final output's checks.**
   Rows never assigned a New Show end up as a single Final Output row with
   a blank (`<NA>`) User Code (278.23 in the fixtures). The unmatched-codes
   warning explicitly filters `final_codes.notna()`, so this row is *not*
   flagged there — the only place it is visible is the review table.

7. **Inconsistent "Film" handling in the grouped stage.** The single-row
   rule converts `Film` to `01`, but the multi-row Other/missing allocation
   only allocates `other`/missing. A show with grouped rows {01, Film}
   keeps the Film row, producing a User Code like `SHOWFilm` that will
   likely be unmatched.

8. **Inconsistent show matching in consolidations.** KRMA/SCMX and the
   invalid-season families use `str.contains` on New Show while ARTH uses
   `.eq`. A future code containing `KRMA`/`SCMX`/`DTNB` as a substring
   would be swept into the wrong consolidation/reallocation.

9. **Turkish-ı normalisation asymmetry.** `clean_custom_id` replaces
   `ı`→`i`; `clean_master_file` does not, so a master Custom ID containing
   dotless ı can never match its source-side counterpart.

10. **Payment amount parsing** strips `$` and `,` but not
    accounting-style parenthesised negatives.

11. **Maintenance, not a bug:** streamlit 1.60 warns that
    `use_container_width` (used on every `st.dataframe`) is removed after
    2025-12-31 — replace with `width='stretch'` whenever you next upgrade
    Streamlit.

## How to re-run

```bash
pip install streamlit pandas numpy openpyxl
cd yt
python generate_fixtures.py   # regenerates fixtures/ deterministically
python test_app.py            # runs all assertions, prints timings
```
