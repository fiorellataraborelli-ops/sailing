# Running this locally

Everything in this repo runs on your own laptop. There is no server, no API key,
and no account needed for the analysis itself.

**Good news on dependencies:** the whole analysis pipeline — VKX parsing, leg
segmentation, start-line geometry, fleet comparison — is **pure Python standard
library**. The only external package is `eccodes`, and only if you want to decode
the wind GRIB files.

---

## 1. Get the code

```bash
git clone https://github.com/fiorellataraborelli-ops/sailing.git
cd sailing
git checkout claude/sailing-race-data-agents-hf37ju
```

Heads-up: the clone is roughly **130 MB**, because the raw Vakaros logs (~68 MB)
and the wind GRIBs (~32 MB) are committed alongside the code. That is deliberate —
it means the reports are reproducible from scratch — but it is not a small clone.

## 2. Check your Python

You need **Python 3.9 or newer** (3.11 is what this was developed against):

```bash
python3 --version
```

macOS ships with a usable Python 3. On Windows, install from python.org and use
`py` instead of `python3` in the commands below.

## 3. One-time setup

```bash
bash local-setup/setup.sh
```

That creates a virtual environment in `.venv/` and installs `eccodes` into it.
If it fails, that only costs you the wind commands — see the troubleshooting note
at the bottom.

## 4. Run it

```bash
bash local-setup/run_all.sh
```

This regenerates every report in `reports/` from the raw files and prints the
headline numbers as it goes. Takes a couple of minutes, mostly parsing 14 boats
of GPS at 2 Hz.

---

## Running individual pieces

Activate the venv first if you want the wind commands:

```bash
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

**One boat, one race day — legs and speeds:**
```bash
python3 -m src.sailing_agents.report data/raw/team/team_2026-09-08.vkx
```

**A whole fleet across a day's races (positions at each mark):**
```bash
python3 -m src.sailing_agents.fleet_report \
  --team data/raw/team/team_2026-09-08.vkx \
  --competitors "data/raw/competitors_2026-09-08/*.vkx" \
  --wind-deg 325 \
  -o reports/2026-09-08_fleet_report.json
```

**Start-line geometry — distance to the line at the gun:**
```bash
python3 -m src.sailing_agents.start_line_report \
  --team "data/raw/team/team_2026-09-07.vkx" \
  --competitors "data/raw/competitors/*.vkx"
```

**Wind GRIBs (needs `eccodes`):**
```bash
python3 -m src.sailing_agents.wind_grib \
  --icon-dir data/wind/2026-09-08/icon-eu-06z \
  --ecmwf-dir data/wind/2026-09-08/ecmwf-ifs-06z \
  -o reports/2026-09-08_wind.json
```

**Rebuild the dashboard** (needs a Claude Design standalone export as the shell):
```bash
python3 dashboard/build_dashboard.py \
  --export path/to/Cascais_Regatta_Dashboard_standalone.html \
  --section dashboard/start_line_section.html \
  --section dashboard/wind_section.html \
  --out dashboard/cascais_regatta_dashboard.html
```

## Adding a new race day

1. Drop the team's file in `data/raw/team/team_<YYYY-MM-DD>.vkx`
2. Drop the competitors' files in `data/raw/competitors_<YYYY-MM-DD>/`
3. Edit the two date variables at the top of `local-setup/run_all.sh`
4. `bash local-setup/run_all.sh`

Boat names come from the filenames, so keep them readable —
`Patakin_3 8-9-2026.vkx` becomes "Patakin 3".

## Viewing the dashboard

Open `docs/index.html` in any browser — double-click it, no server needed.

The **strategy analyser panel will not work locally.** It calls Claude through
`window.claude`, which only exists when the page is opened as a Claude artifact.
Locally it shows a short "unavailable" message and everything else works normally.
For the analyser, use the published artifact link instead.

---

## What each module does

| File | Purpose |
|---|---|
| `src/sailing_agents/vkx_parser.py` | Reads the Vakaros VKX binary format (v1.4 spec) |
| `src/sailing_agents/race_legs.py` | First upwind / first downwind, for a race that wasn't finished |
| `src/sailing_agents/race_multi_leg.py` | All legs of a completed race |
| `src/sailing_agents/start_line.py` | Distance to the line at the gun, position along the line |
| `src/sailing_agents/start_line_report.py` | The above across a fleet, plus wind direction from geometry |
| `src/sailing_agents/fleet_report.py` | Positions at each mark, and speed-vs-distance forensics |
| `src/sailing_agents/wind_grib.py` | Decodes ICON-EU / ECMWF GRIBs, compares to what was sailed |
| `src/sailing_agents/digest.py` | Condenses everything into the analyser's prompt payload |
| `dashboard/build_dashboard.py` | Reassembles the dashboard bundle |

## If `eccodes` won't install

It ships compiled binaries, so it occasionally fails on older systems. The
analysis pipeline does not need it — only `wind_grib.py` does, and it imports it
lazily, so every other command keeps working. On macOS, `brew install eccodes`
before `pip install eccodes` usually fixes it. The already-decoded wind numbers
are committed in `reports/2026-09-08_wind.json` and
`data/wind/2026-09-08/README.md`, so you are not blocked either way.
