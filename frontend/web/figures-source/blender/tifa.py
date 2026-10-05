# Tifa, Animal Crossing style (D-198): clean low-poly parts, every detail painted. Needs lib.py and
# figure.py. Measured from avatars-source/q/Tifa.jpg (front), back/tifa.jpg and stand-side/tifa.jpg:
# 0.60 tall, chin at 0.345, eyes at 0.437, shoulders 0.325, belt 0.236, hem 0.158, boot tops 0.10.
# The 9999 version (D-201): the budget's 10,000 triangles go where they show - the long hair one curtain
# down her back, sculpted into clumps; the suspenders, under-bust band, guard and glove straps, red
# plates, studs and boot straps standing off the body with frame buckles; deeper pleats.
reset("tifa")
fit_arms()
PARTS.clear()

# the darks keep red at or above blue, so nothing turns lilac
SKIN, HAIR = "#F8C6A2", "#211715"
TOP, TRIM, STRAP = "#F2EEEC", "#3A3234", "#2B2528"
GUARD, BAND, RED, RED_LIGHT, RED_DARK = "#2E2524", "#2A2527", "#9C2523", "#B23431", "#7A1E21"
SKIRT, SOCK, SOLE, METAL, METAL_DARK = "#332A29", "#352A29", "#352B2A", "#A9A6AD", "#6A666C"
STEEL = Canvas("steel", 0.02, 0.02, 800, "#D5D2D8")

# ---- head ---------------------------------------------------------------------------------------------
head, face = ac_head(SKIN, seg=32, rings=14)
ac_face(face)
part(head, face, "head")
ac_ears(SKIN, radii=(0.034, 0.024, 0.031), seg=10, rings=7, soft_fold=True)
ring_l = surface("earring-l", [ring((0.124, 0.038, z), 0.0055, 0.0040, 4) for z in (0.358, 0.386)],
                 start=(0.124, 0.038, 0.357), end=(0.124, 0.038, 0.389))
part(ring_l, STEEL, "head")
part(mirror(ring_l, "earring-r"), STEEL, "head")
ac_nose()

# ---- torso and neck ---------------------------------------------------------------------------------
_T = [(0.190, .050, .042, .022), (0.215, .047, .040, .020), (0.236, .0455, .038, .018), (0.250, .046, .039, .016),
      (0.272, .049, .044, .011), (0.295, .050, .044, .012), (0.312, .047, .040, .014), (0.322, .034, .030, .014),
      (0.330, .021, .021, .010), (0.352, .0185, .0185, .006)]
# the same body, with more rings where the bust is (the one under the skirt dropped)
TORSO = [(z, *(float(np.interp(z, [p[0] for p in _T], [p[k] for p in _T])) for k in (1, 2, 3)))
         for z in (0.190, 0.236, 0.250, 0.258, 0.272, 0.280, 0.295, 0.303, 0.312, 0.322, 0.330, 0.352)]


def bust(deg, z):
    """How far her bust stands out (metres): a full mound either side of the front, tucked in sharply
    just above the band under it, sloping up to the collarbone."""
    mounds = sum(math.exp(-((deg - c) / 23) ** 2) for c in (-25, 25))
    return 0.0175 * min(1.0, mounds) * smooth(0.2545, 0.2745, z) * (1 - smooth(0.281, 0.321, z))


torso = surface("torso", bulged_rings(TORSO, 24, bust), start=(0, .022, 0.186), end=(0, .006, 0.354))
body = Canvas("torso", 2 * math.pi * 0.047, 0.19, 2300, SKIN)
y_of, Z = along(torso, [p[0] for p in TORSO], body)
DEG = (body.X / body.width - 0.5) * 360                                   # 0 = front, + toward her left
xd = lambda deg: (0.5 + deg / 360) * body.width
# the cropped tank: its upper edge scoops at the front, climbs to the straps, dips under the arms
edge = np.interp(np.abs(DEG), [0, 12, 22, 27, 32, 50, 58, 90, 124, 134, 146, 154, 166, 180],
                 [.292, .294, .300, .312, .326, .326, .305, .282, .305, .326, .326, .322, .319, .318])
body.fill(TOP, np.maximum(0.2515 - Z, Z - edge))
slope = np.gradient(edge, axis=1) / body.px
body.fill(TRIM, np.where(edge < 0.3255, np.abs(Z - edge) / np.sqrt(1 + slope ** 2) - 0.0026, 1.0))   # not over the shoulder
body.fill(TRIM, body.band(y_of(0.2495), y_of(0.2535)))
body.fill("#D98F6A", body.ellipse(xd(0), y_of(0.2425), 0.0015, 0.003), alpha=0.9)   # navel
# the shadow between her breasts, down from the neckline
body.put("#CDBFC0", 0.45 * np.exp(-(DEG / 7) ** 2) * smooth_np(0.268, 0.278, Z) * (1 - smooth_np(0.286, 0.296, Z)) * (Z < edge))
part(torso, body, "torso")

# suspenders standing off the body: up the front, over the shoulder, down the back, each run ending in a
# frame buckle above the skirt; the black band under the bust stands off too
CHEST = Vector((0, 0.014, 0.27))
strap_c = strap_canvas(STRAP, "#3F383B")
buckle_c = buckle_canvas(METAL, METAL_DARK, STRAP)
for s in (1, -1):
    side = "l" if s > 0 else "r"
    flat_strap(f"suspender-{side}", [(s * 38, 0.228), (s * 38, 0.275), (s * 40, 0.300), (s * 52, 0.308), (s * 90, 0.312),
                                      (s * 128, 0.308), (s * 140, 0.300), (s * 142, 0.275), (s * 142, 0.228)],
               TORSO, CHEST, strap_c, width=0.011, bulge=bust)
    frame_buckle(f"suspender-adj-{side}", on_profile(TORSO, s * 141, 0.290, 0.0030), s * 141, buckle_c, (0.0055, 0.0008, 0.0040), seg=8)


def torso_band(name, z0, z1, rise=0.0014):
    """A band round the torso from z0 to z1, standing ``rise`` off it."""
    zs = [p[0] for p in TORSO]
    at = lambda z, k: ring((0, float(np.interp(z, zs, [p[3] for p in TORSO])), z), float(np.interp(z, zs, [p[1] for p in TORSO])) + k,
                           float(np.interp(z, zs, [p[2] for p in TORSO])) + k, 20)
    return surface(name, [at(z0, 0.0003), at(z0 + 0.0007, rise), at(z1 - 0.0007, rise), at(z1, 0.0003)])


band_trim = Canvas("band", 2 * math.pi * 0.047, 0.006, 2000, TRIM)
band_trim.shade(0.85 + 0.3 * np.sin(np.pi * band_trim.Y / band_trim.height))
part(torso_band("under-bust", 0.2490, 0.2540), band_trim, "torso")

# ---- arms (rest pose: straight out; the shoulder end stays with the torso, the rest follows the arm bone)
ARM = [(0.048, .0165, .0165), (0.062, .0195, .0195), (0.080, .0185, .0185), (0.0895, .0180, .0180),
       (0.0900, .0200, .0200), (0.122, .0206, .0206), (0.1440, .0214, .0214), (0.1445, .0275, .0268),
       (0.1575, .0282, .0274), (0.1580, .0290, .0282), (0.1700, .0290, .0282), (0.1705, .0280, .0270),
       (0.1860, .0276, .0262), (0.1865, .0245, .0225), (0.202, .0238, .0215), (0.210, .0180, .0162)]
AY, AZ = 0.017, 0.292
arm_l = surface("arm-l", [ring((x, AY, AZ), ry, rz, 14, plane="YZ", power=2.2) for x, ry, rz in ARM],
                start=(0.040, AY, AZ), end=(0.2155, AY, AZ))
sleeve = Canvas("arm", 2 * math.pi * 0.024, 0.176, 3200, SKIN)
y_of, _ = along(arm_l, [p[0] for p in ARM], sleeve)
top = 0.5 * sleeve.width                                                  # u = 0.5 is the top of the arm
sleeve.fill(GUARD, sleeve.band(y_of(0.0900), y_of(0.1445)))
sleeve.fill("#4A403F", sleeve.band(y_of(0.0900), y_of(0.0900) + 0.0012))
sleeve.fill(BAND, sleeve.band(y_of(0.094), y_of(0.100)))                  # under the strap round the top of the guard
plate_box = sleeve.box(top - 0.0060, y_of(0.124), top + 0.0060, y_of(0.136), 0.001)                 # the buckle plate under the red one
sleeve.fill("#1C1617", plate_box)
sleeve.fill("#5A5052", np.abs(plate_box) - 0.0004)
for k in (-1, 1):
    sleeve.fill(METAL, sleeve.ellipse(top + k * 0.0034, y_of(0.130), 0.0011, 0.0011))
sleeve.fill(RED, sleeve.band(y_of(0.1445), y_of(0.1578)))                 # the glove's cuff
sleeve.fill(RED_LIGHT, sleeve.band(y_of(0.1445), y_of(0.1445) + 0.0016))
sleeve.fill(BAND, sleeve.band(y_of(0.1578), y_of(0.1702)))                # under the band with its stud
sleeve.fill(RED, sleeve.band(y_of(0.1702), y_of(0.193)))                  # the glove over the hand
sleeve.fill(BAND, sleeve.band(y_of(0.189), y_of(0.193)))                  # across the knuckles
for u in (0.34, 0.45, 0.56, 0.67):                                        # between the fingers
    sleeve.fill("#DDA07E", sleeve.stroke([(u * sleeve.width, y_of(0.1945)), (u * sleeve.width, y_of(0.209))], 0.0008))
arm_w = arm_weights
part(arm_l, sleeve, arm_w("left"))
part(mirror(arm_l, "arm-r"), sleeve, arm_w("right"))
thumb = ellipsoid("thumb-l", (0.184, AY - 0.024, AZ + 0.004), (0.011, 0.010, 0.010), 6, 4)
knuckle = Canvas("thumb", 0.03, 0.03, 1000, SKIN)
part(thumb, knuckle, "forearm-left")
part(mirror(thumb, "thumb-r"), knuckle, "forearm-right")

# on the arm, standing off it: the strap round the top of the guard, buckled on top; the red plate; the
# black band over the glove with its round stud
arm_r = lambda x: float(np.interp(x, [p[0] for p in ARM], [p[1] for p in ARM]))
plate_c = Canvas("plate", 0.06, 0.03, 2000, RED)
plate_c.fill(RED_DARK, plate_c.band(-1, 0.52 * plate_c.height), alpha=0.6)
plate_c.fill(RED_LIGHT, plate_c.band(0.56 * plate_c.height, 0.64 * plate_c.height), alpha=0.6)
stud_plate_c = Canvas("stud-plate", 0.04, 0.02, 1200, BAND)
stud_c = Canvas("stud", 0.04, 0.02, 1600, METAL)
stud_c.put("#F1F0F4", 0.8 * np.exp(-((stud_c.X / stud_c.width - 0.42) / 0.05) ** 2 - ((stud_c.Y / stud_c.height - 0.75) / 0.12) ** 2))
stud_c.fill(METAL_DARK, stud_c.band(0, 0.15 * stud_c.height))
for name, o, cv in (("guard-strap", wrap_band("guard-strap-l", (AY, AZ), arm_r, 0.094, 0.100, seg=14, plane="YZ"), strap_c),
                    ("plate", ellipsoid("plate-l", (0.111, AY, AZ + arm_r(0.111) + 0.0010), (0.0100, 0.0095, 0.0022), 10, 4, power=8), plate_c),
                    ("glove-band", wrap_band("glove-band-l", (AY, AZ), arm_r, 0.158, 0.170, seg=14, plane="YZ"), strap_c),
                    ("stud-plate", ellipsoid("stud-plate-l", (0.164, AY, AZ + arm_r(0.164) + 0.0022), (0.0085, 0.0075, 0.0018), 8, 3, power=8), stud_plate_c),
                    ("stud", ellipsoid("stud-l", (0.164, AY, AZ + arm_r(0.164) + 0.0036), (0.0060, 0.0060, 0.0028), 12, 4), stud_c)):
    part(o, cv, "forearm-left")
    part(mirror(o, name + "-r"), cv, "forearm-right")
for s, side in ((1, "l"), (-1, "r")):
    frame_buckle(f"guard-buckle-{side}", (s * 0.097, AY, AZ + arm_r(0.097) + 0.0024), 0, buckle_c, (0.0046, 0.0008, 0.0044),
                 weights="forearm-left" if s > 0 else "forearm-right", tilt=(-math.pi / 2, 0), seg=8)

# ---- skirt: a yoke, then knife pleats that open toward the hem -----------------------------------------
PLEATS = 14
SKIRT_Z = [(0.158, .094, .084, .021, .0060), (0.172, .0875, .0780, .0205, .0054), (0.186, .081, .072, .020, .0046), (0.2135, .0605, .0525, .019, .0012),
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
    k = 0.6 * smooth(0.214, 0.158, co.z) * smooth(0.025, -0.045, co.y)
    left = smooth(-0.03, 0.03, co.x)
    return {"leg-left": k * left, "leg-right": k * (1 - left), "torso": 1 - k}


part(skirt, cloth, skirt_w)
SKIRT_P = [p[:4] for p in SKIRT_Z]
for s in (1, -1):
    side = "l" if s > 0 else "r"
    for d in (38, 142):
        frame_buckle(f"suspender-buckle-{side}{d}", on_profile(SKIRT_P, s * d, 0.229, 0.0030), s * d, buckle_c, (0.0060, 0.0010, 0.0080), seg=8)

# ---- legs, socks ----------------------------------------------------------------------------------------
LX, LY = 0.043, 0.022
LEG = [(0.080, .0265), (0.095, .0285), (0.120, .0300), (0.1410, .0310), (0.1415, .0290), (0.165, .0275), (0.188, .0210)]
leg_l = surface("leg-l", [ring((LX, LY, z), r, r, 12) for z, r in LEG], start=(LX, LY, 0.078), end=(LX, LY, 0.191))
stocking = Canvas("leg", 2 * math.pi * 0.03, 0.125, 2400, SKIN)
y_of, _ = along(leg_l, [p[0] for p in LEG], stocking)
stocking.fill(SOCK, stocking.band(-1, y_of(0.1412)))
stocking.fill("#4A3D3E", stocking.band(y_of(0.133), y_of(0.1412)))        # the band at the top of the sock
stocking.fill("#2B2223", stocking.band(y_of(0.133) - 0.0006, y_of(0.133) + 0.0004))
part(leg_l, stocking, "leg-left")
part(mirror(leg_l, "leg-r"), stocking, "leg-right")

# ---- boots: a thick sole, a round toe, a strap with a buckle, a turned cuff -----------------------------
BOOT = [(0.0000, .0360, .0585, .0110, 2.6), (0.0040, .0385, .0610, .0110, 2.6), (0.0145, .0385, .0610, .0110, 2.6),
        (0.0170, .0360, .0585, .0110, 2.6), (0.0175, .0345, .0570, .0105, 2.6), (0.0320, .0372, .0585, .0080, 2.5),
        (0.0420, .0362, .0545, .0105, 2.4), (0.0490, .0340, .0470, .0160, 2.3), (0.0550, .0322, .0380, .0215, 2.2),
        (0.0590, .0315, .0345, .0230, 2.1), (0.0790, .0315, .0340, .0230, 2.0), (0.0800, .0318, .0343, .0228, 2.0),
        (0.0845, .0355, .0380, .0226, 2.0), (0.0985, .0358, .0383, .0225, 2.0), (0.1035, .0300, .0320, .0225, 2.0)]
boot_l = surface("boot-l", [ring((LX, cy, z), rx, ry, 16, power=p) for z, rx, ry, cy, p in BOOT],
                 start=(LX, 0.012, 0.0), end=(LX, 0.0225, 0.097))
leather = Canvas("boot", 2 * math.pi * 0.04, 0.21, 2200, RED)
y_of, Z = along(boot_l, [p[0] for p in BOOT], leather)
BDEG = (leather.X / leather.width - 0.5) * 360
leather.shade(0.86 + 0.14 * np.clip(Z / 0.05, 0, 1))                       # darker toward the sole
leather.fill(SOLE, leather.band(-1, y_of(0.0172)))
leather.fill(BAND, leather.band(y_of(0.0595), y_of(0.077)))                # under the strap
seam = np.interp(np.abs(BDEG), [0, 40, 100, 180], [.047, .049, .057, .057])  # where the toe cap meets the upper
leather.fill(RED_DARK, np.maximum(np.abs(Z - seam) - 0.0006, np.abs(BDEG) - 105), alpha=0.8)
leather.fill(RED_DARK, leather.band(y_of(0.0790), y_of(0.0815)))           # the crease under the padded cuff
leather.fill(RED_LIGHT, leather.band(y_of(0.0815), y_of(0.0985)), alpha=0.55)
for d in (-62, 62):                                                        # its rivets
    leather.fill("#3A1A1A", leather.ellipse((0.5 + d / 360) * leather.width, y_of(0.091), 0.0018, 0.0018))
leather.fill(SOCK, leather.band(y_of(0.1033), 1))
part(boot_l, leather, "leg-left")
part(mirror(boot_l, "boot-r"), leather, "leg-right")


def boot_at(z, k=0.0, deg=None):
    """The boot's ring at height z, ``k`` out from it - or, given ``deg``, the point on it."""
    zs = [p[0] for p in BOOT]
    rx, ry, cy, pw = (float(np.interp(z, zs, [p[i] for p in BOOT])) for i in (1, 2, 3, 4))
    if deg is None:
        return ring((LX, cy, z), rx + k, ry + k, 16, power=pw)
    d = math.radians(deg)
    return Vector((LX + _se(math.sin(d), pw) * (rx + k), cy - _se(math.cos(d), pw) * (ry + k), z))


# the boot strap standing off the boot, its buckle at the front of the outer side
boot_strap = surface("boot-strap-l", [boot_at(z, k) for z, k in ((0.0595, 0.0004), (0.0603, 0.0018), (0.0762, 0.0018), (0.0770, 0.0004))])
part(boot_strap, strap_c, "leg-left")
part(mirror(boot_strap, "boot-strap-r"), strap_c, "leg-right")
for s, side in ((1, "l"), (-1, "r")):
    at = boot_at(0.0683, 0.0030, 62)
    at.x = s * at.x
    frame_buckle(f"boot-buckle-{side}", at, s * 50, buckle_c, (0.0080, 0.0010, 0.0085), weights="leg-left" if s > 0 else "leg-right", seg=8)

# ---- hair ---------------------------------------------------------------------------------------------
# One coherent mass: a cap from a crown above her left temple, thick at its edge, sculpted into clumps,
# coming down her back as one curtain to the shoulder blades and ending in points; two blades of fringe
# swept across the forehead to her right; a long lock in front of her right ear, a short one in front
# of her left; and a heavy lock gathered low at her left into a red tie and a teardrop tail. Every piece
# carries strands painted along its length.
hair = Hair((0, 0.024, 0.468), (0.134, 0.130, 0.132), HAIR, tuck=0.06, tuck_from=0.14, tuck_to=0.18)
COLS, CLUMP = 70, 5
LEN = {4: .003, 5: .006, 6: .004, 7: .008, 8: .005, 9: .007, 10: .002}     # each clump down the back a little its own length


def hem(az):
    """The cap's hem: the hairline on her left forehead, above the ears, then the curtain down her back,
    each clump ending in a point."""
    edge = float(np.interp(az, [-180, -165, -150, -135, -120, -114, -108, -104, -75, -50, -20, 20, 29, 46, 60, 75, 90, 104, 108, 114, 125, 140, 155, 165, 180],
                           [.322, .318, .300, .292, .290, .295, .300, .452, .455, .500, .520, .535, .525, .515, .500, .485, .468, .452, .320, .310, .310, .305, .310, .318, .322]))
    if abs(az) >= 108:
        t = az * COLS / 360 / CLUMP + 0.5
        u, k = t % 1, int(t // 1) % (COLS // CLUMP)
        edge += 0.022 * (1 - math.sin(math.pi * u) ** 0.7) - LEN.get(k, 0.0) * math.sin(math.pi * u)
    return edge


hair.cap(hem, cols=COLS, rows=12, ridges=(COLS // CLUMP, 0.15, 40, 0.5), weights=hang(0.30, 0.38), grow=(0.45, 1.1),
         paint_grow=(0.15, 4.0), highlight=0.30, partings=0.70, side_fade=True, parting_color="#150F0E", sweep=1.2)
hair.blade("fringe-a", [(0.045, 0.585), (0.010, 0.556), (-0.020, 0.518), (-0.032, 0.482), (-0.036, 0.455)],
           [.020, .075, .065, .042, .004], [.008, .022, .024, .018, .005], 11, seg=8, steps=4, strands=3)
hair.blade("fringe-b", [(0.015, 0.592), (-0.020, 0.565), (-0.046, 0.525), (-0.062, 0.482), (-0.068, 0.443)],
           [.020, .080, .068, .045, .004], [.008, .022, .024, .018, .005], 12, seg=8, steps=4, strands=3)
# the long lock: from the crown over the temple, then close along the cheek in front of the ear (the
# ear shows outside it), and forward over the shoulder to the chest
hair.blade("lock-right", [(-0.030, 0.590), (-0.085, 0.555), (-0.108, 0.510), (-0.110, -0.016, 0.455), (-0.110, -0.014, 0.405),
                          (-0.103, -0.020, 0.368), (-0.092, -0.031, 0.338), (-0.081, -0.031, 0.305), (-0.060, -0.031, 0.272)],
           [.016, .070, .066, .062, .062, .058, .050, .036, .003], [.004, .018, .022, .022, .022, .020, .018, .014, .003], 13,
           weights=hang(0.30, 0.35), seg=8, steps=3, strands=4)
hair.blade("lock-left", [(0.088, 0.548), (0.112, 0.505), (0.123, 0.465), (0.118, 0.430)],
           [.014, .046, .036, .003], [.004, .016, .016, .003], 14, seg=8, steps=4, strands=3)

back = hang(0.30, 0.38)
# the lock gathered to the tie is a layer under the cap: it starts inside it, lies just under its
# surface, then leaves the curtain at her left and runs over the shoulder blade to the tie
hair.mass("mass-left", [(0.055, 0.095, 0.480), (0.067, 0.110, 0.440), (0.072, 0.117, 0.390), (0.088, 0.122, 0.350),
                        (0.108, 0.132, 0.310), (0.130, 0.147, 0.270), (0.145, 0.153, 0.240)],
          [.090, .120, .125, .120, .100, .060, .034], [.040, .050, .055, .085, .090, .060, .034], 8, back, 0.25, 0.34, 21, tip=False)
band = Canvas("tie", 0.12, 0.02, 1400, "#9E2626")
band.shade(0.9 + 0.2 * np.abs(np.sin(band.Y / band.height * math.pi)))
part(sweep("tie", [(0.1445, 0.153, 0.242), (0.1465, 0.1535, 0.231)], [.032, .032], [.032, .032], hair.axis, seg=10, tip=False), band, "torso")
hair.mass("tail", [(0.146, 0.1535, 0.232), (0.153, 0.156, 0.212), (0.160, 0.160, 0.190), (0.166, 0.163, 0.165)],
          [.034, .050, .045, .004], [.034, .045, .040, .004], 9, "torso", 0.075, 0.14, 23)

# the head as a whole follows the reference's front view, where it is larger than in the side views
scale_parts(HEAD_PARTS, HEAD_PIVOT, 1.07)
assemble("tifa", occlusion_size=2048, samples=32, fade_face_seam=True)
