# Cascais Race Brief — Swedish Team

Wind and telemetry brief for the J/70 World Championship, Cascais, September 2026.
Static site: one `index.html`, one JSON data file, no build step.

Live wind is loaded at runtime, newest source first:

1. `data/wind.json` — refreshed every three hours by GitHub Actions
2. Open-Meteo direct — live, if the host allows the call
3. the snapshot embedded in `index.html` — always works, may be stale

Whichever answers first wins, and the page names its source under the day tabs.

---

## Deploy to Netlify

**1. Push this to GitHub.**

```bash
cd <this folder>
git init -b main
git add .
git commit -m "Cascais race brief: site, wind refresh, analysis tools"
git remote add origin https://github.com/fiorellataraborelli-ops/sailing.git
git push -u origin main
```

The repo currently has only the branch `claude/sailing-race-data-agents-hf37ju` and no
`main`. Pushing `main` as above creates it; set it as the default branch in
**Settings → Branches** so Netlify and Actions pick it up.

**2. Connect Netlify.** app.netlify.com → *Add new site* → *Import an existing project*
→ GitHub → pick `sailing`. `netlify.toml` already sets everything, so leave the build
command empty and the publish directory as `.`. Netlify redeploys on every push, which
includes the three-hourly wind commits — so the site refreshes itself.

**3. Protect it.** This is client race data. In Netlify:
*Site configuration → Access & security → Visitor access → Password protect*, or set
**Site visibility → Private** on a paid plan. `robots.txt` and the `X-Robots-Tag`
header already keep it out of search engines, but those are not access control.

## The three-hourly refresh

`.github/workflows/wind-refresh.yml` runs `tools/fetch_wind.py`, writes
`data/wind.json`, and commits only when the forecast has actually moved.

- Runs on GitHub's servers, so nothing needs to be open on your laptop.
- Trigger it by hand from **Actions → Wind refresh → Run workflow**.
- GitHub cron is UTC and best-effort; a run can land a few minutes late.
- It needs `contents: write`, which the workflow declares. If the push is rejected,
  enable **Settings → Actions → General → Workflow permissions → Read and write**.

## The bias correction, and when it does not apply

The GRIB sits **+18.6° to the right** of the wind this fleet actually races in,
measured against the event's own reports (+19.1° in race 1, +18.0° in race 2 on
8 September). The Nortada bends left into Cascais Bay and a 7 km grid cell cannot
resolve it.

**The correction is only valid in a 10–14 kn gradient Nortada.** Both
`tools/fetch_wind.py` and the page withhold a corrected bearing when the breeze is
under 8 kn or the models disagree by more than 30°, because a thermally driven light
day bends differently. Friday 11 September is exactly that case: 2–8 kn with up to
111° of model disagreement, so the page shows a dash rather than a false bearing.

Recalibrate as more races are sailed — see `docs/ANALYSIS-BRIEF.md`.

## Layout

```
index.html                     the brief; open it directly, no server needed
data/wind.json                 refreshed every 3 h by Actions
data/analysis.json             decoded telemetry + measured race figures
tools/fetch_wind.py            builds data/wind.json
tools/vkx.py                   Vakaros .vkx binary decoder
tools/analyse_legs.py          leg splitting — SEE THE WARNING IN docs/ANALYSIS-BRIEF.md
docs/ANALYSIS-BRIEF.md         what the analysis must cover, and what is unfinished
docs/Cascais-Debrief-8-Sep.pdf the shareable debrief
.github/workflows/wind-refresh.yml
netlify.toml
```

## The VKX format

Reverse-engineered; there was no public decoder. Pages of ~2 KB, each opening with an
8-byte header (`ff 05 01 00` + uint32 block number) and closing with a 3-byte
terminator (`fe` + uint16 page length). Records never straddle a page.

Record `0x02` (45 bytes) is the useful one: type byte, uint64 millisecond timestamp,
int32 latitude and longitude scaled by 1e-7, float32 SOG in m/s, float32 COG in
**radians**, a 4-byte reserved field, then a unit orientation quaternion as 4 float32
(norm verified at 0.99993 — so heel and pitch are derivable, and not yet computed).

Other lengths: `0x03`=21, `0x04`=14 (race timer; payload byte 0 == 3 marks expiry),
`0x05`=18 (start-line position), `0x07`=13, `0x08`=14, `0x0b`=17, `0x0c`=13,
`0x0e`=17, `0x10`=13, `0x21`=53.

There is **no boat name, sail number or device serial anywhere in a `.vkx` file.**
Identity comes only from the filename. Team Sweden is the `vakaros *.vkx` files,
confirmed by exact byte-size match against `data/raw/team/team_*.vkx` and
cross-checked on max boat speed against the five other named boats.
