"""
AppTest suite for yt_reconciliation_clean.py against the synthetic fixtures.

The delivered script keeps its original Windows paths, so this test never
edits it in place: it writes a temporary copy with the path block pointed at
./fixtures and runs streamlit.testing.v1.AppTest on that copy.

Checks:
  1. the app runs with no exceptions and no st.error output
  2. the reconciliation 'matches' column is all True (6 revenue types)
  3. the Final Output GRAND TOTAL equals the fixture grand total
  4. the unmatched-codes warning appears for exactly the deliberately
     unmatched code (WWTR05)
  5. a second run is served from cache (pipeline-time caption ~0s)

Run:  python test_app.py   (or: pytest test_app.py)
"""

import json
import re
import tempfile
import time
from pathlib import Path

from streamlit.testing.v1 import AppTest

YT_DIR = Path(__file__).resolve().parent
SCRIPT = YT_DIR / "yt_reconciliation_clean.py"
FIXTURES = YT_DIR / "fixtures"

PATH_VARS = {
    "payment_summary": "payment_summary.csv",
    "red_rawdata": "red_rawdata_asset.csv",
    "rev_views": "rev_views_by_asset.csv",
    "red_music_video": "red_music_rawdata_video.csv",
    "ads_revenue_shorts_path": "shorts_ads_video_summary.csv",
    "ads_subs_shorts_path": "shorts_subs_video_summary.csv",
    "ads_revenue_dispute_resolution": "adj_asset_raw.csv",
    "transactions_revenue_others": "ecommerce_paid_features.csv",
    "youtube_master_list": "master_list.xlsx",
    "code_mapping_shows": "list_of_codes.xlsx",
}


def make_fixture_pointed_copy(fixtures_dir=FIXTURES):
    """Copy the app with its path block re-pointed at the fixtures dir."""
    source = SCRIPT.read_text(encoding="utf-8")
    for var, filename in PATH_VARS.items():
        target = (Path(fixtures_dir) / filename).resolve().as_posix()
        pattern = rf"^(\s*){re.escape(var)} = '.*'$"
        source, n = re.subn(
            pattern, rf"\1{var} = r'{target}'", source, flags=re.MULTILINE
        )
        assert n == 1, f"expected exactly one path line for {var}, got {n}"
    build_dir = Path(tempfile.mkdtemp(prefix="yt_apptest_"))
    copy_path = build_dir / "yt_reconciliation_under_test.py"
    copy_path.write_text(source, encoding="utf-8")
    return copy_path


def collect_dataframes(at):
    frames = []
    for element in at.dataframe:
        try:
            frames.append(element.value)
        except Exception as exc:  # pragma: no cover - diagnostic aid
            frames.append(f"<unreadable dataframe: {exc}>")
    return frames


def pipeline_caption_seconds(at):
    for caption in at.caption:
        match = re.search(r"Pipeline time this run: ([0-9.]+)s", caption.value)
        if match:
            return float(match.group(1))
    raise AssertionError("pipeline-time caption not found")


def run_once(script_path):
    start = time.perf_counter()
    at = AppTest.from_file(str(script_path), default_timeout=120).run()
    return at, time.perf_counter() - start


def main():
    expected = json.loads(
        (FIXTURES / "expected_totals.json").read_text(encoding="utf-8")
    )
    script_copy = make_fixture_pointed_copy()

    # ---------------- first run ----------------
    at, first_wall = run_once(script_copy)

    assert not at.exception, (
        "app raised: " + "; ".join(e.value for e in at.exception)
    )
    assert len(at.error) == 0, (
        "unexpected st.error output: " + "; ".join(e.value for e in at.error)
    )

    frames = [f for f in collect_dataframes(at) if not isinstance(f, str)]

    # 1. reconciliation: matches all True, one row per revenue type
    recon = next(f for f in frames if "matches" in f.columns)
    assert len(recon) == len(expected["per_data_source"]), recon
    assert bool(recon["matches"].all()), f"reconciliation failed:\n{recon}"
    for _, row in recon.iterrows():
        want = expected["per_data_source"][row["data_source"]]
        assert abs(row["combo_youtube_total"] - want) <= 0.01, row
    successes = [s.value for s in at.success]
    assert any("All revenue types match" in s for s in successes), successes

    # 2. Final Output GRAND TOTAL equals the fixture grand total
    final = next(
        f for f in frames
        if "User Code" in f.columns
        and (f["User Code"] == "GRAND TOTAL").any()
    )
    grand = float(
        final.loc[final["User Code"] == "GRAND TOTAL", "Partner Revenue"]
        .iloc[0]
    )
    assert abs(grand - expected["grand_total"]) <= 0.01, (
        f"GRAND TOTAL {grand:,.2f} != fixture total "
        f"{expected['grand_total']:,.2f}"
    )
    assert any("Final output reconciliation passed" in s for s in successes)

    # 3. unmatched-codes warning fires for exactly the deliberate code
    warnings = [w.value for w in at.warning]
    assert any(
        "no exact match in the List of Codes" in w for w in warnings
    ), warnings
    unmatched = next(
        f for f in frames
        if set(f.columns) == {"User Code", "Partner Revenue"}
    )
    got_codes = sorted(unmatched["User Code"].astype(str))
    assert got_codes == expected["expected_unmatched_user_codes"], got_codes

    first_pipeline = pipeline_caption_seconds(at)

    # ---------------- second run: must be served from cache ----------------
    at2, second_wall = run_once(script_copy)
    assert not at2.exception
    second_pipeline = pipeline_caption_seconds(at2)
    assert second_pipeline < 0.5, (
        f"second run not cached: pipeline took {second_pipeline}s"
    )

    print("ALL CHECKS PASSED")
    print(f"  reconciliation rows all matched: {len(recon)}")
    print(f"  GRAND TOTAL: {grand:,.2f} "
          f"(expected {expected['grand_total']:,.2f})")
    print(f"  unmatched User Codes: {got_codes}")
    print(f"  first run:  wall {first_wall:.2f}s, "
          f"pipeline {first_pipeline:.2f}s")
    print(f"  second run: wall {second_wall:.2f}s, "
          f"pipeline {second_pipeline:.2f}s (cached)")
    return {
        "first_wall": first_wall,
        "first_pipeline": first_pipeline,
        "second_wall": second_wall,
        "second_pipeline": second_pipeline,
    }


def test_app():
    main()


if __name__ == "__main__":
    main()
