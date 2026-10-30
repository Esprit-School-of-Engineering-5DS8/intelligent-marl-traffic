"""The recorded demonstration: both windows of demo_side_by_side.py side by side, as a GIF.

    python scripts/demo_side_by_side.py --left mp --right hybrid_h2 --net grid4x4 \
        --demand peak --scenarios emergency --seed 0 --only-ev ev_1 --ev-view-width 160 \
        --no-chart --record
    python scripts/demo_record.py   # -> docs/demo/ambulance_mp_vs_candidate.gif (+ .png)

One frame per simulated second, from the moment the cameras follow the emergency vehicle
until both have arrived; a window whose vehicle has arrived keeps its last frame. Above each
window: the controller, in the colour of its side, and the vehicle's time on the road (frozen
at its arrival). The backup when the live demonstration cannot run.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "results" / "tmp" / "demo" / "record"
OUT = ROOT / "docs" / "demo" / "ambulance_mp_vs_candidate"
SIDE_COLORS = ("#2a78d6", "#eb6834")  # as demo_chart.py: left blue, right orange
SURFACE, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"
FONTS = Path("C:/Windows/Fonts")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(FONTS / ("segoeuib.ttf" if bold else "segoeui.ttf")), size)
    except OSError:
        return ImageFont.load_default()


def frames(side: str) -> dict[int, Path]:
    return {int(p.stem.split("_")[1]): p for p in sorted(RECORD.glob(f"{side}_*.png"))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scale", type=float, default=0.55, help="size of each window")
    parser.add_argument("--ms", type=int, default=125, help="milliseconds per simulated second")
    parser.add_argument("--note", default="", help="line under the windows")
    args = parser.parse_args()
    meta = {s: json.loads((RECORD / f"{s}.json").read_text()) for s in ("left", "right")}
    shots = {s: frames(s) for s in ("left", "right")}
    start = max(min(shots["left"]), min(shots["right"]))
    end = max(max(shots["left"]), max(shots["right"]))
    w, h = Image.open(next(iter(shots["left"].values()))).size
    w, h = int(w * args.scale), int(h * args.scale)
    head, foot, gap = 92, 46, 12
    big, small, tiny = font(22, True), font(17), font(14)
    out, last = [], {}
    for t in range(start, end + 1):
        canvas = Image.new("RGB", (2 * w + gap, head + h + foot), SURFACE)
        draw = ImageDraw.Draw(canvas)
        for i, side in enumerate(("left", "right")):
            m = shots[side]
            if t in m:
                last[side] = Image.open(m[t]).convert("RGB").resize((w, h))
            x = i * (w + gap)
            if side in last:
                canvas.paste(last[side], (x, head))
            info = meta[side]
            arrived = info["arrive"] is not None and t >= info["arrive"]
            on_road = (min(t, info["arrive"]) if arrived else t) - info["depart"]
            draw.rectangle([x, 0, x + w, 6], fill=SIDE_COLORS[i])
            draw.text((x + 10, 14), info["label"], fill=INK, font=big)
            status = (
                f"ambulance arrivée : {on_road:.0f} s sur la route"
                if arrived
                else f"ambulance en route depuis {max(on_road, 0):.0f} s"
            )
            draw.text((x + 10, 50), status, fill=SIDE_COLORS[i] if arrived else INK2, font=small)
        info = meta["left"]
        note = args.note or (
            f"{info['network']}, heure de pointe, graine de test {info['seed']}, ambulance "
            f"{info['ev']} · même trafic des deux côtés · vitesse x{1000 // args.ms}"
        )
        draw.text((10, head + h + 12), note, fill=INK2, font=tiny)
        out.append(canvas.quantize(colors=128, method=Image.Quantize.MEDIANCUT))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    durations = [args.ms] * (len(out) - 1) + [3000]  # hold the end for 3 s
    out[0].save(OUT.with_suffix(".gif"), save_all=True, append_images=out[1:], loop=0,
                duration=durations, optimize=True)  # fmt: skip
    out[-1].convert("RGB").save(OUT.with_suffix(".png"))
    size = OUT.with_suffix(".gif").stat().st_size / 1e6
    print(f"{len(out)} frames, {size:.1f} MB: {OUT.with_suffix('.gif')}")


if __name__ == "__main__":
    main()
