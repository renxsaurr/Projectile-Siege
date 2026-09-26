"""
PROJECTILE SIEGE
================
A projectile-motion tower-defense game made for Physics 1.

Every cannon shell, catapult stone and airship bomb in this game moves
according to the kinematic equations of projectile motion (no air drag):

    x(t) = x0 + v0x * t               where  v0x = v0 * cos(theta)
    y(t) = y0 + v0y * t - 1/2 g t^2   where  v0y = v0 * sin(theta)

The horizontal velocity never changes; only gravity (g = 9.81 m/s^2)
changes the vertical velocity:  vy(t) = v0y - g t

Defend the tower on the left. If the enemies destroy it, the game is over.
"""

import array
import math
import os
import random

import pygame

pygame.mixer.pre_init(22050, -16, 1, 512)
pygame.init()

# WINDOW DIMENSIONS
WIDTH = 1280
HEIGHT = 720
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.SCALED)
pygame.display.set_caption("Projectile Siege - Physics 101")
clock = pygame.time.Clock()
FPS = 60

# ---------------------------------------------------------------------------
# PHYSICS AND WORLD SCALE (all physics is done in meters and seconds)
# ---------------------------------------------------------------------------
G = 9.81                    # gravitational acceleration (m/s^2)
PPM = 20                    # pixels per meter
GROUND_Y = 630              # screen y of the ground (y = 0 m)
ORIGIN_X = 120              # screen x of the tower's center (x = 0 m)
FIELD_END = (WIDTH - ORIGIN_X) / PPM   # right edge of the screen, in meters

TOWER_H = 11.0              # height of the tower's walkway (m)
TOWER_HALF_W = 1.6          # half of the tower's width (m)
TOWER_MAX_HP = 100
PIVOT = (0.5, TOWER_H + 0.8)   # where the cannon barrel rotates (m)
BARREL_LEN = 2.0            # length of the barrel (m)

MIN_ANGLE, MAX_ANGLE = -35.0, 88.0
MIN_V, MAX_V = 5.0, 32.0
RELOAD_TIME = 0.75          # seconds between cannon shots
DROP_COOLDOWN = 3.0         # seconds between wall drops
BLAST_RADIUS = 1.7          # explosion radius of a shell (m)
DROP_SPEED = 1.2            # horizontal push given to a dropped stone (m/s)

ASSIST_NAMES = ["FULL", "PARTIAL", "OFF"]
ASSIST_MULT = [1, 2, 3]     # score multiplier for each trajectory assist level

HIGHSCORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "highscore.txt")


def to_screen(x, y):
    """Convert world meters to screen pixels."""
    return ORIGIN_X + x * PPM, GROUND_Y - y * PPM


def to_world(sx, sy):
    return (sx - ORIGIN_X) / PPM, (GROUND_Y - sy) / PPM


def dist_to_box(px, py, box):
    x1, y1, x2, y2 = box
    dx = max(x1 - px, 0.0, px - x2)
    dy = max(y1 - py, 0.0, py - y2)
    return math.hypot(dx, dy)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))


def gradient(stops, t):
    for (t1, c1), (t2, c2) in zip(stops, stops[1:]):
        if t <= t2:
            return lerp_color(c1, c2, (t - t1) / (t2 - t1))
    return stops[-1][1]


# ---------------------------------------------------------------------------
# FONTS AND TEXT
# ---------------------------------------------------------------------------
F_MONO = pygame.font.SysFont("consolas,couriernew", 15)
F_MONO_B = pygame.font.SysFont("consolas,couriernew", 15, bold=True)
F_SMALL = pygame.font.SysFont("consolas,couriernew", 13)
F_UI = pygame.font.SysFont("segoeui,arial", 19, bold=True)
F_UI_SMALL = pygame.font.SysFont("segoeui,arial", 15)
F_POP = pygame.font.SysFont("impact,arialblack", 26)
F_POP_BIG = pygame.font.SysFont("impact,arialblack", 40)
F_BIG = pygame.font.SysFont("impact,arialblack", 76)
F_TITLE = pygame.font.SysFont("impact,arialblack", 104)


def draw_text(surf, text, fnt, color, pos, anchor="topleft", shadow=True, alpha=255):
    img = fnt.render(text, True, color)
    rect = img.get_rect(**{anchor: (int(pos[0]), int(pos[1]))})
    if shadow:
        sh = fnt.render(text, True, (0, 0, 0))
        sh.set_alpha(int(alpha * 0.65))
        surf.blit(sh, rect.move(2, 2))
    if alpha < 255:
        img.set_alpha(int(alpha))
    surf.blit(img, rect)
    return rect


# ---------------------------------------------------------------------------
# DRAWING HELPERS (cached glow / soft sprites for particles)
# ---------------------------------------------------------------------------
_glow_cache = {}
_soft_cache = {}
_panel_cache = {}


def glow_sprite(radius, color, level=1.0):
    """Radial glow meant to be blitted with BLEND_ADD."""
    radius = max(4, int(radius) // 4 * 4)
    lvl = max(0, min(8, round(level * 8)))
    key = (radius, color, lvl)
    spr = _glow_cache.get(key)
    if spr is None:
        spr = pygame.Surface((radius * 2, radius * 2))
        spr.fill((0, 0, 0))
        f = lvl / 8
        for r in range(radius, 0, -2):
            k = (1 - r / radius) ** 2 * f
            pygame.draw.circle(spr, (int(color[0] * k), int(color[1] * k), int(color[2] * k)),
                               (radius, radius), r)
        _glow_cache[key] = spr
    return spr


def soft_sprite(radius, color):
    """Soft round blob with per-pixel alpha."""
    radius = max(2, int(radius) // 2 * 2)
    color = (color[0] // 8 * 8, color[1] // 8 * 8, color[2] // 8 * 8)
    key = (radius, color)
    spr = _soft_cache.get(key)
    if spr is None:
        spr = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        for r in range(radius, 0, -1):
            a = int(255 * (1 - r / radius) ** 1.2)
            pygame.draw.circle(spr, (*color, a), (radius, radius), r)
        _soft_cache[key] = spr
    return spr


def add_glow(surf, x, y, radius, color, level=1.0):
    if level <= 0.03:
        return
    spr = glow_sprite(radius, color, level)
    half = spr.get_width() // 2
    surf.blit(spr, (x - half, y - half), special_flags=pygame.BLEND_ADD)


def add_soft(surf, x, y, radius, color, alpha):
    if alpha <= 3:
        return
    spr = soft_sprite(radius, color)
    spr.set_alpha(int(alpha))
    half = spr.get_width() // 2
    surf.blit(spr, (x - half, y - half))


def panel(w, h, alpha=175):
    key = (w, h, alpha)
    s = _panel_cache.get(key)
    if s is None:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(s, (12, 16, 34, alpha), s.get_rect(), border_radius=12)
        pygame.draw.rect(s, (255, 255, 255, 45), s.get_rect(), 1, border_radius=12)
        _panel_cache[key] = s
    return s


def dashed_line(surf, color, a, b, dash=6, gap=5, width=1):
    x1, y1 = a
    x2, y2 = b
    length = math.hypot(x2 - x1, y2 - y1)
    if length < 1:
        return
    dx, dy = (x2 - x1) / length, (y2 - y1) / length
    d = 0.0
    while d < length:
        e = min(d + dash, length)
        pygame.draw.line(surf, color, (x1 + dx * d, y1 + dy * d), (x1 + dx * e, y1 + dy * e), width)
        d += dash + gap


def arrow(surf, color, a, b, width=3, head=9):
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    if length < 2:
        return
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    head = min(head, length * 0.6)
    base = (b[0] - head * 0.7 * math.cos(ang), b[1] - head * 0.7 * math.sin(ang))
    pygame.draw.line(surf, color, a, base, width)
    left = (b[0] - head * math.cos(ang - 0.45), b[1] - head * math.sin(ang - 0.45))
    right = (b[0] - head * math.cos(ang + 0.45), b[1] - head * math.sin(ang + 0.45))
    pygame.draw.polygon(surf, color, [b, left, right])


def make_vignette(color, strength):
    small = pygame.Surface((64, 36), pygame.SRCALPHA)
    for y in range(36):
        for x in range(64):
            dx = (x - 31.5) / 32
            dy = (y - 17.5) / 18
            d = min(1.0, math.hypot(dx, dy) / 1.3)
            small.set_at((x, y), (*color, int(strength * d ** 2.4)))
    return pygame.transform.smoothscale(small, (WIDTH, HEIGHT))


DOT = pygame.Surface((6, 6), pygame.SRCALPHA)
pygame.draw.circle(DOT, (255, 255, 255, 255), (3, 3), 2)

# ---------------------------------------------------------------------------
# SOUND (synthesised at start-up, so no audio files are needed)
# ---------------------------------------------------------------------------


class Sounds:
    def __init__(self):
        self.ok = False
        self.muted = False
        self.bank = {}
        try:
            info = pygame.mixer.get_init()
        except pygame.error:
            info = None
        if not info:
            return
        self.rate, _, self.channels = info
        pygame.mixer.set_num_channels(32)
        rng = random.Random(1234)
        R = self.rate

        def render(duration, fn, vol=0.9):
            buf = array.array("h")
            st = {}
            for i in range(int(R * duration)):
                v = max(-1.0, min(1.0, fn(i / R, st) * vol))
                s = int(v * 32767)
                buf.append(s)
                if self.channels == 2:
                    buf.append(s)
            return pygame.mixer.Sound(buffer=buf.tobytes())

        def noise_lp(st, a, key="lp"):
            lp = st.get(key, 0.0)
            lp += (rng.uniform(-1, 1) - lp) * a
            st[key] = lp
            return lp

        def osc(st, freq, key="ph"):
            ph = st.get(key, 0.0) + math.tau * freq / R
            st[key] = ph
            return math.sin(ph)

        def boom(t, st):
            n = noise_lp(st, 0.02 + 0.3 * math.exp(-t * 6))
            thump = osc(st, 35 + 90 * math.exp(-t * 8))
            env = math.exp(-t * 3.2) * min(1.0, t * 400)
            return (n * 3.2 + thump * 0.8) * env

        def fire(t, st):
            crack = noise_lp(st, 0.6) * math.exp(-t * 28)
            thump = osc(st, 45 + 110 * math.exp(-t * 14)) * math.exp(-t * 9)
            rumble = noise_lp(st, 0.05, "lp2") * 2.5 * math.exp(-t * 7)
            return (crack * 0.9 + thump + rumble) * min(1.0, t * 800)

        def hit(t, st):
            thump = osc(st, 40 + 70 * math.exp(-t * 20)) * math.exp(-t * 14)
            n = noise_lp(st, 0.25) * math.exp(-t * 22)
            return thump + n * 0.8

        def horn(t, st):
            f = 196 if t < 0.42 else 294
            f *= 1 + 0.006 * math.sin(t * 34)
            ph = st.get("ph", 0.0) + math.tau * f / R
            st["ph"] = ph
            v = sum(math.sin(ph * k) / k for k in range(1, 6))
            env = min(1.0, t * 20) * min(1.0, (1.25 - t) * 5)
            return v * 0.5 * env

        def clear(t, st):
            notes = [523, 659, 784, 1046]
            idx = min(3, int(t / 0.11))
            local = t - idx * 0.11
            v = osc(st, notes[idx])
            return v * math.exp(-local * (6 if idx < 3 else 3)) * 0.6

        def gameover(t, st):
            f = 220 * math.exp(-t * 0.7)
            ph = st.get("ph", 0.0) + math.tau * f / R
            st["ph"] = ph
            v = sum(math.sin(ph * k) / k for k in range(1, 5)) * 0.35
            trem = 0.7 + 0.3 * math.sin(t * 22)
            rumble = noise_lp(st, 0.03) * 3.0 * math.exp(-t * 1.2)
            return (v * trem + rumble) * min(1.0, t * 30) * min(1.0, (2.6 - t) * 2)

        def intercept(t, st):
            v = osc(st, 1500 * math.exp(-t * 2.5)) + 0.5 * osc(st, 2250 * math.exp(-t * 2.5), "p2")
            return v * math.exp(-t * 9) * 0.6

        def drop(t, st):
            a = 0.02 + 0.25 * (t / 0.6)
            return noise_lp(st, a) * 2.2 * math.sin(math.pi * min(1.0, t / 0.6))

        def click(t, st):
            return osc(st, 880) * math.exp(-t * 60) * 0.6

        self.bank = {
            "boom": render(1.3, boom, 0.8),
            "fire": render(0.55, fire, 0.75),
            "hit": render(0.3, hit, 0.8),
            "horn": render(1.25, horn, 0.5),
            "clear": render(0.7, clear, 0.6),
            "gameover": render(2.6, gameover, 0.8),
            "intercept": render(0.4, intercept, 0.6),
            "drop": render(0.6, drop, 0.6),
            "click": render(0.08, click, 0.6),
        }
        self.ok = True

    def play(self, name, vol=1.0):
        if not self.ok or self.muted:
            return
        snd = self.bank.get(name)
        if snd:
            ch = snd.play()
            if ch:
                ch.set_volume(vol)


# ---------------------------------------------------------------------------
# BACKGROUND
# ---------------------------------------------------------------------------


def build_background():
    bg = pygame.Surface((WIDTH, HEIGHT))
    sky = [(0.0, (14, 18, 48)), (0.35, (58, 52, 110)), (0.62, (165, 88, 122)),
           (0.84, (242, 142, 96)), (1.0, (255, 196, 122))]
    for y in range(GROUND_Y):
        pygame.draw.line(bg, gradient(sky, y / (GROUND_Y - 1)), (0, y), (WIDTH, y))

    rng = random.Random(42)
    for _ in range(110):
        x = rng.randrange(WIDTH)
        y = rng.randrange(int(GROUND_Y * 0.4))
        b = int(rng.randint(140, 240) * (1 - y / (GROUND_Y * 0.4)))
        bg.set_at((x, y), (b, b, min(255, b + 25)))

    # the setting sun
    sun = (int(WIDTH * 0.70), GROUND_Y - 150)
    for radius, color, level in ((300, (255, 110, 60), 0.8), (140, (255, 190, 110), 1.0)):
        spr = glow_sprite(radius, color, level)
        bg.blit(spr, (sun[0] - spr.get_width() // 2, sun[1] - spr.get_height() // 2),
                special_flags=pygame.BLEND_ADD)
    pygame.draw.circle(bg, (255, 238, 196), sun, 48)

    def ridge(base, amp, color, seed, rough, step):
        r = random.Random(seed)
        p = [r.uniform(0, math.tau) for _ in range(3)]
        pts = [(0, GROUND_Y)]
        for x in range(0, WIDTH + step, step):
            y = base - amp * (0.55 * math.sin(x * 0.0042 + p[0]) + 0.3 * math.sin(x * 0.011 + p[1])
                              + 0.15 * math.sin(x * 0.029 + p[2])) - r.uniform(0, rough)
            pts.append((x, y))
        pts.append((WIDTH, GROUND_Y))
        pygame.draw.polygon(bg, color, pts)

    ridge(GROUND_Y - 175, 105, (104, 72, 124), 1, 5, 8)
    ridge(GROUND_Y - 100, 65, (74, 54, 96), 2, 4, 8)
    ridge(GROUND_Y - 38, 28, (44, 48, 64), 3, 3, 6)

    # ground: dirt with a grass edge
    dirt = [(0.0, (92, 66, 44)), (1.0, (46, 32, 24))]
    for y in range(GROUND_Y, HEIGHT):
        pygame.draw.line(bg, gradient(dirt, (y - GROUND_Y) / (HEIGHT - GROUND_Y)), (0, y), (WIDTH, y))
    for _ in range(260):
        x = rng.randrange(WIDTH)
        y = rng.randrange(GROUND_Y + 12, HEIGHT)
        c = rng.randint(30, 60)
        pygame.draw.circle(bg, (c + 30, c + 18, c), (x, y), rng.randint(1, 2))
    pygame.draw.rect(bg, (60, 118, 56), (0, GROUND_Y - 2, WIDTH, 10))
    pygame.draw.line(bg, (118, 176, 82), (0, GROUND_Y - 2), (WIDTH, GROUND_Y - 2), 2)
    for _ in range(420):
        x = rng.randrange(WIDTH)
        h = rng.randint(3, 9)
        g = rng.randint(90, 150)
        pygame.draw.line(bg, (g - 40, g, g - 60), (x, GROUND_Y), (x + rng.randint(-3, 3), GROUND_Y - h))

    # distance ruler along the ground, measured from the tower's center
    ruler_y = GROUND_Y + 16
    for m in range(0, int(FIELD_END) + 1):
        sx = ORIGIN_X + m * PPM
        if m % 10 == 0:
            pygame.draw.line(bg, (235, 215, 180), (sx, ruler_y - 7), (sx, ruler_y + 7), 2)
            if m > 0:
                draw_text(bg, f"{m} m", F_SMALL, (235, 215, 180), (sx, ruler_y + 9), "midtop")
        elif m % 5 == 0:
            pygame.draw.line(bg, (200, 180, 150), (sx, ruler_y - 4), (sx, ruler_y + 4), 1)
        else:
            pygame.draw.line(bg, (150, 130, 105), (sx, ruler_y - 1), (sx, ruler_y + 2), 1)
    pygame.draw.line(bg, (150, 130, 105), (ORIGIN_X, ruler_y), (WIDTH, ruler_y), 1)
    return bg


def make_clouds():
    clouds = []
    rng = random.Random(9)
    for _ in range(7):
        w, h = rng.randint(180, 300), rng.randint(60, 90)
        spr = pygame.Surface((w, h), pygame.SRCALPHA)
        for _ in range(14):
            r = rng.randint(h // 4, h // 2)
            cx = rng.randint(r, w - r)
            cy = rng.randint(h // 2, h - r) if r < h // 2 else h - r
            blob = soft_sprite(r, (255, 206, 200))
            spr.blit(blob, (cx - r, cy - r))
        clouds.append({"spr": spr, "x": rng.uniform(-100, WIDTH), "y": rng.uniform(30, 300),
                       "speed": rng.uniform(4, 12), "alpha": rng.randint(110, 190)})
    return clouds


def build_tower_sprite():
    w, h = 76, 234
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    rng = random.Random(3)
    body = pygame.Rect(6, 14, 64, 220)

    def bricks(area, row_h=12, brick_w=16):
        for row, y in enumerate(range(area.top, area.bottom, row_h)):
            off = 0 if row % 2 == 0 else brick_w // 2
            for bx in range(area.left - off, area.right, brick_w):
                r = pygame.Rect(bx, y, brick_w, row_h).clip(area)
                if r.width <= 0 or r.height <= 0:
                    continue
                base = 150 + rng.randint(-20, 18)
                pygame.draw.rect(s, (base, base - 8, base - 24), r)
                pygame.draw.rect(s, (88, 80, 72), r, 1)

    bricks(body)
    for i in range(4):   # battlements
        m = pygame.Rect(6 + i * 18, 0, 10, 16)
        bricks(m, 8, 10)
        pygame.draw.rect(s, (88, 80, 72), m, 1)
    pygame.draw.rect(s, (112, 104, 96), (2, 14, 72, 7))
    pygame.draw.rect(s, (72, 66, 60), (2, 14, 72, 7), 1)
    pygame.draw.rect(s, (112, 104, 96), (0, h - 16, 76, 16))
    pygame.draw.rect(s, (72, 66, 60), (0, h - 16, 76, 16), 1)
    # arched door
    pygame.draw.rect(s, (46, 30, 22), (26, h - 46, 24, 30))
    pygame.draw.circle(s, (46, 30, 22), (38, h - 46), 12)
    for x in (30, 36, 42):
        pygame.draw.line(s, (70, 46, 30), (x, h - 52), (x, h - 17))
    pygame.draw.rect(s, (40, 36, 34), (36, 76, 6, 20))    # window slits
    pygame.draw.rect(s, (40, 36, 34), (36, 146, 6, 20))
    # light from the sun on the right, shadow on the left
    shade = pygame.Surface((w, h), pygame.SRCALPHA)
    for x in range(w):
        f = int(150 + 105 * (x / (w - 1)) ** 0.8)
        pygame.draw.line(shade, (f, f, f, 255), (x, 0), (x, h))
    s.blit(shade, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    white = pygame.mask.from_surface(s).to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))
    return s, white


def gen_cracks():
    rng = random.Random()
    cracks = []
    for _ in range(9):
        x, y = rng.uniform(12, 64), rng.uniform(30, 200)
        pts = [(x, y)]
        for _ in range(rng.randint(3, 6)):
            x = max(8, min(68, x + rng.uniform(-9, 9)))
            y += rng.uniform(5, 16)
            pts.append((x, y))
        cracks.append(pts)
    return cracks


# ---------------------------------------------------------------------------
# GAME OBJECTS
# ---------------------------------------------------------------------------
FIRE_COLORS = [(255, 250, 220), (255, 222, 120), (255, 170, 60), (240, 110, 30), (175, 60, 22), (90, 42, 32)]


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "size_end", "color",
                 "kind", "grav", "drag", "rot", "spin", "floor")

    def __init__(self, x, y, vx, vy, life, size, color, kind, grav=0.0, drag=0.0, size_end=None, spin=0.0):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.size = size
        self.size_end = size if size_end is None else size_end
        self.color, self.kind = color, kind
        self.grav, self.drag = grav, drag
        self.rot = random.uniform(0, math.tau)
        self.spin = spin
        self.floor = GROUND_Y + random.uniform(-2, 10)


class FloatText:
    def __init__(self, text, x, y, color, fnt=F_POP, life=1.2, vy=-45):
        self.text, self.x, self.y, self.color, self.fnt = text, x, y, color, fnt
        self.life = self.max_life = life
        self.vy = vy


class Banner:
    def __init__(self, title, subtitle, duration, color=(255, 214, 110)):
        self.title, self.subtitle, self.color = title, subtitle, color
        self.t, self.duration = 0.0, duration


class Shell:
    """A projectile whose position is always computed from the exact kinematic equations."""

    def __init__(self, x0, y0, v0, angle_deg, kind="shell"):
        th = math.radians(angle_deg)
        self.x0, self.y0 = x0, y0
        self.v0, self.angle = v0, angle_deg
        self.vx = v0 * math.cos(th)
        self.vy0 = v0 * math.sin(th)
        self.t = 0.0
        self.x, self.y = x0, y0
        self.kind = kind
        self.alive = True
        self.trail_timer = 0.0

    def pos(self, t):
        return self.x0 + self.vx * t, self.y0 + self.vy0 * t - 0.5 * G * t * t

    def vy(self):
        return self.vy0 - G * self.t

    def ground_time(self):
        """Solve y0 + vy0 t - 1/2 g t^2 = 0 for the positive root."""
        return (self.vy0 + math.sqrt(self.vy0 ** 2 + 2 * G * self.y0)) / G


class Missile(Shell):
    """Enemy projectiles (catapult stones and airship bombs) use the same physics."""

    def __init__(self, x0, y0, vx, vy, kind, damage):
        v0 = math.hypot(vx, vy)
        super().__init__(x0, y0, v0, math.degrees(math.atan2(vy, vx)), kind)
        self.vx, self.vy0 = vx, vy
        self.damage = damage
        self.spin = random.uniform(-8, 8)


ENEMY_STATS = {
    "soldier":  dict(hp=1,  speed=1.5,  w=0.8, h=1.9, period=1.0, strike=2,  score=100),
    "runner":   dict(hp=1,  speed=3.1,  w=0.7, h=1.6, period=0.7, strike=1,  score=150),
    "brute":    dict(hp=3,  speed=0.85, w=1.3, h=2.5, period=1.3, strike=6,  score=300),
    "catapult": dict(hp=3,  speed=1.2,  w=2.8, h=2.4, period=5.0, strike=6,  score=400),
    "bomber":   dict(hp=1,  speed=2.8,  w=3.4, h=1.5, period=0.0, strike=10, score=350),
    "ram":      dict(hp=14, speed=0.55, w=4.4, h=3.2, period=2.2, strike=14, score=2500),
}

PALETTES = {
    "soldier": dict(body=(150, 36, 42), leg=(64, 42, 40), leg_dark=(40, 28, 28), helmet=(84, 84, 96),
                    plume=(220, 44, 40), skin=(205, 160, 122), lean=0),
    "runner": dict(body=(206, 118, 40), leg=(70, 50, 36), leg_dark=(44, 32, 26), helmet=(62, 50, 40),
                   plume=(240, 180, 60), skin=(205, 160, 122), lean=5),
    "brute": dict(body=(96, 96, 108), leg=(56, 56, 64), leg_dark=(38, 38, 44), helmet=(70, 70, 82),
                  plume=(200, 190, 170), skin=(170, 140, 110), lean=0),
}


class Enemy:
    def __init__(self, kind, wave):
        st = ENEMY_STATS[kind]
        self.kind = kind
        self.max_hp = st["hp"] + (6 * (wave // 5 - 1) if kind == "ram" and wave >= 5 else 0)
        self.hp = self.max_hp
        pace = 1 + min(0.45, 0.035 * (wave - 1))
        self.speed = st["speed"] * pace * random.uniform(0.9, 1.1)
        self.w, self.h = st["w"], st["h"]
        self.period, self.strike, self.score = st["period"], st["strike"], st["score"]
        self.x = FIELD_END + random.uniform(1.5, 3.5)
        self.y = self.base_y = 0.0
        self.state = "walk"
        self.anim = random.uniform(0, math.tau)
        self.seed = random.uniform(0, 100)
        self.flash = 0.0
        self.timer = random.uniform(0.2, max(0.3, self.period))
        self.strike_anim = 0.0
        self.arm_phase = 9.0
        self.dead = self.gone = False
        self.has_bomb = False
        self.stop_x = TOWER_HALF_W + self.w / 2 + random.uniform(0.1, 0.8)
        if kind == "catapult":
            self.stop_x = random.uniform(24, 36)
            self.period = max(3.0, 5.5 - 0.15 * (wave - 4))
            self.timer = random.uniform(0.8, 1.8)
        elif kind == "bomber":
            self.y = self.base_y = random.uniform(17, 25)
            self.x = FIELD_END + random.uniform(3, 6)
            self.has_bomb = True
        elif kind == "ram":
            self.stop_x = TOWER_HALF_W + self.w / 2 + 1.5

    def box(self):
        if self.kind == "bomber":
            return (self.x - self.w / 2, self.y - self.h / 2, self.x + self.w / 2, self.y + self.h / 2)
        return (self.x - self.w / 2, 0.0, self.x + self.w / 2, self.h)


def build_wave(n):
    kinds = ["soldier"] * (3 + 2 * n)
    if n >= 2:
        kinds += ["runner"] * (n + 1)
    if n >= 3:
        kinds += ["brute"] * ((n - 1) // 2)
        kinds += ["bomber"] * (n // 3)
    if n >= 4:
        kinds += ["catapult"] * (1 + (n - 4) // 3)
    random.shuffle(kinds)
    kinds.insert(0, "soldier")
    if n % 5 == 0:
        kinds.insert(len(kinds) // 2, "ram")
    return kinds


WAVE_TIPS = {
    1: "Aim with the mouse or W/S.  Change launch speed with the wheel or A/D.",
    2: "NEW: RUNNERS - fast but fragile. Lead your target!",
    3: "NEW: BRUTES (3 hits) and AIRSHIPS - a dropped bomb keeps the airship's horizontal velocity.",
    4: "NEW: CATAPULTS - they lob stones at the tower. Shoot the stones out of the sky!",
    5: "BOSS: SIEGE RAM - pound it with shells before it reaches the walls!",
}

# ---------------------------------------------------------------------------
# THE GAME
# ---------------------------------------------------------------------------


class Game:
    def __init__(self):
        self.sounds = Sounds()
        self.bg = build_background()
        self.clouds = make_clouds()
        self.vignette = make_vignette((0, 0, 0), 150)
        self.red_vignette = make_vignette((210, 0, 0), 230)
        self.tower_sprite, self.tower_white = build_tower_sprite()
        self.crater = pygame.Surface((70, 18), pygame.SRCALPHA)
        for i in range(9, 0, -1):
            pygame.draw.ellipse(self.crater, (34, 24, 18, int(200 * (1 - i / 10))),
                                (35 - i * 3.8, 9 - i * 0.95, i * 7.6, i * 1.9))
        self.canvas = pygame.Surface((WIDTH, HEIGHT))
        self.highscore = self.load_highscore()
        self.assist = 1
        self.show_vectors = True
        self.show_panel = True
        self.fullscreen = False
        self.t_real = 0.0
        self.reset(to_menu=True)

    # ------------------------------------------------------------ state ---
    def reset(self, to_menu=False):
        self.state = "menu" if to_menu else "play"
        self.ground = self.bg.copy()
        self.enemies, self.shells, self.missiles = [], [], []
        self.particles, self.texts = [], []
        self.tower_hp = TOWER_MAX_HP
        self.tower_alive = True
        self.tower_flash = 0.0
        self.tower_emit = 0.0
        self.cracks = gen_cracks()
        self.rubble = []
        self.angle, self.v0 = 40.0, 18.0
        self.reload = self.drop_cd = self.recoil = 0.0
        self.score = self.kills = self.shots = self.hits = self.intercepts = 0
        self.longest = self.highest = 0.0
        self.last_shot = None
        self.shake = 0.0
        self.time_scale = 1.0
        self.slowmo = 0.0
        self.wave = 0
        self.spawn_queue = []
        self.spawn_timer = 0.0
        self.spawn_interval = 2.0
        self.wave_active = False
        self.next_wave_timer = 1.2 if not to_menu else None
        self.banner = None
        self.collapse_t = 0.0
        self.collapse_events = []
        self.over_t = 0.0
        self.new_high = False
        self.zoom = 1.0
        self.hold = {"up": 0.0, "down": 0.0, "left": 0.0, "right": 0.0}
        self.demo_timer, self.demo_spawn, self.demo_plan = 1.5, 0.5, None

    def load_highscore(self):
        try:
            with open(HIGHSCORE_FILE) as f:
                return int(f.read().strip() or 0)
        except (OSError, ValueError):
            return 0

    def save_highscore(self):
        try:
            with open(HIGHSCORE_FILE, "w") as f:
                f.write(str(self.highscore))
        except OSError:
            pass

    # ------------------------------------------------------------- loop ---
    def run(self):
        while True:
            dt = min(clock.tick(FPS) / 1000.0, 0.05)
            for event in pygame.event.get():
                if self.handle_event(event) is False:
                    return
            self.update(dt)
            self.draw()
            pygame.display.flip()

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYDOWN:
            k = event.key
            shift = event.mod & pygame.KMOD_SHIFT
            if k == pygame.K_F11:
                pygame.display.toggle_fullscreen()
            elif k == pygame.K_m:
                self.sounds.muted = not self.sounds.muted
            elif k == pygame.K_t:
                self.assist = (self.assist + 1) % 3
                self.sounds.play("click")
            elif k == pygame.K_v:
                self.show_vectors = not self.show_vectors
            elif k == pygame.K_h:
                self.show_panel = not self.show_panel

            if self.state == "menu":
                if k in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER):
                    self.reset()
                elif k == pygame.K_ESCAPE:
                    return False
            elif self.state == "play":
                if k == pygame.K_SPACE:
                    self.fire()
                elif k == pygame.K_f:
                    self.drop_stone()
                elif k in (pygame.K_p, pygame.K_ESCAPE):
                    self.state = "pause"
                elif k in (pygame.K_UP, pygame.K_w):
                    self.set_angle(self.angle + (0.1 if shift else 1.0))
                elif k in (pygame.K_DOWN, pygame.K_s):
                    self.set_angle(self.angle - (0.1 if shift else 1.0))
                elif k in (pygame.K_RIGHT, pygame.K_d):
                    self.set_speed(self.v0 + (0.1 if shift else 0.5))
                elif k in (pygame.K_LEFT, pygame.K_a):
                    self.set_speed(self.v0 - (0.1 if shift else 0.5))
            elif self.state == "pause":
                if k in (pygame.K_p, pygame.K_ESCAPE):
                    self.state = "play"
                elif k == pygame.K_q:
                    self.reset(to_menu=True)
            elif self.state == "over" and self.over_t > 1.0:
                if k in (pygame.K_r, pygame.K_RETURN, pygame.K_SPACE):
                    self.reset()
                elif k == pygame.K_ESCAPE:
                    self.reset(to_menu=True)

        elif event.type == pygame.MOUSEMOTION and self.state == "play":
            px, py = to_screen(*PIVOT)
            mx, my = event.pos
            if math.hypot(mx - px, my - py) > 25:
                self.set_angle(round(math.degrees(math.atan2(py - my, mx - px)) * 2) / 2)
        elif event.type == pygame.MOUSEWHEEL and self.state == "play":
            self.set_speed(self.v0 + event.y * 0.5)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.state == "menu" and event.button == 1:
                self.reset()
            elif self.state == "play":
                if event.button == 1:
                    self.fire()
                elif event.button == 3:
                    self.drop_stone()
            elif self.state == "over" and self.over_t > 1.0 and event.button == 1:
                self.reset()
        return True

    def set_angle(self, a):
        self.angle = max(MIN_ANGLE, min(MAX_ANGLE, a))

    def set_speed(self, v):
        self.v0 = round(max(MIN_V, min(MAX_V, v)), 2)

    # ------------------------------------------------------------ update ---
    def update(self, real_dt):
        self.t_real += real_dt
        if self.state == "pause":
            return

        if self.slowmo > 0:
            self.slowmo -= real_dt
        target = 0.35 if self.slowmo > 0 else 1.0
        if self.state == "collapse" and self.collapse_t < 1.6:
            target = 0.4
        self.time_scale += (target - self.time_scale) * min(1.0, real_dt * 8)
        dt = real_dt * self.time_scale

        self.shake *= 0.86 ** (real_dt * 60)
        self.recoil *= 0.82 ** (real_dt * 60)
        self.tower_flash = max(0.0, self.tower_flash - real_dt)
        for cl in self.clouds:
            cl["x"] += cl["speed"] * real_dt
            if cl["x"] > WIDTH + 20:
                cl["x"] = -cl["spr"].get_width() - 20

        if self.state == "menu":
            self.update_demo(dt)
        elif self.state == "play":
            self.update_input(real_dt)
            self.update_waves(dt)
            self.reload = max(0.0, self.reload - dt)
            self.drop_cd = max(0.0, self.drop_cd - dt)
        elif self.state == "collapse":
            self.update_collapse(real_dt)
        elif self.state == "over":
            self.over_t += real_dt
            self.zoom += (1.0 - self.zoom) * min(1.0, real_dt * 2)

        self.update_enemies(dt)
        self.update_shells(dt)
        self.update_missiles(dt)
        self.update_tower_fx(dt)
        self.update_particles(dt)
        for ft in self.texts:
            ft.life -= real_dt
            ft.y += ft.vy * real_dt
            ft.vy *= 0.97
        self.texts = [ft for ft in self.texts if ft.life > 0]
        if self.banner:
            self.banner.t += real_dt
            if self.banner.t > self.banner.duration:
                self.banner = None

    def update_input(self, dt):
        keys = pygame.key.get_pressed()
        fine = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        groups = {
            "up": (keys[pygame.K_UP] or keys[pygame.K_w], lambda r: self.set_angle(self.angle + r * (3 if fine else 30))),
            "down": (keys[pygame.K_DOWN] or keys[pygame.K_s], lambda r: self.set_angle(self.angle - r * (3 if fine else 30))),
            "right": (keys[pygame.K_RIGHT] or keys[pygame.K_d], lambda r: self.set_speed(self.v0 + r * (1.5 if fine else 10))),
            "left": (keys[pygame.K_LEFT] or keys[pygame.K_a], lambda r: self.set_speed(self.v0 - r * (1.5 if fine else 10))),
        }
        for name, (held, action) in groups.items():
            if held:
                self.hold[name] += dt
                if self.hold[name] > 0.35:   # key held down: repeat smoothly
                    action(dt)
            else:
                self.hold[name] = 0.0

    def update_waves(self, dt):
        if self.next_wave_timer is not None:
            self.next_wave_timer -= dt
            if self.next_wave_timer <= 0:
                self.next_wave_timer = None
                self.start_wave(self.wave + 1)
            return
        if not self.wave_active:
            return
        if self.spawn_queue:
            self.spawn_timer -= dt
            if self.spawn_timer <= 0:
                kind = self.spawn_queue.pop(0)
                self.enemies.append(Enemy(kind, self.wave))
                self.spawn_timer = self.spawn_interval * random.uniform(0.6, 1.4)
                if kind == "ram":
                    self.banner = Banner("SIEGE RAM!", "A boss approaches the gates", 2.2, (255, 90, 70))
                    self.sounds.play("horn", 0.8)
        elif not self.enemies and not self.missiles:
            self.wave_active = False
            repair = min(15, TOWER_MAX_HP - self.tower_hp)
            self.tower_hp += repair
            bonus = 250 * self.wave
            self.score += bonus
            sub = f"+{bonus} bonus" + (f"   |   Tower repaired +{repair:.0f}" if repair > 0 else "")
            self.banner = Banner("WAVE CLEARED", sub, 3.0, (140, 255, 160))
            self.sounds.play("clear")
            self.next_wave_timer = 4.5

    def start_wave(self, n):
        self.wave = n
        self.wave_active = True
        self.spawn_queue = build_wave(n)
        self.spawn_timer = 1.2
        self.spawn_interval = max(0.65, 2.5 - 0.13 * n)
        tip = WAVE_TIPS.get(n, "Faster, tougher, more of them. Hold the line!")
        self.banner = Banner(f"WAVE {n}", tip, 3.2)
        self.sounds.play("horn")

    def update_demo(self, dt):
        """Menu background: the cannon aims itself by solving the projectile equations."""
        self.demo_spawn -= dt
        if self.demo_spawn <= 0 and len(self.enemies) < 6:
            self.enemies.append(Enemy(random.choice(["soldier", "soldier", "runner", "brute", "catapult"]), 3))
            self.demo_spawn = random.uniform(1.0, 2.2)
        self.reload = max(0.0, self.reload - dt)
        self.demo_timer -= dt
        targets = [e for e in self.enemies if e.kind != "bomber" and 6 < e.x < FIELD_END - 3]
        if self.demo_plan is None and self.demo_timer <= 0 and targets:
            e = min(targets, key=lambda en: en.x)
            th = math.radians(random.choice([25, 35, 45, 55, 65]))
            mx, my = PIVOT[0] + BARREL_LEN * math.cos(th), PIVOT[1] + BARREL_LEN * math.sin(th)
            tx = e.x
            v = None
            for _ in range(3):   # lead the target by its travel during the flight
                dx = tx - mx
                denom = 2 * math.cos(th) ** 2 * (dx * math.tan(th) + my)
                if dx <= 0 or denom <= 0:
                    break
                v = math.sqrt(G * dx * dx / denom)
                flight = dx / (v * math.cos(th))
                tx = e.x - (e.speed * flight if e.state == "walk" else 0)
            if v and MIN_V <= v <= MAX_V:
                self.demo_plan = (math.degrees(th), v)
        if self.demo_plan:
            ang, v = self.demo_plan
            self.angle += (ang - self.angle) * min(1.0, dt * 5)
            self.v0 += (v - self.v0) * min(1.0, dt * 5)
            if abs(self.angle - ang) < 0.3:
                self.angle, self.v0 = ang, v
                self.fire(force=True)
                self.demo_plan = None
                self.demo_timer = random.uniform(0.6, 1.6)

    # ------------------------------------------------------------ cannon ---
    def muzzle(self):
        th = math.radians(self.angle)
        return PIVOT[0] + BARREL_LEN * math.cos(th), PIVOT[1] + BARREL_LEN * math.sin(th)

    def predict(self):
        mx, my = self.muzzle()
        th = math.radians(self.angle)
        vx, vy = self.v0 * math.cos(th), self.v0 * math.sin(th)
        T = (vy + math.sqrt(vy * vy + 2 * G * my)) / G
        H = my + (vy * vy / (2 * G) if vy > 0 else 0.0)
        R = mx + vx * T
        return mx, my, vx, vy, T, H, R

    def fire(self, force=False):
        if self.reload > 0 or (self.state != "play" and not force):
            return
        mx, my = self.muzzle()
        self.shells.append(Shell(mx, my, self.v0, self.angle))
        if self.state == "play":
            self.shots += 1
        self.reload = RELOAD_TIME
        self.recoil = 12
        self.shake = max(self.shake, 4)
        self.sounds.play("fire", 0.7)
        sx, sy = to_screen(mx, my)
        th = math.radians(self.angle)
        dx, dy = math.cos(th), -math.sin(th)
        self.particles.append(Particle(sx, sy, 0, 0, 0.14, 46, (255, 220, 150), "flash"))
        for _ in range(14):
            spd = random.uniform(60, 260)
            spread = random.uniform(-0.35, 0.35)
            vx = (dx * math.cos(spread) - dy * math.sin(spread)) * spd
            vy = (dx * math.sin(spread) + dy * math.cos(spread)) * spd
            self.particles.append(Particle(sx, sy, vx, vy, random.uniform(0.15, 0.35),
                                           random.uniform(5, 10), random.choice(FIRE_COLORS[:3]),
                                           "fire", drag=6, size_end=1))
        for _ in range(8):
            spd = random.uniform(20, 110)
            self.particles.append(Particle(sx, sy, dx * spd + random.uniform(-15, 15), dy * spd - 10,
                                           random.uniform(0.9, 1.8), random.uniform(6, 10), (200, 196, 190),
                                           "smoke", grav=-25, drag=1.8, size_end=random.uniform(18, 28)))

    def drop_stone(self):
        """Emergency weapon: drop a stone off the wall (a horizontal launch from rest height h)."""
        if self.drop_cd > 0 or self.state != "play":
            return
        x0, y0 = TOWER_HALF_W + 0.3, TOWER_H + 0.3
        self.shells.append(Shell(x0, y0, DROP_SPEED, 0.0, kind="rock"))
        self.drop_cd = DROP_COOLDOWN
        self.sounds.play("drop", 0.6)
        t_fall = math.sqrt(2 * y0 / G)
        sx, sy = to_screen(x0, y0)
        self.texts.append(FloatText(f"free fall: t = √(2h/g) = {t_fall:.2f} s", sx + 20, sy - 20,
                                    (200, 230, 255), F_MONO_B, 2.2, -12))

    # ------------------------------------------------------------- shells ---
    def update_shells(self, dt):
        steps = 4
        h = dt / steps
        for s in self.shells:
            for _ in range(steps):
                if not s.alive:
                    break
                s.t += h
                s.x, s.y = s.pos(s.t)
                if s.y <= 0:
                    tg = s.ground_time()
                    s.t = tg
                    s.x, s.y = s.pos(tg)
                    s.y = 0.0
                    self.shell_impact(s, None)
                    break
                if s.t > 0.1 and s.x < TOWER_HALF_W and s.y < TOWER_H + 0.5:
                    self.shell_impact(s, None)   # landed on our own battlements
                    break
                hit = None
                for e in self.enemies:
                    if not e.dead and dist_to_box(s.x, s.y, e.box()) < 0.25:
                        hit = e
                        break
                if hit:
                    self.shell_impact(s, hit)
                    break
                for m in self.missiles:
                    if m.alive and math.hypot(m.x - s.x, m.y - s.y) < 0.8:
                        m.alive = False
                        self.intercepts += 1
                        pts = 200 * ASSIST_MULT[self.assist]
                        self.score += pts
                        sx, sy = to_screen(s.x, s.y)
                        self.texts.append(FloatText(f"INTERCEPT! +{pts}", sx, sy - 20, (120, 220, 255)))
                        self.sounds.play("intercept")
                        self.shell_impact(s, None, intercepted=True)
                        break
            if not s.alive:
                continue
            # smoke trail
            s.trail_timer -= dt
            if s.trail_timer <= 0:
                s.trail_timer = 0.02
                sx, sy = to_screen(s.x, s.y)
                self.particles.append(Particle(sx, sy, random.uniform(-8, 8), random.uniform(-8, 8),
                                               random.uniform(0.5, 0.9), 3, (220, 214, 205), "smoke",
                                               grav=-10, drag=1, size_end=9))
        self.shells = [s for s in self.shells if s.alive]

    def shell_impact(self, s, direct, intercepted=False):
        s.alive = False
        if s.kind == "shell" and self.state in ("play", "collapse", "over", "menu"):
            self.record_shot(s)
        visible = s.x < FIELD_END + 3
        radius = BLAST_RADIUS if s.kind == "shell" else 1.8
        hit = self.explode(s.x, s.y, radius, direct=direct, visible=visible, scale=1.0 if s.kind == "shell" else 0.8)
        if s.kind == "shell" and (hit or intercepted) and self.state == "play":
            self.hits += 1

    def record_shot(self, s):
        T = s.t
        apex_t = max(0.0, min(T, s.vy0 / G))
        ax, ay = s.pos(apex_t)
        pts = [to_screen(*s.pos(T * i / 60)) for i in range(61)]
        self.last_shot = dict(pts=pts, apex=(ax, ay), land=(s.x, s.y), T=T, v0=s.v0, angle=s.angle,
                              ground=s.y <= 0.01)
        if self.state == "play":
            if s.y <= 0.01:
                self.longest = max(self.longest, s.x)
            self.highest = max(self.highest, ay)

    # ----------------------------------------------------------- missiles ---
    def update_missiles(self, dt):
        steps = 3
        h = dt / steps
        for m in self.missiles:
            for _ in range(steps):
                if not m.alive:
                    break
                m.t += h
                m.x, m.y = m.pos(m.t)
                if self.tower_alive and -TOWER_HALF_W - 0.3 <= m.x <= TOWER_HALF_W + 0.3 and m.y <= TOWER_H + 0.7:
                    m.alive = False
                    sx, sy = to_screen(m.x, m.y)
                    if m.kind == "bomb":
                        self.explode(m.x, m.y, 1.2, player=False, scale=0.9)
                    else:
                        self.dust_burst(sx, sy, 14, (150, 140, 130))
                        self.sounds.play("hit", 0.8)
                    self.damage_tower(m.damage, m.x, m.y, heavy=m.kind == "bomb")
                elif m.y <= 0:
                    m.alive = False
                    sx, sy = to_screen(m.x, 0)
                    if m.kind == "bomb":
                        self.explode(m.x, 0, 1.2, player=False, scale=0.7)
                    else:
                        self.dust_burst(sx, sy, 12, (140, 110, 80))
            if m.alive:
                sx, sy = to_screen(m.x, m.y)
                if random.random() < 0.5:
                    col = (255, 190, 90) if m.kind == "bomb" else (150, 140, 130)
                    kind = "fire" if m.kind == "bomb" else "smoke"
                    self.particles.append(Particle(sx, sy, 0, 0, 0.4, 3, col, kind, size_end=6 if kind == "smoke" else 1))
        self.missiles = [m for m in self.missiles if m.alive]

    # ----------------------------------------------------------- enemies ---
    def update_enemies(self, dt):
        cheering = self.state in ("collapse", "over")
        for e in self.enemies:
            e.flash = max(0.0, e.flash - dt)
            e.strike_anim = max(0.0, e.strike_anim - dt)
            e.arm_phase += dt
            if e.kind == "bomber":
                e.x -= e.speed * dt
                e.anim += dt * 3
                e.y = e.base_y + math.sin(e.anim) * 0.3
                if e.has_bomb and not cheering and self.state != "menu":
                    drop_h = e.y - 0.8 - (TOWER_H + 0.7)
                    if drop_h > 0 and e.x - e.speed * math.sqrt(2 * drop_h / G) <= 0.3:
                        e.has_bomb = False
                        self.missiles.append(Missile(e.x, e.y - 0.8, -e.speed, 0.0, "bomb", e.strike))
                if e.x < -10:
                    e.gone = True
                continue
            if cheering:
                e.state = "cheer"
                continue
            if e.state == "walk":
                e.x -= e.speed * dt
                e.anim += dt * e.speed * 5.5
                if e.x <= e.stop_x:
                    e.x = e.stop_x
                    e.state = "siege" if e.kind == "catapult" else "attack"
            elif e.state == "attack":
                e.timer -= dt
                if e.timer <= 0:
                    e.timer = e.period
                    e.strike_anim = 0.3
                    if self.state == "play":
                        self.damage_tower(e.strike, TOWER_HALF_W, random.uniform(0.5, 2.2) if e.kind != "ram" else 1.6,
                                          heavy=e.kind in ("ram", "brute"))
            elif e.state == "siege":
                e.timer -= dt
                if e.timer <= 0:
                    e.timer = e.period * random.uniform(0.85, 1.15)
                    e.arm_phase = 0.0
                    self.catapult_fire(e)
        self.enemies = [e for e in self.enemies if not e.dead and not e.gone]

    def catapult_fire(self, e):
        """The catapult solves the projectile equation to hit the tower wall."""
        th = math.radians(52)
        x0, y0 = e.x - 0.9, 3.3
        tx, ty = TOWER_HALF_W - 0.2, random.uniform(3.0, 9.0)
        dx, dy = x0 - tx, ty - y0
        denom = 2 * math.cos(th) ** 2 * (dx * math.tan(th) - dy)
        if denom <= 0:
            return
        v = math.sqrt(G * dx * dx / denom) * random.uniform(0.985, 1.015)
        if self.state == "menu":
            v *= 0.8   # the demo catapults never hit
        self.missiles.append(Missile(x0, y0, -v * math.cos(th), v * math.sin(th), "stone", e.strike))
        sx, sy = to_screen(x0, y0)
        self.dust_burst(sx, sy, 6, (170, 150, 120))

    def damage_tower(self, amount, x, y, heavy=False):
        if not self.tower_alive or self.state != "play":
            return
        self.tower_hp -= amount
        self.tower_flash = 0.12
        self.shake = max(self.shake, 7 if heavy else 3)
        self.sounds.play("hit", 0.7 if heavy else 0.4)
        sx, sy = to_screen(x, y)
        for _ in range(10 if heavy else 5):
            self.particles.append(Particle(sx, sy, random.uniform(-40, 160), random.uniform(-220, -40),
                                           random.uniform(0.6, 1.2), random.uniform(2, 4),
                                           random.choice([(150, 142, 130), (120, 112, 100)]), "debris",
                                           grav=900, spin=random.uniform(-10, 10)))
        self.texts.append(FloatText(f"-{amount:.0f}", sx + 16, sy - 10, (255, 90, 80), F_POP, 0.9))
        if self.tower_hp <= 0:
            self.tower_hp = 0
            self.destroy_tower()

    def kill_enemy(self, e, bx, by):
        e.dead = True
        sx, sy = to_screen(e.x, e.y + (0 if e.kind == "bomber" else e.h * 0.5))
        big = e.kind in ("catapult", "ram", "bomber")
        pal = PALETTES.get(e.kind)
        colors = [pal["body"], pal["helmet"], pal["skin"]] if pal else [(110, 74, 44), (80, 54, 34), (60, 60, 66)]
        if e.kind == "bomber":
            colors = [(130, 50, 52), (90, 36, 40), (70, 60, 50)]
        away = 1 if e.x >= bx else -1
        for _ in range(18 if big else 8):
            self.particles.append(Particle(sx + random.uniform(-10, 10), sy + random.uniform(-10, 10),
                                           away * random.uniform(40, 260) + random.uniform(-60, 60),
                                           random.uniform(-420, -120), random.uniform(1.5, 3.0),
                                           random.uniform(2.5, 6 if big else 4), random.choice(colors),
                                           "debris", grav=900, spin=random.uniform(-14, 14)))
        if big:
            self.explosion_fx(sx, sy, 1.2, ground=False)
            self.sounds.play("boom", 0.8)
        self.kills += 1

    def explode(self, x, y, radius, direct=None, player=True, visible=True, scale=1.0):
        """Blast at (x, y) meters. Returns True if any enemy was hurt."""
        sx, sy = to_screen(x, y)
        if visible:
            self.explosion_fx(sx, sy, scale, ground=y < 0.4)
            self.shake = max(self.shake, 7 * scale)
            self.sounds.play("boom", 0.55 * scale + 0.2)
        if not player:
            return False
        hurt = False
        killed = []
        for e in self.enemies:
            if e.dead:
                continue
            if dist_to_box(x, y, e.box()) <= radius:
                hurt = True
                e.hp -= 2 if e is direct else 1
                e.flash = 0.12
                if e.hp <= 0:
                    self.kill_enemy(e, x, y)
                    killed.append(e)
        for m in self.missiles:
            if m.alive and math.hypot(m.x - x, m.y - y) <= radius * 1.2:
                m.alive = False
                hurt = True
        if killed and self.state == "play":
            n = len(killed)
            mult = ASSIST_MULT[self.assist] * (1 + 0.5 * (n - 1))
            for e in killed:
                pts = int(e.score * mult)
                self.score += pts
                ex, ey = to_screen(e.x, e.y + e.h + 0.3 if e.kind != "bomber" else e.y + 1)
                self.texts.append(FloatText(f"+{pts}", ex, ey, (255, 235, 140), F_POP, 1.0))
            if direct in killed and n == 1:
                self.texts.append(FloatText("DIRECT HIT!", sx, sy - 60, (255, 200, 90), F_POP, 1.1))
            if n >= 2:
                label = {2: "DOUBLE KILL!", 3: "TRIPLE KILL!"}.get(n, f"MULTI KILL x{n}!")
                self.texts.append(FloatText(label, sx, sy - 70, (255, 120, 90), F_POP_BIG, 1.6, -30))
            if n >= 3:
                self.slowmo = 0.45
        return hurt

    def explosion_fx(self, sx, sy, scale=1.0, ground=False):
        P = self.particles
        P.append(Particle(sx, sy, 0, 0, 0.28, 110 * scale, (255, 214, 150), "flash"))
        P.append(Particle(sx, sy, 0, 0, 0.45, 8, (255, 236, 210), "ring", size_end=80 * scale))
        for _ in range(int(18 * scale)):
            a = random.uniform(0, math.tau) if not ground else random.uniform(math.pi, math.tau)
            spd = random.uniform(40, 230) * scale
            P.append(Particle(sx, sy, math.cos(a) * spd, math.sin(a) * spd, random.uniform(0.35, 0.8),
                              random.uniform(10, 22) * scale, random.choice(FIRE_COLORS[:4]), "fire",
                              grav=-70, drag=3.2, size_end=2))
        for _ in range(int(22 * scale)):
            a = random.uniform(0, math.tau) if not ground else random.uniform(math.pi * 1.05, math.tau * 0.97)
            spd = random.uniform(200, 540) * scale
            P.append(Particle(sx, sy, math.cos(a) * spd, math.sin(a) * spd, random.uniform(0.3, 0.75),
                              2, (255, 214, 130), "spark", grav=520, drag=1.2))
        for _ in range(int(11 * scale)):
            a = random.uniform(0, math.tau)
            spd = random.uniform(15, 90) * scale
            g = random.randint(55, 85)
            P.append(Particle(sx + random.uniform(-8, 8), sy + random.uniform(-8, 8), math.cos(a) * spd,
                              math.sin(a) * spd - 25, random.uniform(1.3, 2.6), 10 * scale, (g, g - 4, g - 8),
                              "smoke", grav=-28, drag=1.6, size_end=random.uniform(28, 44) * scale))
        if ground:
            for _ in range(int(14 * scale)):
                c = random.randint(60, 105)
                P.append(Particle(sx, sy - 2, random.uniform(-230, 230), random.uniform(-460, -140),
                                  random.uniform(1.4, 2.8), random.uniform(2, 4.5), (c + 30, c + 10, c - 10),
                                  "debris", grav=900, spin=random.uniform(-12, 12)))
            self.dust_burst(sx, sy, 8, (150, 120, 90))
            self.ground.set_clip(pygame.Rect(0, GROUND_Y - 2, WIDTH, HEIGHT))
            cw = int(70 * scale)
            crater = pygame.transform.smoothscale(self.crater, (cw, int(18 * scale)))
            self.ground.blit(crater, (sx - cw // 2, GROUND_Y - int(6 * scale)))
            self.ground.set_clip(None)

    def dust_burst(self, sx, sy, n, color):
        for _ in range(n):
            self.particles.append(Particle(sx, sy, random.uniform(-110, 110), random.uniform(-70, -5),
                                           random.uniform(0.7, 1.5), 5, color, "smoke", grav=-10, drag=2.5,
                                           size_end=random.uniform(14, 24)))

    # ------------------------------------------------------ tower & fx ----
    def update_tower_fx(self, dt):
        if not self.tower_alive:
            return
        frac = self.tower_hp / TOWER_MAX_HP
        if frac >= 0.6:
            return
        self.tower_emit -= dt
        if self.tower_emit > 0:
            return
        self.tower_emit = 0.05 if frac < 0.3 else 0.12
        sx = ORIGIN_X + random.uniform(-26, 26)
        sy = GROUND_Y - random.uniform(40, 220)
        g = random.randint(40, 70)
        self.particles.append(Particle(sx, sy, random.uniform(-8, 8), random.uniform(-40, -20),
                                       random.uniform(1.5, 2.6), 6, (g, g, g), "smoke", grav=-20, drag=0.4,
                                       size_end=random.uniform(22, 34)))
        if frac < 0.35:
            self.particles.append(Particle(sx, sy, random.uniform(-10, 10), random.uniform(-60, -30),
                                           random.uniform(0.4, 0.8), random.uniform(6, 11),
                                           random.choice(FIRE_COLORS[1:4]), "fire", grav=-40, size_end=1))

    def destroy_tower(self):
        self.tower_alive = False
        self.state = "collapse"
        self.collapse_t = 0.0
        self.sounds.play("gameover", 0.9)
        self.sounds.play("boom", 1.0)
        self.shake = 22
        if self.score > self.highscore:
            self.highscore = self.score
            self.new_high = True
            self.save_highscore()
        self.collapse_events = [(i * 0.28 + random.uniform(0, 0.15), random.uniform(-1.4, 1.4),
                                 random.uniform(1, TOWER_H)) for i in range(8)]
        for _ in range(70):
            sx = ORIGIN_X + random.uniform(-32, 32)
            sy = GROUND_Y - random.uniform(10, 230)
            base = random.randint(115, 165)
            self.particles.append(Particle(sx, sy, random.uniform(-260, 300), random.uniform(-520, -80),
                                           random.uniform(2.5, 4.5), random.uniform(4, 9),
                                           (base, base - 8, base - 24), "debris", grav=900,
                                           spin=random.uniform(-10, 10)))
        rng = random.Random()
        self.rubble = []
        for _ in range(26):
            cx = ORIGIN_X + rng.gauss(0, 26)
            cy = GROUND_Y - abs(rng.gauss(0, 12))
            r = rng.uniform(6, 14)
            pts = [(cx + math.cos(a) * r * rng.uniform(0.6, 1.1), cy + math.sin(a) * r * rng.uniform(0.5, 0.9))
                   for a in [i * math.tau / 6 + rng.uniform(-0.3, 0.3) for i in range(6)]]
            base = rng.randint(105, 150)
            self.rubble.append((pts, (base, base - 8, base - 22)))
        self.shells.clear()

    def update_collapse(self, dt):
        self.collapse_t += dt
        self.zoom += (1.35 - self.zoom) * min(1.0, dt * 3)
        while self.collapse_events and self.collapse_events[0][0] <= self.collapse_t:
            _, x, y = self.collapse_events.pop(0)
            self.explode(x, y, 1, player=False, scale=1.3)
            self.shake = max(self.shake, 14)
        if self.collapse_t < 2.4:
            for _ in range(3):
                self.dust_burst(ORIGIN_X + random.uniform(-50, 50), GROUND_Y - 4, 1, (150, 130, 110))
        if self.collapse_t > 3.4:
            self.state = "over"
            self.over_t = 0.0

    def update_particles(self, dt):
        for p in self.particles:
            p.life -= dt
            if p.drag:
                f = max(0.0, 1 - p.drag * dt)
                p.vx *= f
                p.vy *= f
            p.vy += p.grav * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.rot += p.spin * dt
            if p.kind == "debris" and p.y > p.floor:
                p.y = p.floor
                p.vy = -p.vy * 0.3 if abs(p.vy) > 60 else 0.0
                p.vx *= 0.55
                p.spin *= 0.5
        self.particles = [p for p in self.particles if p.life > 0]
        if len(self.particles) > 1800:
            self.particles = self.particles[-1800:]

    # -------------------------------------------------------------- draw ---
    def draw(self):
        c = self.canvas
        c.blit(self.ground, (0, 0))
        for cl in self.clouds:
            cl["spr"].set_alpha(cl["alpha"])
            c.blit(cl["spr"], (cl["x"], cl["y"]))

        self.draw_last_shot(c)
        if self.state == "play":
            self.draw_preview(c)
        self.draw_tower(c)
        for e in self.enemies:
            self.draw_enemy(c, e)
        for m in self.missiles:
            self.draw_missile(c, m)
        for s in self.shells:
            self.draw_shell(c, s)
        self.draw_particles(c)
        if self.state == "play":
            self.draw_aim(c)
            self.draw_rangefinder(c)
        for ft in self.texts:
            a = 255 * min(1.0, ft.life / (ft.max_life * 0.4))
            draw_text(c, ft.text, ft.fnt, ft.color, (ft.x, ft.y), "center", alpha=a)

        # camera: shake + zoom
        screen.fill((10, 10, 20))
        ox = random.uniform(-self.shake, self.shake)
        oy = random.uniform(-self.shake, self.shake)
        if self.zoom > 1.005:
            w, h = WIDTH / self.zoom, HEIGHT / self.zoom
            fx, fy = ORIGIN_X + 220, GROUND_Y - 170
            rect = pygame.Rect(0, 0, int(w), int(h))
            rect.center = (fx, fy)
            rect.clamp_ip(c.get_rect())
            view = pygame.transform.smoothscale(c.subsurface(rect), (WIDTH, HEIGHT))
            screen.blit(view, (ox, oy))
        else:
            screen.blit(c, (ox, oy))

        screen.blit(self.vignette, (0, 0))
        if self.state == "play" and self.tower_hp < TOWER_MAX_HP * 0.3:
            pulse = 0.55 + 0.45 * math.sin(self.t_real * 6)
            self.red_vignette.set_alpha(int(255 * pulse * (1 - self.tower_hp / (TOWER_MAX_HP * 0.3)) * 0.8 + 40))
            screen.blit(self.red_vignette, (0, 0))

        if self.state == "menu":
            self.draw_menu(screen)
        elif self.state in ("play", "pause"):
            self.draw_hud(screen)
            if self.banner:
                self.draw_banner(screen, self.banner)
            if self.state == "pause":
                self.draw_pause(screen)
        elif self.state == "collapse":
            a = min(255, self.collapse_t * 300)
            draw_text(screen, "THE TOWER IS FALLING!", F_BIG, (255, 90, 70), (WIDTH / 2, 150), "center", alpha=a)
        elif self.state == "over":
            self.draw_over(screen)

    def draw_tower(self, c):
        w, h = self.tower_sprite.get_size()
        left, top = ORIGIN_X - w // 2, GROUND_Y - h
        if not self.tower_alive:
            if self.state == "collapse" and self.collapse_t < 2.4:
                k = min(1.0, self.collapse_t / 2.2)
                sink = k * k * (h + 20)
                tilt = self.collapse_t * 7
                img = pygame.transform.rotate(self.tower_sprite, tilt)
                rect = img.get_rect(center=(ORIGIN_X - tilt * 1.5, GROUND_Y - h / 2 + sink))
                c.set_clip(pygame.Rect(0, 0, WIDTH, GROUND_Y + 4))
                c.blit(img, rect)
                c.set_clip(None)
            for pts, col in self.rubble:
                pygame.draw.polygon(c, col, pts)
                pygame.draw.polygon(c, (70, 64, 58), pts, 1)
            return

        c.blit(self.tower_sprite, (left, top))
        frac = self.tower_hp / TOWER_MAX_HP
        n = int(len(self.cracks) * (1 - frac) + 0.001)
        for pts in self.cracks[:n]:
            pygame.draw.lines(c, (42, 32, 28), False, [(left + x, top + y) for x, y in pts], 2)
        # warm, flickering light in the windows
        flick = 0.75 + 0.25 * math.sin(self.t_real * 13) * math.sin(self.t_real * 7.3)
        for wy in (86, 156):
            pygame.draw.rect(c, (255, 190, 90), (left + 37, top + wy - 8, 4, 16))
            add_glow(c, left + 39, top + wy, 22, (255, 150, 60), 0.6 * flick)
        # waving banner on a pole
        pole_x, pole_top = left + 11, top - 46
        pygame.draw.line(c, (70, 56, 40), (pole_x, top + 2), (pole_x, pole_top), 3)
        pts_top, pts_bot = [], []
        for i in range(9):
            fx = pole_x + 2 + i * 4.5
            wave = math.sin(self.t_real * 6 - i * 0.7) * (i * 0.6)
            pts_top.append((fx, pole_top + 2 + wave))
            pts_bot.append((fx, pole_top + 20 + wave))
        pygame.draw.polygon(c, (40, 80, 180), pts_top + pts_bot[::-1])
        pygame.draw.lines(c, (255, 210, 90), False, [(x, y + 10) for x, y in pts_top[1:-1]], 2)
        if self.tower_flash > 0:
            self.tower_white.set_alpha(int(220 * self.tower_flash / 0.12))
            c.blit(self.tower_white, (left, top))
        self.draw_cannon(c)

    def draw_cannon(self, c):
        px, py = to_screen(*PIVOT)
        pygame.draw.polygon(c, (96, 64, 38), [(px - 17, py + 16), (px + 17, py + 16), (px + 9, py - 2), (px - 9, py - 2)])
        pygame.draw.polygon(c, (60, 40, 24), [(px - 17, py + 16), (px + 17, py + 16), (px + 9, py - 2), (px - 9, py - 2)], 2)
        th = math.radians(self.angle)
        dx, dy = math.cos(th), -math.sin(th)
        nx, ny = -dy, dx
        L = BARREL_LEN * PPM
        r0 = self.recoil
        bx, by = px - dx * (9 + r0), py - dy * (9 + r0)
        ex, ey = px + dx * (L - r0), py + dy * (L - r0)
        body = [(bx + nx * 9, by + ny * 9), (ex + nx * 6.5, ey + ny * 6.5),
                (ex - nx * 6.5, ey - ny * 6.5), (bx - nx * 9, by - ny * 9)]
        pygame.draw.polygon(c, (50, 52, 62), body)
        pygame.draw.line(c, (120, 124, 140), (bx + nx * 5, by + ny * 5), (ex + nx * 3.5, ey + ny * 3.5), 2)
        pygame.draw.line(c, (28, 28, 34), (ex + nx * 8, ey + ny * 8), (ex - nx * 8, ey - ny * 8), 5)
        pygame.draw.line(c, (170, 132, 60), (px - dx * 2 + nx * 9, py - dy * 2 + ny * 9),
                         (px - dx * 2 - nx * 9, py - dy * 2 - ny * 9), 3)
        pygame.draw.circle(c, (40, 40, 48), (int(bx), int(by)), 7)
        pygame.draw.circle(c, (190, 150, 64), (int(px), int(py)), 5)
        if self.reload > 0 and self.state == "play":   # reload ring
            frac = 1 - self.reload / RELOAD_TIME
            rect = pygame.Rect(0, 0, 30, 30)
            rect.center = (px, py + 30)
            pygame.draw.arc(c, (255, 220, 120), rect, math.pi / 2, math.pi / 2 + frac * math.tau, 3)

    def draw_humanoid(self, c, e, sx, sy, s, pal, weapon):
        fl = e.flash > 0

        def C(col):
            return (255, 255, 255) if fl else col

        if e.state == "cheer":
            sy -= abs(math.sin(self.t_real * 9 + e.seed)) * 10
        walking = e.state == "walk"
        swing = math.sin(e.anim) * 7 * s if walking else 0
        lean = pal["lean"] * s
        hip = (sx, sy - 17 * s)
        lw = max(2, int(4 * s))
        pygame.draw.line(c, C(pal["leg_dark"]), hip, (sx + swing, sy), lw)
        pygame.draw.line(c, C(pal["leg"]), hip, (sx - swing, sy), lw)
        body = pygame.Rect(0, 0, int(13 * s), int(17 * s))
        body.midbottom = (sx - lean * 0.5, sy - 15 * s)
        pygame.draw.rect(c, C(pal["body"]), body, border_radius=int(3 * s))
        pygame.draw.line(c, C((50, 36, 30)), (body.left, body.bottom - 4 * s), (body.right, body.bottom - 4 * s), max(1, int(2 * s)))
        hx, hy = sx - lean - s, sy - 36 * s
        pygame.draw.circle(c, C(pal["skin"]), (int(hx), int(hy)), int(5.5 * s))
        pygame.draw.rect(c, C(pal["helmet"]), (hx - 6.5 * s, hy - 7.5 * s, 13 * s, 6.5 * s), border_radius=int(4 * s))
        if e.kind == "brute":
            pygame.draw.polygon(c, C(pal["plume"]), [(hx - 6 * s, hy - 5 * s), (hx - 11 * s, hy - 13 * s), (hx - 3 * s, hy - 7 * s)])
            pygame.draw.polygon(c, C(pal["plume"]), [(hx + 6 * s, hy - 5 * s), (hx + 11 * s, hy - 13 * s), (hx + 3 * s, hy - 7 * s)])
        else:
            pygame.draw.circle(c, C(pal["plume"]), (int(hx + 4 * s), int(hy - 8 * s)), int(3 * s))
        pygame.draw.circle(c, (255, 70, 40), (int(hx - 3 * s), int(hy)), max(1, int(1.4 * s)))

        thrust = math.sin(e.strike_anim / 0.3 * math.pi) * 9 * s if e.strike_anim > 0 else 0
        if e.state == "cheer":
            thrust = 0
        if weapon == "spear":
            a = (sx + 9 * s - thrust, sy - 26 * s)
            b = (sx - 19 * s - thrust, sy - 30 * s)
            if e.state == "cheer":
                a, b = (sx + 4 * s, sy - 20 * s), (sx - 2 * s, sy - 50 * s)
            pygame.draw.line(c, C((120, 86, 52)), a, b, max(2, int(2 * s)))
            ang = math.atan2(b[1] - a[1], b[0] - a[0])
            tip = (b[0] + math.cos(ang) * 7 * s, b[1] + math.sin(ang) * 7 * s)
            pygame.draw.polygon(c, C((200, 204, 214)), [tip, (b[0] + math.cos(ang + 1.6) * 3 * s, b[1] + math.sin(ang + 1.6) * 3 * s),
                                                          (b[0] + math.cos(ang - 1.6) * 3 * s, b[1] + math.sin(ang - 1.6) * 3 * s)])
        elif weapon == "dagger":
            hand = (sx - 7 * s - thrust, sy - 24 * s)
            pygame.draw.line(c, C((210, 214, 224)), hand, (hand[0] - 9 * s, hand[1] - 2 * s), max(2, int(2 * s)))
        elif weapon == "axe":
            swing_a = -1.2 + (math.sin(e.strike_anim / 0.3 * math.pi) * 1.6 if e.strike_anim > 0 else 0)
            if e.state == "cheer":
                swing_a = -1.9
            hand = (sx + 2 * s, sy - 26 * s)
            top = (hand[0] + math.cos(swing_a + math.pi) * 20 * s, hand[1] + math.sin(swing_a + math.pi) * 20 * s)
            pygame.draw.line(c, C((110, 78, 48)), hand, top, max(2, int(3 * s)))
            pygame.draw.circle(c, C((180, 184, 196)), (int(top[0]), int(top[1])), int(5 * s))
            # shield in front
            pygame.draw.rect(c, C((120, 80, 44)), (sx - 15 * s, sy - 34 * s, 7 * s, 22 * s), border_radius=int(2 * s))
            pygame.draw.rect(c, C((170, 170, 180)), (sx - 15 * s, sy - 34 * s, 7 * s, 22 * s), max(1, int(1.5 * s)), border_radius=int(2 * s))

    def draw_enemy(self, c, e):
        sx, sy = to_screen(e.x, e.y)
        fl = e.flash > 0

        def C(col):
            return (255, 255, 255) if fl else col

        if e.kind == "soldier":
            self.draw_humanoid(c, e, sx, sy, 1.0, PALETTES["soldier"], "spear")
        elif e.kind == "runner":
            self.draw_humanoid(c, e, sx, sy, 0.85, PALETTES["runner"], "dagger")
        elif e.kind == "brute":
            self.draw_humanoid(c, e, sx, sy, 1.35, PALETTES["brute"], "axe")
        elif e.kind == "catapult":
            wheel_rot = e.x * PPM / 8
            for wx in (sx - 20, sx + 20):
                pygame.draw.circle(c, C((70, 46, 28)), (int(wx), int(sy - 8)), 8)
                for k in range(3):
                    a = wheel_rot + k * math.pi / 3
                    pygame.draw.line(c, C((110, 76, 44)), (wx - math.cos(a) * 7, sy - 8 - math.sin(a) * 7),
                                     (wx + math.cos(a) * 7, sy - 8 + math.sin(a) * 7), 2)
            pygame.draw.rect(c, C((120, 82, 48)), (sx - 28, sy - 20, 56, 8))
            pygame.draw.line(c, C((104, 70, 40)), (sx - 6, sy - 18), (sx + 4, sy - 40), 5)
            pygame.draw.line(c, C((104, 70, 40)), (sx + 16, sy - 18), (sx + 4, sy - 40), 5)
            ph = e.arm_phase
            f = min(1.0, ph / 0.18) if ph < 0.18 else max(0.0, 1 - (ph - 0.18) / 1.4)
            ang = math.radians(lerp(-18, 118, f))
            pivot = (sx + 4, sy - 32)
            tip = (pivot[0] + math.cos(ang) * 36, pivot[1] - math.sin(ang) * 36)
            tail = (pivot[0] - math.cos(ang) * 8, pivot[1] + math.sin(ang) * 8)
            pygame.draw.line(c, C((150, 104, 60)), tail, tip, 5)
            pygame.draw.circle(c, C((80, 56, 34)), (int(tip[0]), int(tip[1])), 6)
            if f < 0.05 and e.state != "cheer":
                pygame.draw.circle(c, C((130, 126, 120)), (int(tip[0]), int(tip[1] - 3)), 5)
            pygame.draw.rect(c, C((60, 60, 66)), (sx + 18, sy - 34, 12, 14))   # counterweight
            pygame.draw.circle(c, C((200, 180, 60)), (int(pivot[0]), int(pivot[1])), 3)
        elif e.kind == "bomber":
            pygame.draw.line(c, C((70, 56, 44)), (sx - 12, sy + 10), (sx - 8, sy + 16), 1)
            pygame.draw.line(c, C((70, 56, 44)), (sx + 12, sy + 10), (sx + 8, sy + 16), 1)
            pygame.draw.rect(c, C((96, 66, 40)), (sx - 12, sy + 15, 24, 9), border_radius=2)
            pygame.draw.ellipse(c, C((128, 46, 50)), (sx - 36, sy - 14, 72, 28))
            pygame.draw.ellipse(c, C((168, 70, 70)), (sx - 30, sy - 12, 58, 12))
            for k in (-16, 0, 16):
                pygame.draw.line(c, C((96, 34, 40)), (sx + k, sy - 13), (sx + k, sy + 13), 1)
            pygame.draw.polygon(c, C((100, 36, 40)), [(sx + 30, sy), (sx + 46, sy - 14), (sx + 44, sy)])
            pygame.draw.polygon(c, C((100, 36, 40)), [(sx + 30, sy + 2), (sx + 46, sy + 14), (sx + 44, sy + 2)])
            pw = abs(math.sin(e.anim * 9)) * 9 + 1
            pygame.draw.ellipse(c, C((200, 200, 200)), (sx + 46 - pw / 2, sy - 9, pw, 18))
            pygame.draw.circle(c, C((230, 220, 200)), (int(sx - 18), int(sy)), 5)
            pygame.draw.circle(c, (40, 20, 20), (int(sx - 20), int(sy - 1)), 1)
            pygame.draw.circle(c, (40, 20, 20), (int(sx - 16), int(sy - 1)), 1)
            if e.has_bomb:
                pygame.draw.circle(c, C((30, 30, 34)), (int(sx), int(sy + 28)), 5)
                pygame.draw.circle(c, (255, 80, 40), (int(sx), int(sy + 23)), 2)
        elif e.kind == "ram":
            wobble = math.sin(e.anim * 2) * 1.5 if e.state == "walk" else 0
            thrust = math.sin(e.strike_anim / 0.3 * math.pi) * 14 if e.strike_anim > 0 else 0
            lx = sx - 44 - thrust
            pygame.draw.rect(c, C((100, 70, 42)), (lx - 32, sy - 42, 60, 12))
            pygame.draw.polygon(c, C((70, 72, 82)), [(lx - 32, sy - 46), (lx - 46, sy - 36), (lx - 32, sy - 26)])
            pygame.draw.circle(c, (255, 80, 40), (int(lx - 36), int(sy - 38)), 2)
            roof = [(sx - 46, sy - 20 + wobble), (sx + 46, sy - 20 + wobble), (sx + 32, sy - 64 + wobble), (sx - 32, sy - 64 + wobble)]
            pygame.draw.polygon(c, C((92, 60, 36)), roof)
            for k in range(1, 5):
                y = sy - 20 - k * 9 + wobble
                pygame.draw.line(c, C((66, 42, 26)), (sx - 46 + k * 3.2, y), (sx + 46 - k * 3.2, y), 2)
            pygame.draw.polygon(c, C((60, 40, 24)), roof, 2)
            for k in (-30, -10, 10, 30):
                pygame.draw.circle(c, C((150, 150, 160)), (int(sx + k), int(sy - 50 + wobble)), 2)
            pygame.draw.circle(c, C((225, 215, 195)), (int(sx), int(sy - 40 + wobble)), 9)
            pygame.draw.circle(c, (30, 20, 20), (int(sx - 3), int(sy - 42 + wobble)), 2)
            pygame.draw.circle(c, (30, 20, 20), (int(sx + 3), int(sy - 42 + wobble)), 2)
            pygame.draw.line(c, C((70, 56, 40)), (sx + 20, sy - 64), (sx + 20, sy - 94), 3)
            pygame.draw.polygon(c, C((190, 30, 30)), [(sx + 21, sy - 94), (sx + 44, sy - 88 + math.sin(self.t_real * 6) * 3), (sx + 21, sy - 80)])
            wheel_rot = e.x * PPM / 11
            for wx in (sx - 34, sx - 12, sx + 12, sx + 34):
                pygame.draw.circle(c, C((56, 38, 24)), (int(wx), int(sy - 11)), 11)
                pygame.draw.circle(c, C((110, 110, 120)), (int(wx), int(sy - 11)), 11, 2)
                pygame.draw.line(c, C((110, 76, 44)), (wx - math.cos(wheel_rot) * 9, sy - 11 - math.sin(wheel_rot) * 9),
                                 (wx + math.cos(wheel_rot) * 9, sy - 11 + math.sin(wheel_rot) * 9), 2)
        if e.max_hp > 1 and e.state != "cheer":
            x1, y1, x2, y2 = e.box()
            bw = max(30, int((x2 - x1) * PPM))
            bx, by = to_screen(e.x, y2)
            by -= 22 if e.kind == "ram" else 12
            if e.kind == "ram":
                by -= 30
            pygame.draw.rect(c, (20, 20, 20), (bx - bw / 2 - 1, by - 1, bw + 2, 6))
            pygame.draw.rect(c, (230, 60, 50), (bx - bw / 2, by, bw * e.hp / e.max_hp, 4))

    def draw_missile(self, c, m):
        sx, sy = to_screen(m.x, m.y)
        if m.kind == "bomb":
            pygame.draw.circle(c, (30, 30, 36), (int(sx), int(sy)), 6)
            add_glow(c, sx, sy - 5, 12, (255, 120, 40), 0.8)
        else:
            a = m.t * m.spin
            pts = [(sx + math.cos(a + k * 1.26) * 6 * (0.8 + 0.2 * (k % 2)), sy + math.sin(a + k * 1.26) * 6 * (0.8 + 0.2 * (k % 2)))
                   for k in range(5)]
            pygame.draw.polygon(c, (128, 122, 114), pts)
            pygame.draw.polygon(c, (80, 76, 70), pts, 1)

    def draw_shell(self, c, s):
        sx, sy = to_screen(s.x, s.y)
        if sy < -6:   # above the screen: show an altitude marker
            pygame.draw.polygon(c, (255, 230, 150), [(sx, 6), (sx - 7, 18), (sx + 7, 18)])
            draw_text(c, f"{s.y:.0f} m", F_SMALL, (255, 230, 150), (sx, 22), "midtop")
            return
        if s.kind == "rock":
            pygame.draw.circle(c, (120, 114, 106), (int(sx), int(sy)), 6)
            pygame.draw.circle(c, (80, 76, 70), (int(sx), int(sy)), 6, 1)
            return
        add_glow(c, sx, sy, 16, (255, 150, 60), 0.9)
        pygame.draw.circle(c, (30, 30, 34), (int(sx), int(sy)), 5)
        pygame.draw.circle(c, (120, 120, 130), (int(sx - 1), int(sy - 2)), 2)
        if self.show_vectors and s is self.newest_shell():
            vx, vy = s.vx, s.vy()
            k = 2.2
            arrow(c, (90, 220, 255), (sx, sy), (sx + vx * k, sy), 2, 7)
            arrow(c, (255, 110, 200), (sx, sy), (sx, sy - vy * k), 2, 7)

    def newest_shell(self):
        for s in reversed(self.shells):
            if s.kind == "shell":
                return s
        return None

    def draw_particles(self, c):
        for p in self.particles:
            k = 1 - p.life / p.max_life
            size = p.size + (p.size_end - p.size) * k
            if p.kind == "fire":
                idx = min(len(FIRE_COLORS) - 1, int(k * len(FIRE_COLORS)))
                add_soft(c, p.x, p.y, size, FIRE_COLORS[idx], 255 * (1 - k * 0.6))
            elif p.kind == "smoke":
                add_soft(c, p.x, p.y, size, p.color, 150 * (1 - k))
            elif p.kind == "spark":
                pygame.draw.line(c, p.color, (p.x, p.y), (p.x - p.vx * 0.025, p.y - p.vy * 0.025), 2)
            elif p.kind == "flash":
                add_glow(c, p.x, p.y, size * (1 + k * 0.4), p.color, (1 - k) ** 1.5)
            elif p.kind == "ring":
                r = int(size)
                if r > 1:
                    ring = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
                    pygame.draw.circle(ring, (*p.color, int(200 * (1 - k))), (r + 2, r + 2), r, max(1, int(5 * (1 - k))))
                    c.blit(ring, (p.x - r - 2, p.y - r - 2))
            elif p.kind == "debris":
                hs = size * min(1.0, p.life / 0.4)
                ca, sa = math.cos(p.rot), math.sin(p.rot)
                pts = [(p.x + ca * dx - sa * dy, p.y + sa * dx + ca * dy)
                       for dx, dy in ((-hs, -hs * 0.6), (hs, -hs * 0.6), (hs, hs * 0.6), (-hs, hs * 0.6))]
                pygame.draw.polygon(c, p.color, pts)

    def draw_aim(self, c):
        px, py = to_screen(*PIVOT)
        th = math.radians(self.angle)
        dashed_line(c, (230, 230, 240), (px, py), (px + 75, py), 5, 4)
        rect = pygame.Rect(0, 0, 100, 100)
        rect.center = (px, py)
        a0, a1 = (0, th) if th >= 0 else (th, 0)
        if abs(th) > 0.01:
            pygame.draw.arc(c, (255, 220, 120), rect, a0, a1, 2)
        draw_text(c, f"θ={self.angle:.1f}°", F_MONO_B, (255, 220, 120),
                  (px + 80, py + (6 if th >= 0 else -6)), "topleft" if th >= 0 else "bottomleft")
        if not self.show_vectors:
            return
        mx, my = to_screen(*self.muzzle())
        k = 3.0
        vx, vy = self.v0 * math.cos(th) * k, self.v0 * math.sin(th) * k
        dashed_line(c, (90, 220, 255), (mx + vx, my), (mx + vx, my - vy), 4, 4)
        dashed_line(c, (255, 110, 200), (mx, my - vy), (mx + vx, my - vy), 4, 4)
        arrow(c, (90, 220, 255), (mx, my), (mx + vx, my), 2, 8)
        arrow(c, (255, 110, 200), (mx, my), (mx, my - vy), 2, 8)
        arrow(c, (255, 250, 230), (mx, my), (mx + vx, my - vy), 3, 11)
        draw_text(c, "v₀x", F_SMALL, (90, 220, 255), (mx + vx / 2, my + 4), "midtop")
        draw_text(c, "v₀y", F_SMALL, (255, 110, 200), (mx - 4, my - vy / 2), "midright")
        draw_text(c, f"v₀={self.v0:.1f} m/s", F_MONO_B, (255, 250, 230), (mx + vx + 6, my - vy - 6), "bottomleft")

    def draw_preview(self, c):
        if self.assist == 2:
            return
        mx, my, vx, vy, T, H, R = self.predict()
        limit = T if self.assist == 0 else T * 0.3
        step = 0.06
        n = max(1, int(limit / step))
        for i in range(1, n + 1):
            t = i * step
            sx, sy = to_screen(mx + vx * t, my + vy * t - 0.5 * G * t * t)
            if sx > WIDTH + 10:
                break
            fade = 1.0 if self.assist == 0 else 1 - i / (n + 1)
            DOT.set_alpha(int(220 * fade))
            c.blit(DOT, (sx - 3, sy - 3))
        if self.assist == 0:
            if vy > 0:
                ta = vy / G
                ax, ay = to_screen(mx + vx * ta, H)
                pygame.draw.polygon(c, (255, 230, 150), [(ax, ay - 6), (ax + 5, ay), (ax, ay + 6), (ax - 5, ay)])
                draw_text(c, f"H={H:.1f} m", F_SMALL, (255, 230, 150), (ax, ay - 9), "midbottom")
            lx, ly = to_screen(R, 0)
            if lx < WIDTH:
                pygame.draw.line(c, (255, 120, 90), (lx - 6, ly - 6), (lx + 6, ly + 6), 3)
                pygame.draw.line(c, (255, 120, 90), (lx - 6, ly + 6), (lx + 6, ly - 6), 3)
                draw_text(c, f"R={R:.1f} m", F_SMALL, (255, 180, 150), (lx, ly - 12), "midbottom")

    def draw_last_shot(self, c):
        ls = self.last_shot
        if not ls or self.state not in ("play", "pause"):
            return
        pts = ls["pts"]
        for i in range(0, len(pts) - 1, 2):
            pygame.draw.line(c, (255, 226, 160), pts[i], pts[i + 1], 1)
        ax, ay = ls["apex"]
        sax, say = to_screen(ax, ay)
        if say > 0:
            dashed_line(c, (255, 226, 160), (sax, say), (sax, GROUND_Y), 3, 5)
            pygame.draw.circle(c, (255, 226, 160), (int(sax), int(say)), 3)
            draw_text(c, f"H = {ay:.1f} m", F_SMALL, (255, 226, 160), (sax + 6, say - 4), "bottomleft")
        lx, ly = to_screen(*ls["land"])
        if lx < WIDTH - 40 and ls["ground"]:
            draw_text(c, f"R = {ls['land'][0]:.1f} m", F_SMALL, (255, 226, 160), (lx, ly + 4), "midtop", alpha=200)

    def draw_rangefinder(self, c):
        ground = [e for e in self.enemies if e.kind != "bomber" and e.x < FIELD_END]
        shown = []
        if ground:
            shown.append(min(ground, key=lambda en: en.x))
        mx, my = to_world(*pygame.mouse.get_pos())
        for e in self.enemies:
            if dist_to_box(mx, my, e.box()) < 0.6 and e not in shown:
                shown.append(e)
        for e in shown:
            x1, y1, x2, y2 = e.box()
            sx, sy = to_screen(e.x, y2)
            label = f"d={e.x:.1f} m" + (f"  alt={e.y:.1f} m" if e.kind == "bomber" else "")
            pygame.draw.polygon(c, (140, 255, 170), [(sx, sy - 4), (sx - 5, sy - 11), (sx + 5, sy - 11)])
            draw_text(c, label, F_SMALL, (140, 255, 170), (sx, sy - 13 - (8 if e.max_hp > 1 else 0)), "midbottom")

    # ---------------------------------------------------------------- HUD ---
    def draw_hud(self, s):
        if self.show_panel:
            self.draw_physics_panel(s)

        # tower integrity bar
        frac = self.tower_hp / TOWER_MAX_HP
        bw, bh = 380, 20
        bx, by = WIDTH / 2 - bw / 2, 20
        s.blit(panel(bw + 20, 58), (bx - 10, 8))
        col = gradient([(0.0, (230, 50, 40)), (0.4, (240, 190, 50)), (1.0, (90, 220, 110))], frac)
        pygame.draw.rect(s, (30, 20, 20), (bx, by + 18, bw, bh), border_radius=6)
        if frac > 0:
            pygame.draw.rect(s, col, (bx, by + 18, bw * frac, bh), border_radius=6)
        if self.tower_flash > 0:
            pygame.draw.rect(s, (255, 255, 255), (bx, by + 18, bw * frac, bh), border_radius=6)
        pygame.draw.rect(s, (255, 255, 255), (bx, by + 18, bw, bh), 1, border_radius=6)
        draw_text(s, "TOWER INTEGRITY", F_UI_SMALL, (230, 230, 240), (bx, by - 4))
        draw_text(s, f"{self.tower_hp:.0f} / {TOWER_MAX_HP}", F_UI_SMALL, (230, 230, 240), (bx + bw, by - 4), "topright")

        # score block
        s.blit(panel(250, 128), (WIDTH - 264, 8))
        draw_text(s, f"{self.score:,}", F_POP_BIG, (255, 226, 130), (WIDTH - 24, 12), "topright")
        draw_text(s, f"WAVE {self.wave}", F_UI, (255, 255, 255), (WIDTH - 250, 64))
        left = len(self.spawn_queue) + len(self.enemies)
        draw_text(s, f"enemies: {left}", F_UI_SMALL, (200, 200, 220), (WIDTH - 24, 67), "topright")
        draw_text(s, f"best {self.highscore:,}", F_UI_SMALL, (170, 170, 200), (WIDTH - 250, 96))
        draw_text(s, f"assist {ASSIST_NAMES[self.assist]}  x{ASSIST_MULT[self.assist]}", F_UI_SMALL,
                  (140, 255, 170), (WIDTH - 24, 96), "topright")

        # wall drop cooldown
        x, y = 16, HEIGHT - 66
        ready = self.drop_cd <= 0
        s.blit(panel(220, 34, 150), (x, y))
        txt = "[F] WALL DROP  ready" if ready else f"[F] WALL DROP  {self.drop_cd:.1f}s"
        draw_text(s, txt, F_MONO_B, (140, 255, 170) if ready else (170, 170, 180), (x + 12, y + 8))

        if self.next_wave_timer is not None and self.wave > 0 and not self.banner:
            draw_text(s, f"next wave in {math.ceil(self.next_wave_timer)}", F_UI, (255, 255, 255), (WIDTH / 2, 110), "center")

        help_txt = ("Mouse/W S: angle   Wheel/A D: speed   Shift: fine   Click/SPACE: fire   RMB/F: wall drop   "
                    "T: assist   V: vectors   H: panel   P: pause   M: mute")
        draw_text(s, help_txt, F_SMALL, (225, 215, 200), (WIDTH / 2, HEIGHT - 8), "midbottom", alpha=200)

    def draw_physics_panel(self, s):
        x0, y0 = 14, 12
        s.blit(panel(372, 272), (x0, y0))
        mx, my, vx, vy, T, H, R = self.predict()
        x, y = x0 + 14, y0 + 10
        lh = 19
        draw_text(s, "PROJECTILE MOTION", F_MONO_B, (255, 214, 110), (x, y), shadow=False)
        draw_text(s, f"g = {G} m/s²", F_MONO, (200, 200, 220), (x0 + 358, y), "topright", shadow=False)
        y += lh + 4
        rows = [
            (f"θ   = {self.angle:6.1f}°", (255, 220, 120)),
            (f"v₀  = {self.v0:6.1f} m/s", (255, 250, 230)),
            (f"v₀x = v₀·cosθ = {vx:6.2f} m/s", (90, 220, 255)),
            (f"v₀y = v₀·sinθ = {vy:6.2f} m/s", (255, 110, 200)),
            (f"h₀  = {my:6.2f} m  (launch height)", (220, 220, 230)),
        ]
        for text, col in rows:
            draw_text(s, text, F_MONO, col, (x, y), shadow=False)
            y += lh
        pygame.draw.line(s, (255, 255, 255, 60), (x, y + 3), (x0 + 358, y + 3))
        y += 9
        if self.assist == 2:
            draw_text(s, "PHYSICIST MODE - predictions hidden", F_MONO_B, (140, 255, 170), (x, y), shadow=False)
            y += lh
            draw_text(s, "solve  h₀ + v₀y·t − ½gt² = 0  for T,", F_MONO, (200, 200, 220), (x, y), shadow=False)
            y += lh
            draw_text(s, "then  R = x₀ + v₀x·T", F_MONO, (200, 200, 220), (x, y), shadow=False)
            y += lh
        else:
            draw_text(s, f"T = {T:5.2f} s   time of flight", F_MONO, (230, 230, 240), (x, y), shadow=False)
            y += lh
            draw_text(s, f"H = {H:5.2f} m   max height", F_MONO, (230, 230, 240), (x, y), shadow=False)
            y += lh
            draw_text(s, f"R = {R:5.2f} m   range (from tower)", F_MONO, (230, 230, 240), (x, y), shadow=False)
            y += lh
        pygame.draw.line(s, (255, 255, 255, 60), (x, y + 3), (x0 + 358, y + 3))
        y += 9
        sh = self.newest_shell()
        if sh:
            draw_text(s, f"SHELL t={sh.t:4.2f}s  x={sh.x:5.1f}m  y={sh.y:5.1f}m", F_MONO, (255, 226, 160), (x, y), shadow=False)
            y += lh
            draw_text(s, f"      vx={sh.vx:+6.2f}  vy={sh.vy():+6.2f} m/s", F_MONO, (255, 226, 160), (x, y), shadow=False)
            y += lh
            draw_text(s, "      vx stays constant, vy = v₀y − g·t", F_SMALL, (170, 170, 190), (x, y), shadow=False)
        elif self.last_shot:
            ls = self.last_shot
            draw_text(s, f"LAST  θ={ls['angle']:.1f}°  v₀={ls['v0']:.1f} m/s", F_MONO, (255, 226, 160), (x, y), shadow=False)
            y += lh
            draw_text(s, f"      R={ls['land'][0]:.1f} m  T={ls['T']:.2f} s  H={ls['apex'][1]:.1f} m",
                      F_MONO, (255, 226, 160), (x, y), shadow=False)
            y += lh
            acc = 100 * self.hits / self.shots if self.shots else 0
            draw_text(s, f"      shots {self.shots}   accuracy {acc:.0f}%", F_SMALL, (170, 170, 190), (x, y), shadow=False)
        else:
            draw_text(s, "x = x₀ + v₀x·t", F_MONO, (200, 200, 220), (x, y), shadow=False)
            y += lh
            draw_text(s, "y = h₀ + v₀y·t − ½·g·t²", F_MONO, (200, 200, 220), (x, y), shadow=False)

    def draw_banner(self, s, b):
        t = b.t
        alpha = 255 * min(1.0, t / 0.15, (b.duration - t) / 0.4)
        pop = 1 + max(0.0, 0.5 - t * 2.5)
        img = F_BIG.render(b.title, True, b.color)
        if pop > 1.001:
            img = pygame.transform.smoothscale(img, (int(img.get_width() * pop), int(img.get_height() * pop)))
        rect = img.get_rect(center=(WIDTH / 2, 190))
        add_glow(s, WIDTH / 2, 190, 200, (b.color[0] // 3, b.color[1] // 3, b.color[2] // 3), alpha / 255)
        sh = F_BIG.render(b.title, True, (0, 0, 0))
        if pop > 1.001:
            sh = pygame.transform.smoothscale(sh, img.get_size())
        sh.set_alpha(int(alpha * 0.6))
        s.blit(sh, rect.move(4, 4))
        img.set_alpha(int(alpha))
        s.blit(img, rect)
        draw_text(s, b.subtitle, F_UI, (255, 255, 255), (WIDTH / 2, 250), "center", alpha=alpha)

    def draw_menu(self, s):
        dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        dim.fill((8, 10, 24, 90))
        s.blit(dim, (0, 0))
        bob = math.sin(self.t_real * 1.6) * 4
        add_glow(s, WIDTH / 2, 130, 320, (120, 70, 30), 0.9)
        draw_text(s, "PROJECTILE SIEGE", F_TITLE, (255, 214, 110), (WIDTH / 2, 120 + bob), "center")
        draw_text(s, "a Physics 101 projectile-motion defense game", F_UI, (235, 225, 240), (WIDTH / 2, 190), "center")

        w, h = 640, 262
        px, py = WIDTH / 2 - w / 2, 232
        s.blit(panel(w, h, 190), (px, py))
        x, y = px + 26, py + 18
        draw_text(s, "THE PHYSICS", F_MONO_B, (255, 214, 110), (x, y), shadow=False)
        lines = [
            "v₀x = v₀·cosθ          (constant - no air drag)",
            "v₀y = v₀·sinθ          vy = v₀y − g·t",
            "x = x₀ + v₀x·t          y = h₀ + v₀y·t − ½·g·t²",
        ]
        y += 24
        for ln in lines:
            draw_text(s, ln, F_MONO, (215, 215, 235), (x, y), shadow=False)
            y += 20
        y += 12
        draw_text(s, "THE MISSION", F_MONO_B, (255, 214, 110), (x, y), shadow=False)
        y += 24
        for ln in ["Enemies march on your tower. If they destroy it, the game is over.",
                   "Set the launch angle θ and launch speed v₀, then fire.",
                   "Shoot stones and bombs out of the air. Drop rocks on anyone at the wall.",
                   f"Trajectory assist [T]: {ASSIST_NAMES[self.assist]}  (score x{ASSIST_MULT[self.assist]})"
                   "  - turn it OFF and do the math!"]:
            draw_text(s, ln, F_UI_SMALL, (225, 225, 240), (x, y), shadow=False)
            y += 22
        blink = 155 + 100 * math.sin(self.t_real * 4)
        draw_text(s, "PRESS ENTER OR CLICK TO DEFEND THE TOWER", F_POP, (255, 255, 255), (WIDTH / 2, py + h + 40), "center", alpha=blink)
        draw_text(s, f"best score {self.highscore:,}", F_UI_SMALL, (200, 200, 220), (WIDTH / 2, py + h + 72), "center")
        draw_text(s, "F11 fullscreen   M mute   ESC quit", F_SMALL, (200, 190, 180), (WIDTH / 2, HEIGHT - 8), "midbottom")

    def draw_pause(self, s):
        dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        dim.fill((6, 8, 20, 160))
        s.blit(dim, (0, 0))
        draw_text(s, "PAUSED", F_BIG, (255, 214, 110), (WIDTH / 2, HEIGHT / 2 - 60), "center")
        draw_text(s, "P / ESC  resume        Q  quit to menu", F_UI, (230, 230, 240), (WIDTH / 2, HEIGHT / 2 + 10), "center")

    def draw_over(self, s):
        a = min(1.0, self.over_t / 0.8)
        dim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        dim.fill((20, 4, 8, int(170 * a)))
        s.blit(dim, (0, 0))
        alpha = 255 * a
        draw_text(s, "THE TOWER HAS FALLEN", F_BIG, (255, 90, 70), (WIDTH / 2, 120), "center", alpha=alpha)
        if self.over_t < 0.4:
            return
        w, h = 520, 330
        px, py = WIDTH / 2 - w / 2, 185
        s.blit(panel(w, h, 200), (px, py))
        draw_text(s, f"{self.score:,}", F_BIG, (255, 226, 130), (WIDTH / 2, py + 50), "center")
        if self.new_high:
            glow = 180 + 75 * math.sin(self.t_real * 6)
            draw_text(s, "NEW HIGH SCORE!", F_POP, (140, 255, 170), (WIDTH / 2, py + 100), "center", alpha=glow)
        else:
            draw_text(s, f"best {self.highscore:,}", F_UI, (200, 200, 220), (WIDTH / 2, py + 100), "center")
        acc = 100 * self.hits / self.shots if self.shots else 0
        stats = [
            ("Waves survived", f"{max(0, self.wave - 1)}  (fell on wave {self.wave})"),
            ("Enemies destroyed", f"{self.kills}"),
            ("Shots fired / accuracy", f"{self.shots}  /  {acc:.0f}%"),
            ("Projectiles intercepted", f"{self.intercepts}"),
            ("Longest shot (range)", f"{self.longest:.1f} m"),
            ("Highest arc (max height)", f"{self.highest:.1f} m"),
        ]
        y = py + 132
        for label, val in stats:
            draw_text(s, label, F_UI_SMALL, (200, 200, 220), (px + 40, y), shadow=False)
            draw_text(s, val, F_MONO_B, (255, 255, 255), (px + w - 40, y + 2), "topright", shadow=False)
            y += 28
        if self.over_t > 1.0:
            blink = 155 + 100 * math.sin(self.t_real * 4)
            draw_text(s, "R / ENTER  rebuild the tower        ESC  menu", F_UI, (255, 255, 255),
                      (WIDTH / 2, py + h + 34), "center", alpha=blink)


if __name__ == "__main__":
    Game().run()
    pygame.quit()
