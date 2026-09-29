"""Bake the current snapshot into a single self-contained dashboard file.

    python scripts/build_static.py            -> dist/airindex_dashboard.html

The result opens straight from disk (no server), which is handy for judges
or for attaching to a submission. The "Run scrape cycle" button is hidden in
this mode because there is no API behind it.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from airindex import snapshot  # noqa: E402

html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
data = json.dumps(snapshot.build(), separators=(",", ":"))
inject = f"<script>window.AIRINDEX_DATA={data};</script>\n<script>"
full = html.replace("<script>\n(() => {", inject + "\n(() => {", 1)

out = ROOT / "dist"
out.mkdir(exist_ok=True)
(out / "airindex_dashboard.html").write_text(full, encoding="utf-8")

# Fragment variant (no <html>/<head>/<body>) for hosts that wrap the page themselves
head = re.search(r"<!--ARTIFACT-START-->(.*)<!--HEAD-END-->", full, re.S).group(1)
body = re.search(r"<!--BODY-START-->(.*)<!--BODY-END-->", full, re.S).group(1)
(out / "airindex_fragment.html").write_text(head + body, encoding="utf-8")
print("wrote dist/airindex_dashboard.html and dist/airindex_fragment.html")
