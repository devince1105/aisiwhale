# Tifa, Animal Crossing style (D-198): clean low-poly parts, every detail painted. Needs lib.py and
# figure.py. Measured from avatars-source/q/Tifa.jpg (front), back/tifa.jpg and stand-side/tifa.jpg:
# 0.60 tall, chin at 0.345, eyes at 0.437, shoulders 0.325, belt 0.236, hem 0.158, boot tops 0.10.
reset("tifa")
PARTS.clear()

SKIN, HAIR = "#F8C6A2", "#42353A"
TOP, TRIM, STRAP = "#F2EEEC", "#3A3234", "#322C2F"
GUARD, BAND, RED, RED_LIGHT, RED_DARK = "#37333B", "#2E2A30", "#A32A2A", "#BC3F3A", "#7A1E21"
SKIRT, SOCK, SOLE, METAL = "#37302F", "#3A2F30", "#352B2A", "#B6B4BE"
LINE, IRIS, WHITE, LID, BROW = "#46302A", "#5E4336", "#FAF4EF", "#F2AD9C", "#5A3E32"
STEEL = Canvas("steel", 0.02, 0.02, 800, "#D5D2D8")

# ---- head ---------------------------------------------------------------------------------------------
HEAD_Y = 0.02
head = surface("head", [ring((0, HEAD_Y, z), rx, ry, 24, power=p) for z, rx, ry, p in [
    (0.350, .066, .070, 2.6), (0.360, .087, .091, 2.6), (0.378, .098, .101, 2.5), (0.400, .1015, .104, 2.4), (0.425, .102, .105, 2.35),
    (0.455, .100, .104, 2.35), (0.490, .095, .100, 2.35), (0.520, .088, .093, 2.35), (0.548, .074, .079, 2.35), (0.568, .050, .054, 2.35)]],
    start=(0, HEAD_Y, 0.345), end=(0, HEAD_Y, 0.580))
FX, FZ, FW, FH = -0.115, 0.335, 0.23, 0.29             # the face canvas: the front of the head, and a strip above
planar_front(head, FX, FZ, FW, FH, wrap=(0.83, 0.99))  # for the rest of the head, unrolled
face = Canvas("face", FW, FH, 3400, SKIN)
fx, fz = (lambda x: x - FX), (lambda z: z - FZ)


def eye(cx, cz, outer):
    """An Animal Crossing eye, as in the reference: a round white ringed in dark brown - heavy over
    the top and down her right of it, fine elsewhere - with a tall iris pushed to her left (she
    glances that way), two thick lashes at the outer corner and a blush of pink over the lid."""
    a, b = 0.0235, 0.0232
    X, Y = face.X - fx(cx), face.Y - fz(cz)
    e = face.ellipse(fx(cx), fz(cz), a, b)
    ang = np.degrees(np.arctan2(Y / b, X / a)) % 360       # 0 = toward her left, 90 = up
    face.put(LID, 0.55 * np.clip(np.sin(np.radians(ang)), 0, 1) ** 0.8 * np.clip(1 - e / 0.0065, 0, 1) * (e > 0))
    face.fill(WHITE, e)
    iris = np.maximum(face.ellipse(fx(cx + 0.0070), fz(cz - 0.0005), 0.0152, 0.0222), e)
    face.fill(IRIS, iris)
    face.put(LINE, 0.35 * face.cover(iris) * np.clip(Y / b, 0, 1))          # the lid's shadow on the iris
    t = np.interp(ang, [0, 45, 90, 135, 180, 215, 250, 270, 315, 360],
                  [0.0011, 0.0022, 0.0027, 0.0027, 0.0024, 0.0016, 0.0008, 0.0005, 0.0006, 0.0011])
    face.fill(LINE, np.abs(e) - t)
    for at, tilt, length in ((36, 26, 0.0115), (9, -8, 0.0075)):
        th = math.radians(at if outer > 0 else 180 - at)
        d = math.radians(tilt if outer > 0 else 180 - tilt)
        bx, bz = fx(cx) + a * math.cos(th), fz(cz) + b * math.sin(th)
        face.fill(LINE, face.stroke([(bx - math.cos(d) * 0.003, bz - math.sin(d) * 0.003),
                                     (bx + math.cos(d) * length, bz + math.sin(d) * length)], 0.0023, 0.0009))
    face.fill(BROW, face.stroke([(fx(cx - 0.0165), fz(cz + 0.0375)), (fx(cx), fz(cz + 0.0425)), (fx(cx + 0.0165), fz(cz + 0.039))],
                                0.0014, 0.0015, 0.0027))


for s in (1, -1):
    eye(s * 0.055, 0.437, s)
    bx, bz = fx(s * 0.074), fz(0.392)
    face.put("#F4A090", 0.5 * np.clip(1 - np.hypot((face.X - bx) / 0.021, (face.Y - bz) / 0.012), 0, 1) ** 1.3)
    for k in (-1, 0, 1):
        hx = bx + k * 0.0068
        face.fill("#EE8F84", face.stroke([(hx - 0.0026, bz - 0.0052), (hx + 0.0026, bz + 0.0052)], 0.0008), alpha=0.7)
face.fill("#6E3A28", face.stroke([(fx(-0.0245), fz(0.4025)), (fx(-0.014), fz(0.3935)), (fx(0), fz(0.3900)),
                                  (fx(0.014), fz(0.3935)), (fx(0.0245), fz(0.4025))], 0.0019))
part(head, face, "head")

ear = ellipsoid("ear-l", (0.110, 0.040, 0.414), (0.034, 0.019, 0.034), 8, 6)
lobe = Canvas("ear", 0.06, 0.06, 2000, SKIN)
lobe.fill("#E6A27C", np.abs(lobe.ellipse(0.75 * lobe.width, 0.5 * lobe.height, 0.0050, 0.0150)) - 0.0012, soft=0.001)   # the fold inside
part(ear, lobe, "head")
part(mirror(ear, "ear-r"), lobe, "head")
ring_l = surface("earring-l", [ring((0.127, 0.038, z), 0.0048, 0.0034, 4) for z in (0.353, 0.378)],
                 start=(0.127, 0.038, 0.352), end=(0.127, 0.038, 0.380))
part(ring_l, STEEL, "head")
part(mirror(ring_l, "earring-r"), STEEL, "head")
nose_c = Canvas("nose", 0.03, 0.02, 2000, "#F6894B")
nose_c.shade(0.93 + 0.16 * nose_c.Y / nose_c.height)                     # lighter on top
part(ellipsoid("nose", (0, HEAD_Y - 0.1055, 0.417), (0.0125, 0.0085, 0.0068), 8, 5), nose_c, "head")

# ---- torso and neck ---------------------------------------------------------------------------------
TORSO = [(0.190, .050, .042, .022), (0.215, .047, .040, .020), (0.236, .0455, .038, .018), (0.250, .046, .039, .016),
         (0.272, .049, .044, .011), (0.295, .050, .044, .012), (0.312, .047, .040, .014), (0.322, .034, .030, .014),
         (0.330, .021, .021, .010), (0.352, .0185, .0185, .006)]
torso = surface("torso", [ring((0, cy, z), rx, ry, 16) for z, rx, ry, cy in TORSO], start=(0, .022, 0.186), end=(0, .006, 0.354))
body = Canvas("torso", 2 * math.pi * 0.047, 0.19, 2300, SKIN)
y_of, Z = along(torso, [p[0] for p in TORSO], body)
DEG = (body.X / body.width - 0.5) * 360                                   # 0 = front, + toward her left
xd = lambda deg: (0.5 + deg / 360) * body.width
# the cropped tank: its upper edge scoops at the front, climbs to the straps, dips under the arms
edge = np.interp(np.abs(DEG), [0, 12, 22, 30, 36, 46, 56, 90, 124, 134, 146, 154, 166, 180],
                 [.304, .305, .309, .318, .326, .326, .305, .282, .305, .326, .326, .322, .319, .318])
body.fill(TOP, np.maximum(0.2515 - Z, Z - edge))
slope = np.gradient(edge, axis=1) / body.px
body.fill(TRIM, np.where(edge < 0.3255, np.abs(Z - edge) / np.sqrt(1 + slope ** 2) - 0.0019, 1.0))   # not over the shoulder
body.fill(TRIM, body.band(y_of(0.2495), y_of(0.2535)))
body.fill("#D98F6A", body.ellipse(xd(0), y_of(0.2425), 0.0015, 0.003), alpha=0.9)   # navel
for s in (1, -1):
    # suspenders: up the front, over the shoulder, down the back; a buckle above the belt on each run
    body.fill(STRAP, body.stroke([(xd(s * 38), y_of(0.236)), (xd(s * 38), y_of(0.275)), (xd(s * 40), y_of(0.303)),
                                  (xd(s * 55), y_of(0.317)), (xd(s * 90), y_of(0.3245)), (xd(s * 125), y_of(0.317)),
                                  (xd(s * 140), y_of(0.303)), (xd(s * 142), y_of(0.275)), (xd(s * 142), y_of(0.236))], 0.0044))
    for d in (38, 142):
        x, y = xd(s * d), y_of(0.2445)
        body.fill(METAL, body.box(x - 0.0056, y - 0.0066, x + 0.0056, y + 0.0066, 0.001))
        body.fill(STRAP, body.box(x - 0.003, y - 0.0038, x + 0.003, y + 0.0038, 0.0005))
part(torso, body, "torso")

# ---- arms (rest pose: straight out; the shoulder end stays with the torso, the rest follows the arm bone)
ARM = [(0.048, .0165, .0165), (0.062, .0195, .0195), (0.080, .0185, .0185), (0.1000, .0175, .0175),
       (0.1005, .0200, .0200), (0.122, .0206, .0206), (0.1440, .0214, .0214), (0.1445, .0275, .0268),
       (0.1575, .0282, .0274), (0.1580, .0290, .0282), (0.1700, .0290, .0282), (0.1705, .0280, .0270),
       (0.1860, .0276, .0262), (0.1865, .0245, .0225), (0.202, .0238, .0215), (0.210, .0180, .0162)]
AY, AZ = 0.017, 0.292
arm_l = surface("arm-l", [ring((x, AY, AZ), ry, rz, 12, plane="YZ", power=2.2) for x, ry, rz in ARM],
                start=(0.040, AY, AZ), end=(0.2155, AY, AZ))
sleeve = Canvas("arm", 2 * math.pi * 0.024, 0.176, 3200, SKIN)
y_of, _ = along(arm_l, [p[0] for p in ARM], sleeve)
top = 0.5 * sleeve.width                                                  # u = 0.5 is the top of the arm
sleeve.fill(GUARD, sleeve.band(y_of(0.1005), y_of(0.1445)))
sleeve.fill("#4D4853", sleeve.band(y_of(0.1005), y_of(0.1005) + 0.0012))
sleeve.fill(BAND, sleeve.band(y_of(0.105), y_of(0.111)))                  # a strap round the top of the guard
sleeve.fill(METAL, sleeve.box(top - 0.0042, y_of(0.104), top + 0.0042, y_of(0.112), 0.0008))
sleeve.fill(RED, sleeve.box(top - 0.0075, y_of(0.118), top + 0.0075, y_of(0.136), 0.0018))   # the red plate
sleeve.fill(RED_DARK, np.abs(sleeve.box(top - 0.0075, y_of(0.118), top + 0.0075, y_of(0.136), 0.0018)) - 0.0006)
sleeve.fill(RED, sleeve.band(y_of(0.1445), y_of(0.1578)))                 # the glove's cuff
sleeve.fill(RED_LIGHT, sleeve.band(y_of(0.1445), y_of(0.1445) + 0.0016))
sleeve.fill(BAND, sleeve.band(y_of(0.1578), y_of(0.1702)))                # the black band with its stud
sleeve.fill("#5E5B66", sleeve.ellipse(top, y_of(0.164), 0.0056, 0.0056))
sleeve.fill(METAL, sleeve.ellipse(top, y_of(0.164), 0.0044, 0.0044))
sleeve.fill("#F1F0F4", sleeve.ellipse(top - 0.0012, y_of(0.164) + 0.0012, 0.0014, 0.0014))
sleeve.fill(RED, sleeve.band(y_of(0.1702), y_of(0.1863)))                 # the glove over the hand
sleeve.fill(RED_DARK, sleeve.band(y_of(0.1848), y_of(0.1863)))
for u in (0.34, 0.45, 0.56, 0.67):                                        # between the fingers
    sleeve.fill("#DDA07E", sleeve.stroke([(u * sleeve.width, y_of(0.190)), (u * sleeve.width, y_of(0.209))], 0.0008))
arm_w = lambda side: (lambda co: {f"arm-{side}": smooth(0.062, 0.100, abs(co.x)), "torso": 1 - smooth(0.062, 0.100, abs(co.x))})
part(arm_l, sleeve, arm_w("left"))
part(mirror(arm_l, "arm-r"), sleeve, arm_w("right"))
thumb = ellipsoid("thumb-l", (0.184, AY - 0.024, AZ + 0.004), (0.011, 0.010, 0.010), 6, 4)
knuckle = Canvas("thumb", 0.03, 0.03, 1000, SKIN)
part(thumb, knuckle, "arm-left")
part(mirror(thumb, "thumb-r"), knuckle, "arm-right")

# ---- skirt: a yoke, then knife pleats that open toward the hem -----------------------------------------
PLEATS = 10
SKIRT_Z = [(0.158, .088, .078, .021, .0050), (0.186, .079, .070, .020, .0040), (0.2135, .0605, .0525, .019, .0012),
           (0.2140, .0600, .0520, .019, 0), (0.2385, .0495, .0425, .018, 0)]
rows = []
for z, rx, ry, cy, amp in SKIRT_Z:
    row = ring((0, cy, z), rx, ry, PLEATS * 4)
    for i, p in enumerate(row):          # each pleat slopes in across its face, then steps out to the next
        k = 1 + amp * (1, 0.33, -0.33, -1)[i % 4] / rx
        p.x, p.y = p.x * k, cy + (p.y - cy) * k
    rows.append(row)
skirt = surface("skirt", rows)
cloth = Canvas("skirt", 2 * math.pi * 0.07, 0.10, 2000, SKIRT)
y_of, Z = along(skirt, [p[0] for p in SKIRT_Z], cloth)
t = (cloth.X / cloth.width * PLEATS) % 1
cloth.shade(np.where(Z < 0.2137, np.where(t < 0.75, 1.14 - 0.26 * t / 0.75, 0.62), 1.0))
cloth.fill("#413739", cloth.band(y_of(0.214), cloth.height))              # the yoke
for z in (0.2165, 0.2365):
    cloth.fill("#5A4C4E", cloth.band(y_of(z) - 0.0005, y_of(z) + 0.0005))


def skirt_w(co):
    """The front of the hem follows the legs (so it lifts over the thighs when she sits and swings
    when she walks); the yoke and the back stay with the torso."""
    k = 0.6 * smooth(0.214, 0.158, co.z) * min(1.0, max(0.0, -(co.y - 0.02) / 0.07)) ** 0.6
    left = smooth(-0.03, 0.03, co.x)
    return {"leg-left": k * left, "leg-right": k * (1 - left), "torso": 1 - k}


part(skirt, cloth, skirt_w)

# ---- legs, socks ----------------------------------------------------------------------------------------
LX, LY = 0.043, 0.022
LEG = [(0.080, .0265), (0.095, .0285), (0.120, .0300), (0.1410, .0310), (0.1415, .0290), (0.165, .0275), (0.200, .0240)]
leg_l = surface("leg-l", [ring((LX, LY, z), r, r, 12) for z, r in LEG], start=(LX, LY, 0.078), end=(LX, LY, 0.202))
stocking = Canvas("leg", 2 * math.pi * 0.03, 0.125, 2400, SKIN)
y_of, _ = along(leg_l, [p[0] for p in LEG], stocking)
stocking.fill(SOCK, stocking.band(-1, y_of(0.1412)))
stocking.fill("#4A3D3E", stocking.band(y_of(0.133), y_of(0.1412)))        # the band at the top of the sock
stocking.fill("#2B2223", stocking.band(y_of(0.133) - 0.0006, y_of(0.133) + 0.0004))
part(leg_l, stocking, "leg-left")
part(mirror(leg_l, "leg-r"), stocking, "leg-right")

# ---- boots: a thick sole, a round toe, a strap with a buckle, a turned cuff -----------------------------
BOOT = [(0.0000, .0355, .0575, .0120, 2.6), (0.0120, .0360, .0580, .0120, 2.6), (0.0125, .0335, .0550, .0115, 2.6),
        (0.0280, .0348, .0570, .0100, 2.5), (0.0380, .0342, .0555, .0115, 2.4), (0.0460, .0332, .0500, .0165, 2.3),
        (0.0520, .0322, .0410, .0215, 2.2), (0.0600, .0315, .0345, .0235, 2.1), (0.0750, .0315, .0340, .0230, 2.0),
        (0.0900, .0325, .0348, .0225, 2.0), (0.0905, .0355, .0378, .0225, 2.0), (0.1030, .0360, .0383, .0225, 2.0),
        (0.1035, .0300, .0320, .0225, 2.0)]
boot_l = surface("boot-l", [ring((LX, cy, z), rx, ry, 16, power=p) for z, rx, ry, cy, p in BOOT],
                 start=(LX, 0.012, 0.0), end=(LX, 0.0225, 0.097))
leather = Canvas("boot", 2 * math.pi * 0.04, 0.21, 2200, RED)
y_of, Z = along(boot_l, [p[0] for p in BOOT], leather)
BDEG = (leather.X / leather.width - 0.5) * 360
leather.shade(0.86 + 0.14 * np.clip(Z / 0.05, 0, 1))                       # darker toward the sole
leather.fill(SOLE, leather.band(-1, y_of(0.0123)))
leather.fill(BAND, leather.band(y_of(0.056), y_of(0.069)))                 # the strap
leather.fill("#4A444B", leather.band(y_of(0.069) - 0.0009, y_of(0.069)))
bxc = (0.5 + 62 / 360) * leather.width                                     # the buckle, front of the outer side
leather.fill(METAL, leather.box(bxc - 0.0075, y_of(0.0535), bxc + 0.0075, y_of(0.0715), 0.0012))
leather.fill(BAND, leather.box(bxc - 0.0042, y_of(0.0575), bxc + 0.0042, y_of(0.0675), 0.0006))
leather.fill(METAL, leather.box(bxc - 0.0009, y_of(0.0575), bxc + 0.0009, y_of(0.0675)))
leather.fill(RED_DARK, leather.band(y_of(0.0865), y_of(0.0903)))           # the shadow under the cuff
leather.fill(RED_LIGHT, leather.band(y_of(0.0903), y_of(0.1032)), alpha=0.55)
leather.fill(SOCK, leather.band(y_of(0.1033), 1))
part(boot_l, leather, "leg-left")
part(mirror(boot_l, "boot-r"), leather, "leg-right")

# ---- hair ---------------------------------------------------------------------------------------------
# One coherent mass: a cap from a crown above her left temple, thick at its edge; two blades of fringe
# swept across the forehead to her right; a long lock in front of her right ear, a short one in front
# of her left; behind, a lock to the right shoulder blade and a heavy one gathered low at her left
# into a red tie and a teardrop tail. Every piece carries strands painted along its length.
HC, HR = Vector((0, 0.024, 0.468)), Vector((0.134, 0.130, 0.132))
AXIS = lambda co: Vector((0, 0.024, co.z))


def hscale(z):
    """The hair's horizontal scale at a height: an ellipsoid above its middle; below, it stands
    away from the head a little more as it falls (the reference's hair is widest at the jaw)."""
    k = z - HC.z
    return math.sqrt(max(1e-4, 1 - (k / HR.z) ** 2)) if k >= 0 else 1 + 0.13 * smooth(0, 0.07, -k)


def on_hair(x, z, lift=0.0):
    """The point on the front of the hair's surface at (x, z), ``lift`` off it."""
    rx, ry = HR.x * hscale(z) + lift, HR.y * hscale(z) + lift
    x = max(-0.995 * rx, min(0.995 * rx, x))
    return Vector((x, HC.y - ry * math.sqrt(1 - (x / rx) ** 2), z))


def strands(name, o, count, weights, ppm=1100, length=0.2, girth=0.14, seed=0):
    cv = Canvas(name, girth, length, ppm, HAIR)
    cv.streaks(count, groove=0.3, drift=0.14, seed=seed)
    cv.shade(1.06 - 0.16 * (cv.Y / cv.height))                             # a little darker toward the ends
    return part(o, cv, weights)


# the cap: columns from the crown, each ending at its own height - the hairline on her left forehead,
# above the ears, the bowl over the nape
COLS, ROWS = 32, 9
hem = lambda az: float(np.interp(az, [-180, -150, -128, -112, -75, -50, -20, 20, 29, 46, 60, 75, 112, 128, 150, 180],
                                 [.340, .345, .360, .452, .455, .500, .520, .535, .525, .500, .465, .455, .452, .360, .345, .340]))
polar = lambda z: math.acos(min(1, (z - HC.z) / HR.z)) if z >= HC.z else math.pi / 2 + (HC.z - z) / HR.z
height = lambda ph: HC.z + HR.z * math.cos(ph) if ph <= math.pi / 2 else HC.z - (ph - math.pi / 2) * HR.z
rows = []
for j in range(1, ROWS + 1):
    row = []
    for i in range(COLS):
        az = -180 + 360 * i / COLS
        z = height(polar(hem(az)) * j / ROWS)
        a = math.radians(az)
        row.append(Vector((HC.x + HR.x * hscale(z) * math.sin(a), HC.y - HR.y * hscale(z) * math.cos(a), z)))
    rows.append(row)
cap = surface("cap", rows, start=(HC.x, HC.y, HC.z + HR.z), inside=HC)
rim(cap, 0.026, AXIS)
crown = Canvas("cap", 2 * math.pi * 0.134, 0.30, 940, HAIR)
crown.streaks(72, groove=0.3, drift=0.14, seed=3)
crown.shade(1.0 + 0.16 * np.exp(-((crown.Y / crown.height - 0.32) / 0.14) ** 2))       # a soft sheen round the crown
px = (0.5 + 22 / 360) * crown.width                                        # the parting, above her left eye
crown.fill("#231B1E", np.maximum(crown.column(px - 0.0012, px + 0.0012), 0.03 - crown.Y), alpha=0.85)
part(cap, crown, "head")


def blade(name, pts, widths, thicks, seed, weights="head", seg=6):
    """A lock lying on the hair: ``pts`` are (x, z) on the front of the head, or full positions."""
    path = [Vector(p) if len(p) == 3 else on_hair(p[0], p[1], thicks[min(i, len(thicks) - 1)] / 2 - 0.006) for i, p in enumerate(pts)]
    o = sweep(name, path, widths, thicks, HC, seg=seg)
    return strands(name, o, max(4, int(max(widths) / 0.007)), weights, length=0.16, girth=2.2 * max(widths), seed=seed)


hang = lambda z0, z1: (lambda co: {"head": smooth(z0, z1, co.z), "torso": 1 - smooth(z0, z1, co.z)})
blade("fringe-a", [(0.045, 0.585), (0.016, 0.554), (-0.010, 0.515), (-0.019, 0.480), (-0.022, 0.452)],
      [.016, .060, .045, .025, .003], [.004, .016, .016, .012, .003], 11)
blade("fringe-b", [(0.015, 0.592), (-0.020, 0.565), (-0.046, 0.525), (-0.062, 0.482), (-0.068, 0.443)],
      [.016, .066, .052, .030, .003], [.004, .016, .016, .012, .003], 12)
# the long lock: from the crown over the temple, then close along the cheek in front of the ear (the
# ear shows outside it), and forward over the shoulder to the chest
blade("lock-right", [(-0.030, 0.590), (-0.085, 0.555), (-0.108, 0.510), (-0.099, -0.040, 0.455), (-0.099, -0.038, 0.405),
                     (-0.095, -0.036, 0.368), (-0.092, -0.031, 0.338), (-0.081, -0.031, 0.305), (-0.060, -0.031, 0.272)],
      [.016, .066, .054, .048, .046, .042, .036, .026, .003], [.004, .016, .018, .018, .018, .016, .014, .011, .003], 13,
      weights=hang(0.30, 0.35))
blade("lock-left", [(0.088, 0.548), (0.112, 0.505), (0.123, 0.465), (0.118, 0.430)],
      [.014, .046, .036, .003], [.004, .016, .014, .003], 14)

back = hang(0.30, 0.38)
# the long hair is a layer under the cap: each mass starts inside it, lies just under its surface
# down to the hem (so it reads as the same head of hair, and covers the skull behind the ears), then
# swells out below - the left one over the shoulder to the tie, the right one to a point
strands("mass-left", sweep("mass-left", [(0.055, 0.095, 0.480), (0.067, 0.110, 0.440), (0.072, 0.117, 0.390), (0.088, 0.122, 0.350),
                                         (0.108, 0.132, 0.310), (0.130, 0.147, 0.270), (0.145, 0.153, 0.240)],
                           [.090, .120, .125, .120, .100, .060, .034], [.040, .050, .055, .085, .090, .060, .034], AXIS, seg=10, tip=False),
        24, back, length=0.25, girth=0.34, seed=21)
strands("mass-right", sweep("mass-right", [(-0.055, 0.095, 0.480), (-0.067, 0.110, 0.440), (-0.072, 0.117, 0.390), (-0.090, 0.118, 0.350),
                                           (-0.100, 0.118, 0.315), (-0.100, 0.112, 0.285)],
                            [.090, .120, .125, .100, .060, .004], [.040, .050, .055, .070, .050, .004], AXIS, seg=10),
        22, back, length=0.20, girth=0.34, seed=22)
band = Canvas("tie", 0.12, 0.02, 1400, "#9E2626")
band.shade(0.9 + 0.2 * np.abs(np.sin(band.Y / band.height * math.pi)))
part(sweep("tie", [(0.1445, 0.153, 0.244), (0.1465, 0.1535, 0.228)], [.042, .042], [.042, .042], AXIS, seg=10, tip=False), band, "torso")
strands("tail", sweep("tail", [(0.146, 0.1535, 0.232), (0.153, 0.156, 0.212), (0.160, 0.160, 0.190), (0.166, 0.163, 0.165)],
                      [.030, .050, .045, .004], [.030, .045, .040, .004], AXIS, seg=10),
        9, "torso", length=0.075, girth=0.14, seed=23)

# the head as a whole follows the reference's front view, where it is larger than in the side views
for o, _, _ in PARTS:
    if o.name.split("-")[0] in ("head", "ear", "earring", "nose", "cap", "fringe", "lock", "mass", "tie", "tail"):
        scale_about(o, (0, HEAD_Y, 0.345), 1.07)
assemble("tifa", occlusion_size=2048, samples=32)
