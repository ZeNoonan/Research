"""Streamlit viewer for the Shinnecock Hills 2026 architectural-proxy form tables.

Run with:  streamlit run golf/app.py
"""

from pathlib import Path
import re

import pandas as pd
import streamlit as st

DATA_FILE = Path(__file__).parent / "data" / "shinnecock_form_tables.md"


def split_sections(markdown_text):
    """Split the markdown into (title, body) blocks keyed on '## ' headings."""
    lines = markdown_text.splitlines()
    sections = []
    preamble = []
    current_title = None
    current_body = []

    for line in lines:
        if line.startswith("## "):
            if current_title is None:
                sections.append((None, "\n".join(preamble).strip()))
            else:
                sections.append((current_title, "\n".join(current_body).strip()))
            current_title = line[3:].strip()
            current_body = []
        elif current_title is None:
            preamble.append(line)
        else:
            current_body.append(line)

    if current_title is None:
        sections.append((None, "\n".join(preamble).strip()))
    else:
        sections.append((current_title, "\n".join(current_body).strip()))
    return sections


def parse_markdown_table(body):
    """Return (DataFrame, leftover_text). Pulls the first pipe-table out of body."""
    table_lines = []
    other_lines = []
    in_table = False

    for line in body.splitlines():
        stripped = line.strip()
        is_row = stripped.startswith("|") and stripped.endswith("|")
        if is_row:
            in_table = True
            table_lines.append(stripped)
        else:
            if in_table and stripped == "":
                in_table = False
            other_lines.append(line)

    if not table_lines:
        return None, body

    def cells(row):
        return [c.strip() for c in row.strip("|").split("|")]

    header = cells(table_lines[0])
    rows = [cells(r) for r in table_lines[2:]]  # skip the |---|---| separator
    df = pd.DataFrame(rows, columns=header)
    return df, "\n".join(other_lines).strip()


def clean_markup(value):
    """Strip bold markers so '**1**' renders as '1' in the dataframe grid."""
    return re.sub(r"\*+", "", value).strip()


RESULT_STYLES = {
    "MC": ("#fde2e2", "#8b1a1a"),
    "NIF": ("#eceff1", "#607d8b"),
    "WD": ("#ede7f6", "#5e35b1"),
    "?": ("#fff8e1", "#9e7700"),
}


def style_form_cell(value):
    raw = clean_markup(str(value))
    if raw in RESULT_STYLES:
        bg, fg = RESULT_STYLES[raw]
        return f"background-color: {bg}; color: {fg};"
    if raw in ("1",) or raw.startswith("T") and raw[1:].isdigit() and int(raw[1:]) <= 10:
        return "background-color: #e3f4e3; color: #1b5e20; font-weight: 600;"
    if raw.isdigit() and int(raw) <= 10:
        return "background-color: #e3f4e3; color: #1b5e20; font-weight: 600;"
    return ""


def main():
    st.set_page_config(page_title="Shinnecock 2026 Form", layout="wide")

    text = DATA_FILE.read_text()
    sections = split_sections(text)

    title_line = text.splitlines()[0].lstrip("# ").strip()
    st.title(title_line)

    for heading, body in sections:
        if heading is None:
            intro = "\n".join(
                l for l in body.splitlines() if not l.startswith("#")
            ).strip()
            if intro:
                st.markdown(intro)
            continue

        st.header(heading)
        df, leftover = parse_markdown_table(body)

        if df is None:
            st.markdown(body)
            continue

        display_df = df.map(clean_markup)

        if heading.lower().startswith("form table"):
            # Display columns Pebble -> US Opens -> Scottish -> Opens.
            event_order = ["24PB", "25PB", "26PB", "23US", "24US", "25US",
                           "23Sc", "24Sc", "25Sc", "23OC", "24OC", "25OC"]
            ordered = [c for c in ("#", "Player") if c in display_df.columns]
            ordered += [c for c in event_order if c in display_df.columns]
            display_df = display_df[ordered]
            with st.expander("Filter players", expanded=False):
                query = st.text_input("Search by name", "")
            if query:
                mask = display_df["Player"].str.contains(query, case=False, na=False)
                display_df = display_df[mask]
            styled = display_df.style.map(
                style_form_cell,
                subset=[c for c in display_df.columns if c not in ("#", "Player")],
            )
            st.dataframe(styled, use_container_width=True, hide_index=True,
                         height=min(60 + 35 * len(display_df), 900))
        elif heading.lower().startswith("cut"):
            cut_values = display_df["Cut%"].str.rstrip("%").astype(float) / 100.0
            grid = display_df.assign(**{"Cut%": cut_values})
            st.dataframe(
                grid,
                use_container_width=True,
                hide_index=True,
                height=min(60 + 35 * len(grid), 900),
                column_config={
                    "Cut%": st.column_config.ProgressColumn(
                        "Cut%", format="percent", min_value=0.0, max_value=1.0
                    )
                },
            )
        else:
            st.dataframe(display_df, use_container_width=True, hide_index=True)

        if leftover:
            st.markdown(leftover)


if __name__ == "__main__":
    main()
