from __future__ import annotations

from pathlib import Path

from markdown_it import MarkdownIt

project_dir = Path(__file__).resolve().parents[1]
source = project_dir / "docs" / "RainCell_GPU_技术与使用报告.md"
target = project_dir / "docs" / "RainCell_GPU_技术与使用报告.html"
renderer = MarkdownIt(
    "commonmark", {"html": False, "linkify": True, "typographer": True}
).enable("table")
body = renderer.render(source.read_text(encoding="utf-8"))

html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RainCell GPU · 技术与使用报告</title>
<style>
:root{{--ink:#17211d;--muted:#5f6c65;--paper:#f5f4ee;--line:#cdd1c8;--teal:#075d57;--acid:#d9ff43;--orange:#ff8a38}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.78 system-ui,-apple-system,"Segoe UI",sans-serif}}
header{{border-bottom:1px solid var(--line);padding:22px 5vw;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;background:rgba(245,244,238,.95);backdrop-filter:blur(10px);z-index:2}}
header b{{font-size:20px;letter-spacing:-.03em}} header b i{{color:var(--teal);font-style:normal}} header a{{font-size:12px;font-weight:800;color:var(--teal);text-decoration:none;border-bottom:1px solid}}
main{{max-width:920px;margin:0 auto;padding:52px 28px 90px}} h1{{font-size:42px;line-height:1.14;letter-spacing:-.05em;margin:0 0 34px;max-width:780px}} h2{{font-size:25px;letter-spacing:-.035em;margin:52px 0 14px;border-top:1px solid var(--line);padding-top:23px}} h3{{font-size:17px;margin:28px 0 7px;color:var(--teal)}} p,li{{color:#334139}} strong{{color:var(--ink)}} a{{color:var(--teal)}} code{{background:#e5e8df;padding:2px 5px;font-size:.9em}} pre{{background:#10231f;color:#e8f2e6;padding:19px;overflow:auto;border-left:4px solid var(--acid);line-height:1.55}} pre code{{background:transparent;padding:0}} table{{border-collapse:collapse;width:100%;font-size:13px;margin:18px 0 26px;background:#fafaf6}} th,td{{border:1px solid var(--line);padding:9px 11px;text-align:left}} th{{background:#e6e8e0;color:var(--teal)}} blockquote{{border-left:3px solid var(--orange);padding-left:15px;color:var(--muted)}}
@media(max-width:600px){{header{{padding:16px 20px}}main{{padding:34px 20px 70px}}h1{{font-size:31px}}table{{display:block;overflow-x:auto}}}}
</style></head><body><header><b>RainCell <i>GPU</i></b><a href="/">返回仿真 ↗</a></header><main>{body}</main></body></html>"""
target.write_text(html, encoding="utf-8")
print(target)
