"""Render writeup.md -> writeup.html and writeup.pdf (Illini-themed, print-ready).

Usage:  python report/build_writeup.py
"""
from __future__ import annotations

import os

import markdown

HERE = os.path.dirname(os.path.abspath(__file__))
MD = os.path.join(HERE, "writeup.md")
HTML = os.path.join(HERE, "writeup.html")
PDF = os.path.join(HERE, "writeup.pdf")

ORANGE = "#E84A27"
NAVY = "#13294B"

CSS = f"""
@page {{ size: letter; margin: 2cm; }}
body {{ font-family: Helvetica, Arial, sans-serif; color: #1c2533;
        line-height: 1.5; font-size: 11pt; }}
h1 {{ color: {NAVY}; border-bottom: 4px solid {ORANGE}; padding-bottom: 6px;
      font-size: 22pt; margin-bottom: 2px; }}
h2 {{ color: {NAVY}; border-left: 6px solid {ORANGE}; padding-left: 10px;
      margin-top: 22px; font-size: 15pt; }}
h3 {{ color: {ORANGE}; margin-top: 0; font-weight: 600; }}
a {{ color: {ORANGE}; text-decoration: none; }}
table {{ border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 9.5pt; }}
th {{ background: {NAVY}; color: #fff; text-align: left; padding: 6px 8px; }}
td {{ border: 1px solid #d6dbe4; padding: 6px 8px; vertical-align: top; }}
tr:nth-child(even) td {{ background: #f4f6fa; }}
code {{ background: #eef1f6; padding: 1px 4px; border-radius: 3px;
        font-family: "Courier New", monospace; font-size: 9.5pt; }}
pre {{ background: #f4f6fa; border-left: 4px solid {ORANGE}; padding: 10px;
       overflow-x: auto; }}
pre code {{ background: none; }}
hr {{ border: none; border-top: 1px solid #d6dbe4; margin: 18px 0; }}
strong {{ color: {NAVY}; }}
em {{ color: #4a5568; }}
"""

TEMPLATE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Illini Portal Fit Engine — Write-up</title><style>{css}</style></head>
<body>{body}</body></html>"""


def main() -> None:
    with open(MD, encoding="utf-8") as fh:
        body = markdown.markdown(
            fh.read(), extensions=["tables", "fenced_code", "sane_lists"]
        )
    html = TEMPLATE.format(css=CSS, body=body)

    with open(HTML, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"wrote {HTML}")

    try:
        from xhtml2pdf import pisa

        with open(PDF, "wb") as fh:
            status = pisa.CreatePDF(html, dest=fh)
        if status.err:
            print("PDF had warnings but was written.")
        print(f"wrote {PDF}")
    except Exception as exc:  # noqa: BLE001
        print(f"PDF step skipped ({exc}). Open writeup.html and Save as PDF.")


if __name__ == "__main__":
    main()
