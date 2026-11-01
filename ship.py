"""Draw a pixel pirate ship that grows from public GitHub activity.

Reads a git-koi snapshot (git-koi collect <login> --output snapshot.json):
    python ship.py snapshot.json ship/ship.gif
    python ship.py --check
"""
import json
import math
import sys
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw

W, H, SCALE, FRAMES, FRAME_MS = 128, 80, 2, 24, 110
SEA_Y = 62
MAST_AT = (0, 250, 1000)  # lifetime contributions for a sloop, brigantine, frigate

JOLLY_ROGER = (
    "...........",
    "....###....",
    "...#.#.#...",
    "....###....",
    "...#...#...",
    ".....#.....",
    "...#...#...",
    "...........",
)

PALETTE = [(0, 0, 0)]  # index 0 is the transparent background


def ink(hex_color):
    rgb = tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    if rgb not in PALETTE[1:]:
        PALETTE.append(rgb)
    return PALETTE.index(rgb, 1)


HULL, HULL_DARK, RAIL, WOOD = ink("#5c3a21"), ink("#2e1c10"), ink("#d4a24c"), ink("#8a5a32")
PORT, SAIL, SAIL_SHADE, ROPE = ink("#1c1210"), ink("#f1e8d0"), ink("#cdbf9c"), ink("#8c7a5e")
FLAG, FLAG_EDGE, BONE, PENNANT = ink("#161616"), ink("#55555a"), ink("#f4f4f0"), ink("#c8372d")
SEA, SEA_DEEP, CREST, FOAM = ink("#2b6aa3"), ink("#1d4f80"), ink("#7fb8e0"), ink("#e6f4fc")


def derive(snapshot):
    """Turn a snapshot into the ship's looks. Same snapshot, same ship."""
    counts = [d["contribution_count"] for d in snapshot["contribution_history"]["days"]]
    streak = 0
    for count in reversed(counts):
        if not count:
            break
        streak += 1
    month = sum(counts[-30:])
    repos = [r for r in snapshot["repositories"] if not r["is_fork"]]
    colors = snapshot["language_colors"]
    langs = Counter(r["primary_language"] for r in repos if r["primary_language"] in colors)
    return {
        "masts": sum(sum(counts) >= need for need in MAST_AT),
        "guns": len(repos),
        "wind": 0 if not month else 1 if month < 30 else 2 if month < 120 else 3,
        "sailing": bool(counts and counts[-1]),
        "pennant": min(streak, 14),
        "stripes": [colors[lang] for lang, _ in langs.most_common(3)],
    }


def wave(phase):
    return math.sin(2 * math.pi * phase)


def draw_flag(d, mast_x, top, t, flap):
    width, height = len(JOLLY_ROGER[0]), len(JOLLY_ROGER)
    for col in range(width):
        # The free end flaps hardest; the hoist stays on the mast.
        dy = round(flap * (width - col) / width * wave(2 * t + col / 7))
        for row, line in enumerate(JOLLY_ROGER):
            # A grey edge keeps the black flag visible on dark pages.
            edge = col == 0 or row in (0, height - 1)
            fill = BONE if line[col] == "#" else FLAG_EDGE if edge else FLAG
            d.point((mast_x - width + col, top + row + dy), fill)


def draw_sail(d, x_left, x_right, top, bottom, billow, stripe):
    mid = (top + bottom) // 2
    d.polygon([(x_left, top), (x_right, top), (x_right + billow, mid), (x_right, bottom),
               (x_left, bottom), (x_left + billow, mid)], fill=SAIL, outline=ROPE)
    d.line([(x_left + 1, top + 1), (x_left + billow + 1, mid), (x_left + 1, bottom - 1)], SAIL_SHADE)
    if stripe is not None:
        d.rectangle([x_left + billow + 1, mid - 1, x_right + billow - 1, mid], fill=stripe)


def draw_ship(d, ship, t, bob):
    """Draw the ship at bobbing height `bob`; returns the bow's x for the wake."""
    n, wind = ship["masts"], ship["wind"]
    length = 34 + 14 * n
    x0 = W // 2 - length // 2 - 4  # stern; the bow points right
    x1 = x0 + length
    keel = SEA_Y + 3 + bob
    deck = keel - 8 - n
    stern_top = deck - 4
    main = (n - 1) // 2
    sail_w = 20 - 2 * n
    masts = []
    for i in range(n):
        x = x0 + 10 + round((length - 22) * (i + 0.5) / n)
        top = deck - 24 - 3 * n - (8 if i == main else 0)
        masts.append((x, top, top + (10 if i == main else 3)))

    # Rigging and spars first, so the hull and sails sit on top of them.
    sprit = (x1 + 10, deck - 8)
    d.line([(x1 - 2, deck - 2), sprit], WOOD)
    d.line([(masts[-1][0], masts[-1][1]), sprit], ROPE)
    d.line([(masts[0][0], masts[0][1]), (x0 + 1, stern_top)], ROPE)
    for (xa, ta, _), (xb, tb, _) in zip(masts, masts[1:]):
        d.line([(xa, ta), (xb, tb)], ROPE)
    if not ship["sailing"]:
        d.line([(x1 - 3, deck + 1), (x1 + 3, SEA_Y + 8)], ROPE)  # anchor cable

    # Stern staff and the streak pennant streaming aft.
    staff_x = x0 + 2
    d.line([(staff_x, stern_top), (staff_x, stern_top - 7)], WOOD)
    pennant = 3 + ship["pennant"]
    for k in range(pennant):
        dy = round((0.4 + 0.3 * wind) * 2 * k / pennant * wave(2 * t + k / 6))
        y = stern_top - 7 + dy
        d.line([(staff_x - 1 - k, y), (staff_x - 1 - k, y + (1 if k < pennant * 0.6 else 0))], PENNANT)

    for i, (x, top, sail_top) in enumerate(masts):
        d.line([(x, top), (x, deck)], WOOD)
        course_top = sail_top + round((deck - 4 - sail_top) * 0.42)
        stripe = ink(ship["stripes"][i % len(ship["stripes"])]) if ship["stripes"] else None
        for s_top, s_bottom, half, s_stripe in (
            (sail_top, course_top - 2, sail_w // 2 - 2, None),
            (course_top, deck - 4, sail_w // 2, stripe),
        ):
            d.line([(x - half - 1, s_top), (x + half + 1, s_top)], WOOD)  # yard
            if ship["sailing"]:
                flutter = 1 if wind >= 2 and wave(2 * t + i / 3) > 0.6 else 0
                draw_sail(d, x - half, x + half, s_top + 1, s_bottom, 1 + wind // 2 + flutter, s_stripe)
            else:
                d.rectangle([x - half, s_top + 1, x + half, s_top + 2], fill=SAIL)  # furled
        if i == main:
            draw_flag(d, x, top, t, 0.5 + 0.5 * wind if ship["sailing"] else 0.5)

    d.polygon([(x0, stern_top), (x0 + 9, stern_top), (x0 + 9, deck), (x1 - 6, deck),
               (x1, deck - 3), (x1 - 4, keel), (x0 + 3, keel)], fill=HULL, outline=HULL_DARK)
    d.line([(x0 + 2, deck + 2), (x1 - 5, deck + 2)], RAIL)
    d.rectangle([x0 + 3, stern_top + 2, x0 + 5, stern_top + 3], fill=RAIL)  # stern lantern
    ports = min(ship["guns"], 2 + 2 * n)
    for p in range(ports):
        px = x0 + 12 + round((length - 24) * (p + 0.5) / ports)
        d.rectangle([px, deck + 4, px + 1, deck + 5], fill=PORT)
    return x1


def draw_frame(ship, f):
    t = f / FRAMES
    wind = ship["wind"]
    im = Image.new("P", (W, H), 0)
    d = ImageDraw.Draw(im)
    bow = draw_ship(d, ship, t, round((0.6 + 0.4 * wind) * wave(t)))

    amp = 0.5 + 0.6 * wind
    for x in range(W):
        phase = x / 22 + t  # the sea runs aft past the ship
        top = SEA_Y + round(amp * wave(phase))
        d.line([(x, top), (x, H - 1)], SEA)
        d.point((x, top), FOAM if wind >= 2 and wave(phase) < -0.8 else CREST)
        for row in range(SEA_Y + 6, H, 5):
            if wave(x / 9 + 2 * t + row / 7) > 0.75:
                d.point((x, row), SEA_DEEP)
    if ship["sailing"]:
        for k in range(2 + wind):
            if (f + k) % 3:
                d.point((bow - 3 + k * 2, SEA_Y - 1 + (f + k) % 2), FOAM)  # bow wave
    return im


def render(ship, path):
    frames = [draw_frame(ship, f) for f in range(FRAMES)]
    palette = [c for rgb in PALETTE for c in rgb]
    big = []
    for im in frames:
        im.putpalette(palette)
        big.append(im.resize((W * SCALE, H * SCALE), Image.NEAREST))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    big[0].save(path, save_all=True, append_images=big[1:], duration=FRAME_MS,
                loop=0, transparency=0, disposal=2, optimize=False)


def check():
    def snap(counts, langs):
        return {
            "contribution_history": {"days": [{"contribution_count": c} for c in counts]},
            "repositories": [{"is_fork": False, "primary_language": l} for l in langs]
            + [{"is_fork": True, "primary_language": "Go"}],
            "language_colors": {"Python": "#3572a5", "Go": "#00add8"},
        }

    calm = derive(snap([0] * 40, []))
    assert calm == {"masts": 1, "guns": 0, "wind": 0, "sailing": False, "pennant": 0, "stripes": []}, calm
    busy = derive(snap([5] * 300, ["Go", "Python", "Python", None]))
    assert busy["masts"] == 3 and busy["guns"] == 4 and busy["wind"] == 3, busy
    assert busy["sailing"] and busy["pennant"] == 14, busy
    assert busy["stripes"] == ["#3572a5", "#00add8"], busy  # forks don't count
    assert derive(snap([300, 0, 0, 1, 1], []))["masts"] == 2
    print("ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--check"]:
        check()
    else:
        ship = derive(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
        render(ship, sys.argv[2])
        print(ship)
