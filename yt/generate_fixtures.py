"""
Synthetic fixture generator for yt_reconciliation_clean.py.

Builds a small, self-consistent set of source files in ./fixtures whose
payment summary is derived FROM the generated revenue totals, so the app's
reconciliation passes by construction.

Every quirk of the real source files is reproduced:
  - red_rawdata / red_music_video / shorts-subs / ecommerce carry one
    metadata row above the header (skip_first_row=True in the app)
  - the ADJ dispute file's header sits on physical row 3 with junk above
    (exercises find_header)
  - the ecommerce file uses 'Channel Name' / 'Earnings (USD)'
  - shorts-ads uses 'Net Partner Revenue (Post revshare)'
  - the master xlsx uses 'New Show ' WITH a trailing space, and contains a
    'spec' season and an ANNE01-style combined show+season code
  - List of Codes.xlsx has 'User Code' / 'Description', includes RKMS and
    descriptions carrying keywords such as 'Fugget' and 'Science Max'

Deliberate scenarios baked into the rows:
  - Asset Title keyword matches (Fugget / Science Max / Garfield /
    Karma's World, plus a lower-case Video Title match for Rule 2)
  - Custom ID substring matches ('dtnb', 'd7mst_tivfg', 'wwtr_')
  - rows that stay missing New Show (zzz_unknown_* / Nine Story Extras)
  - an 's05' inside a Custom ID to trigger season extraction (wwtr_ row)
  - DTNB has >2 existing seasons, so its missing-season rows are allocated
  - GARF has a 'spec' (-> Other) season plus keyword rows with no season,
    exercising the grouped Other/missing-season allocation
  - a DTNB season-12 row (invalid-season family reallocation)
  - WWTR05 ends up as a final User Code with no match in List of Codes

Usage:
    python generate_fixtures.py                    # small fixtures (default)
    python generate_fixtures.py --red-rows 200000  # large red_rawdata timing run
    python generate_fixtures.py --outdir /tmp/big_fixtures --red-rows 200000
"""

import argparse
import json
import random
from pathlib import Path

import pandas as pd

COUNTRIES = ["US", "CA", "GB", "DE", "AU", "FR", "MX", "BR", "IN", "JP"]

# ------------------------------------------------------------------
# Master list definition. Custom IDs deliberately avoid any "S<digits>"
# pattern so the app's season-extraction regex only fires where intended.
# ------------------------------------------------------------------
MASTER_BLOCKS = [
    # (cid prefix, count, 'New Show ' value, New Show Name, New Season)
    ("dtnb_ep01_", 10, "DTNB", "Daniel Tiger's Neighborhood", "01"),
    ("dtnb_ep02_", 10, "DTNB", "Daniel Tiger's Neighborhood", "02"),
    ("dtnb_ep03_", 10, "DTNB", "Daniel Tiger's Neighborhood", "03"),
    ("dtnb_badrow_", 3, "DTNB", "Daniel Tiger's Neighborhood", "12"),
    ("garf_ep_", 10, "GARF", "Garfield and Friends", "01"),
    ("garf_extra_", 5, "GARF", "Garfield and Friends", "spec"),
    ("arth_ep16_", 5, "ARTH", "Arthur", "16"),
    ("arth_ep17_", 5, "ARTH", "Arthur", "17"),
    ("arth_ep18_", 5, "ARTH", "Arthur", "18"),
    ("arth_ep19_", 5, "ARTH", "Arthur", "19"),
    ("anne_ep_", 5, "ANNE01", "Anne with an E", ""),
    ("scmx_ep03_", 5, "SCMX", "Science Max", "03"),
    ("scmx_ep05_", 5, "SCMX", "Science Max", "05"),
    ("krma_ep_", 5, "KRMA", "Karma's World", "02"),
]

# Titles for master-mapped filler rows, keyed by show code. Kept free of
# "S<digits>" tokens.
SHOW_TITLES = {
    "DTNB": "Daniel Tiger's Neighborhood Episode",
    "GARF": "Garfield and Friends Episode",
    "ARTH": "Arthur Episode",
    "ANNE01": "Anne with an E Episode",
    "SCMX": "Science Max Episode",
    "KRMA": "Karma's World Episode",
}

# Order matters: the app maps each Asset Title keyword to the FIRST List of
# Codes row whose Description contains the keyword.
LIST_OF_CODES = [
    ("FUGT01", "Fugget About It Season One"),
    ("SCMX01", "Science Max Season One"),
    ("SCMX03", "Science Max Season Three"),
    ("GARF01", "Garfield and Friends Season One"),
    ("DTNB01", "Daniel Tiger's Neighborhood Season One"),
    ("DTNB02", "Daniel Tiger's Neighborhood Season Two"),
    ("DTNB03", "Daniel Tiger's Neighborhood Season Three"),
    ("ARTH01", "Arthur Season One"),
    ("ARTH02", "Arthur Season Two"),
    ("KRMA01", "Karma's World Season One"),
    ("ANNE01", "Anne with an E Season One"),
    ("RKMS", "Rockin Music Selection"),
    ("MSBC01", "The Magic School Bus Season One"),
    ("WOTB01", "Wheels on the Bus Nursery Rhymes"),
    ("BLNK01", "Blank Placeholder Series"),
    ("QRPT01", "Quarterly Report Placeholder"),
]


def build_master_ids():
    rows = []
    for prefix, count, show, name, season in MASTER_BLOCKS:
        for i in range(1, count + 1):
            rows.append(
                {
                    "Custom ID": f"{prefix}{i:03d}",
                    "New Show ": show,
                    "New Show Name": name,
                    "New Season": season,
                }
            )
    return rows


def money(rng, low=0.5, high=40.0):
    return round(rng.uniform(low, high), 2)


def write_csv_with_metadata(path, metadata_line, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        if metadata_line is not None:
            fh.write(metadata_line + "\n")
        fh.write(",".join(header) + "\n")
        for row in rows:
            fh.write(",".join(str(v) for v in row) + "\n")


def generate(outdir, red_rows, seed):
    rng = random.Random(seed)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    master_rows = build_master_ids()
    master_ids = [r["Custom ID"] for r in master_rows]
    show_by_id = {r["Custom ID"]: r["New Show "] for r in master_rows}

    def filler_row(i, with_asset_id=True):
        cid = master_ids[i % len(master_ids)]
        title = f"{SHOW_TITLES[show_by_id[cid]]} {i % 40 + 1}"
        row = [rng.choice(COUNTRIES)]
        if with_asset_id:
            row.append(f"AID{i:07d}")
        row += [cid, title, money(rng)]
        return row

    totals = {}

    # ---------------- red_rawdata (skip_first_row) ----------------
    red = [filler_row(i) for i in range(red_rows)]
    red += [
        ["US", "AID9000001", "fug_unmapped_001",
         "Fugget About It - Best Moments", money(rng)],
        ["CA", "AID9000002", "dtnb_movie_special",
         "Backpack Adventures Movie", money(rng)],
        ["US", "AID9000003", "d7mst_tivfg",
         "Untitled Bus Adventure", money(rng)],
        ["GB", "AID9000004", "wwtr_weird_waters_s05",
         "Deep Lake Compilation", money(rng)],
        ["US", "AID9000005", "zzz_unknown_asset_001",
         "Mystery Compilation Vol 1", money(rng)],
        ["DE", "AID9000006", "zzz_unknown_asset_002",
         "Mystery Compilation Vol 2", money(rng)],
        ["FR", "AID9000007", "zzz_unknown_asset_003",
         "Mystery Compilation Vol 3", money(rng)],
    ]
    write_csv_with_metadata(
        outdir / "red_rawdata_asset.csv",
        "YouTube red_rawdata asset report - synthetic fixture",
        ["Country", "Asset ID", "Custom ID", "Asset Title", "Partner Revenue"],
        red,
    )
    totals["red_rawdata"] = sum(r[-1] for r in red)

    # ---------------- rev_views (header on row 1) ----------------
    rev = [filler_row(280 + i) for i in range(280)]
    rev += [
        ["US", "AID9100001", "unmapped_cat_video_01",
         "Garfield and Friends Compilation", money(rng)],
        ["US", "AID9100002", "unmapped_lab_video_01",
         "Science Max Experiments", money(rng)],
        ["CA", "AID9100003", "zzz_unknown_asset_004",
         "Mystery Compilation Vol 4", money(rng)],
    ]
    write_csv_with_metadata(
        outdir / "rev_views_by_asset.csv",
        None,
        ["Country", "Asset ID", "Custom ID", "Asset Title", "Partner Revenue"],
        rev,
    )
    totals["rev_views"] = sum(r[-1] for r in rev)

    # ---------------- red_music_video (skip_first_row, Video Title) --------
    music = []
    for i in range(190):
        cid = master_ids[i % len(master_ids)]
        title = f"{SHOW_TITLES[show_by_id[cid]]} Song {i % 30 + 1}"
        music.append(
            [rng.choice(COUNTRIES), f"AID{8000000 + i:07d}", cid, title,
             money(rng)]
        )
    music.append(
        ["US", "AID8900001", "mv_unknown_theme_001",
         "wheels on the bus sing along", money(rng)]
    )
    write_csv_with_metadata(
        outdir / "red_music_rawdata_video.csv",
        "YouTube red_music rawdata video report - synthetic fixture",
        ["Country", "Asset ID", "Custom ID", "Video Title", "Partner Revenue"],
        music,
    )
    totals["red_music_video"] = sum(r[-1] for r in music)

    # ---------------- shorts subs (skip_first_row) ----------------
    # One row per Video ID; VD0001..VD0150. The first 120 Video IDs are shared
    # with the shorts-ads file (providing its Custom IDs via the merge);
    # VD0121..VD0150 exist only here, exercising the outer-merge right side.
    subs = []
    for i in range(150):
        cid = master_ids[i % len(master_ids)]
        subs.append(
            [rng.choice(COUNTRIES), f"VD{i + 1:04d}", cid,
             f"Shorts Video {i + 1}", money(rng, 0.05, 5.0)]
        )
    write_csv_with_metadata(
        outdir / "shorts_subs_video_summary.csv",
        "YouTube shorts subscription video summary - synthetic fixture",
        ["Country", "Video ID", "Custom ID", "Video Title", "Partner Revenue"],
        subs,
    )
    totals["shorts_subs"] = sum(r[-1] for r in subs)

    # ---------------- shorts ads (header row 1, revshare column) ----------
    ads = []
    for i in range(120):
        ads.append(
            [f"VD{i + 1:04d}", f"Shorts Clip {i + 1}", money(rng, 0.05, 5.0)]
        )
    ads += [
        ["VD0900", "Daniel Tiger Shorts Mix", money(rng, 0.05, 5.0)],
        ["VD0901", "Random Shorts Mix 1", money(rng, 0.05, 5.0)],
        ["VD0902", "Random Shorts Mix 2", money(rng, 0.05, 5.0)],
    ]
    write_csv_with_metadata(
        outdir / "shorts_ads_video_summary.csv",
        None,
        ["Video ID", "Video Title", "Net Partner Revenue (Post revshare)"],
        ads,
    )
    totals["shorts_ads"] = sum(r[-1] for r in ads)

    # ---------------- ADJ dispute file (find_header, header on row 3) ------
    adj = []
    for i in range(60):
        cid = master_ids[(i * 7) % len(master_ids)]
        amount = money(rng, 0.1, 4.0)
        if i % 5 == 0:
            amount = -amount
        adj.append(
            [rng.choice(COUNTRIES), cid,
             f"{SHOW_TITLES[show_by_id[cid]]} adjustment {i + 1}", amount]
        )
    adj_path = outdir / "adj_asset_raw.csv"
    with open(adj_path, "w", newline="", encoding="utf-8") as fh:
        # Junk rows are comma-padded so pandas' headerless preview read
        # (which find_header relies on) parses a consistent field count.
        fh.write("Adjustment Claim Report,,,\n")
        fh.write("Generated for reconciliation fixture testing,,,\n")
        fh.write("Country,Custom ID,Asset Title,Partner Revenue\n")
        for row in adj:
            fh.write(",".join(str(v) for v in row) + "\n")
    totals["adj"] = sum(r[-1] for r in adj)

    # ---------------- ecommerce (skip_first_row, Channel Name) -------------
    channels = [
        "Fugget About It Official",
        "Science Max Official",
        "Karma's World Official",
        "Nine Story Extras",
    ]
    ecom = []
    for i in range(200):
        ecom.append([channels[i % len(channels)], money(rng, 0.1, 8.0)])
    write_csv_with_metadata(
        outdir / "ecommerce_paid_features.csv",
        "Ecommerce paid features report - synthetic fixture",
        ["Channel Name", "Earnings (USD)"],
        ecom,
    )
    totals["ecommerce"] = sum(r[-1] for r in ecom)

    # ---------------- master xlsx ('New Show ' with trailing space) --------
    master_df = pd.DataFrame(
        master_rows,
        columns=["Custom ID", "New Show ", "New Show Name", "New Season"],
    )
    master_df.to_excel(outdir / "master_list.xlsx", index=False)

    # ---------------- List of Codes xlsx ----------------
    codes_df = pd.DataFrame(LIST_OF_CODES, columns=["User Code", "Description"])
    codes_df.to_excel(outdir / "list_of_codes.xlsx", index=False)

    # ---------------- payment summary FROM the fixture totals --------------
    # Labels use the ORIGINAL payment-summary wording: the keys of
    # PAYMENT_SUMMARY_REVENUE_TYPE_MAPPING, plus 'Ads Revenue' and
    # 'Ads Revenue: Dispute Resolution' as-is, plus a final Total row.
    payment_rows = [
        ("Subscriptions Revenue - YouTube Premium / Music Premium",
         totals["red_rawdata"] + totals["red_music_video"]),
        ("Ads Revenue", totals["rev_views"]),
        ("YouTube Shorts - Ads Revenue", totals["shorts_ads"]),
        ("YouTube Shorts - Subscription Revenue", totals["shorts_subs"]),
        ("Ads Revenue: Dispute Resolution", totals["adj"]),
        ("Transactions Revenue - Others", totals["ecommerce"]),
    ]
    grand_total = sum(v for _, v in payment_rows)
    with open(outdir / "payment_summary.csv", "w", newline="",
              encoding="utf-8") as fh:
        fh.write("Revenue Type,Partner Revenue (USD)\n")
        for label, value in payment_rows:
            fh.write(f"{label},{value:.2f}\n")
        fh.write(f"Total,{grand_total:.2f}\n")

    # ---------------- expected values for the test ----------------
    expected = {
        "seed": seed,
        "red_rows": red_rows,
        "file_totals": {k: round(v, 6) for k, v in totals.items()},
        "per_data_source": {
            "Subscription Revenue: YT & Music Premium":
                round(totals["red_rawdata"] + totals["red_music_video"], 6),
            "Ads Revenue": round(totals["rev_views"], 6),
            "YT Shorts Ads Revenue": round(totals["shorts_ads"], 6),
            "YT Shorts Subs Revenue": round(totals["shorts_subs"], 6),
            "Ads Revenue: Dispute Resolution": round(totals["adj"], 6),
            "Transactions Revenue: Others": round(totals["ecommerce"], 6),
        },
        "grand_total": round(grand_total, 6),
        "expected_unmatched_user_codes": ["WWTR05"],
    }
    with open(outdir / "expected_totals.json", "w", encoding="utf-8") as fh:
        json.dump(expected, fh, indent=2)

    print(f"Fixtures written to {outdir.resolve()}")
    print(f"  red_rawdata rows: {len(red)}")
    print(f"  grand total: {grand_total:,.2f}")
    return expected


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--outdir", default=str(Path(__file__).parent / "fixtures")
    )
    parser.add_argument(
        "--red-rows", type=int, default=290,
        help="Number of filler rows in red_rawdata (200000 for the large "
             "timing fixture; keep the default for the committed fixtures).",
    )
    parser.add_argument("--seed", type=int, default=20260301)
    args = parser.parse_args()
    generate(args.outdir, args.red_rows, args.seed)
