"""
YouTube revenue reconciliation - cleaned and fully cached build.

CHANGES IN THIS REVISION (visible outputs preserved unless flagged):

1. DEAD CODE REMOVED
   Everything that was commented out, computed-but-never-displayed, or only
   fed diagnostics has been deleted: Maya snapshots, missing-before tables,
   Custom ID candidate capture / CHECK 2+3, keyword_mapping_review /
   "Rows Populated", sections 3/4/5, both-missing tables, SCMX05 trace,
   seasons 01/16 trace, GARF/pec trace, selected-User-Code trace,
   display_paginated_dataframe, dataframe_to_csv_bytes, join_unique_values,
   normalise_title_text, the dead show_debug sidebar checkbox, the unused
   journal_coding / asset-id-to-find paths, the never-used master New Show
   length "validation", and the season_helper columns on the code mapping.

2. THE HIDDEN CSS CONTAINER IS GONE
   Almost everything after "Missing New Season Review" was indented inside a
   container hidden with display:none - including the TEMPORARY source-file
   totals check, which re-read ALL SEVEN source CSVs with plain pd.read_csv
   on EVERY Streamlit rerun (roughly 800 MB+ of parsing per interaction),
   plus the entire grouped-output pipeline running uncached at module level.
   That was the main reason interactions were slow.

3. FINAL OUTPUT PIPELINE NOW CACHED
   The grouped Show/Season pipeline (single-row rule, Other/missing-season
   allocation, invalid-season family reallocation, SCMX/ARTH/KRMA
   consolidations, User Code build, code-mapping merge) now runs inside the
   cached build_report() function. Reruns render three small cached tables
   and touch no source files and no multi-million-row frames.

4. LOADERS PARSE ONLY THE REQUIRED COLUMNS
   load_csv now probes the header first, then passes usecols to pd.read_csv
   so pandas parses only the requested columns. On the 500 MB / 300 MB files
   this substantially cuts first-run parse time and memory.

5. BEHAVIOUR FIX - MISSING COMMA IN ASSET_TITLE_SHOW_KEYWORDS  ** FLAGGED **
   The list previously contained "Wheels on the Bus" with no trailing comma,
   so Python silently concatenated it with the next entry into the single
   keyword "Wheels on the BusBarney". Neither "Wheels on the Bus" nor
   "Barney" was matching. Fixed - so rows containing those titles may now
   pick up a New Show where they previously fell into the missing list.

6. GUARDS NOW RAISE VISIBLY
   Several st.error + st.stop guards (duplicate User Codes, invalid-season
   revenue with no recipients, allocation reconciliation failures) sat
   inside the hidden container, so a failure would have silently frozen the
   app with an invisible message. They now raise with a clear message.

7. UNMATCHED USER CODES ARE NOW VISIBLE
   The check for final User Codes with no match in the List of Codes file
   was previously hidden by the CSS container. It now shows a visible
   warning when it finds anything, because those rows appear in the Final
   Output with blank Description. Delete that small block if unwanted.

8. CACHE ENTRIES BOUNDED
   max_entries added so old months / superseded rule edits don't accumulate
   large pickled frames in memory.

BUG-FIX PASS (2026-07-31) - eleven review findings addressed:

 1. The payment-summary required-column check now runs BEFORE the file's
    Revenue Type column is first touched, so a malformed file produces
    the intended clear error instead of a raw KeyError.
 2. load_csv gained optional_usecols; red_rawdata and rev_views now load
    'Asset Labels' when the file has it, restoring the Custom ID fallback
    that the usecols optimisation had silently disabled.
 3. New Season extraction (S01-S19) searches only the free-text columns
    (Custom ID / Asset Title / Video Title / Asset Labels) instead of
    every column, so machine columns can no longer donate a season.
 4. Custom ID substring rules require the match to start at a word
    boundary ('az_' no longer fires inside 'topaz_').
 5. The shorts ads/subs Video ID merge is a left join without an
    indicator column: subs-only Video IDs no longer create phantom
    NaN-revenue 'YT Shorts Ads Revenue' rows.
 6. Blank final User Codes (rows that never received a New Show) now
    appear in the unmatched-codes warning table.
 7. 'Film' grouped seasons are treated like Other/missing in the grouped
    allocation, matching the single-grouped-row rule's handling.
 8. SCMX / KRMA consolidations and invalid-season family matching use
    exact New Show equality instead of substring containment (as the
    ARTH consolidation already did).
 9. clean_master_file applies the same dotless-i normalisation as
    clean_custom_id, so such master Custom IDs can match again.
10. Payment-summary amounts in accounting parentheses parse as negative.
11. st.dataframe uses width='stretch' (use_container_width is removed
    from Streamlit after 2025-12-31; this needs Streamlit >= 1.46).
"""

import html
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(layout="wide")

# ============================================================
#                 CONSTANTS / PATTERNS
# ============================================================

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F680-\U0001F6FF"  # transport
    "\U0001F700-\U0001F77F"  # alchemical
    "\U0001F780-\U0001F7FF"  # geometric shapes ext.
    "\U0001F800-\U0001F8FF"  # arrows
    "\U0001F900-\U0001F9FF"  # pictographs
    "\U0001FA00-\U0001FA6F"  # chess
    "\U0001FA70-\U0001FAFF"  # pictographs ext A
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+"
)

# Tokens used to decide whether a text cell counts as "missing".
NEW_SHOW_MISSING_TOKENS = ["none", "nan", "null", "<na>"]

# Hardcoded Asset Title keywords. Add further keywords to this list over time.
# Asset Title matching is case-sensitive; List of Codes Description matching is
# deliberately case-insensitive. The first matching List of Codes row is used.
#
# NOTE: a missing comma previously merged "Wheels on the Bus" and "Barney"
# into one useless keyword. Fixed in this revision.
ASSET_TITLE_SHOW_KEYWORDS = [
    "Fugget",
    "Astroblast",
    "Kratt",
    "Goosebumps",
    "Daniel Tiger",
    "Farzzle's World",
    "Science Max",
    "Magic School Bus",
    "Wheels on the Bus",
    "Barney",
    "Barney's",
    "Clifford",
    "Garfield",
    "Paris & Pups",
    "Lakebottom",
    "Karma's World",
    "Maya & Miguel",
    "Angelina Ballerina",
    "Dr. Panda",
    "Bucket Full of Dinosaurs",
    "Labuntina",
    "Almost Naked Animals",
    "Finding Stuff Out",
    "Donkey Hodie",
    "Let's Go Bananas",
    "Rosie's Rules",
    "Animorphs",
    "Brad Meltzer",
    "Book Hungry Bears",
    "Adventures of Napkin Man",
    "Pirate Express",
    "Horrible Histories",
    "Open Season",
    "Xavier Riddle",
    "Weird Waters",
    "Zerby Derby",
    "Bally Bunch",
    "Woohoos",
    "Artzooka",
    "Do Not Watch This Show",
    "The Baby-Sitters Club",
]

# Custom ID substring mapping. Add new entries here as:
# "text to find": "New Show value"
# Matching is case-insensitive, must start at a word boundary (start of the
# id, or straight after a space/underscore), and only fills rows where
# New Show is missing.
CUSTOM_ID_SHOW_MAPPING = {
    "fait": "FAIT",
    "dnws_": "DTNB",
    "dtnb": "DTNB",
    "dntb": "DTNB",
    "Daniel tiger": "DTNB",
    "daniel tigers": "DTNB",
    "namir hani": "DTNB",
    "le village de dany": "DTNB",
    "tratando con grandes emociones": "DTNB",
    "aventuras de regreso a la escuela": "DTNB",
    "aatb": "AATB",
    "we believe kids": "WEBE",
    "lbb": "LATB",
    "latb_": "LATB",
    "fsot_": "FSOT",
    "fso_": "FSOT",
    "garf": "GARF",
    "wkrt": "WKRT",
    "msbc": "MSBC",
    "ppds": "PPDS",
    "vhcp": "VHCP",
    "bscb": "BSCB",
    "zede": "ZRDS",
    "maya_": "MAYA",
    "mayaandmiguel": "MAYA",
    "mayaanadmiguel": "MAYA",
    "maya  miguel": "MAYA",
    "astb": "ASTR",
    "lbta": "LBTA",
    "anan_": "ANAN",
    "anam_": "ANAN",
    "cplb_": "CPLB",
    "camp_": "CPLB",
    "smax": "SCMX",
    "scmx": "SCMX",
    "barn_": "BARN",
    "rrls": "RRLS",
    "amph": "ANIM",
    "twhs": "TWHS",
    "piex": "PEXP",
    "hhst": "HORR",
    "hbfd": "HBFD",
    "bhb_": "BKHB",
    "dyln_": "DYLN",
    "clifford_": "CBDC",
    "cbdc_": "CBDC",
    "webe_": "WEBE",
    "wwtr_": "WWTR",
    "krma_": "KRMA",
    "angb_": "ANGB",
    "xavr_": "XAVR",
    "xavier riddle": "XAVR",
    "sing_": "TSAL",
    "tsal_": "TSAL",
    "futz_": "FUTZ",
    "drpd_": "DRPD",
    "nman_": "AONM",
    "aonm_": "AONM",
    "aodd_": "AODD",
    "bnwd_": "BARN",
    "dkny_": "DKNY",
    "gb_": "GSBP",
    "gsbp_": "GSBP",
    "wgrl_": "WGRL",
    "fzwd_": "FZWD",
    "maks_": "MAKS",
    "mast_": "MAKS",
    "supw_": "SPRW",
    "lgbn_": "LGBN",
    "csqr_": "CSQR",
    "romo_": "RKMS",
    "the woohoos": "TWHS",
    "l8a_wnxjopa": "LATB",
    "d7mst_tivfg": "MSBC",
    "bsc_": "BSCB",
    "kaplan daniel": "DTNB",
    "artz_": "ARTZ",
    "az_": "ARTZ",
    "artzooka_": "ARTZ",
    "ride_": "RIDE",
    "lkco_": "LOOK",
    "loko_": "LOOK",
    "thbi_": "TBIG",
    "atom_": "ATOM",
    "alit_": "ALIT",
    "dafr_": "DAFR",
    "lubb_": "LUBB",
    "brbf_": "GIVE",
    "ccrz01_": "CCRZ",
}

# Asset Title substring mapping applied after:
# 1. ASSET_TITLE_SHOW_KEYWORDS (Asset Title, then Video Title)
# 2. CUSTOM_ID_SHOW_MAPPING
# Matching is case-insensitive and only fills rows where New Show is missing.
ASSET_TITLE_SHOW_MAPPING = {
    "Daniel tigre": "DTNB",
    "#luandballybunch": "LATB",
    "El Autobús Mágico": "MSBC",
    "singalings": "TSAL",
    "#sciencemax": "SCMX",
    "woohoos": "TWHS",
    "parisandpups": "PAPS",
    "Karma": "KRMA",
    "Cache Craze": "CCRZ",
    "Cat in the Hat": "CHSP",
}

# Grouped rows treated as invalid seasons. Their revenue is spread equally
# across every other grouped row belonging to the same New Show family, and
# the invalid rows are then removed. Add new families/seasons here.
INVALID_SEASONS_BY_FAMILY = {
    "DTNB": ["12", "13"],
    "CPLB": ["13"],
    "FAIT": ["11", "16"],
    "CBDC": ["03"],
    "LBNT": ["01"],
    "LBTA": ["02"],
}

# ============================================================
# RECONCILIATION REVENUE-TYPE MAPPING
# ============================================================

# Keys are the labels found in the independent payment_summary file.
# Values are the canonical data_source labels used by combo_youtube.
PAYMENT_SUMMARY_REVENUE_TYPE_MAPPING = {
    "Transactions Revenue - Others":
        "Transactions Revenue: Others",

    "YouTube Shorts - Ads Revenue":
        "YT Shorts Ads Revenue",

    "YouTube Shorts - Subscription Revenue":
        "YT Shorts Subs Revenue",

    "Subscriptions Revenue - YouTube Premium / Music Premium":
        "Subscription Revenue: YT & Music Premium",
}


# ============================================================
#                     GENERAL LOADERS
# ============================================================


def file_signature(path):
    """Return (path, size, mtime_ns) - used as the cache key so that an
    edited or re-downloaded file automatically invalidates the cache."""
    p = Path(path)
    if not p.exists():
        st.error(f"Source file not found: {path}")
        st.stop()
    stat = p.stat()
    return (str(p), stat.st_size, stat.st_mtime_ns)


def _clean_header_value(value):
    return str(value).replace("\ufeff", "").strip()


@st.cache_data(show_spinner=False, max_entries=10)
def load_csv(
    file_sig,
    skip_first_row=False,
    usecols=None,
    optional_usecols=None,
    find_header=False,
):
    """
    Load a CSV, validating any requested columns and - new in this revision -
    passing usecols down to pd.read_csv so that only the required columns are
    parsed. On the largest source files this is a major speed/memory saving.

    Parameters
    ----------
    file_sig:
        Tuple returned by file_signature().
    skip_first_row:
        For source files whose layout contains exactly one introductory row.
    usecols:
        Columns to retain. Every requested column must be present (with the
        Video Title fallback below) or the app stops with a visible error.
    optional_usecols:
        Columns to retain when the file has them and to skip silently when
        it does not (e.g. Asset Labels). Only applies when usecols is also
        given; they take no part in find_header detection.
    find_header:
        Inspect the first 10 physical rows and use the row containing all
        requested column names as the CSV header.
    """
    filename = file_sig[0]
    header_row = None

    if find_header:
        if not usecols:
            raise ValueError(
                "find_header=True requires an explicit usecols list."
            )

        preview = pd.read_csv(
            filename,
            header=None,
            nrows=10,
            dtype="string",
            keep_default_na=False,
        )

        expected_columns = {_clean_header_value(c) for c in usecols}

        matching_header_rows = []
        for row_number, row in preview.iterrows():
            row_values = {_clean_header_value(v) for v in row.tolist()}
            if expected_columns.issubset(row_values):
                matching_header_rows.append(row_number)

        if len(matching_header_rows) != 1:
            preview_for_display = preview.copy()
            preview_for_display.index = preview_for_display.index + 1
            preview_for_display.index.name = "Physical CSV row"

            st.error(
                "The expected CSV header could not be identified "
                f"unambiguously in:\n\n{filename}"
            )
            st.write("Expected columns:", list(usecols))
            st.write(
                "Number of matching header rows found:",
                len(matching_header_rows),
            )
            st.write(
                "First 10 physical rows of the source file:",
                preview_for_display,
            )
            st.stop()

        header_row = matching_header_rows[0]

    # ------------------------------------------------------------
    # Probe the header only (nrows=0 parses no data rows), so the
    # requested columns can be validated and mapped to the raw header
    # names BEFORE the full parse.
    # ------------------------------------------------------------
    probe_kwargs = {}
    if find_header:
        probe_kwargs["header"] = header_row
    elif skip_first_row:
        probe_kwargs["skiprows"] = [0]

    raw_header = list(pd.read_csv(filename, nrows=0, **probe_kwargs).columns)

    # Map cleaned name -> raw name (raw names may carry a BOM or spaces,
    # and pd.read_csv(usecols=...) must be given the raw names).
    cleaned_to_raw = {}
    for column in raw_header:
        cleaned_to_raw.setdefault(_clean_header_value(column), column)

    resolved_columns = None
    if usecols is not None:
        requested = [_clean_header_value(c) for c in usecols]
        resolved_columns = []
        missing_columns = []

        for name in requested:
            if name in cleaned_to_raw:
                resolved_columns.append(name)
            elif name == "Asset Title" and "Video Title" in cleaned_to_raw:
                # Video-summary source files legitimately contain Video Title
                # instead of Asset Title. clean_custom_id() creates Asset
                # Title from Video Title later, preserving Video Title.
                if "Video Title" not in resolved_columns:
                    resolved_columns.append("Video Title")
            else:
                missing_columns.append(name)

        if missing_columns:
            st.error(
                "The source CSV does not contain all required columns."
            )
            st.write("Source file:", filename)
            st.write("Missing required columns:", missing_columns)
            st.write(
                "Columns actually found:",
                [_clean_header_value(c) for c in raw_header],
            )
            st.stop()

        for name in (optional_usecols or []):
            cleaned_name = _clean_header_value(name)
            if (cleaned_name in cleaned_to_raw
                    and cleaned_name not in resolved_columns):
                resolved_columns.append(cleaned_name)

    # ------------------------------------------------------------
    # Full read - parsing only the columns actually needed.
    # ------------------------------------------------------------
    read_kwargs = {}
    if find_header:
        read_kwargs["header"] = header_row
    elif skip_first_row:
        read_kwargs["skiprows"] = [0]
    if resolved_columns is not None:
        read_kwargs["usecols"] = [
            cleaned_to_raw[name] for name in resolved_columns
        ]

    df = pd.read_csv(filename, **read_kwargs)

    # Remove invisible BOM characters and surrounding spaces from headings.
    df.columns = (
        pd.Index(df.columns)
        .astype("string")
        .str.replace("\ufeff", "", regex=False)
        .str.strip()
    )

    if resolved_columns is not None:
        df = df.loc[:, resolved_columns].copy()

    return df


@st.cache_data(show_spinner=False, max_entries=4)
def load_excel(file_sig, usecols=None):
    return pd.read_excel(file_sig[0], usecols=usecols)


# ============================================================
#                     CLEANING FUNCTIONS
# ============================================================


def clean_custom_id(df, use_asset_label=True):
    # Preserve Video Title for source tracing.
    # If the source has Video Title but no Asset Title, copy Video Title
    # into Asset Title without deleting the original Video Title column.
    df = df.copy()

    if "Video Title" in df.columns and "Asset Title" not in df.columns:
        df["Asset Title"] = df["Video Title"]

    # fill with Asset Title always
    df["Custom ID"] = df["Custom ID"].fillna(df["Asset Title"])

    # fill with Asset Labels ONLY if requested AND exists
    if use_asset_label and "Asset Labels" in df.columns:
        df["Custom ID"] = df["Custom ID"].fillna(df["Asset Labels"])

    # Normalise
    df["Custom ID"] = (
        df["Custom ID"]
        .astype(str)
        .str.lower()
        .str.replace(EMOJI_PATTERN, "", regex=True)
        .str.normalize("NFKD")
        .str.replace(r"[^\w\s]", "", regex=True)
        .str.replace("ı", "i", regex=False)
    )

    return df


def strip_leading_dashes(df):
    df["Custom ID"] = df["Custom ID"].astype(str).str.lstrip("-")
    return df


def clean_master_file(df):
    # Work on a copy so the loaded master dataframe is not modified elsewhere.
    df = df.copy()

    # --------------------------------------------------------
    # Verify the required master-list columns
    # --------------------------------------------------------

    if "Custom ID" not in df.columns:
        raise KeyError(
            "The YouTube master list does not contain the "
            "required 'Custom ID' column."
        )

    if "New Season" not in df.columns:
        raise KeyError(
            "The YouTube master list does not contain the "
            "required 'New Season' column."
        )

    # The master spreadsheet appears to use "New Show " with a trailing
    # space. Check explicitly for the two expected names.
    if "New Show" in df.columns:
        master_new_show_column = "New Show"
    elif "New Show " in df.columns:
        master_new_show_column = "New Show "
    else:
        raise KeyError(
            "The YouTube master list contains neither 'New Show' "
            "nor 'New Show ' with a trailing space. "
            f"Available columns are: {list(df.columns)}"
        )

    # ========================================================
    # CORRECTION 1: Change spec to Other in New Season
    # ========================================================

    spec_season_mask = (
        df["New Season"]
        .astype("string")
        .fillna("")
        .str.strip()
        .str.casefold()
        .eq("spec")
        .fillna(False)
        .to_numpy(dtype=bool)
    )

    df.loc[spec_season_mask, "New Season"] = "Other"

    # ========================================================
    # CORRECTION 2: Split selected New Show codes into
    #               New Show and New Season
    # ========================================================

    cleaned_master_new_show = (
        df[master_new_show_column]
        .astype("string")
        .fillna("")
        .str.strip()
        .str.upper()
    )

    # Only these exact cleaned values are changed:
    # ANNE01 -> New Show ANNE / New Season 01 (etc.)
    show_season_split_mask = (
        cleaned_master_new_show
        .isin(["ANNE01", "ANNE02", "ANNE03", "GRFF01", "GRFF03"])
        .fillna(False)
        .to_numpy(dtype=bool)
    )

    # First, take the final two characters and place them into New Season.
    df.loc[show_season_split_mask, "New Season"] = (
        cleaned_master_new_show.loc[show_season_split_mask]
        .str[-2:]
        .to_numpy()
    )

    # Then remove those final two characters from New Show.
    df.loc[show_season_split_mask, master_new_show_column] = (
        cleaned_master_new_show.loc[show_season_split_mask]
        .str[:-2]
        .to_numpy()
    )

    # ========================================================
    # CORRECTION 3: Standardise all New Show values to uppercase
    # ========================================================

    df[master_new_show_column] = (
        df[master_new_show_column]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    # ========================================================
    # CORRECTION 4: Standardise exact New Show codes
    # ========================================================

    new_show_code_corrections = {
        "BME": "BRAD",
        "BRUN1": "BABT",
        "BRUN2": "BABT",
        "BRUN3": "BABT",
        "AMPH": "ANIM",
        "ANGX": "AXMS",
        "CAFL": "CPTF",
        "CRUM": "TMOC",
        "DIDA": "DDAN",
        "GHTR": "GHST",
        "HOHI": "HORR",
        "WAWE": "WWDA",
        "WTKD": "WKDD",
        "THBI": "TBIG",
        "SWTV": "SWAP",
        "SPLA": "SPLB",
        "SMAX": "SCMX",
        "SKST": "STIC",
        "SKOO": "SKLD",
        "PIEX": "PEXP",
        "MNCH": "MCHF",
        "MASH": "MXAS",
        "IAAN": "IMAA",
        "THWO": "TTWD",
        "UKII": "UKI",
        "BRBF": "GIVE",
        "XAVRR": "XAVR",
    }

    df[master_new_show_column] = (
        df[master_new_show_column]
        .replace(new_show_code_corrections)
        .astype("string")
    )

    # ========================================================
    # EXISTING CUSTOM ID CLEANING
    # ========================================================

    # Same normalisation chain as clean_custom_id, including the dotless-i
    # replacement, so master and source Custom IDs stay comparable.
    df["Custom ID"] = (
        df["Custom ID"]
        .astype(str)
        .str.lower()
        .str.replace(EMOJI_PATTERN, "", regex=True)
        .str.normalize("NFKD")
        .str.replace(r"[^\w\s]", "", regex=True)
        .str.replace("ı", "i", regex=False)
    )

    df = (
        df
        .dropna(subset=["Custom ID"])
        .drop_duplicates(subset=["Custom ID"])
    )

    return df


# ============================================================
#                     MERGE + POST MERGE
# ============================================================


def merge_on_custom_id(df, master):
    master = master.drop_duplicates(subset=["Custom ID"])
    merged = df.merge(master, how="left", on="Custom ID")
    return merged


def apply_show_season(df):
    df["Show_Season"] = (
        df["New Show Name"].astype(str) + " - " + df["New Season"].astype(str)
    )
    return df


def apply_territory(df, country_column_exists=True):
    # Build NA-safe Boolean masks before passing them to np.where.
    # The master uses "New Show " with a trailing space; fall back to
    # "New Show" if a future master drops the space.
    new_show_column = "New Show " if "New Show " in df.columns else "New Show"

    new_show_is_supw = (
        df[new_show_column]
        .astype("string")
        .fillna("")
        .str.strip()
        .str.upper()
        .eq("SUPW")
        .fillna(False)
        .to_numpy(dtype=bool)
    )

    new_show_name_is_peep = (
        df["New Show Name"]
        .astype("string")
        .fillna("")
        .str.strip()
        .str.casefold()
        .eq("peep")
        .fillna(False)
        .to_numpy(dtype=bool)
    )

    if country_column_exists:
        country_is_ca = (
            df["Country"]
            .astype("string")
            .fillna("")
            .str.strip()
            .str.upper()
            .eq("CA")
            .fillna(False)
            .to_numpy(dtype=bool)
        )

        df["Territory"] = np.where(
            country_is_ca,
            "CA",
            np.where(new_show_is_supw, "9SUSA", "INTL"),
        )
    else:
        df["Territory"] = "INTL"

    df["Territory"] = np.where(new_show_name_is_peep, "CA", df["Territory"])

    return df


def complete_post_merge_clean(df, has_country=True):
    df = apply_show_season(df)
    df = apply_territory(df, country_column_exists=has_country)
    return df


# ============================================================
#                    PIPELINE WRAPPERS
# ============================================================


def run_pipeline(df, master, use_asset_label=True, has_country=True):
    df = clean_custom_id(df, use_asset_label)
    df = strip_leading_dashes(df)
    df = merge_on_custom_id(df, master)
    df = complete_post_merge_clean(df, has_country)
    return df


# ============================================================
#                    SHARED HELPERS
# ============================================================


def standardise_payment_summary_revenue_type(series):
    """
    Standardise payment_summary Revenue Type values to the canonical
    data_source names used by combo_youtube. Any value not included in
    PAYMENT_SUMMARY_REVENUE_TYPE_MAPPING is left unchanged.
    """
    cleaned = (
        series
        .astype("string")
        .map(html.unescape)
        .str.replace("\u00a0", " ", regex=False)
        .str.strip()
    )

    return cleaned.replace(PAYMENT_SUMMARY_REVENUE_TYPE_MAPPING)


def bold_total_row(row, column_name, total_label):
    """Apply bold formatting and a top border to a total row."""
    cell_value = row[column_name]

    is_total_row = (
        pd.notna(cell_value)
        and str(cell_value).strip() == total_label
    )

    style = (
        "font-weight: bold; border-top: 2px solid black;"
        if is_total_row
        else ""
    )

    return [style] * len(row)


def missing_text_mask(series, missing_tokens):
    """Vectorised 'is this text cell missing' check."""
    cleaned = series.astype("string").str.strip().str.casefold()
    return series.isna() | cleaned.eq("") | cleaned.isin(missing_tokens)


# ============================================================
#                     FILE PATHS
# ============================================================

with st.echo():
    payment_summary = 'C:/Users/Darragh.Noonan/Downloads/python/distribution/YT Reports 1/YouTube_9StoryIreland_M_20260301_payment_summary_v1-0.csv'

    red_rawdata = 'C:/Users/Darragh.Noonan/Downloads/python/distribution/YT Reports 1/YouTube_9StoryIreland_M_20260301_20260331_red_rawdata_asset_v1-1.csv'
    rev_views = 'C:/Users/Darragh.Noonan/Downloads/python/distribution/YT Reports 1/YouTube_9StoryIreland_M_20260301_20260331_rev_views_by_asset_v1-0.csv'
    red_music_video = 'C:/Users/Darragh.Noonan/Downloads/python/distribution/YT Reports 1/YouTube_9StoryIreland_M_20260301_20260331_red_music_rawdata_video_v1-1.csv'
    ads_revenue_shorts_path = 'C:/Users/Darragh.Noonan/Downloads/python/distribution/YT Reports 1/YouTube_9StoryIreland_M_20260301_20260331_monthly_shorts_non_music_ads_video_summary_v1-1.csv'
    ads_subs_shorts_path = 'C:/Users/Darragh.Noonan/Downloads/python/distribution/YT Reports 1/YouTube_9StoryIreland_M_20260301_20260331_monthly_shorts_non_music_subscription_video_summary_v1-0.csv'
    ads_revenue_dispute_resolution = 'C:/Users/Darragh.Noonan/Downloads/python/distribution/YT Reports 1/YouTube_9StoryIreland_M_20260301_ADJ_asset_raw_v1-1.csv'
    transactions_revenue_others = 'C:/Users/Darragh.Noonan/Downloads/python/distribution/YT Reports 1/YouTube_9StoryIreland_Ecommerce_paid_features_M_20260301_20260331_v1-1.csv'

    youtube_master_list = 'C:/Users/Darragh.Noonan/Downloads/python/distribution/YT Reports/Youtube Analysis - Master List.xlsx'
    code_mapping_shows = 'C:/Users/Darragh.Noonan/Downloads/python/distribution/feb_2025/List of Codes.xlsx'

# --------------------------------------------------------
# INFORMATIONAL: SOURCE FILE TO PAYMENT SUMMARY MAPPING
# --------------------------------------------------------

payment_summary_source_mapping = pd.DataFrame(
    [
        {
            "Revenue Type": "Subscription Revenue: YT & Music Premium",
            "Source File": Path(red_rawdata).name,
        },
        {
            "Revenue Type": "Subscription Revenue: YT & Music Premium",
            "Source File": Path(red_music_video).name,
        },
        {
            "Revenue Type": "Ads Revenue",
            "Source File": Path(rev_views).name,
        },
        {
            "Revenue Type": "YT Shorts Ads Revenue",
            "Source File": Path(ads_revenue_shorts_path).name,
        },
        {
            "Revenue Type": "YT Shorts Subs Revenue",
            "Source File": Path(ads_subs_shorts_path).name,
        },
        {
            "Revenue Type": "Ads Revenue: Dispute Resolution",
            "Source File": Path(ads_revenue_dispute_resolution).name,
        },
        {
            "Revenue Type": "Transactions Revenue: Others",
            "Source File": Path(transactions_revenue_others).name,
        },
    ]
)

st.markdown("#### How the source files feed the payment summary")
st.caption(
    "This table is for information only. It shows which input data file "
    "feeds each Revenue Type in the payment_summary report. The two "
    "subscription files roll up into the payment summary's single "
    "'Subscription Revenue: YT & Music Premium' line."
)

st.dataframe(
    payment_summary_source_mapping,
    width="stretch",
    hide_index=True,
    column_config={
        "Revenue Type": st.column_config.TextColumn(
            "Revenue Type in payment_summary"
        ),
        "Source File": st.column_config.TextColumn(
            "File loaded into memory"
        ),
    },
)

# ============================================================
#        STAGE 1 (CACHED): LOAD, CLEAN, MERGE, RECONCILE
# ============================================================


@st.cache_data(show_spinner=False, max_entries=2)
def build_combo(
    payment_summary_sig,
    red_rawdata_sig,
    rev_views_sig,
    red_music_video_sig,
    ads_revenue_shorts_sig,
    ads_subs_shorts_sig,
    ads_revenue_dispute_resolution_sig,
    transactions_revenue_others_sig,
    youtube_master_sig,
    code_mapping_sig,
):
    """Everything from file load through the payment-summary reconciliation.

    Only re-runs when a source file changes (path, size or mtime)."""

    # ---- show code mapping ----
    show_code_mapping = load_excel(
        code_mapping_sig,
        usecols=["User Code", "Description"],
    ).copy()

    show_code_mapping["User Code"] = (
        show_code_mapping["User Code"].astype("string").str.strip()
    )
    show_code_mapping["Description"] = (
        show_code_mapping["Description"].astype("string").str.strip()
    )
    show_code_mapping["New Show"] = show_code_mapping["User Code"].str[:4]

    # ---- master ----
    master = clean_master_file(load_excel(youtube_master_sig))

    # ---- the seven revenue sources ----
    # Asset Labels is optional: when a file carries it, it restores the
    # Custom ID <- Asset Labels fallback in clean_custom_id that the
    # usecols optimisation had silently disabled.
    df_1 = run_pipeline(
        load_csv(
            red_rawdata_sig,
            skip_first_row=True,
            usecols=['Country', 'Asset ID', 'Custom ID', 'Asset Title', 'Partner Revenue'],
            optional_usecols=['Asset Labels'],
        ),
        master,
    )
    df_3 = run_pipeline(
        load_csv(
            rev_views_sig,
            usecols=['Country', 'Asset ID', 'Custom ID', 'Asset Title', 'Partner Revenue'],
            optional_usecols=['Asset Labels'],
        ),
        master,
    )
    df_4 = run_pipeline(
        load_csv(
            red_music_video_sig,
            skip_first_row=True,
            usecols=['Country', 'Asset ID', 'Custom ID', 'Video Title', 'Partner Revenue'],
        ),
        master,
        use_asset_label=False,
    )

    # Shorts
    # No Country or Custom ID in ads revenue shorts path
    ads_revenue_shorts = load_csv(
        ads_revenue_shorts_sig,
        usecols=[
            "Video ID",
            "Video Title",
            "Net Partner Revenue (Post revshare)",
        ],
    ).rename(
        columns={
            "Net Partner Revenue (Post revshare)": "Partner Revenue",
        }
    )

    ads_subs_raw = load_csv(
        ads_subs_shorts_sig,
        skip_first_row=True,
        usecols=['Country', 'Video ID', 'Custom ID', 'Video Title', 'Partner Revenue'],
    )

    video_id_map = ads_subs_raw[["Video ID", "Custom ID"]].drop_duplicates(
        subset=["Video ID"]
    )
    # Left join: subs-only Video IDs carry no shorts-ads revenue, so an
    # outer join would only create phantom NaN-revenue rows under the
    # "YT Shorts Ads Revenue" label (their real revenue arrives via
    # ads_subs_shorts below).
    ads_with_custom_id_shorts = pd.merge(
        ads_revenue_shorts, video_id_map, on="Video ID", how="left",
    )
    ads_with_custom_id_shorts = run_pipeline(
        ads_with_custom_id_shorts, master, use_asset_label=False,
        has_country=False,
    )

    ads_subs_shorts = run_pipeline(ads_subs_raw, master, use_asset_label=False)

    # Dispute-resolution adjustment file: same asset-level structure as the
    # standard asset revenue sources, with a metadata row first.
    ads_revenue_dispute_resolution_df = run_pipeline(
        load_csv(
            ads_revenue_dispute_resolution_sig,
            find_header=True,
            usecols=["Country", "Custom ID", "Asset Title", "Partner Revenue"],
        ),
        master,
    )

    # Paid-features transaction file: the first row is metadata and the
    # second row contains the headers. Only Channel Name and Earnings (USD)
    # are required. It has no Custom ID, so a missing Custom ID is added;
    # Asset Title rules can still populate New Show from Channel Name.
    transactions_revenue_others_df = (
        load_csv(
            transactions_revenue_others_sig,
            skip_first_row=True,
            usecols=['Channel Name', 'Earnings (USD)'],
        )
        .rename(
            columns={
                'Channel Name': 'Asset Title',
                'Earnings (USD)': 'Partner Revenue',
            }
        )
    )
    transactions_revenue_others_df['Custom ID'] = pd.NA
    transactions_revenue_others_df = run_pipeline(
        transactions_revenue_others_df,
        master,
        has_country=False,
    )

    # Combine all
    # Label every row with the canonical reconciliation name. The
    # payment_summary Revenue Type is mapped to the same canonical key below.
    # red_rawdata and red_music_video intentionally share one label:
    # together they make up the payment summary's single subscription line.
    df_1["data_source"] = "Subscription Revenue: YT & Music Premium"
    df_3["data_source"] = "Ads Revenue"
    df_4["data_source"] = "Subscription Revenue: YT & Music Premium"
    ads_with_custom_id_shorts["data_source"] = "YT Shorts Ads Revenue"
    ads_subs_shorts["data_source"] = "YT Shorts Subs Revenue"
    ads_revenue_dispute_resolution_df["data_source"] = (
        "Ads Revenue: Dispute Resolution"
    )
    transactions_revenue_others_df["data_source"] = (
        "Transactions Revenue: Others"
    )

    combo_youtube = pd.concat(
        [
            df_1,
            df_3,
            df_4,
            ads_with_custom_id_shorts,
            ads_subs_shorts,
            ads_revenue_dispute_resolution_df,
            transactions_revenue_others_df,
        ],
        ignore_index=True,
        sort=False,
    ).drop(columns=["Uploader"], errors="ignore")

    combo_youtube["Partner Revenue"] = pd.to_numeric(
        combo_youtube["Partner Revenue"],
        errors="raise",
    )

    # Total Partner Revenue in combo_youtube, grouped by data_source.
    data_source_totals = (
        combo_youtube.groupby(
            "data_source", as_index=False, dropna=False
        )["Partner Revenue"]
        .sum()
        .rename(columns={"Partner Revenue": "combo_youtube_total"})
        .sort_values("data_source")
        .reset_index(drop=True)
    )

    # ---- payment summary ----
    payment_summary_df = load_csv(payment_summary_sig)
    payment_summary_df.columns = (
        payment_summary_df.columns
        .astype(str)
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )

    # Validate the required columns BEFORE any of them are touched, so a
    # malformed payment file raises this clear message rather than a raw
    # KeyError from the Original Revenue Type line below.
    required_payment_columns = ["Revenue Type", "Partner Revenue (USD)"]
    missing_payment_columns = [
        column for column in required_payment_columns
        if column not in payment_summary_df.columns
    ]
    if missing_payment_columns:
        raise KeyError(
            "The payment_summary file is missing required columns: "
            + ", ".join(missing_payment_columns)
        )

    # Preserve the independent payment-summary wording for audit purposes.
    payment_summary_df["Original Revenue Type"] = (
        payment_summary_df["Revenue Type"]
        .astype("string")
        .map(html.unescape)
        .str.replace("\u00a0", " ", regex=False)
        .str.strip()
    )

    # Create the canonical reconciliation key.
    payment_summary_df["data_source"] = (
        standardise_payment_summary_revenue_type(
            payment_summary_df["Original Revenue Type"]
        )
    )

    payment_summary_df["Revenue Type"] = (
        payment_summary_df["Revenue Type"].astype("string").str.strip()
    )

    total_row_mask = (
        payment_summary_df["Revenue Type"]
        .str.casefold()
        .eq("total")
        .fillna(False)
    )
    if total_row_mask.any():
        total_row_position = np.flatnonzero(total_row_mask.to_numpy())[0]
        payment_summary_df = payment_summary_df.iloc[:total_row_position].copy()

    payment_summary_df = payment_summary_df.dropna(
        subset=["Revenue Type", "Partner Revenue (USD)"]
    ).copy()

    # Accounting-style "(1,234.56)" negatives become "-1234.56".
    payment_summary_df["Partner Revenue (USD)"] = pd.to_numeric(
        payment_summary_df["Partner Revenue (USD)"]
        .astype("string")
        .str.strip()
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace(r"^\((.*)\)$", r"-\1", regex=True),
        errors="raise",
    )

    # Reconcile using the canonical key created above, not the payment
    # summary's original wording. Grouping by "Revenue Type" here would
    # bypass PAYMENT_SUMMARY_REVENUE_TYPE_MAPPING and create two separate
    # outer-merge rows for labels that mean the same thing.
    payment_summary_totals = (
        payment_summary_df.groupby(
            "data_source", as_index=False, dropna=False
        )["Partner Revenue (USD)"]
        .sum()
        .rename(columns={"Partner Revenue (USD)": "payment_summary_total"})
        .sort_values("data_source")
        .reset_index(drop=True)
    )

    reconciliation = (
        data_source_totals.merge(
            payment_summary_totals,
            on="data_source",
            how="outer",
            indicator="match_status",
        )
        .sort_values("data_source")
        .reset_index(drop=True)
    )
    reconciliation["difference"] = (
        reconciliation["combo_youtube_total"].fillna(0)
        - reconciliation["payment_summary_total"].fillna(0)
    )
    reconciliation["matches"] = reconciliation["difference"].abs().le(0.01)

    # Standardise combo column names AFTER the source-level totals
    # (for example, "New Show " -> "New Show").
    combo_youtube.columns = (
        combo_youtube.columns
        .astype(str)
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )

    return {
        "combo": combo_youtube,
        "show_code_mapping": show_code_mapping,
        "reconciliation": reconciliation,
    }


# ============================================================
#   STAGE 2 (CACHED): NEW SHOW RULES -> NEW SEASON -> OUTPUT
# ============================================================


@st.cache_data(show_spinner=False, max_entries=2)
def build_report(
    payment_summary_sig,
    red_rawdata_sig,
    rev_views_sig,
    red_music_video_sig,
    ads_revenue_shorts_sig,
    ads_subs_shorts_sig,
    ads_revenue_dispute_resolution_sig,
    transactions_revenue_others_sig,
    youtube_master_sig,
    code_mapping_sig,
    asset_title_keywords,
    custom_id_mapping_items,
    asset_title_mapping_items,
    invalid_seasons_items,
):
    """Applies every mapping rule and builds all three display tables:
    the reconciliation, the Missing New Show review, and the final grouped
    Output by Title (which previously ran uncached at module level).

    Re-runs when a file changes OR when the keyword / custom-id / invalid-
    season mappings are edited - but a mapping edit reuses the cached
    Stage 1 result, so the big files are not reloaded."""

    base = build_combo(
        payment_summary_sig,
        red_rawdata_sig,
        rev_views_sig,
        red_music_video_sig,
        ads_revenue_shorts_sig,
        ads_subs_shorts_sig,
        ads_revenue_dispute_resolution_sig,
        transactions_revenue_others_sig,
        youtube_master_sig,
        code_mapping_sig,
    )
    combo = base["combo"]
    show_code_mapping = base["show_code_mapping"]

    out = {"reconciliation": base["reconciliation"]}

    required_review_columns = [
        "Asset Title",
        "Country",
        "Custom ID",
        "New Show",
        "Partner Revenue",
    ]
    missing_review_columns = [
        column for column in required_review_columns
        if column not in combo.columns
    ]
    out["missing_review_columns"] = missing_review_columns
    if missing_review_columns:
        return out

    # One-off string conversions, reused by every rule below.
    title_str = combo["Asset Title"].astype("string")

    has_video_title = "Video Title" in combo.columns
    video_title_str = (
        combo["Video Title"].astype("string") if has_video_title else None
    )

    has_custom_id = "Custom ID" in combo.columns
    cid_str = combo["Custom ID"].astype("string") if has_custom_id else None

    # --------------------------------------------------------
    # STAGE A - fill New Show.
    # The missing mask is computed once and maintained incrementally
    # as the rules assign values.
    # --------------------------------------------------------
    missing = missing_text_mask(combo["New Show"], NEW_SHOW_MISSING_TOKENS)

    # Build one New Show result per keyword from the first matching
    # List of Codes Description row.
    keyword_show_mapping = {}
    descriptions = show_code_mapping["Description"]
    for keyword in asset_title_keywords:
        code_match = descriptions.str.contains(
            keyword, case=False, regex=False, na=False
        )
        if code_match.any():
            keyword_show_mapping[keyword] = show_code_mapping.loc[
                code_match, "New Show"
            ].iloc[0]
        else:
            keyword_show_mapping[keyword] = pd.NA

    # --------------------------------------------------------
    # Rule 1: Asset Title keywords (case-sensitive), applied in list
    # order, scanning ONLY the rows still missing a New Show.
    # --------------------------------------------------------
    pending = combo.index[missing]
    for keyword in asset_title_keywords:
        mapped_new_show = keyword_show_mapping[keyword]
        if pd.isna(mapped_new_show) or len(pending) == 0:
            continue

        title_subset = title_str.loc[pending]
        hits = title_subset.str.contains(
            keyword, case=True, regex=False, na=False
        )
        rows_to_update = title_subset.index[hits]
        if len(rows_to_update) == 0:
            continue

        combo.loc[rows_to_update, "New Show"] = mapped_new_show
        missing.loc[rows_to_update] = False
        pending = pending.difference(rows_to_update)

    # --------------------------------------------------------
    # Rule 2: the same keywords against Video Title (case-insensitive),
    # only for rows where New Show is still missing.
    # --------------------------------------------------------
    if has_video_title:
        pending = combo.index[missing]

        for keyword in asset_title_keywords:
            mapped_new_show = keyword_show_mapping[keyword]
            if pd.isna(mapped_new_show) or len(pending) == 0:
                continue

            video_title_subset = video_title_str.loc[pending]
            hits = video_title_subset.str.contains(
                keyword, case=False, regex=False, na=False
            )
            rows_to_update = video_title_subset.index[hits]
            if len(rows_to_update) == 0:
                continue

            combo.loc[rows_to_update, "New Show"] = mapped_new_show
            missing.loc[rows_to_update] = False
            pending = pending.difference(rows_to_update)

    # --------------------------------------------------------
    # Rule 3: Custom ID substring mapping (case-insensitive), in dict
    # order, again scanning only the shrinking still-missing subset.
    # The match must start at a word boundary (start of the id, or after
    # a space/underscore), so a short token such as "az_" no longer
    # fires inside unrelated ids like "topaz_collection".
    # --------------------------------------------------------
    if has_custom_id:
        pending = combo.index[missing]
        for custom_id_text, mapped_new_show in custom_id_mapping_items:
            if len(pending) == 0:
                break

            custom_id_pattern = r"(?<![0-9a-z])" + re.escape(custom_id_text)
            cid_subset = cid_str.loc[pending]
            hits = cid_subset.str.contains(
                custom_id_pattern, case=False, regex=True, na=False
            )
            rows_to_update = cid_subset.index[hits]
            if len(rows_to_update) == 0:
                continue

            combo.loc[rows_to_update, "New Show"] = mapped_new_show
            missing.loc[rows_to_update] = False
            pending = pending.difference(rows_to_update)

    # --------------------------------------------------------
    # Rule 4: explicit Asset Title substring mappings (case-insensitive),
    # applied last, only where New Show is still missing.
    # --------------------------------------------------------
    pending = combo.index[missing]
    for asset_title_text, mapped_new_show in asset_title_mapping_items:
        if len(pending) == 0:
            break

        title_subset = title_str.loc[pending]
        hits = title_subset.str.contains(
            asset_title_text, case=False, regex=False, na=False
        )
        rows_to_update = title_subset.index[hits]
        if len(rows_to_update) == 0:
            continue

        combo.loc[rows_to_update, "New Show"] = mapped_new_show
        missing.loc[rows_to_update] = False
        pending = pending.difference(rows_to_update)

    # --------------------------------------------------------
    # STAGE A COMPLETE. Recompute the mask from scratch once so the
    # review table uses exactly the same definition as before.
    # --------------------------------------------------------
    final_missing = missing_text_mask(combo["New Show"], NEW_SHOW_MISSING_TOKENS)

    missing_after_rows = combo.loc[final_missing].copy()

    # Some source files contain Asset ID, some contain Video ID, and some
    # may contain neither. Missing optional columns display as blanks.
    missing_new_show_review = missing_after_rows.copy()
    optional_review_columns = ["data_source", "Asset ID", "Video Title", "Video ID"]
    for column in optional_review_columns:
        if column not in missing_new_show_review.columns:
            missing_new_show_review[column] = pd.NA

    out["missing_new_show_review"] = (
        missing_new_show_review.loc[
            :,
            [
                "Asset Title",
                "Country",
                "Custom ID",
                "data_source",
                "Asset ID",
                "Video ID",
                "Video Title",
                "Partner Revenue",
            ],
        ]
        .rename(columns={"data_source": "Data Source Type"})
        .sort_values(
            ["Partner Revenue", "Asset Title", "Country", "Custom ID"],
            ascending=[False, True, True, True],
            na_position="last",
        )
        .reset_index(drop=True)
    )

    # --------------------------------------------------------
    # STAGE B1 - New Season direct rule.
    # For rows where New Season is missing, search the free-text source
    # columns for S01 through S19 and map the matched value to 01
    # through 19. Machine columns (Asset ID, Video ID, data_source,
    # Territory, Show_Season, ...) are deliberately excluded so an
    # incidental "S12"-style token in an identifier cannot donate a
    # season.
    # --------------------------------------------------------
    if "New Season" not in combo.columns:
        raise KeyError("Required column 'New Season' is missing from combo.")

    new_season_missing_before = missing_text_mask(
        combo["New Season"], NEW_SHOW_MISSING_TOKENS
    )
    season_search_columns = [
        column
        for column in ["Custom ID", "Asset Title", "Video Title",
                       "Asset Labels"]
        if column in combo.columns
    ]
    season_search_text = (
        combo.loc[new_season_missing_before, season_search_columns]
        .astype("string")
        .fillna("")
        .agg(" | ".join, axis=1)
    )

    extracted_new_season = season_search_text.str.extract(
        r"S(0[1-9]|1[0-9])(?!\d)",
        flags=re.IGNORECASE,
        expand=False,
    )

    season_rows_to_update = extracted_new_season.dropna()
    combo.loc[season_rows_to_update.index, "New Season"] = season_rows_to_update

    # --------------------------------------------------------
    # STAGE B2 - New Season allocation.
    # Rows still missing New Season are spread across the distinct
    # existing seasons of the same New Show. Allocation applies only
    # where more than two seasons exist. This duplicates rows, so it
    # runs after all New Show rules and the review table above.
    # --------------------------------------------------------
    combo["Partner Revenue"] = pd.to_numeric(
        combo["Partner Revenue"], errors="coerce"
    )
    allocation_total_before = float(combo["Partner Revenue"].fillna(0).sum())

    missing_after_direct_rule = missing_text_mask(
        combo["New Season"], NEW_SHOW_MISSING_TOKENS
    )
    valid_existing_season = (
        ~missing_after_direct_rule
        & ~combo["New Season"]
        .astype("string")
        .str.strip()
        .str.casefold()
        .eq("other")
        & ~missing_text_mask(combo["New Show"], NEW_SHOW_MISSING_TOKENS)
    )

    season_lookup = (
        combo.loc[valid_existing_season, ["New Show", "New Season"]]
        .drop_duplicates()
        .sort_values(["New Show", "New Season"])
    )
    season_lookup["Existing Season Count"] = (
        season_lookup.groupby("New Show")["New Season"].transform("size")
    )
    eligible_season_lookup = season_lookup.loc[
        season_lookup["Existing Season Count"] > 2
    ].copy()

    allocation_source_mask = (
        missing_after_direct_rule
        & combo["New Show"].isin(eligible_season_lookup["New Show"])
    )
    allocation_source_rows = combo.loc[allocation_source_mask].copy()
    allocation_source_rows["Season Allocation Source Row"] = (
        allocation_source_rows.index
    )
    allocation_source_rows["Season Allocation Original Revenue"] = (
        allocation_source_rows["Partner Revenue"]
    )

    if allocation_source_rows.empty:
        final_combo = combo.copy()
        final_combo["Season Allocation Source Row"] = pd.NA
        final_combo["Season Allocation Original Revenue"] = pd.NA
        final_combo["Season Allocation Method"] = pd.NA
    else:
        allocated_rows = allocation_source_rows.drop(
            columns=["New Season"]
        ).merge(
            eligible_season_lookup,
            on="New Show",
            how="inner",
            validate="many_to_many",
        )
        allocated_rows["Partner Revenue"] = (
            allocated_rows["Season Allocation Original Revenue"]
            / allocated_rows["Existing Season Count"]
        )
        allocated_rows["Season Allocation Method"] = (
            "Evenly allocated across existing seasons"
        )
        allocated_rows = allocated_rows.drop(columns=["Existing Season Count"])

        unallocated_rows = combo.loc[~allocation_source_mask].copy()
        unallocated_rows["Season Allocation Source Row"] = pd.NA
        unallocated_rows["Season Allocation Original Revenue"] = pd.NA
        unallocated_rows["Season Allocation Method"] = pd.NA
        final_combo = pd.concat(
            [unallocated_rows, allocated_rows], ignore_index=True, sort=False
        )

    if "New Show Name" in final_combo.columns:
        final_combo["Show_Season"] = (
            final_combo["New Show Name"].astype("string")
            + " - "
            + final_combo["New Season"].astype("string")
        )

    allocation_total_after = float(
        final_combo["Partner Revenue"].fillna(0).sum()
    )
    allocation_total_difference = (
        allocation_total_after - allocation_total_before
    )
    if abs(allocation_total_difference) > 0.01:
        raise ValueError(
            "New Season allocation changed total Partner Revenue by "
            f"{allocation_total_difference:,.6f}."
        )

    combo = final_combo

    # ========================================================
    # FINAL GROUPED OUTPUT (previously uncached at module level)
    # ========================================================

    # Remove an opening "S" from New Season values (S01 -> 01).
    # ^ means "only at the beginning".
    combo["New Season"] = (
        combo["New Season"]
        .astype("string")
        .str.strip()
        .str.replace(r"^[Ss]", "", regex=True)
    )

    # Only the three columns this analysis needs; the full detailed frame
    # is never copied or returned (it can exceed 1 GB in memory).
    show_season_source = combo.loc[
        :, ["New Show", "New Season", "Partner Revenue"]
    ].copy()
    show_season_source["Partner Revenue"] = pd.to_numeric(
        show_season_source["Partner Revenue"], errors="coerce"
    )
    source_total = float(show_season_source["Partner Revenue"].sum())

    # Group by New Show and New Season. dropna=False keeps missing
    # New Show / New Season values visible to the later rules.
    revenue_by_show_season = (
        show_season_source
        .groupby(["New Show", "New Season"], dropna=False, as_index=False)
        .agg(
            **{
                "Partner Revenue": ("Partner Revenue", "sum"),
                "Row Count": ("Partner Revenue", "size"),
            }
        )
        .sort_values(["New Show", "New Season"], na_position="last")
        .reset_index(drop=True)
    )

    # --------------------------------------------------------
    # SINGLE GROUPED ROW RULE
    # Where a New Show has only one grouped New Season row, change
    # Film, Other, or a missing New Season to season 01.
    # --------------------------------------------------------
    single_row_season_check = (
        revenue_by_show_season["New Season"]
        .astype("string")
        .fillna("")
        .str.strip()
        .str.casefold()
    )

    grouped_rows_per_show = (
        revenue_by_show_season
        .groupby("New Show", dropna=False)["New Season"]
        .transform("size")
    )

    single_row_source_season_mask = (
        revenue_by_show_season["New Season"].isna()
        | single_row_season_check.isin(
            ["", "film", "other", "none", "nan", "null", "<na>"]
        )
    ).fillna(False)

    single_row_to_season_01_mask = (
        grouped_rows_per_show.eq(1) & single_row_source_season_mask
    ).fillna(False).to_numpy(dtype=bool)

    revenue_by_show_season.loc[
        single_row_to_season_01_mask, "New Season"
    ] = "01"

    revenue_by_show_season = (
        revenue_by_show_season
        .sort_values(["New Show", "New Season"], na_position="last")
        .reset_index(drop=True)
    )

    # --------------------------------------------------------
    # ALLOCATE "OTHER", "FILM" AND MISSING-SEASON REVENUE ACROSS
    # THE VALID GROUPED SEASONS OF THE SAME NEW SHOW.
    # Source rows are removed once allocated; shows with no valid
    # season keep their source rows untouched. "Film" is included so
    # multi-row shows treat it the same way the single-grouped-row
    # rule above does.
    # --------------------------------------------------------
    season_was_na = revenue_by_show_season["New Season"].isna()
    season_check = (
        revenue_by_show_season["New Season"]
        .astype("string")
        .fillna("")
        .str.strip()
        .str.casefold()
    )

    is_other = season_check.eq("other").fillna(False)
    is_missing_season = (
        season_was_na
        | season_check.isin(["", "none", "nan", "null", "<na>", "film"])
    ).fillna(False)

    is_allocation_source = (is_other | is_missing_season).astype(bool)
    is_valid_recipient = (~is_allocation_source).astype(bool)

    show_key = revenue_by_show_season["New Show"]

    recipient_count = (
        is_valid_recipient.astype("int64")
        .groupby(show_key, dropna=False)
        .transform("sum")
        .fillna(0)
        .astype("int64")
    )

    allocation_source_total = (
        revenue_by_show_season["Partner Revenue"]
        .where(is_allocation_source, 0.0)
        .groupby(show_key, dropna=False)
        .transform("sum")
        .fillna(0.0)
    )

    receive_allocation_mask = (
        is_valid_recipient & recipient_count.gt(0)
    ).fillna(False)
    safe_recipient_count = recipient_count.replace(0, np.nan)

    amount_added = pd.Series(
        np.where(
            receive_allocation_mask.to_numpy(dtype=bool),
            allocation_source_total / safe_recipient_count,
            0.0,
        ),
        index=revenue_by_show_season.index,
    ).fillna(0.0)

    revenue_by_show_season["Partner Revenue"] = (
        revenue_by_show_season["Partner Revenue"] + amount_added
    )

    # Remove Other/missing source rows only where a valid recipient exists.
    allocated_source_mask = (
        is_allocation_source & recipient_count.gt(0)
    ).fillna(False).to_numpy(dtype=bool)

    revenue_by_show_season = (
        revenue_by_show_season.loc[~allocated_source_mask]
        .sort_values(["New Show", "New Season"], na_position="last")
        .reset_index(drop=True)
    )

    # --------------------------------------------------------
    # INVALID SEASONS - REALLOCATE TO VALID GROUPED ROWS.
    # See INVALID_SEASONS_BY_FAMILY at the top of the file.
    # For each family: total the invalid-season revenue, split it
    # equally across the other grouped rows, remove the invalid rows.
    # --------------------------------------------------------
    invalid_seasons_by_family = dict(invalid_seasons_items)

    invalid_show_check = (
        revenue_by_show_season["New Show"]
        .astype("string")
        .str.strip()
        .str.upper()
    )
    invalid_season_check = (
        revenue_by_show_season["New Season"]
        .astype("string")
        .str.strip()
        .str.replace(r"^[Ss]", "", regex=True)
    )

    invalid_family = pd.Series(
        pd.NA, index=revenue_by_show_season.index, dtype="string"
    )
    # Exact-equality matching (like the ARTH consolidation below), so a
    # future code merely containing a family name cannot be swept in.
    for family_name in invalid_seasons_by_family:
        family_show_mask = invalid_show_check.eq(family_name).fillna(False)
        invalid_family.loc[family_show_mask] = family_name

    invalid_source_mask = pd.Series(
        False, index=revenue_by_show_season.index, dtype=bool
    )
    for family_name, family_seasons in invalid_seasons_by_family.items():
        family_source_mask = (
            invalid_family.eq(family_name)
            & invalid_season_check.isin(family_seasons)
        ).fillna(False)
        invalid_source_mask = invalid_source_mask | family_source_mask

    invalid_source_mask = invalid_source_mask.fillna(False).astype(bool)
    invalid_recipient_mask = (
        invalid_family.notna() & ~invalid_source_mask
    ).fillna(False)

    invalid_source_revenue_by_family = (
        revenue_by_show_season["Partner Revenue"]
        .where(invalid_source_mask, 0.0)
        .groupby(invalid_family, dropna=False)
        .transform("sum")
        .fillna(0.0)
    )

    invalid_recipient_count_by_family = (
        invalid_recipient_mask.astype("int64")
        .groupby(invalid_family, dropna=False)
        .transform("sum")
        .fillna(0)
        .astype("int64")
    )

    # Fail clearly rather than silently deleting revenue if a family
    # contains an invalid row but no other grouped rows.
    invalid_no_recipient_mask = (
        invalid_source_mask & invalid_recipient_count_by_family.eq(0)
    )
    if invalid_no_recipient_mask.any():
        offending = revenue_by_show_season.loc[
            invalid_no_recipient_mask,
            ["New Show", "New Season", "Partner Revenue"],
        ]
        raise ValueError(
            "Invalid-season revenue cannot be allocated because one or "
            "more affected New Show families have no other grouped season "
            "rows:\n" + offending.to_string(index=False)
        )

    invalid_total_before = float(
        revenue_by_show_season["Partner Revenue"].fillna(0.0).sum()
    )

    invalid_safe_recipient_count = invalid_recipient_count_by_family.replace(
        0, np.nan
    )
    invalid_amount_added = (
        (invalid_source_revenue_by_family / invalid_safe_recipient_count)
        .where(invalid_recipient_mask, 0.0)
        .fillna(0.0)
    )

    revenue_by_show_season.loc[
        invalid_recipient_mask, "Partner Revenue"
    ] = (
        revenue_by_show_season.loc[invalid_recipient_mask, "Partner Revenue"]
        + invalid_amount_added.loc[invalid_recipient_mask]
    )

    revenue_by_show_season = (
        revenue_by_show_season.loc[~invalid_source_mask]
        .copy()
        .reset_index(drop=True)
    )

    invalid_total_after = float(
        revenue_by_show_season["Partner Revenue"].fillna(0.0).sum()
    )
    invalid_total_difference = invalid_total_after - invalid_total_before
    if abs(invalid_total_difference) > 0.01:
        raise ValueError(
            "Invalid-season allocation failed reconciliation: Partner "
            f"Revenue changed by ${invalid_total_difference:,.2f}."
        )

    # --------------------------------------------------------
    # SCMX SEASON CONSOLIDATION: SCMX season 05 -> 03.
    # --------------------------------------------------------
    scmx_show_check = (
        revenue_by_show_season["New Show"]
        .astype("string")
        .str.strip()
        .str.upper()
    )
    scmx_season_check = (
        revenue_by_show_season["New Season"]
        .astype("string")
        .str.strip()
        .str.replace(r"^[Ss]", "", regex=True)
    )
    scmx_05_to_03_mask = (
        scmx_show_check.eq("SCMX")
        & scmx_season_check.eq("05")
    ).fillna(False).to_numpy(dtype=bool)

    revenue_by_show_season.loc[scmx_05_to_03_mask, "New Season"] = "03"

    # --------------------------------------------------------
    # ARTH SEASON CONSOLIDATION: 16/17 -> 01, 18/19 -> 02.
    # --------------------------------------------------------
    arth_show_check = (
        revenue_by_show_season["New Show"]
        .astype("string")
        .str.strip()
        .str.upper()
    )
    arth_season_check = (
        revenue_by_show_season["New Season"]
        .astype("string")
        .str.strip()
        .str.replace(r"^[Ss]", "", regex=True)
    )

    arth_to_01_mask = (
        arth_show_check.eq("ARTH") & arth_season_check.isin(["16", "17"])
    ).fillna(False).to_numpy(dtype=bool)
    arth_to_02_mask = (
        arth_show_check.eq("ARTH") & arth_season_check.isin(["18", "19"])
    ).fillna(False).to_numpy(dtype=bool)

    revenue_by_show_season.loc[arth_to_01_mask, "New Season"] = "01"
    revenue_by_show_season.loc[arth_to_02_mask, "New Season"] = "02"

    # --------------------------------------------------------
    # KRMA SEASON CONSOLIDATION: every KRMA season -> 01.
    # fillna(True) means a genuinely missing New Season on a KRMA
    # row is also changed to 01.
    # --------------------------------------------------------
    krma_show_check = (
        revenue_by_show_season["New Show"]
        .astype("string")
        .str.strip()
        .str.upper()
    )
    krma_season_check = (
        revenue_by_show_season["New Season"]
        .astype("string")
        .str.strip()
        .str.replace(r"^[Ss]", "", regex=True)
    )
    krma_change_mask = (
        krma_show_check.eq("KRMA")
        & krma_season_check.ne("01").fillna(True)
    ).fillna(False).to_numpy(dtype=bool)

    revenue_by_show_season.loc[krma_change_mask, "New Season"] = "01"

    # --------------------------------------------------------
    # Build the final User Code as New Show plus New Season.
    # Example: GARF + 01 -> GARF01.
    # --------------------------------------------------------
    revenue_by_show_season["User Code"] = (
        revenue_by_show_season["New Show"].astype("string").str.strip()
        + revenue_by_show_season["New Season"].astype("string").str.strip()
    )

    # --------------------------------------------------------
    # Prepare the code mapping and split User Code into
    # New Show and New Season.
    # RKMS is an intentional exception: the complete User Code is the
    # New Show, and it does not contain a New Season.
    # --------------------------------------------------------
    code_mapping = (
        show_code_mapping.loc[:, ["User Code", "Description"]].copy()
    )
    code_mapping["User Code"] = (
        code_mapping["User Code"].astype("string").str.strip()
    )
    code_mapping["Description"] = (
        code_mapping["Description"].astype("string").str.strip()
    )

    rksm_user_code_mask = code_mapping["User Code"].eq("RKMS").fillna(False)

    code_mapping["New Season"] = code_mapping["User Code"].str[-2:]
    code_mapping.loc[rksm_user_code_mask, "New Season"] = pd.NA

    code_mapping["New Show"] = code_mapping["User Code"].str[:-2]
    code_mapping.loc[rksm_user_code_mask, "New Show"] = "RKMS"

    rksm_mapping_check = code_mapping.loc[
        rksm_user_code_mask, ["User Code", "New Show", "New Season"]
    ]
    assert rksm_mapping_check["New Show"].eq("RKMS").all(), (
        "RKMS mapping failed: New Show must remain RKMS."
    )
    assert rksm_mapping_check["New Season"].isna().all(), (
        "RKMS mapping failed: New Season must be missing."
    )

    # Fail clearly rather than letting a many-to-many merge duplicate
    # revenue.
    duplicate_user_codes = (
        code_mapping["User Code"].notna()
        & code_mapping["User Code"].duplicated(keep=False)
    )
    if duplicate_user_codes.any():
        raise ValueError(
            "The final grouped dataset cannot be created because "
            "code_mapping_shows contains duplicate User Code values: "
            + ", ".join(
                code_mapping.loc[duplicate_user_codes, "User Code"]
                .sort_values()
                .unique()
                .tolist()
            )
        )

    # --------------------------------------------------------
    # Group again by the final User Code. Necessary because the ARTH
    # consolidation can give previously separate rows the same code
    # (ARTH16 and ARTH17 both become ARTH01).
    # --------------------------------------------------------
    final_grouped_dataset = (
        revenue_by_show_season
        .groupby("User Code", dropna=False, as_index=False)
        .agg(**{"Partner Revenue": ("Partner Revenue", "sum")})
    )

    # Final User Codes with no exact match in code_mapping_shows keep
    # their Partner Revenue but show blank New Show / New Season /
    # Description after the merge. Surface them so they can be fixed.
    # A missing (blank) User Code - revenue whose rows never received a
    # New Show - is surfaced here too instead of sitting silently in the
    # output.
    final_codes = (
        final_grouped_dataset["User Code"].astype("string").str.strip()
    )
    mapping_codes = code_mapping["User Code"].astype("string").str.strip()
    unmatched_mask = final_codes.isna() | ~final_codes.isin(mapping_codes)

    out["unmatched_user_codes"] = (
        final_grouped_dataset.loc[
            unmatched_mask, ["User Code", "Partner Revenue"]
        ]
        .copy()
        .sort_values("Partner Revenue", ascending=False, na_position="last")
        .reset_index(drop=True)
    )

    # Add Description from code_mapping_shows.
    final_grouped_dataset = (
        final_grouped_dataset
        .merge(code_mapping, how="left", on="User Code", validate="many_to_one")
        .loc[
            :,
            ["User Code", "New Show", "New Season", "Description",
             "Partner Revenue"],
        ]
        .sort_values("User Code", na_position="last")
        .reset_index(drop=True)
    )

    # --------------------------------------------------------
    # Totals and the display frame with a GRAND TOTAL row.
    # --------------------------------------------------------
    grouped_total = float(final_grouped_dataset["Partner Revenue"].sum())

    total_row = pd.DataFrame(
        [
            {
                "User Code": "GRAND TOTAL",
                "New Show": "",
                "New Season": "",
                "Description": "",
                "Partner Revenue": grouped_total,
            }
        ]
    )

    out["final_output_display"] = pd.concat(
        [final_grouped_dataset, total_row], ignore_index=True
    )
    out["grouped_total"] = grouped_total
    out["source_total"] = source_total

    return out


# ============================================================
#                     SIDEBAR CONTROLS
# ============================================================

with st.sidebar:
    st.header("Controls")
    if st.button("Clear cache & reload source files"):
        st.cache_data.clear()
        if hasattr(st, "rerun"):
            st.rerun()
        else:
            st.experimental_rerun()


# ============================================================
#                 BUILD EVERYTHING (CACHED)
# ============================================================

pipeline_start = time.perf_counter()
with st.spinner(
    "Building YouTube revenue tables "
    "(only slow on the first run or after a file changes)..."
):
    data = build_report(
        payment_summary_sig=file_signature(payment_summary),
        red_rawdata_sig=file_signature(red_rawdata),
        rev_views_sig=file_signature(rev_views),
        red_music_video_sig=file_signature(red_music_video),
        ads_revenue_shorts_sig=file_signature(ads_revenue_shorts_path),
        ads_subs_shorts_sig=file_signature(ads_subs_shorts_path),
        ads_revenue_dispute_resolution_sig=file_signature(
            ads_revenue_dispute_resolution
        ),
        transactions_revenue_others_sig=file_signature(
            transactions_revenue_others
        ),
        youtube_master_sig=file_signature(youtube_master_list),
        code_mapping_sig=file_signature(code_mapping_shows),
        asset_title_keywords=tuple(ASSET_TITLE_SHOW_KEYWORDS),
        custom_id_mapping_items=tuple(CUSTOM_ID_SHOW_MAPPING.items()),
        asset_title_mapping_items=tuple(ASSET_TITLE_SHOW_MAPPING.items()),
        invalid_seasons_items=tuple(
            (family, tuple(seasons))
            for family, seasons in INVALID_SEASONS_BY_FAMILY.items()
        ),
    )
st.caption(
    f"Pipeline time this run: {time.perf_counter() - pipeline_start:.1f}s "
    "(near-zero when served from cache)."
)

# ============================================================
#     RECONCILIATION: combo_youtube vs payment_summary
# ============================================================

st.subheader("Reconciliation: combo_youtube vs payment_summary")
st.dataframe(
    data["reconciliation"].style.format(
        {
            "combo_youtube_total": "${:,.2f}",
            "payment_summary_total": "${:,.2f}",
            "difference": "${:,.2f}",
        },
        na_rep="-",
    ),
    width="stretch",
)
if bool(data["reconciliation"]["matches"].fillna(False).all()):
    st.success("All revenue types match the payment summary to within $0.01.")
else:
    st.error(
        "One or more revenue types do not match the payment summary - "
        "see the match_status and difference columns above."
    )

if data["missing_review_columns"]:
    st.error(
        "The following required columns are missing from combo_youtube: "
        + ", ".join(data["missing_review_columns"])
    )
    st.stop()

# ============================================================
#              YOUTUBE MASTER MISSING NEW SHOW REVIEW
# ============================================================

st.header("YouTube Master - Missing New Show Review")

st.dataframe(
    data["missing_new_show_review"],
    width="stretch",
    hide_index=True,
    column_config={
        "Asset Title": st.column_config.TextColumn("Asset Title"),
        "Country": st.column_config.TextColumn("Country"),
        "Custom ID": st.column_config.TextColumn("Custom ID"),
        "Data Source Type": st.column_config.TextColumn("Data Source Type"),
        "Asset ID": st.column_config.TextColumn("Asset ID"),
        "Video ID": st.column_config.TextColumn("Video ID"),
        "Video Title": st.column_config.TextColumn("Video Title"),
        "Partner Revenue": st.column_config.NumberColumn(
            "Partner Revenue",
            format="$%.2f",
        ),
    },
)

# ============================================================
#                   FINAL OUTPUT BY TITLE
# ============================================================

st.header("Final Output by Title")
st.dataframe(
    data["final_output_display"].style
    .format({"Partner Revenue": "${:,.2f}"}, na_rep="-")
    .apply(
        bold_total_row,
        axis=1,
        column_name="User Code",
        total_label="GRAND TOTAL",
    ),
    width="stretch",
    hide_index=True,
)

final_output_difference = data["grouped_total"] - data["source_total"]

if abs(final_output_difference) <= 0.01:
    st.success(
        "Final output reconciliation passed: the grouped Partner Revenue "
        f"total of ${data['grouped_total']:,.2f} agrees to the final "
        "consolidated dataset."
    )
else:
    st.error(
        "Final output reconciliation failed: the grouped result differs "
        "from the final consolidated dataset by "
        f"${final_output_difference:,.2f}."
    )

if not data["unmatched_user_codes"].empty:
    st.warning(
        "Some final User Codes have no exact match in the List of Codes "
        "file. These rows keep their Partner Revenue but show a blank "
        "Description in the table above. A blank User Code means the "
        "underlying rows never received a New Show - see the Missing "
        "New Show Review."
    )
    st.dataframe(
        data["unmatched_user_codes"].style.format(
            {"Partner Revenue": "${:,.2f}"}, na_rep="-"
        ),
        width="stretch",
        hide_index=True,
    )
