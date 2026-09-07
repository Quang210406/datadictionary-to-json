"""Renders introduction.md to a printable PDF for the tester.

    .buildvenv/bin/python build/make_intro_pdf.py

She reads Excel, not Markdown: double-clicking a .md on a Mac opens TextEdit
showing raw ** and | characters, which is a bad first thirty seconds for the
one reader who can least afford confusion. So the guide ships as a PDF.

Rendering goes Markdown -> styled HTML -> headless Chrome. Chrome is used
because it is already on the machine and its print engine handles Vietnamese
diacritics and page breaking correctly; the alternatives all wanted another
system dependency. Nothing here is bundled into Hecate.app.

Re-run this after editing introduction.md.
"""

import pathlib
import subprocess
import sys

import markdown

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "introduction.md"
OUT_PDF = ROOT / "introduction.pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Print styling. Deliberately plain: this is a document to be read once and
# kept beside a keyboard, not a brochure. The palette is the app's, so the
# guide and the window look like the same product.
CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }

:root {
  --text: #1c1c1a; --muted: #4a4a45; --faint: #6d6d67;
  --accent: #0d6e63; --accent-sf: #e4efed;
  --border: #d8d8d3; --surface-2: #f4f4f1; --warn: #8a5300;
}

* { box-sizing: border-box; }

body {
  font: 10.5pt/1.62 -apple-system, "SF Pro Text", "Helvetica Neue", sans-serif;
  color: var(--text); margin: 0;
  -webkit-font-smoothing: antialiased;
}

h1 {
  font-size: 25pt; font-weight: 650; letter-spacing: -0.5pt;
  margin: 0 0 2pt; color: var(--accent);
}
/* The one-line subtitle under the title. */
h1 + p { color: var(--faint); font-size: 11pt; margin: 0 0 20pt; }

h2 {
  font-size: 14pt; font-weight: 640; letter-spacing: -0.2pt;
  margin: 22pt 0 7pt; padding-top: 9pt;
  border-top: 1.5pt solid var(--accent);
  break-after: avoid; break-inside: avoid;
}
h3 {
  font-size: 11.5pt; font-weight: 640; margin: 15pt 0 5pt;
  break-after: avoid;
}
h4 { font-size: 10.5pt; font-weight: 640; margin: 12pt 0 4pt; break-after: avoid; }

p { margin: 0 0 8pt; orphans: 3; widows: 3; }
strong { font-weight: 640; }

ul, ol { margin: 0 0 9pt; padding-left: 17pt; }
li { margin-bottom: 3.5pt; }
li::marker { color: var(--accent); font-weight: 600; }

/* Steps she follows at the keyboard must never split across a page. */
ol { break-inside: avoid; }

table {
  border-collapse: collapse; width: 100%;
  margin: 4pt 0 12pt; font-size: 9.5pt;
  break-inside: avoid;
}
th {
  text-align: left; font-weight: 640; font-size: 8.5pt;
  text-transform: uppercase; letter-spacing: 0.4pt; color: var(--muted);
  background: var(--surface-2);
  padding: 6pt 8pt; border-bottom: 1pt solid var(--border);
}
td { padding: 6pt 8pt; border-bottom: 0.75pt solid var(--border); vertical-align: top; }

blockquote {
  margin: 10pt 0; padding: 9pt 12pt;
  background: var(--accent-sf);
  border-left: 3pt solid var(--accent);
  border-radius: 0 4pt 4pt 0;
  break-inside: avoid;
}
blockquote p:last-child { margin-bottom: 0; }

/* Inline spans use the BODY font, not a monospace one, and that is a
   deliberate correctness fix rather than taste. Chrome emits no ToUnicode
   mapping for Vietnamese glyphs rendered in SF Mono or Menlo: the text prints
   correctly but is absent from the PDF's text layer, so "có khoảng trắng
   thừa" could not be searched, selected or copied. Courier New survives but
   looks dated beside SF Pro. These spans are mostly UI labels she reads as
   words anyway. The fenced block below keeps a real monospace because it is
   pure ASCII, where the problem does not arise and alignment matters. */
code {
  font-family: inherit; font-size: 9.5pt;
  background: var(--surface-2); padding: 1pt 4.5pt; border-radius: 3pt;
  border: 0.5pt solid var(--border);
}
pre {
  background: var(--surface-2); border: 0.75pt solid var(--border);
  border-radius: 4pt; padding: 9pt 11pt; margin: 4pt 0 12pt;
  break-inside: avoid;
}
pre code {
  background: none; padding: 0; border: none; line-height: 1.5;
  font: 9pt Menlo, ui-monospace, monospace;   /* ASCII only, extracts fine */
}

/* Every "---" in the source sits directly above a section heading, and the
   heading already draws the teal rule. Rendering both gave every section a
   doubled separator. */
hr { display: none; }
"""

PAGE = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<title>Hecate</title><style>{css}</style></head>
<body>{body}</body></html>"""


def main():
    if not SOURCE.exists():
        sys.exit(f"missing {SOURCE}")

    body = markdown.markdown(
        SOURCE.read_text(encoding="utf-8"),
        extensions=["tables", "fenced_code", "sane_lists"],
    )
    html_path = ROOT / "build" / "_introduction.html"
    html_path.write_text(PAGE.format(css=CSS, body=body), encoding="utf-8")

    subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={OUT_PDF}", html_path.as_uri()],
        check=True, capture_output=True,
    )
    html_path.unlink()
    print(f"wrote {OUT_PDF} ({OUT_PDF.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
