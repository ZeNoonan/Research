# Golf Analysis

Workspace for golf form and course-fit research.

## Structure

```
golf/
├── app.py                          # Streamlit viewer for the form tables
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

## Running the viewer

```bash
pip install -r golf/requirements.txt
streamlit run golf/app.py
```

The app renders the narrative, an interactive/searchable form table with
results colour-coded (top-10s green, missed cuts red), and the cut% leaderboard
with a progress-bar column.
