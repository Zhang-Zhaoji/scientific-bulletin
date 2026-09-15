from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
FONT_BOLD = Path(r"C:\Windows\Fonts\msyhbd.ttc")
FONT_REGULAR = Path(r"C:\Windows\Fonts\msyh.ttc")

IVORY = (247, 239, 218, 255)
BLACK = (20, 18, 17, 255)
RED = (184, 24, 20, 255)
GOLD = (210, 153, 35, 255)

COVERS = {
    "20260726": {
        "issue": "020",
        "date": "2026/07/26",
        "headline": ["单细胞多组学", "解码阿尔茨海默病的三维基因组"],
    },
    "20260802": {
        "issue": "021",
        "date": "2026/08/02",
        "headline": ["脑膜淋巴与 APOE4", "免疫、脂质与认知的交汇"],
    },
    "20260809": {
        "issue": "022",
        "date": "2026/08/09",
        "headline": ["超快速深层 3D 组织学", "术中追踪胶质瘤浸润"],
    },
    "20260817": {
        "issue": "023",
        "date": "2026/08/17",
        "headline": ["LRRK2 分子开关", "激活与自抑制的结构基础"],
    },
    "20260823": {
        "issue": "024",
        "date": "2026/08/23",
        "headline": ["无测序空间转录组学", "单分子分辨率的全基因组图谱"],
    },
    "20260829": {
        "issue": "025",
        "date": "2026/08/29",
        "headline": ["ERBB4 与阿尔茨海默病", "兴奋性神经元如何推动病理"],
    },
    "20260906": {
        "issue": "026",
        "date": "2026/09/06",
        "headline": ["自组装 RNA 转运载体", "从蛋白质多面体到神经递送"],
    },
    "20260913": {
        "issue": "027",
        "date": "2026/09/13",
        "headline": ["阿尔茨海默病亚型", "共病理与疾病级联的多重路径"],
    },
}


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size=size)


def draw_cover(source: Path, output: Path, spec: dict[str, object], style: str) -> None:
    base = Image.open(source).convert("RGBA")
    if base.size != (1448, 1086):
        base = base.resize((1448, 1086), Image.Resampling.LANCZOS)

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    if style == "simple-outline":
        white = (255, 255, 255, 255)

        def outlined_text(position: tuple[int, int], text: str, size: int, stroke: int = 4) -> None:
            d.text(
                position,
                text,
                font=font(FONT_BOLD, size),
                fill=BLACK,
                stroke_width=stroke,
                stroke_fill=white,
            )

        outlined_text((52, 30), "神经科学快讯", 110, 8)
        outlined_text((57, 180), f"第 {spec['issue']} 期", 59, 6)
        outlined_text((398, 191), str(spec["date"]), 49, 6)
        d.line((59, 282, 875, 282), fill=BLACK, width=8)
        d.line((59, 296, 300, 296), fill=white, width=5)

        headline = list(spec["headline"])
        outlined_text((55, 330), headline[0], 55, 6)
        outlined_text((55, 410), headline[1], 48, 6)

        result = Image.alpha_composite(base, overlay).convert("RGB")
        output.parent.mkdir(parents=True, exist_ok=True)
        result.save(output, format="PNG", optimize=True)
        return

    if style == "panel-large":
        d.polygon([(0, 0), (1080, 0), (820, 625), (0, 730)], fill=(247, 239, 218, 240))
        d.polygon([(0, 0), (30, 0), (30, 730), (0, 738)], fill=RED)
        d.polygon([(1080, 0), (1135, 0), (855, 640), (820, 625)], fill=GOLD)

        title_font = font(FONT_BOLD, 132)
        prefix = "神经科学"
        suffix = "快讯"
        x, y = 55, 28
        d.text((x, y), prefix, font=title_font, fill=BLACK, stroke_width=1, stroke_fill=BLACK)
        prefix_width = d.textlength(prefix, font=title_font)
        d.text((x + prefix_width, y), suffix, font=title_font, fill=RED, stroke_width=1, stroke_fill=RED)
        d.rectangle((58, 194, 900, 203), fill=BLACK)
        d.rectangle((900, 194, 1015, 203), fill=RED)

        issue_font = font(FONT_BOLD, 70)
        date_font = font(FONT_BOLD, 59)
        d.rounded_rectangle((58, 232, 418, 337), radius=5, fill=RED)
        d.text((80, 239), f"第 {spec['issue']} 期", font=issue_font, fill=IVORY)
        d.text((456, 250), str(spec["date"]), font=date_font, fill=BLACK)

        d.rectangle((58, 376, 110, 390), fill=RED)
        d.rectangle((126, 376, 920, 383), fill=GOLD)

        headline = list(spec["headline"])
        d.text((58, 419), headline[0], font=font(FONT_BOLD, 66), fill=RED)
        d.text((58, 510), headline[1], font=font(FONT_BOLD, 58), fill=BLACK)
        d.text((62, 606), "NEUROSCIENCE BULLETIN  ·  WEEKLY FRONTIERS", font=font(FONT_REGULAR, 23), fill=(70, 62, 54, 255))

        result = Image.alpha_composite(base, overlay).convert("RGB")
        output.parent.mkdir(parents=True, exist_ok=True)
        result.save(output, format="PNG", optimize=True)
        return

    # A print-like masthead wedge preserves the generated art while guaranteeing
    # strong contrast and a stable series identity.
    d.polygon([(0, 0), (815, 0), (655, 480), (0, 610)], fill=(247, 239, 218, 238))
    d.polygon([(0, 0), (25, 0), (25, 610), (0, 616)], fill=RED)
    d.polygon([(815, 0), (865, 0), (682, 495), (655, 480)], fill=GOLD)

    title_font = font(FONT_BOLD, 88)
    prefix = "神经科学"
    suffix = "快讯"
    x, y = 58, 50
    d.text((x, y), prefix, font=title_font, fill=BLACK, stroke_width=1, stroke_fill=BLACK)
    prefix_width = d.textlength(prefix, font=title_font)
    d.text((x + prefix_width, y), suffix, font=title_font, fill=RED, stroke_width=1, stroke_fill=RED)
    d.rectangle((58, 164, 690, 170), fill=BLACK)
    d.rectangle((690, 164, 770, 170), fill=RED)

    issue_font = font(FONT_BOLD, 46)
    date_font = font(FONT_BOLD, 39)
    d.rounded_rectangle((58, 196, 303, 273), radius=4, fill=RED)
    d.text((78, 202), f"第 {spec['issue']} 期", font=issue_font, fill=IVORY)
    d.text((334, 211), str(spec["date"]), font=date_font, fill=BLACK)

    d.rectangle((58, 302, 94, 312), fill=RED)
    d.rectangle((105, 302, 730, 306), fill=GOLD)

    headline = list(spec["headline"])
    d.text((58, 334), headline[0], font=font(FONT_BOLD, 43), fill=RED)
    d.text((58, 397), headline[1], font=font(FONT_BOLD, 39), fill=BLACK)
    d.text((60, 466), "NEUROSCIENCE BULLETIN  ·  WEEKLY FRONTIERS", font=font(FONT_REGULAR, 19), fill=(70, 62, 54, 255))

    result = Image.alpha_composite(base, overlay).convert("RGB")
    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output, format="PNG", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Add exact masthead typography to generated bulletin cover art.")
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "Imgs")
    parser.add_argument("--style", choices=("panel", "panel-large", "simple-outline"), default="panel")
    parser.add_argument("--suffix", default="", help="Filename suffix inserted before .png")
    args = parser.parse_args()

    outputs: list[Path] = []
    for date_key, spec in COVERS.items():
        source = args.source_dir / f"{date_key}_background.png"
        if not source.exists():
            raise FileNotFoundError(source)
        output = args.output_dir / f"{date_key}{args.suffix}.png"
        draw_cover(source, output, spec, args.style)
        outputs.append(output)
        print(output)

    thumb_size = (724, 543)
    gap = 18
    sheet = Image.new("RGB", (thumb_size[0] * 2 + gap * 3, thumb_size[1] * 4 + gap * 5), (24, 22, 20))
    for index, output in enumerate(outputs):
        thumb = Image.open(output).convert("RGB").resize(thumb_size, Image.Resampling.LANCZOS)
        col, row = index % 2, index // 2
        sheet.paste(thumb, (gap + col * (thumb_size[0] + gap), gap + row * (thumb_size[1] + gap)))
    review_path = args.output_dir / f"cover_review_020_027{args.suffix}.jpg"
    sheet.save(review_path, format="JPEG", quality=92, optimize=True)
    print(review_path)


if __name__ == "__main__":
    main()
