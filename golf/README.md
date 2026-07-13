# Golf Analysis

Workspace for golf form and course-fit research.

## Structure

```
golf/
├── app.py                          # Streamlit viewer for the form tables
├── index.html                      # Static viewer (GitHub Pages-friendly)
├── requirements.txt                # Python dependencies
├── data/
│   ├── shinnecock_form_tables.md   # Shinnecock Hills 2026 proxy form data (audited)
│   └── changelog.md                # Cell-by-cell data-integrity audit log
└── README.md
```

## Shinnecock Hills 2026 — Architectural Proxy Form

`data/shinnecock_form_tables.md` holds two tables built to project form for
Flynn-designed Shinnecock Hills using twelve architectural-proxy events
(Open Championships, Genesis Scottish Opens, Pebble Beach Pro-Ams, and recent
US Opens):

- **Form table (50 × 13)** — finishing position per player per event
  (twelve proxies plus `26US`, the 2026 U.S. Open at Shinnecock itself,
  won by Wyndham Clark), ordered by verified cut%.
- **Cut-make leaderboard** — made-cut rate ranked among players with 5+
  verified events (NIF/WD/? excluded from the denominator).

All 650 cells were audited against full final leaderboards (640 verified,
10 left as `?`); see `data/changelog.md` for every correction.

## Viewing the data

### Static page (mobile-friendly, no install)

Open `golf/index.html` in any browser. It's a self-contained page — no build,
no server, no Python — so it also works on GitHub Pages at
`https://<user>.github.io/Research/golf/`.

Includes a player search, colour-coded results (top-10s green, missed cuts
red, NIF grey, unverified amber), and a progress-bar cut% leaderboard.

### Streamlit app

```bash
pip install -r golf/requirements.txt
streamlit run golf/app.py
```

Same data and styling, with Streamlit's interactive dataframes.
