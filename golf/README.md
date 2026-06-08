# Golf Analysis

Workspace for golf form and course-fit research.

## Structure

```
golf/
├── app.py                          # Streamlit viewer for the form tables
├── index.html                      # Static viewer (GitHub Pages-friendly)
├── requirements.txt                # Python dependencies
├── data/
│   └── shinnecock_form_tables.md   # Shinnecock Hills 2026 proxy form data
└── README.md
```

## Shinnecock Hills 2026 — Architectural Proxy Form

`data/shinnecock_form_tables.md` holds two tables built to project form for
Flynn-designed Shinnecock Hills using twelve architectural-proxy events
(Open Championships, Genesis Scottish Opens, Pebble Beach Pro-Ams, and recent
US Opens):

- **Form Table (50 × 12)** — finishing position per player per proxy event.
- **Cut% Leaderboard** — made-cut rate ranked among players with 5+ verified events.

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
