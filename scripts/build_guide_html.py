"""Self-contained HTML version of a Markdown guide: clickable table of contents, coloured
code, light and dark themes, no external resource (readable offline).

    python scripts/build_guide_html.py docs/GUIDE_SOUTENANCE_LLM.md
    # writes docs/GUIDE_SOUTENANCE_LLM.html
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

import markdown
from markdown.extensions.toc import slugify_unicode
from pygments.formatters import HtmlFormatter
from pygments.styles import get_all_styles

PAGE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ --bg: #ffffff; --fg: #1f2328; --muted: #59636e; --line: #d1d9e0; --soft: #f6f8fa;
         --link: #0969da; --accent: #0b5cad; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg: #0d1117; --fg: #e6edf3; --muted: #9198a1; --line: #30363d; --soft: #161b22;
           --link: #4493f8; --accent: #79b8ff; }}
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--fg);
        font: 16px/1.6 -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }}
a {{ color: var(--link); }}
.layout {{ display: grid; grid-template-columns: 300px minmax(0, 1fr);
           max-width: 1400px; margin: 0 auto; }}
nav.toc {{ position: sticky; top: 0; height: 100vh; overflow-y: auto; padding: 24px 16px;
           border-right: 1px solid var(--line); font-size: 14px; }}
nav.toc .title {{ font-weight: 700; margin-bottom: 8px; }}
nav.toc ul {{ list-style: none; padding-left: 12px; margin: 4px 0; }}
nav.toc > ul {{ padding-left: 0; }}
nav.toc a {{ text-decoration: none; display: block; padding: 2px 0; }}
nav.toc a:hover {{ text-decoration: underline; }}
main {{ padding: 24px 40px 80px; min-width: 0; }}
h1 {{ font-size: 2em; border-bottom: 1px solid var(--line); padding-bottom: 8px; }}
h2 {{ font-size: 1.5em; border-bottom: 1px solid var(--line); padding-bottom: 6px;
      margin-top: 48px; }}
h3 {{ font-size: 1.2em; margin-top: 36px; color: var(--accent); }}
code {{ font-family: Consolas, "Cascadia Mono", Menlo, monospace; font-size: 0.9em;
        background: var(--soft); padding: 1px 5px; border-radius: 4px; }}
.codehilite {{ background: var(--soft) !important; border: 1px solid var(--line);
               border-radius: 6px; overflow-x: auto; margin: 12px 0; }}
.codehilite pre {{ margin: 0; padding: 12px 14px; font-size: 13.5px; line-height: 1.5; }}
.codehilite code {{ background: none; padding: 0; }}
table {{ border-collapse: collapse; margin: 12px 0; display: block; overflow-x: auto;
         font-size: 14.5px; }}
th, td {{ border: 1px solid var(--line); padding: 6px 10px; vertical-align: top;
          text-align: left; }}
th {{ background: var(--soft); }}
hr {{ border: 0; border-top: 1px solid var(--line); margin: 32px 0; }}
.top {{ font-size: 13px; color: var(--muted); }}
@media (max-width: 900px) {{
  .layout {{ grid-template-columns: 1fr; }}
  nav.toc {{ position: static; height: auto; border-right: 0;
             border-bottom: 1px solid var(--line); }}
  main {{ padding: 16px; }}
}}
@media print {{ nav.toc {{ display: none; }} .layout {{ display: block; }} }}
{light}
@media (prefers-color-scheme: dark) {{
{dark}
}}
</style>
</head>
<body>
<div class="layout">
<nav class="toc"><div class="title">Sommaire</div>{toc}</nav>
<main>
{body}
<p class="top"><a href="#">Retour en haut</a> · généré depuis {source}</p>
</main>
</div>
</body>
</html>
"""


def pygments_css(style: str, selector: str = ".codehilite") -> str:
    css = HtmlFormatter(style=style).get_style_defs(selector)
    # the background is set by the page theme
    return re.sub(r"\.codehilite \{ background: [^;]+; \}", "", css)


def deepen_lists(text: str) -> str:
    """Python-Markdown nests a list only with 4 spaces; the guides use 2 (as GitHub does):
    double the indentation outside code blocks."""
    out, in_code = [], False
    for line in text.splitlines():
        if line.startswith("```"):
            in_code = not in_code
        if not in_code and line.startswith(" "):
            stripped = line.lstrip(" ")
            line = " " * (2 * (len(line) - len(stripped))) + stripped
        out.append(line)
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    text = args.source.read_text(encoding="utf-8")
    md = markdown.Markdown(
        extensions=["extra", "sane_lists", "toc", "codehilite"],
        extension_configs={
            "toc": {"slugify": slugify_unicode, "toc_depth": "2-3"},
            "codehilite": {"guess_lang": False, "css_class": "codehilite"},
        },
    )
    body = md.convert(deepen_lists(text))
    title = re.search(r"^# (.+)$", text, re.M)
    styles = set(get_all_styles())
    dark = "github-dark" if "github-dark" in styles else "monokai"
    page = PAGE.format(
        title=html.escape(title.group(1) if title else args.source.stem),
        toc=md.toc,
        body=body,
        source=html.escape(args.source.as_posix()),
        light=pygments_css("default"),
        dark=pygments_css(dark),
    )
    out = args.out or args.source.with_suffix(".html")
    out.write_text(page, encoding="utf-8")
    print(f"{out} ({len(page) // 1024} Ko)")


if __name__ == "__main__":
    main()
