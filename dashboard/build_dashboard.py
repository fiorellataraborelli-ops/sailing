"""Rebuild the Cascais dashboard bundle: Claude Design export + analyser panel.

The dashboard ships as a Claude Design "standalone" export — a self-unpacking
bundle whose real page lives JSON-encoded inside a
`<script type="__bundler/template">` tag. To change the page you decode that
string, edit it, and re-encode it. Two things in there are easy to get wrong,
which is why this script exists rather than being done by hand:

  1. Every `</` in the re-encoded template must become `<\\u002F`. The browser's
     HTML tokenizer scans raw <script> text for the literal sequence
     "</script" and closes the tag there, regardless of JSON quoting — so an
     unescaped `</script>` inside the template silently truncates the bundle.
     JSON reads `\\u002F` back as "/", so the decoded page is unchanged.
  2. The analyser panel goes in at body level, OUTSIDE the `<x-dc>` element,
     so the Claude Design template runtime never processes its script.

The Claude Design export is used only as the SHELL (fonts, React, the unpacker).
The page itself is `dashboard/dashboard_template.html` — the decoded template,
tracked in this repo, which is where layout and styling edits belong. Re-exporting
from Claude Design replaces the shell; keep editing the tracked template.

Usage:
    python3 dashboard/build_dashboard.py \
        --export   path/to/Cascais_Regatta_Dashboard_standalone.html \
        --template dashboard/dashboard_template.html \
        --panel    dashboard/analyser_panel.html \
        --digest   reports/analyser_digest.json \
        --out      dashboard/cascais_regatta_dashboard.html

Then publish the result as an artifact declaring `capabilities: {sample: {}}`,
which is what lets the panel call Claude.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

TEMPLATE_TAG = re.compile(r'(<script type="__bundler/template">)(.*?)(</script>)', re.S)
BODY_END = "\n</body></html>"
PLACEHOLDER = "__SA_DIGEST__"


def encode_template(template: str) -> str:
    """JSON-encode the page template for embedding in the bundler script tag."""
    return json.dumps(template).replace("</", "<\\u002F")


def build(
    export_path: str,
    template_path: str,
    panel_path: str,
    digest_path: str,
    title: str,
    section_paths: list[str] | None = None,
) -> str:
    with open(export_path, encoding="utf-8") as f:
        bundle = f.read()

    bundle = bundle.replace("<title>Bundled Page</title>", f"<title>{title}</title>", 1)

    match = TEMPLATE_TAG.search(bundle)
    if not match:
        raise SystemExit("no __bundler/template script found — is this a Claude Design standalone export?")

    with open(template_path, encoding="utf-8") as f:
        template = f.read()

    with open(panel_path, encoding="utf-8") as f:
        panel = f.read()
    with open(digest_path, encoding="utf-8") as f:
        digest = json.load(f)

    if PLACEHOLDER not in panel:
        raise SystemExit(f"panel is missing the {PLACEHOLDER} placeholder")
    panel = panel.replace(PLACEHOLDER, json.dumps(digest, separators=(",", ":")))

    if template.count(BODY_END) != 1:
        raise SystemExit("could not find a unique body close in the template")

    # Static sections first, then the analyser panel last, so the panel stays
    # at the bottom of the page.
    blocks = []
    for path in section_paths or []:
        with open(path, encoding="utf-8") as f:
            blocks.append(f.read())
    blocks.append(panel)
    template = template.replace(BODY_END, "\n" + "\n".join(blocks) + BODY_END, 1)

    encoded = encode_template(template)
    rebuilt = bundle[: match.start(2)] + encoded + bundle[match.end(2) :]

    # Verify the round trip before handing the file back: an unescaped "</"
    # would have truncated the script tag, and the bundle would fail to unpack
    # in the browser with a JSON parse error instead of rendering.
    check = TEMPLATE_TAG.search(rebuilt)
    if "</" in check.group(2):
        raise SystemExit("escaping failed: literal '</' left inside the template tag")
    if json.loads(check.group(2)) != template:
        raise SystemExit("round-trip mismatch: re-encoded template does not decode to the source")

    return rebuilt


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", required=True, help="Claude Design standalone .html export (shell only)")
    ap.add_argument("--template", default="dashboard/dashboard_template.html")
    ap.add_argument("--panel", default="dashboard/analyser_panel.html")
    ap.add_argument("--digest", default="reports/analyser_digest.json")
    ap.add_argument("--section", action="append", default=None,
                    help="static HTML section to append before the analyser panel (repeatable)")
    ap.add_argument("--out", default="dashboard/cascais_regatta_dashboard.html")
    ap.add_argument("--title", default="Cascais Regatta Dashboard")
    args = ap.parse_args(argv)

    sections = args.section if args.section is not None else ["dashboard/start_line_section.html"]
    rebuilt = build(args.export, args.template, args.panel, args.digest, args.title, sections)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(rebuilt)
    print(f"wrote {args.out} ({len(rebuilt)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
