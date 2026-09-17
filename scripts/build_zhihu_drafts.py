from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "zhihu" / "drafts"
MAX_CHARS = 100_000
TARGET_CHARS = 88_000
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
FONT_NORMAL = r"C:\Windows\Fonts\msyh.ttc"

ISSUES = [
    ("20260726", "020", "report_20260726_2350.md", "2026-07-25"),
    ("20260802", "021", "report_20260802_1723.md", "2026-08-02"),
    ("20260809", "022", "report_20260809_0123.md", "2026-08-08"),
    ("20260817", "023", "report_20260817_0139.md", "2026-08-17"),
    ("20260823", "024", "report_20260823_1005.md", "2026-08-22"),
    ("20260829", "025", "report_20260829_0123.md", "2026-08-29"),
    ("20260906", "026", "report_20260906_0123.md", "2026-09-06"),
    ("20260913", "027", "report_20260913_0123.md", "2026-09-13"),
]

SOURCE_NAMES = {
    "arxiv": "arXiv", "biorxiv": "bioRxiv", "nature": "Nature",
    "science": "Science", "cell": "Cell", "jneurophys": "J Neurophysiol",
    "jneurosci": "J Neurosci", "jcogn": "J Cognitive Neurosci",
    "jvis": "J Vision", "pnas": "PNAS", "natcomm": "Nature Communications",
    "brain": "Brain", "sciadv": "Science Advances", "elife": "eLife",
    "plos": "PLOS",
}


def load_source(report_name: str) -> str:
    raw = (ROOT / "LLM_Results" / report_name).read_text(encoding="utf-8")
    marker = "# 神经科学文献策展报告"
    at = raw.find(marker)
    if at < 0:
        raise ValueError(f"Missing report marker: {report_name}")
    text = raw[at + len(marker):].lstrip("\r\n")
    text = re.sub(r"^生成时间：[^\r\n]*\r?\n", "", text, count=1)
    text = re.sub(r"\A(?:\s|---\s*)*", "", text)
    return text.strip() + "\n"


def report_counts(text: str) -> dict[str, int]:
    names = ["头条推荐", "深度解读", "简要提及", "跨界启发", "已过滤"]
    result = {}
    overview = text.split("## 📈 各领域文章分布", 1)[0]
    for name in names:
        m = re.search(rf"\*\*{name}\*\*\s*:\s*(\d+)\s*篇", overview)
        result[name] = int(m.group(1)) if m else 0
    return result


def make_stat_image(output: Path, date: str, issue: str, counts: dict[str, int], summary_date: str) -> dict:
    summary_path = ROOT / "getfiles" / f"summary_{summary_date}.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    source_rows = [(SOURCE_NAMES.get(key, key), int(value.get("count", 0)))
                   for key, value in summary["sources"].items()]
    source_rows.sort(key=lambda row: (-row[1], row[0]))
    selected = counts["头条推荐"] + counts["深度解读"] + counts["简要提及"] + counts["跨界启发"]

    im = Image.new("RGB", (1200, 720), "#f7f2e8")
    d = ImageDraw.Draw(im)
    d.polygon([(0, 0), (1200, 0), (1200, 95), (0, 155)], fill="#aa1b19")
    d.text((48, 31), f"神经科学快讯 · 第 {issue} 期", font=ImageFont.truetype(FONT_BOLD, 47), fill="white")
    d.text((48, 165), "本期文章发表与入选概览", font=ImageFont.truetype(FONT_BOLD, 42), fill="#171717")
    d.text((48, 221), f"周报日期 {date[:4]}/{date[4:6]}/{date[6:]}  ·  采集批次 {summary_date}",
           font=ImageFont.truetype(FONT_NORMAL, 24), fill="#57534b")

    card_data = [("本期入选", selected), ("深度解读", counts["深度解读"]),
                 ("简要提及", counts["简要提及"]), ("头条推荐", counts["头条推荐"])]
    for index, (label, value) in enumerate(card_data):
        x = 48 + index * 283
        d.rounded_rectangle((x, 270, x + 250, 391), radius=14, fill="white", outline="#d6cab4", width=2)
        d.text((x + 19, 286), label, font=ImageFont.truetype(FONT_NORMAL, 22), fill="#56514b")
        d.text((x + 18, 318), f"{value:,}", font=ImageFont.truetype(FONT_BOLD, 52), fill="#aa1b19")

    d.text((48, 425), "主要采集来源条目数（未去重）", font=ImageFont.truetype(FONT_BOLD, 29), fill="#171717")
    top_rows = source_rows[:5]
    maximum = max((value for _, value in top_rows), default=1)
    for index, (label, value) in enumerate(top_rows):
        y = 476 + index * 36
        d.text((48, y), label, font=ImageFont.truetype(FONT_NORMAL, 22), fill="#171717")
        width = round(610 * value / maximum)
        d.rounded_rectangle((465, y + 4, 465 + width, y + 25), radius=5, fill="#d39e31")
        d.text((1090, y), str(value), font=ImageFont.truetype(FONT_BOLD, 22), fill="#171717")
    d.text((48, 674), "口径：来源条目可能重复；入选数来自周报，不等于来源条目之和。",
           font=ImageFont.truetype(FONT_NORMAL, 19), fill="#57534b")

    output.parent.mkdir(parents=True, exist_ok=True)
    im.save(output, format="PNG", optimize=True)
    return {"summary_file": str(summary_path.relative_to(ROOT)).replace("\\", "/"),
            "selected": selected, "report_counts": counts,
            "top_sources": top_rows, "source_total_un_deduplicated": sum(v for _, v in source_rows)}


def split_modules(text: str, date: str, issue: str, stat_name: str) -> list[str]:
    # The first module contains report-wide statistics; later modules are complete
    # article blocks beginning at ### headings. Keep articles intact across parts.
    heading_re = re.compile(r"(?m)^### .+$")
    matches = list(heading_re.finditer(text))
    blocks = [text[:matches[0].start()]] if matches else [text]
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append(text[match.start():end])

    parts: list[list[str]] = []
    current: list[str] = []
    current_len = 0
    category_heading = ""
    for block in blocks:
        first_line = block.splitlines()[0].strip() if block.strip() else ""
        is_category = first_line.startswith("### ") and not re.search(r"[A-Za-z]{5}", first_line)
        if is_category:
            category_heading = first_line
        if current and current_len + len(block) > TARGET_CHARS:
            parts.append(current)
            current = [category_heading + "\n\n"] if category_heading and not is_category else []
            current_len = sum(map(len, current))
        if len(block) > TARGET_CHARS:
            raise ValueError(f"Article module exceeds target: {date} {first_line}")
        current.append(block)
        current_len += len(block)
    if current:
        parts.append(current)

    result = []
    total = len(parts)
    for index, blocks_in_part in enumerate(parts, start=1):
        title = f"神经科学快讯·第{issue}期（{date[:4]}/{date[4:6]}/{date[6:]}）"
        if total > 1:
            title += f"｜{index}/{total}"
        intro = f"# {title}\n\n"
        if index == 1:
            intro += f"![本期文章发表统计](assets/{stat_name})\n\n"
            intro += "图示口径：采集来源条目未去重；入选文章数以本期周报分类为准。\n\n"
        else:
            intro += f"本篇为第{issue}期的第{index}/{total}部分，接续上一部分。\n\n"
        body = intro + "".join(blocks_in_part).strip() + "\n"
        utf16_units = len(body.encode("utf-16-le")) // 2
        if len(body) > MAX_CHARS or utf16_units > MAX_CHARS:
            raise ValueError(f"Part exceeds 100,000 characters: {date} part {index}: "
                             f"Unicode={len(body)}, UTF-16={utf16_units}")
        result.append(body)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Build unpublished Zhihu review drafts from local weekly reports.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    manifest = {"limit_characters_per_part": MAX_CHARS,
                "character_counts": "Unicode code points and UTF-16 code units; both are capped at 100,000",
                "issues": []}

    for date, issue, filename, summary_date in ISSUES:
        text = load_source(filename)
        counts = report_counts(text)
        stat_name = f"stats_{date}.png"
        evidence = make_stat_image(out / "assets" / stat_name, date, issue, counts, summary_date)
        parts = split_modules(text, date, issue, stat_name)
        part_rows = []
        for index, part in enumerate(parts, start=1):
            name = f"{date}_part{index:02d}.md"
            (out / name).write_text(part, encoding="utf-8", newline="\n")
            part_rows.append({"file": name, "characters": len(part),
                              "utf16_code_units": len(part.encode("utf-16-le")) // 2})
        manifest["issues"].append({"date": date, "issue": issue, "source": f"LLM_Results/{filename}",
                                   "statistics": evidence, "image": f"assets/{stat_name}", "parts": part_rows})

    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(out), "issues": len(manifest["issues"]),
                      "parts": sum(len(i["parts"]) for i in manifest["issues"]),
                      "largest_part": max(p["characters"] for i in manifest["issues"] for p in i["parts"])},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
