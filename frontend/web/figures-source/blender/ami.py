# Ami, Animal Crossing style (D-211): built as the others are, on Tifa's proportions (head, body, arms,
# height); the hair, the face and the dress come from avatars-source/q/Ami.jpg (front), back/ami.jpg and
# stand-side/ami.jpg. Needs lib.py and figure.py. A blue bob - Rei's round shape, with a fringe swept from a
# parting on her left across her right brow - a gold tiara with a blue gem on the forehead, blue earrings,
# blue eyes; the sailor suit - a white leotard coming down in a V over a pleated blue skirt, a blue sailor
# collar striped white (a V in front, a square flap behind), a light blue bow on the chest with a round
# brooch, a big blue bow at the back of the waist, a blue choker with a gold star, white puffs at the
# shoulders, white gloves to the elbow with a blue band, blue boots to the knee trimmed white in a V.
# The 9999 version: the budget goes on the hair (its clumps, the fringe) and on what stands off the suit -
# the collar, both bows and the brooch, the choker, the puffs, the glove bands, the tiara and its gem.
reset("ami")
fit_arms()
PARTS.clear()

SKIN, HAIR = "#FCD6BB", "#33497D"
WHITE, BLUE, BLUE_DARK, BLUE_LIGHT, SKY = "#F6F1F3", "#2F5AA8", "#1E3E86", "#5A82CC", "#9CBDEE"
GOLD, GOLD_DARK = "#EDBB6A", "#B98436"

# ---- head (Tifa's), blue eyes, the tiara ---------------------------------------------------------------
head, face = ac_head(SKIN, seg=32, rings=14)
ac_face(face, colors={"iris": "#22396F", "brow": "#2E3C70"})
x0, z0 = FACE_BOX[:2]
for s in (1, -1):
    cx, cz = s * 0.055, 0.437
    e = face.ellipse(cx - x0, cz - z0, 0.0235, 0.0232)
    iris = np.maximum(face.ellipse(cx + 0.0070 - x0, cz - 0.0005 - z0, 0.0152, 0.0222), e + 0.0018)
    face.put("#5B86D2", 0.8 * face.cover(iris) * np.clip((cz - z0 + 0.004 - face.Y) / 0.020, 0, 1) ** 1.2)
part(head, face, "head")
ac_ears(SKIN, radii=(0.034, 0.024, 0.031), seg=10, rings=7, soft_fold=True)
ac_nose()
stud_c = Canvas("stud", 0.03, 0.015, 1600, BLUE_LIGHT)
stud_c.shade(0.7 + 0.5 * stud_c.Y / stud_c.height)
stud = ellipsoid("earring-l", (0.1150, 0.0300, 0.3880), (0.0046, 0.0046, 0.0046), 8, 4)
part(stud, stud_c, "head")
part(mirror(stud, "earring-r"), stud_c, "head")

# the tiara: a gold band across the forehead, rising toward her left, dipping at the gem
tiara_c = Canvas("tiara", 0.20, 0.02, 1400, GOLD)
tiara_c.shade(0.80 + 0.35 * np.sin(np.pi * tiara_c.Y / tiara_c.height))
tiara_z = lambda x: 0.4840 + 0.0110 * x / 0.080 - 0.0050 * max(0.0, 1 - abs(x) / 0.016)
tiara_pts = [Vector((x, face_front(x, tiara_z(x)) - 0.0014, tiara_z(x))) for x in np.linspace(-0.084, 0.084, 9)]
tiara = sweep("tiara", tiara_pts, [0.0060] * 9, [0.0016] * 9, lambda c: Vector((c.x * 0.6, HEAD_Y + 0.06, c.z)), seg=6, steps=2, tip=False)
part(tiara, tiara_c, "head")
gem_c = Canvas("gem", 0.03, 0.03, 1600, "#1F4F86")
gem_c.put("#6EA8E6", 0.7 * np.exp(-((gem_c.X - 0.012) / 0.004) ** 2 - ((gem_c.Y - 0.019) / 0.004) ** 2))
GEM = Vector((0.0, face_front(0.0, tiara_z(0.0)) - 0.0030, tiara_z(0.0) + 0.0010))
gem = ellipsoid("gem", GEM, (0.0050, 0.0028, 0.0068), 10, 5)
project_front(gem, -0.015, GEM.z - 0.015, 0.03, 0.03)
part(gem, gem_c, "head")

# ---- torso: the white leotard -------------------------------------------------------------------------
_T = [(0.190, .050, .042, .022), (0.215, .047, .040, .020), (0.236, .0455, .038, .018), (0.250, .046, .039, .016),
      (0.272, .049, .044, .011), (0.295, .050, .044, .012), (0.312, .047, .040, .014), (0.322, .034, .030, .014),
      (0.330, .021, .021, .010), (0.352, .0185, .0185, .006)]
TORSO = [(z, *(float(np.interp(z, [p[0] for p in _T], [p[k] for p in _T])) for k in (1, 2, 3)))
         for z in (0.190, 0.236, 0.250, 0.258, 0.272, 0.280, 0.295, 0.303, 0.312, 0.322, 0.330, 0.352)]


def bust(deg, z):
    """Her bust under the leotard: a mound either side of the front."""
    mounds = sum(math.exp(-((deg - c) / 24) ** 2) for c in (-25, 25))
    return 0.011 * min(1.0, mounds) * smooth(0.252, 0.272, z) * (1 - smooth(0.282, 0.318, z))


torso = surface("torso", bulged_rings(TORSO, 28, bust), start=(0, .022, 0.186), end=(0, .006, 0.354))
body = Canvas("torso", 2 * math.pi * 0.047, 0.19, 2300, WHITE)
y_of, Z = along(torso, [p[0] for p in TORSO], body)
DEG = (body.X / body.width - 0.5) * 360
body.shade(0.95 + 0.06 * np.cos(np.radians(DEG)) ** 2)
part(torso, body, "torso")
zs = [p[0] for p in TORSO]


def torso_ring(z, k, seg=24):
    return ring((0, float(np.interp(z, zs, [p[3] for p in TORSO])), z), float(np.interp(z, zs, [p[1] for p in TORSO])) + k,
                float(np.interp(z, zs, [p[2] for p in TORSO])) + k, seg)


# the choker: a blue band with a gold star at the front
choker_c = Canvas("choker", 2 * math.pi * 0.024, 0.012, 2400, BLUE)
choker_c.shade(0.80 + 0.32 * np.sin(np.pi * choker_c.Y / choker_c.height) ** 0.6)
sx, sy = 0.5 * choker_c.width, 0.5 * choker_c.height
ang = np.arctan2(choker_c.Y - sy, choker_c.X - sx)
star_r = 0.0032 * (0.55 + 0.45 * np.cos(5 * (ang - math.pi / 2)) ** 2)
choker_c.fill(GOLD, np.hypot(choker_c.X - sx, choker_c.Y - sy) - star_r)
part(surface("choker", [torso_ring(z, k) for z, k in ((0.3290, 0.0004), (0.3302, 0.0030), (0.3368, 0.0026), (0.3380, 0.0004))]), choker_c, "torso")

# the sailor collar: a shell lying on the shoulders from the neck to its hem - a V down to the bow in
# front, a square flap behind - blue, two white stripes along the hem
COLLAR_TOP, ROWS, SPAN = 0.3310, 6, 56


def collar_hem(deg):
    return float(np.interp(abs(deg), [0, 30, 55, 80, 100, 122, 128, 180], [.290, .300, .313, .319, .320, .318, .296, .293]))


opening = lambda f: 36 - 32 * f                     # the half-angle of the V at the front, from the neck down
rows = []
for j in range(ROWS + 1):
    f = j / ROWS
    a0 = opening(f)
    row = []
    for i in range(SPAN + 1):
        deg = a0 + (360 - 2 * a0) * i / SPAN
        deg = deg - 360 if deg > 180 else deg
        z = COLLAR_TOP + f * (collar_hem(deg) - COLLAR_TOP)
        row.append(on_profile(TORSO, deg, z, 0.0026, bulge=bust))
    rows.append(row)
collar = surface("collar", rows, closed=False, inside=(0, 0.012, 0.30))
rim(collar, 0.0018, lambda co: Vector((0, 0.012, co.z)))
sailor = Canvas("sailor", 0.36, 0.06, 2200, BLUE)
U, V = sailor.X / sailor.width, np.clip(sailor.Y / sailor.height, 0, 1)
A0 = 36 - 32 * V
CDEG = A0 + (360 - 2 * A0) * U
CDEG = np.where(CDEG > 180, CDEG - 360, CDEG)
HEM = np.interp(np.abs(CDEG), [0, 30, 55, 80, 100, 122, 128, 180], [.290, .300, .313, .319, .320, .318, .296, .293])
above = (1 - V) * (COLLAR_TOP - HEM)                 # metres above the hem
for lo, hi in ((0.0022, 0.0036), (0.0050, 0.0064)):
    sailor.fill(WHITE, np.maximum(lo - above, above - hi))
sailor.shade(0.92 + 0.10 * V)
part(collar, sailor, "torso")

# the bow on the chest: two light blue loops and their tails, a round blue brooch at the knot
BOW = on_profile(TORSO, 0, 0.2860, 0.0060, bulge=bust)
ribbon = Canvas("ribbon", 0.06, 0.04, 1600, SKY)
ribbon.shade(0.82 + 0.30 * np.sin(np.pi * ribbon.Y / ribbon.height) ** 0.7)
ribbon.fill(BLUE_LIGHT, np.abs(ribbon.Y - 0.5 * ribbon.height) - 0.0012, alpha=0.35)
for s, side in ((1, "l"), (-1, "r")):
    at = BOW + Vector((s * 0.0255, -0.0010, 0.0020))
    loop = ellipsoid(f"bow-{side}", at, (0.0245, 0.0055, 0.0185), 10, 5, power=2.3)
    part(turn(loop, at, (0, s * -0.18, 0)), ribbon, "torso")                   # its outer end a little up
    part(sweep(f"bow-tail-{side}", [BOW + Vector((s * 0.006, 0.0, -0.006)), BOW + Vector((s * 0.020, -0.002, -0.026)),
                                    BOW + Vector((s * 0.030, -0.0005, -0.044))], [0.018, 0.016, 0.012], [0.0032, 0.0032, 0.0028],
               lambda c: c + Vector((0, 1, 0)), seg=6, steps=2), ribbon, "torso")
brooch_c = Canvas("brooch", 0.04, 0.02, 1600, "#2462B8")
brooch_c.shade(0.70 + 0.45 * brooch_c.Y / brooch_c.height)
brooch_c.put("#BFD8FF", 0.85 * np.exp(-((brooch_c.X / brooch_c.width - 0.43) / 0.05) ** 2 - ((brooch_c.Y / brooch_c.height - 0.76) / 0.08) ** 2))
part(ellipsoid("brooch", BOW + Vector((0, -0.0050, 0)), (0.0098, 0.0066, 0.0098), 12, 6), brooch_c, "torso")

# ---- skirt: Tifa's knife pleats, blue; the leotard's V coming down over its front -------------------------
PLEATS = 14
SKIRT_Z = [(0.158, .094, .084, .021, .0060), (0.172, .0875, .0780, .0205, .0054), (0.186, .081, .072, .020, .0046), (0.2135, .0605, .0525, .019, .0012),
           (0.2140, .0600, .0520, .019, 0), (0.2385, .0495, .0425, .018, 0)]
rows = []
for z, rx, ry, cy, amp in SKIRT_Z:
    row = ring((0, cy, z), rx, ry, PLEATS * 4)
    for i, p in enumerate(row):
        k = 1 + amp * (1, 0.33, -0.33, -1)[i % 4] / rx
        p.x, p.y = p.x * k, cy + (p.y - cy) * k
    rows.append(row)
skirt = surface("skirt", rows)
cloth = Canvas("skirt", 2 * math.pi * 0.07, 0.10, 2000, BLUE)
y_of, SZ = along(skirt, [p[0] for p in SKIRT_Z], cloth)
SDEG = (cloth.X / cloth.width - 0.5) * 360
t = (cloth.X / cloth.width * PLEATS) % 1
cloth.shade(np.where(SZ < 0.2137, np.where(t < 0.75, 1.14 - 0.26 * t / 0.75, 0.66), 1.0))
cloth.fill(WHITE, (0.2385 - 0.028 * np.clip(1 - np.abs(SDEG) / 42, 0, 1)) - SZ)                # the leotard's V
cloth.fill("#C9C3CC", np.abs(SZ - (0.2385 - 0.028 * np.clip(1 - np.abs(SDEG) / 42, 0, 1))) - 0.0004, alpha=0.6)


def skirt_w(co):
    """The front of the hem follows the legs (so it lifts over the thighs when she sits and swings when
    she walks); the top and the back stay with the torso."""
    k = 0.6 * smooth(0.214, 0.158, co.z) * smooth(0.025, -0.045, co.y)
    left = smooth(-0.03, 0.03, co.x)
    return {"leg-left": k * left, "leg-right": k * (1 - left), "torso": 1 - k}


part(skirt, cloth, skirt_w)

# the big bow at the back of the waist: two loops, the knot, two tails down over the skirt
BACK_BOW = on_profile(TORSO, 180, 0.2445, 0.0080)
bow_c = Canvas("back-bow", 0.08, 0.05, 1400, BLUE)
bow_c.shade(0.80 + 0.32 * np.sin(np.pi * bow_c.Y / bow_c.height) ** 0.7)
for s, side in ((1, "l"), (-1, "r")):
    at = BACK_BOW + Vector((s * 0.0330, 0.0030, 0.0050))
    loop = ellipsoid(f"back-bow-{side}", at, (0.0320, 0.0075, 0.0190), 12, 5, power=2.3)
    part(turn(loop, at, (0, s * 0.18, 0)), bow_c, "torso")                     # its outer end a little up
    part(sweep(f"back-bow-tail-{side}", [(s * 0.0090, BACK_BOW.y + 0.004, 0.2360), (s * 0.0200, 0.0800, 0.2150), (s * 0.0280, 0.0950, 0.1950)],
               [0.020, 0.019, 0.016], [0.0032, 0.0032, 0.0028], lambda c: c + Vector((0, -1, 0)), seg=6, steps=2), bow_c, "torso")
part(ellipsoid("back-bow-knot", BACK_BOW + Vector((0, 0.0060, 0.0010)), (0.0090, 0.0070, 0.0110), 10, 5), bow_c, "torso")

# ---- arms: bare to the elbow, white gloves with a blue band, white puffs at the shoulders -----------------
ARM = [(0.048, .0165, .0165), (0.062, .0198, .0198), (0.080, .0190, .0190), (0.100, .0180, .0180), (0.122, .0174, .0174),
       (0.140, .0172, .0172), (0.152, .0172, .0170), (0.156, .0215, .0205), (0.164, .0250, .0238), (0.176, .0264, .0251),
       (0.188, .0262, .0249), (0.199, .0246, .0233), (0.207, .0206, .0193), (0.2125, .0140, .0130)]
AY, AZ = 0.017, 0.292
arm_l = surface("arm-l", [ring((x, AY, AZ), ry, rz, 14, plane="YZ", power=2.2) for x, ry, rz in ARM],
                start=(0.040, AY, AZ), end=(0.2155, AY, AZ))
sleeve = Canvas("arm", 2 * math.pi * 0.024, 0.176, 3200, SKIN)
y_of, AXP = along(arm_l, [p[0] for p in ARM], sleeve)
sleeve.fill(WHITE, sleeve.band(y_of(0.0990), sleeve.height + 1))
sleeve.fill("#DCD6DE", sleeve.band(y_of(0.1560), y_of(0.1560) + 0.0006), alpha=0.6)
part(arm_l, sleeve, arm_weights("left"))
part(mirror(arm_l, "arm-r"), sleeve, arm_weights("right"))
thumb = ellipsoid("thumb-l", (0.184, AY - 0.024, AZ + 0.004), (0.011, 0.010, 0.010), 6, 4)
knuckle = Canvas("thumb", 0.03, 0.03, 1000, WHITE)
part(thumb, knuckle, "forearm-left")
part(mirror(thumb, "thumb-r"), knuckle, "forearm-right")
arm_r = lambda x: float(np.interp(x, [p[0] for p in ARM], [p[1] for p in ARM]))
band = wrap_band("glove-band-l", (AY, AZ), arm_r, 0.0950, 0.1060, seg=14, plane="YZ", rise=0.0034)
band_c = Canvas("glove-band", 2 * math.pi * 0.022, 0.014, 2000, BLUE)
band_c.shade(0.85 + 0.25 * np.sin(np.pi * band_c.Y / band_c.height))
part(band, band_c, "forearm-left")
part(mirror(band, "glove-band-r"), band_c, "forearm-right")
puff_c = Canvas("puff", 0.08, 0.04, 1200, WHITE)
puff_c.shade(0.90 + 0.12 * np.sin(np.pi * puff_c.Y / puff_c.height))
PUFF = Vector((0.0570, 0.0160, 0.3000))
puff = ellipsoid("puff-l", PUFF, (0.0150, 0.0250, 0.0240), 10, 5)
part(puff, puff_c, arm_weights("left"))
part(mirror(puff, "puff-r"), puff_c, arm_weights("right"))

# ---- legs, bare; blue boots to the knee, trimmed white in a V at the front ---------------------------------
LX, LY = 0.040, 0.022
LEG = [(0.080, .0232), (0.100, .0240), (0.125, .0232), (0.150, .0244), (0.172, .0254), (0.190, .0225)]
leg_l = surface("leg-l", [ring((LX, LY, z), r, r, 12) for z, r in LEG], start=(LX, LY, 0.078), end=(LX, LY, 0.193))
legs = Canvas("leg", 2 * math.pi * 0.025, 0.125, 2200, SKIN)
legs.shade(0.95 + 0.06 * np.cos(np.radians((legs.X / legs.width - 0.5) * 360)) ** 2)
part(leg_l, legs, "leg-left")
part(mirror(leg_l, "leg-r"), legs, "leg-right")
BOOT = [(0.0000, .0290, .0480, .0100, 2.4), (0.0030, .0312, .0502, .0100, 2.4), (0.0070, .0312, .0502, .0100, 2.4),
        (0.0085, .0298, .0488, .0100, 2.4), (0.0200, .0305, .0478, .0090, 2.3), (0.0330, .0300, .0445, .0105, 2.3),
        (0.0440, .0285, .0385, .0160, 2.2), (0.0520, .0272, .0330, .0205, 2.1), (0.0580, .0266, .0298, .0225, 2.0),
        (0.0850, .0262, .0280, .0226, 2.0), (0.1150, .0272, .0288, .0222, 2.0), (0.1200, .0276, .0292, .0222, 2.0),
        (0.1225, .0250, .0266, .0222, 2.0)]
boot_l = surface("boot-l", [ring((LX, cy, z), rx, ry, 14, power=p) for z, rx, ry, cy, p in BOOT],
                 start=(LX, 0.010, 0.0), end=(LX, 0.0222, 0.118))
leather = Canvas("boot", 2 * math.pi * 0.033, 0.21, 2200, BLUE)
y_of, BZ = along(boot_l, [p[0] for p in BOOT], leather)
BDEG = (leather.X / leather.width - 0.5) * 360
leather.shade(0.86 + 0.14 * np.clip(BZ / 0.05, 0, 1))
leather.fill(BLUE_DARK, leather.band(-1, y_of(0.0075)))
seam = np.interp(np.abs(BDEG), [0, 40, 100, 180], [.044, .046, .052, .052])
leather.fill(BLUE_DARK, np.maximum(np.abs(BZ - seam) - 0.0005, np.abs(BDEG) - 105), alpha=0.5)
top_v = 0.1205 - 0.0130 * np.clip(1 - np.abs(BDEG) / 34, 0, 1)            # the top edge, dipping to a V at the front
leather.fill(WHITE, np.maximum(top_v - 0.0050 - BZ, BZ - top_v))
leather.fill(SKIN, top_v - BZ)
part(boot_l, leather, "leg-left")
part(mirror(boot_l, "boot-r"), leather, "leg-right")

# ---- hair: Rei's round bob, swept from a parting on her left ----------------------------------------------
hair = Hair((0, 0.030, 0.455), (0.140, 0.135, 0.1452), HAIR, flare=0.04, flare_depth=0.03, tuck=0.20, tuck_from=0.045, tuck_to=0.100,
            dome=2.4)
COLS, CLUMP = 84, 6
PHASE = 0.5


def bob(az):
    """The cap's hem: the hairline over the forehead, higher on her left where the tiara shows, over the top
    of the ears at the sides, then the nape, each clump coming to a point."""
    edge = float(np.interp(az, [-180, -124, -112, -106, -100, -88, -80, -70, -46, -20, 0, 20, 34, 50, 64, 74, 82, 90, 100, 106, 112, 124, 180],
                           [.354, .360, .372, .400, .422, .428, .452, .470, .499, .525, .540, .545, .534, .512, .492, .476, .456, .432, .422, .400, .372, .360, .354]))
    if abs(az) >= 104:
        u = (az * COLS / 360 / CLUMP + PHASE) % 1
        edge += 0.036 * abs(2 * u - 1) ** 0.9
    return edge


hair.cap(bob, cols=COLS, rows=12, rim_depth=0.016, ridges=(COLS // CLUMP, 0.13, 40, PHASE), parting=24,
         highlight=0.20, partings=0.40, parting_color="#152A5E", crown_shade=(0.25, 0.35))
hair.blade("fringe-a", [(0.050, 0.588), (0.020, 0.560), (-0.010, 0.524), (-0.030, 0.488), (-0.040, 0.458)],
           [.018, .066, .056, .030, .003], [.006, .020, .022, .016, .003], 11, seg=8, steps=3, strands=3)
hair.blade("fringe-b", [(0.022, 0.594), (-0.020, 0.568), (-0.052, 0.530), (-0.068, 0.494), (-0.074, 0.468)],
           [.018, .070, .060, .034, .003], [.006, .020, .022, .016, .003], 12, seg=8, steps=3, strands=3)
hair.blade("fringe-c", [(0.064, 0.582), (0.050, 0.556), (0.034, 0.528), (0.022, 0.506), (0.014, 0.490)],
           [.014, .042, .034, .018, .002], [.005, .016, .018, .012, .003], 13, seg=8, steps=3, strands=2)
for s, name in ((-1, "lock-right"), (1, "lock-left")):
    hair.blade(name, [(s * 0.094, -0.046, 0.548), (s * 0.112, -0.031, 0.500), (s * 0.116, -0.021, 0.450), (s * 0.112, -0.016, 0.400),
                      (s * 0.099, -0.014, 0.352)],
               [.018, .054, .048, .036, .002], [.004, .018, .022, .020, .003], 17 + s, seg=8, steps=3, strands=3)

# the head as a whole as on Tifa: the crown at 0.600 makes her 0.618 tall, as the office expects
scale_parts(HEAD_PARTS + ("tiara", "gem"), HEAD_PIVOT, 1.07)
assemble("ami", occlusion_size=2048, samples=32, fade_face_seam=True)
