#!/usr/bin/env python3
"""Render HYDRA architecture PNGs for the README."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "architecture"

BG = (15, 16, 18)
INK = (243, 239, 230)
MUTED = (141, 136, 124)
LINE = (42, 40, 36)
PANEL = (24, 23, 20)
PANEL2 = (32, 30, 26)
ACCENT = (196, 165, 116)
OK = (125, 174, 122)
BAD = (196, 107, 99)
WARN = (214, 176, 74)

SERIF = "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"
SANS = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
SANS_B = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def rr(draw: ImageDraw.ImageDraw, box, fill, outline=None, width=2, radius=14):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def center(draw, xy, text, fnt, fill=INK):
    x, y = xy
    bbox = draw.textbbox((0, 0), text, font=fnt)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((x - w / 2, y - h / 2), text, font=fnt, fill=fill)


def text(draw, xy, value, fnt, fill=INK):
    draw.text(xy, value, font=fnt, fill=fill)


def arrow_right(draw, x1, y, x2, color=ACCENT, head=12):
    draw.line((x1, y, x2 - 2, y), fill=color, width=3)
    draw.polygon([(x2, y), (x2 - head, y - 7), (x2 - head, y + 7)], fill=color)


def arrow_down(draw, x, y1, y2, color=ACCENT, head=12):
    draw.line((x, y1, x, y2 - 2), fill=color, width=3)
    draw.polygon([(x, y2), (x - 7, y2 - head), (x + 7, y2 - head)], fill=color)


def card(draw, box, title, lines, *, stroke=ACCENT, badge=None, badge_fill=ACCENT):
    x0, y0, x1, y1 = box
    rr(draw, box, PANEL, stroke, width=2, radius=16)
    if badge:
        bx0, by0 = x0 + 18, y0 + 16
        rr(draw, (bx0, by0, bx0 + 44, by0 + 26), badge_fill, badge_fill, radius=8)
        center(draw, (bx0 + 22, by0 + 13), badge, font(SANS_B, 13), BG)
        text(draw, (bx0 + 56, y0 + 18), title, font(SANS_B, 20), INK)
    else:
        text(draw, (x0 + 20, y0 + 18), title, font(SANS_B, 20), INK)
    yy = y0 + (56 if badge else 50)
    for line in lines:
        text(draw, (x0 + 20, yy), line, font(SANS, 16), MUTED)
        yy += 24


def save(img: Image.Image, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    img.save(path, "PNG", optimize=True)
    print(f"wrote {path} ({path.stat().st_size} bytes)")


def render_system() -> None:
    w, h = 1600, 1180
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)

    center(d, (w / 2, 56), "HYDRA SYSTEM", font(SERIF, 42), INK)
    center(
        d,
        (w / 2, 100),
        "Amazon catalog  ·  last-good stays up when a scrape fails",
        font(SANS, 20),
        MUTED,
    )

    # Inputs
    y = 150
    inputs = [
        (80, "AMAZON URLS", ["Product pages to scrape", "asin + title required"]),
        (560, "CONTRACT", ["amazon_products", "Quality floor: 5 products"]),
        (1040, "BRIGHT DATA", ["Dataset gd_l7q7dkf244hwjntr0", "Live key optional"]),
    ]
    for x, title, lines in inputs:
        card(d, (x, y, x + 480, y + 140), title, lines)

    for x in (320, 800, 1280):
        arrow_down(d, x, 298, 348)

    # Mode
    y = 356
    card(d, (80, y, 760, y + 130), "REPLAY", ["fixtures/amazon_products.json", "HYDRA_MODE=replay  ·  no API key"])
    card(d, (840, y, 1520, y + 130), "LIVE SCRAPE", ["Bright Data unlocker / dataset", "Isolated on :8081 so replay stays intact"])
    arrow_down(d, 420, 494, 544)
    arrow_down(d, 1180, 494, 544)
    d.line((420, 544, 1180, 544), fill=ACCENT, width=3)
    arrow_down(d, 800, 544, 594)

    # Pipeline
    y = 602
    rr(d, (80, y, 1520, y + 210), PANEL2, ACCENT, width=2, radius=18)
    text(d, (104, y + 18), "HYDRA PIPELINE", font(SANS_B, 18), ACCENT)
    text(d, (104, y + 46), "Acquire, parse, validate, then promote. Raw never writes the serving catalog.", font(SANS, 16), MUTED)
    stages = [
        ("01", "ACQUIRE", "Fetch or replay"),
        ("02", "PARSE", "Rows + types"),
        ("03", "VALIDATE", "Contract checks"),
        ("04", "LOAD", "Atomic promote"),
        ("05", "DERIVE", "Health + cards"),
    ]
    gap = 24
    box_w = 248
    x = 110
    for i, (num, title, sub) in enumerate(stages):
        card(d, (x, y + 82, x + box_w, y + 190), title, [sub], badge=num)
        if i < len(stages) - 1:
            arrow_right(d, x + box_w + 2, y + 136, x + box_w + gap - 2)
        x += box_w + gap

    arrow_down(d, 800, 820, 870)

    # Serving + ledgers
    y = 878
    card(
        d,
        (80, y, 760, y + 168),
        "LAST-GOOD CATALOG",
        ["data/hydra-live.json", "Keep products_good when products_now is bad", "Served on the dashboard"],
        stroke=OK,
    )
    card(
        d,
        (840, y, 1520, y + 168),
        "DASHBOARD",
        ["Vercel production + local :8080", "Break Amazon  ·  Detect → Verify", "Cards show what broke, then what healed"],
        stroke=ACCENT,
    )

    y = 1070
    for x, title in ((80, "PORT LEDGER"), (560, "DUCKDB LEDGER"), (1040, "SIGNOZ TRACES")):
        rr(d, (x, y, x + 480, y + 72), PANEL, LINE, width=2, radius=14)
        center(d, (x + 240, y + 36), title, font(SANS_B, 18), MUTED)

    save(img, "hydra-architecture-system.png")


def render_heal() -> None:
    w, h = 1600, 720
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)

    center(d, (w / 2, 52), "CLOSED-LOOP HEAL", font(SERIF, 40), INK)
    center(
        d,
        (w / 2, 96),
        "A repair counts only if the same check that failed, passes afterward",
        font(SANS, 20),
        MUTED,
    )

    stages = [
        ("01", "DETECT", "Failed scrape opens\nan incident (MTTD)", WARN),
        ("02", "CLASSIFY", "Map telemetry to\nfailure class F1–F6", ACCENT),
        ("03", "GUARD", "Budget, circuit,\napproval tier", ACCENT),
        ("04", "ACT", "Run one primitive\nP1–P8", ACCENT),
        ("05", "VERIFY", "Re-run the same\nassertion", OK),
    ]
    box_w, box_h = 252, 250
    gap = 36
    total = 5 * box_w + 4 * gap
    x = (w - total) / 2
    y = 160
    for i, (num, title, body, color) in enumerate(stages):
        rr(d, (x, y, x + box_w, y + box_h), PANEL, color, width=3, radius=18)
        rr(d, (x + 18, y + 18, x + 70, y + 52), color, color, radius=8)
        center(d, (x + 44, y + 35), num, font(SANS_B, 16), BG)
        text(d, (x + 20, y + 72), title, font(SANS_B, 24), INK)
        yy = y + 118
        for line in body.split("\n"):
            text(d, (x + 20, yy), line, font(SANS, 17), MUTED)
            yy += 26
        if i < len(stages) - 1:
            arrow_right(d, x + box_w + 2, y + box_h / 2, x + box_w + gap - 2, color)
        x += box_w + gap

    # return path
    d.line((1348, 410, 1348, 560, 252, 560, 252, 410), fill=OK, width=3)
    d.polygon([(252, 410), (245, 424), (259, 424)], fill=OK)
    center(d, (w / 2, 600), "Verify fails → open another incident     ·     Verify passes → catalog is healthy", font(SANS, 18), MUTED)
    center(d, (w / 2, 668), "Stages on the dashboard: idle  ·  yellow in progress  ·  red when broken  ·  green when done", font(SANS, 16), MUTED)

    save(img, "hydra-architecture-heal-loop.png")


def render_last_good() -> None:
    w, h = 1600, 820
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)

    center(d, (w / 2, 52), "LAST-GOOD CATALOG", font(SERIF, 40), INK)
    center(
        d,
        (w / 2, 96),
        "Bright Data and the fixture never overwrite the serving document",
        font(SANS, 20),
        MUTED,
    )

    y = 160
    steps = [
        ("1", "RAW RUN", ["data/raw/run-<id>.json", "CLI output stays here"]),
        ("2", "NORMALIZE + VALIDATE", ["Contract amazon_products", "asin, title, quality floor"]),
        ("3", "ATOMIC PROMOTE", ["Write a temp file, then replace", "Only a valid document is published"]),
    ]
    x = 70
    for i, (num, title, lines) in enumerate(steps):
        card(d, (x, y, x + 460, y + 180), title, lines, badge=num)
        if i < 2:
            arrow_right(d, x + 466, y + 90, x + 510)
        x += 500

    # fork
    arrow_down(d, 1280, 348, 410)
    d.line((420, 410, 1280, 410), fill=ACCENT, width=3)

    card(
        d,
        (80, 430, 760, 640),
        "OK — SERVE LAST-GOOD",
        ["data/hydra-live.json", "products_good becomes the catalog", "Dashboard cards stay complete"],
        stroke=OK,
        badge="UP",
        badge_fill=OK,
    )
    card(
        d,
        (840, 430, 1520, 640),
        "FAIL — HOLD THIS SCRAPE",
        ["products_now is rejected", "Last-good stays on screen", "Heal loop starts on the dashboard"],
        stroke=BAD,
        badge="HOLD",
        badge_fill=BAD,
    )

    rr(d, (80, 680, 1520, 776), (36, 22, 20), BAD, width=2, radius=16)
    center(d, (w / 2, 716), "NEVER WRITE RAW TO LATEST", font(SANS_B, 22), BAD)
    center(
        d,
        (w / 2, 750),
        "data/latest.json and data/hydra-live.json accept only a schema-valid, quality-gated document",
        font(SANS, 17),
        MUTED,
    )

    save(img, "hydra-architecture-last-good.png")


def render_fault_map() -> None:
    w, h = 1600, 860
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)

    center(d, (w / 2, 52), "AMAZON FAULT MAP", font(SERIF, 40), INK)
    center(d, (w / 2, 96), "Same agent  ·  eight faults  ·  Break Amazon on the dashboard", font(SANS, 20), MUTED)

    headers = [("FAULT", 80, 620), ("CLASS", 720, 240), ("FIRST REPAIR", 980, 540)]
    y = 150
    rr(d, (60, y, 1540, y + 64), PANEL2, LINE, width=2, radius=12)
    for label, x, _w in headers:
        text(d, (x, y + 20), label, font(SANS_B, 16), ACCENT)

    rows = [
        ("Loud · HTTP 403", "F1 acquisition", "P6 backoff, then P1"),
        ("Loud · captcha wall", "F1 acquisition", "P1 escalate acquisition"),
        ("Quiet · volume collapse", "F2 / F4", "P5 replay raw, then P1"),
        ("Quiet · selector drift", "F2 structural", "P5 then P1"),
        ("Schema · price renamed", "F4 quality", "Guard asks before reshape"),
        ("Schema · prices become n/a", "F3 schema", "P4 quarantine"),
        ("Quality · null flood", "F4 quality", "P5 replay from raw"),
        ("Poison · one bad row", "F3 / F6", "P4 drop the poison row"),
    ]
    y = 228
    for i, (fault, klass, repair) in enumerate(rows):
        fill = PANEL if i % 2 == 0 else PANEL2
        rr(d, (60, y, 1540, y + 64), fill, LINE, width=1, radius=10)
        text(d, (80, y + 20), fault, font(SANS_B, 18), INK)
        text(d, (720, y + 20), klass, font(SANS, 18), MUTED)
        text(d, (980, y + 20), repair, font(SANS, 18), ACCENT)
        y += 70

    center(d, (w / 2, 820), "Cards show the damaged fields for that fault, then return to last-good after Verify", font(SANS, 17), MUTED)
    save(img, "hydra-architecture-fault-map.png")


if __name__ == "__main__":
    render_system()
    render_heal()
    render_last_good()
    render_fault_map()
