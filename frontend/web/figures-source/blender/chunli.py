# Chun-Li, Animal Crossing style (D-213): built as the others are, on Tifa's proportions (head, body, arms,
# height); the hair, the face and the dress come from avatars-source/q/ChunLi.jpg (front),
# back/chunli.jpg and stand-side/chunli.jpg. Needs lib.py and figure.py. Dark brown hair swept back into
# two buns behind the top of the head, under white silk covers frilled in gold, white ribbons hanging from
# them; a fringe swept across her right brow, a short lock before each ear, pearl earrings; the blue qipao
# - a mandarin collar trimmed gold, a gold placket curling across to her right, gold crescents on the
# breast, the back and the puffed sleeves, a white sash, a front and a back panel trimmed gold with the
# slits between - brown tights, spiked bracelets, white lace-up boots. The 9999 version: the budget goes on
# the hair, the buns, their frills and ribbons, and on what stands off the dress - the collar, the puffed
# sleeves, the sash, the two panels, the bracelets and their spikes.
reset("chunli")
fit_arms()
PARTS.clear()

SKIN, HAIR = "#FBCDAA", "#3A2A26"
BLUE, BLUE_DARK, GOLD, GOLD_DARK = "#2D4E96", "#203A74", "#DDA95C", "#A8763A"
WHITE, SILK_SHADE, TIGHTS, LEATHER, SILVER = "#F3ECEE", "#D9CDD6", "#5A3A30", "#3E3840", "#DCD8DE"
BOOT_WHITE, SOLE, LACE = "#F1EAEA", "#9C8274", "#BDB3B8"


def crescent(cv, AX, Z, cx, cz, mask, r=0.0140, scale=1.0):
    """A gold crescent with a curl beneath, its horns toward the middle and up (``AX``: across from the
    middle, mirrored, so the pair face each other)."""
    r *= scale
    d1 = np.hypot(AX - cx, Z - cz) - r
    d2 = np.hypot(AX - (cx - 0.0048 * scale), Z - (cz + 0.0052 * scale)) - 0.0118 * scale
    d = np.maximum(d1, -d2)
    tail = polyline(AX, Z, [(cx + 0.0010 * scale, cz - 0.0125 * scale), (cx + 0.0040 * scale, cz - 0.0175 * scale),
                            (cx + 0.0010 * scale, cz - 0.0220 * scale)], 0.0016 * scale, samples=8)
    d = np.minimum(d, tail)
    cv.fill(GOLD_DARK, np.where(mask, d - 0.0007, 1e3))
    cv.fill(GOLD, np.where(mask, d, 1e3))


# ---- head (Tifa's), pearl earrings ------------------------------------------------------------------------
head, face = ac_head(SKIN, seg=32, rings=14)
ac_face(face)
part(head, face, "head")
ac_ears(SKIN, radii=(0.034, 0.024, 0.031), seg=10, rings=7, soft_fold=True)
ac_nose()
pearl_c = Canvas("pearl", 0.03, 0.015, 1600, "#EDE6EA")
pearl_c.shade(0.78 + 0.35 * pearl_c.Y / pearl_c.height)
pearl_c.put("#FFFFFF", 0.8 * np.exp(-((pearl_c.X / pearl_c.width - 0.42) / 0.06) ** 2 - ((pearl_c.Y / pearl_c.height - 0.72) / 0.10) ** 2))
pearl = ellipsoid("earring-l", (0.1170, 0.0320, 0.3830), (0.0058, 0.0058, 0.0058), 8, 5)
part(pearl, pearl_c, "head")
part(mirror(pearl, "earring-r"), pearl_c, "head")

# ---- torso: the qipao above the sash, her tights below ----------------------------------------------------
TORSO = [(0.183, .032, .026, .022), (0.192, .049, .036, .022), (0.205, .057, .041, .021), (0.220, .054, .040, .020),
         (0.236, .0475, .038, .018), (0.250, .046, .039, .016), (0.258, .0465, .040, .0145), (0.272, .049, .044, .011),
         (0.280, .0495, .044, .011), (0.295, .050, .044, .012), (0.303, .0488, .042, .013), (0.312, .047, .040, .014),
         (0.322, .034, .030, .014), (0.330, .021, .021, .010), (0.352, .0185, .0185, .006)]


def bust(deg, z):
    """A full bust either side of the front, the seat behind."""
    mounds = sum(math.exp(-((deg - c) / 23) ** 2) for c in (-25, 25))
    seat = sum(math.exp(-((abs(deg) - c) / 28) ** 2) for c in (150,))
    return (0.0165 * min(1.0, mounds) * smooth(0.256, 0.276, z) * (1 - smooth(0.286, 0.318, z))
            + 0.010 * seat * smooth(0.181, 0.194, z) * (1 - smooth(0.208, 0.236, z)))


torso = surface("torso", bulged_rings(TORSO, 28, bust), start=(0, .022, 0.178), end=(0, .006, 0.354))
body = Canvas("torso", 2 * math.pi * 0.047, 0.20, 2300, BLUE)
y_of, Z = along(torso, [p[0] for p in TORSO], body)
DEG = (body.X / body.width - 0.5) * 360
zs = [p[0] for p in TORSO]
RX = np.interp(Z, zs, [p[1] for p in TORSO])
XS = np.sin(np.radians(DEG)) * RX
AX = np.abs(XS)
FRONT = np.cos(np.radians(DEG)) > 0
body.fill(TIGHTS, body.band(-1, y_of(0.2450)))
body.shade(0.92 + 0.10 * np.cos(np.radians(DEG)) ** 2)
# the placket: from the collar across to her right, a knot on it; the crescents on the breast and the back
placket = polyline(XS, Z, [(0.004, 0.3255), (-0.012, 0.3245), (-0.030, 0.3170), (-0.042, 0.3050), (-0.046, 0.2920)], 0.0012)
body.fill(GOLD_DARK, np.where(FRONT, placket - 0.0006, 1e3))
body.fill(GOLD, np.where(FRONT, placket, 1e3))
body.fill(GOLD, np.where(FRONT, polyline(XS, Z, [(-0.018, 0.3280), (-0.012, 0.3205)], 0.0011, samples=4), 1e3))
body.fill(GOLD, np.where(FRONT, np.hypot(XS + 0.015, Z - 0.3240) - 0.0024, 1e3))
crescent(body, AX, Z, 0.0350, 0.2900, FRONT)
crescent(body, AX, Z, 0.0310, 0.2920, ~FRONT, scale=0.9)
part(torso, body, "torso")


def torso_ring(z, k, seg=24):
    return ring((0, float(np.interp(z, zs, [p[3] for p in TORSO])), z), float(np.interp(z, zs, [p[1] for p in TORSO])) + k,
                float(np.interp(z, zs, [p[2] for p in TORSO])) + k, seg)


# the mandarin collar: blue, gold along its edges and either side of the opening
collar_c = Canvas("collar", 2 * math.pi * 0.026, 0.026, 2400, BLUE)
cu = (collar_c.X / collar_c.width - 0.5) * 360
collar_c.fill(GOLD, collar_c.band(0.80 * collar_c.height, collar_c.height))
collar_c.fill(GOLD, collar_c.band(-1, 0.10 * collar_c.height))
collar_c.fill(GOLD, np.abs(np.abs(cu) - 6.0) * np.pi / 180 * 0.026 - 0.0010)
collar_c.fill(BLUE_DARK, np.abs(cu) * np.pi / 180 * 0.026 - 0.0004)
for k in (-1, 1):                                                         # a little gold curl either side
    cx = (0.5 + k * 22 / 360) * collar_c.width
    collar_c.fill(GOLD, np.abs(collar_c.ellipse(cx, 0.45 * collar_c.height, 0.0030, 0.0030)) - 0.0006)
COLLAR_Z = [(0.3175, .0310, .0292, .0132), (0.3205, .0296, .0282, .0128), (0.3400, .0270, .0260, .0104), (0.3418, .0258, .0248, .0102),
            (0.3420, .0240, .0230, .0102)]
part(surface("collar", [ring((0, cy, z), rx, ry, 24) for z, rx, ry, cy in COLLAR_Z]), collar_c, "torso")

# the white sash
sash_c = Canvas("sash", 2 * math.pi * 0.05, 0.026, 2400, WHITE)
sash_c.shade(0.90 + 0.10 * np.sin(np.pi * sash_c.Y / sash_c.height))
for y in (0.35, 0.65):
    sash_c.fill(SILK_SHADE, np.abs(sash_c.Y - y * sash_c.height) - 0.0004, alpha=0.6)
part(surface("sash", [torso_ring(z, k, 32) for z, k in ((0.2440, 0.0006), (0.2452, 0.0042), (0.2668, 0.0040), (0.2680, 0.0006))]), sash_c, "torso")

# ---- the skirt: a front panel narrowing to its hem, a back panel flaring round the sides; the slits between
def panel(name, rows_, back):
    """An open sheet hanging from under the sash: rows (z, rx, ry, cy, half-angle), from the top down."""
    rows = []
    for z, rx, ry, cy, a in rows_:
        row = []
        for i in range(17):
            d = math.radians((180 if back else 0) - a + 2 * a * i / 16)
            row.append(Vector((math.sin(d) * rx, cy - math.cos(d) * ry, z)))
        rows.append(row)
    o = surface(name, rows, closed=False, inside=(0, 0.02, 0.2))
    rim(o, 0.0025, lambda co: Vector((0, 0.020, co.z)))
    return o


FRONT_PANEL = [(0.2460, .0500, .0440, .018, 37), (0.2300, .0560, .0480, .019, 36), (0.2100, .0610, .0520, .020, 34),
               (0.1900, .0640, .0560, .020, 32), (0.1700, .0660, .0590, .021, 31), (0.1420, .0680, .0620, .021, 30)]
BACK_PANEL = [(0.2460, .0500, .0440, .018, 40), (0.2300, .0580, .0520, .019, 42), (0.2100, .0660, .0600, .020, 46),
              (0.1900, .0720, .0660, .021, 50), (0.1700, .0770, .0700, .022, 53), (0.1420, .0820, .0740, .022, 56)]
for name, rows_, back in (("panel-front", FRONT_PANEL, False), ("panel-back", BACK_PANEL, True)):
    o = panel(name, rows_, back)
    cv = Canvas(name, 0.10 if not back else 0.13, 0.11, 2000, BLUE)
    cv.shade(0.92 + 0.10 * np.sin(np.pi * cv.X / cv.width))
    edge = np.minimum(np.minimum(cv.X, cv.width - cv.X), cv.height - cv.Y)          # from the sides and the hem
    cv.fill(GOLD, edge - 0.0045)
    cv.fill(GOLD_DARK, np.abs(edge - 0.0045) - 0.0005)
    cv.fill(GOLD_DARK, np.abs(edge) - 0.0004, alpha=0.6)

    def weights(co, back=back):
        """The front panel's lower half follows the legs, as a skirt's front does; the back one barely."""
        k = (0.30 if back else 0.75) * smooth(0.225, 0.150, co.z)
        left = smooth(-0.03, 0.03, co.x)
        return {"leg-left": k * left, "leg-right": k * (1 - left), "torso": 1 - k}

    part(o, cv, weights)

# ---- arms: bare, puffed sleeves trimmed gold, spiked bracelets ------------------------------------------
ARM = [(0.048, .0165, .0165), (0.062, .0198, .0198), (0.080, .0190, .0190), (0.100, .0180, .0180), (0.122, .0174, .0174),
       (0.140, .0172, .0172), (0.152, .0172, .0170), (0.156, .0215, .0205), (0.164, .0250, .0238), (0.176, .0264, .0251),
       (0.188, .0262, .0249), (0.199, .0246, .0233), (0.207, .0206, .0193), (0.2125, .0140, .0130)]
AY, AZ = 0.017, 0.292
arm_l = surface("arm-l", [ring((x, AY, AZ), ry, rz, 14, plane="YZ", power=2.2) for x, ry, rz in ARM],
                start=(0.040, AY, AZ), end=(0.2155, AY, AZ))
sleeve = Canvas("arm", 2 * math.pi * 0.024, 0.176, 3200, SKIN)
y_of, AXP = along(arm_l, [p[0] for p in ARM], sleeve)
sleeve.fill(BLUE, sleeve.band(-1, y_of(0.0900)))                           # under the puff
for u in (0.34, 0.45, 0.56, 0.67):                                        # between the fingers
    sleeve.fill("#DDA07E", sleeve.stroke([(u * sleeve.width, y_of(0.192)), (u * sleeve.width, y_of(0.209))], 0.0008))
part(arm_l, sleeve, arm_weights("left"))
part(mirror(arm_l, "arm-r"), sleeve, arm_weights("right"))
thumb = ellipsoid("thumb-l", (0.184, AY - 0.024, AZ + 0.004), (0.011, 0.010, 0.010), 6, 4)
knuckle = Canvas("thumb", 0.03, 0.03, 1000, SKIN)
part(thumb, knuckle, "forearm-left")
part(mirror(thumb, "thumb-r"), knuckle, "forearm-right")
arm_r = lambda x: float(np.interp(x, [p[0] for p in ARM], [p[1] for p in ARM]))

# the puffed sleeve: a round puff along the upper arm, a gold crescent on it, a scalloped gold-trimmed hem
PUFF = [(0.0440, .0220, .0220), (0.0500, .0290, .0300), (0.0600, .0330, .0345), (0.0720, .0345, .0360), (0.0840, .0335, .0350),
        (0.0940, .0300, .0315), (0.1000, .0250, .0262), (0.1030, .0215, .0225)]
puff = surface("puff-l", [ring((x, AY, AZ), ry, rz, 16, plane="YZ") for x, ry, rz in PUFF])
puff_c = Canvas("puff", 2 * math.pi * 0.032, 0.07, 2000, BLUE)
y_of, PXP = along(puff, [p[0] for p in PUFF], puff_c)
PU = puff_c.X / puff_c.width
puff_c.shade(0.85 + 0.20 * np.sin(np.pi * np.clip((PXP - 0.044) / 0.059, 0, 1)))
scallop = 0.0965 - 0.0025 * np.abs(np.sin(PU * math.pi * 10))             # the hem's scallops
puff_c.fill(GOLD, np.maximum(scallop - PXP, PXP - (scallop + 0.0035)))
puff_c.fill(BLUE_DARK, (scallop + 0.0035) - PXP)                            # the hem turned under
PUFF_ARC = (PU - 0.5) * 2 * math.pi * 0.032                              # metres round from the top (u = 0.5), the outside when it hangs
crescent(puff_c, PUFF_ARC, -PXP, 0.004, -0.0700, np.abs(PUFF_ARC) < 0.03, scale=0.65)   # up the arm is toward the shoulder
part(puff, puff_c, arm_weights("left"))
part(mirror(puff, "puff-r"), puff_c, arm_weights("right"))

# the bracelet: a black leather band, two silver spikes out at the sides of the wrist, two studs
band = wrap_band("bracelet-l", (AY, AZ), arm_r, 0.1380, 0.1545, seg=16, plane="YZ", rise=0.0055)
band_c = Canvas("bracelet", 2 * math.pi * 0.023, 0.02, 2000, LEATHER)
band_c.shade(0.85 + 0.25 * np.sin(np.pi * band_c.Y / band_c.height))
part(band, band_c, "forearm-left")
part(mirror(band, "bracelet-r"), band_c, "forearm-right")
spike_c = Canvas("spike", 0.03, 0.03, 1200, SILVER)
spike_c.put("#FFFFFF", 0.6 * np.exp(-((spike_c.X / spike_c.width - 0.25) / 0.08) ** 2))
spike_c.shade(0.75 + 0.35 * spike_c.Y / spike_c.height)
R_BAND = arm_r(0.1462) + 0.0055
for i, a in enumerate((0.0, math.pi, math.pi / 2, -math.pi / 2)):             # top and bottom: spikes; front and back: studs
    n = Vector((0, -math.sin(a), math.cos(a)))
    base = Vector((0.1462, AY, AZ)) + n * (R_BAND - 0.0010)
    if i < 2:
        o = sweep(f"spike-l{i}", [base, base + n * 0.0070, base + n * 0.0140], [0.0090, 0.0050, 0.0], [0.0090, 0.0050, 0.0],
                  lambda c, n=n: c - n.cross(Vector((1, 0, 0))), seg=6, steps=1)
    else:
        o = ellipsoid(f"spike-l{i}", base + n * 0.0010, (0.0050, 0.0050, 0.0050), 8, 4)
    part(o, spike_c, "forearm-left")
    part(mirror(o, f"spike-r{i}"), spike_c, "forearm-right")

# ---- legs in brown tights; white lace-up boots with a turned cuff ------------------------------------------
LX, LY = 0.040, 0.022
LEG = [(0.080, .0262), (0.100, .0278), (0.125, .0290), (0.150, .0312), (0.172, .0322), (0.190, .0285), (0.200, .0250)]
leg_l = surface("leg-l", [ring((LX, LY, z), r, r, 14) for z, r in LEG], start=(LX, LY, 0.078), end=(LX, LY, 0.203))
tights = Canvas("leg", 2 * math.pi * 0.029, 0.13, 2200, TIGHTS)
tights.put("#7A5446", 0.45 * np.cos(np.radians((tights.X / tights.width - 0.5) * 360)).clip(0, 1) ** 2)    # sheer where it faces you
part(leg_l, tights, "leg-left")
part(mirror(leg_l, "leg-r"), tights, "leg-right")
BOOT = [(0.0000, .0360, .0585, .0110, 2.6), (0.0040, .0385, .0610, .0110, 2.6), (0.0145, .0385, .0610, .0110, 2.6),
        (0.0170, .0360, .0585, .0110, 2.6), (0.0175, .0345, .0570, .0105, 2.6), (0.0320, .0372, .0585, .0080, 2.5),
        (0.0420, .0362, .0545, .0105, 2.4), (0.0490, .0340, .0470, .0160, 2.3), (0.0550, .0322, .0380, .0215, 2.2),
        (0.0590, .0315, .0345, .0230, 2.1), (0.0790, .0315, .0340, .0230, 2.0), (0.0800, .0318, .0343, .0228, 2.0),
        (0.0845, .0355, .0380, .0226, 2.0), (0.0985, .0358, .0383, .0225, 2.0), (0.1035, .0300, .0320, .0225, 2.0)]
boot_l = surface("boot-l", [ring((LX, cy, z), rx, ry, 16, power=p) for z, rx, ry, cy, p in BOOT],
                 start=(LX, 0.012, 0.0), end=(LX, 0.0225, 0.097))
boot_c = Canvas("boot", 2 * math.pi * 0.04, 0.21, 2200, BOOT_WHITE)
y_of, BZ = along(boot_l, [p[0] for p in BOOT], boot_c)
BDEG = (boot_c.X / boot_c.width - 0.5) * 360
BU = BDEG * np.pi / 180 * 0.034                                           # metres round from the front
boot_c.shade(0.90 + 0.10 * np.clip(BZ / 0.05, 0, 1))
boot_c.fill(SOLE, boot_c.band(-1, y_of(0.0172)))
boot_c.fill(SILK_SHADE, boot_c.band(y_of(0.0790), y_of(0.0815)))          # the crease under the turned cuff
lace = np.full(BZ.shape, 1e3)
for z in np.arange(0.036, 0.080, 0.008):                                  # the laces, crossing up the front
    lace = np.minimum(lace, polyline(BU, BZ, [(-0.0080, z), (0.0080, z + 0.008)], 0.0006, samples=4))
    lace = np.minimum(lace, polyline(BU, BZ, [(0.0080, z), (-0.0080, z + 0.008)], 0.0006, samples=4))
boot_c.fill(LACE, np.where(BZ < 0.080, lace, 1e3))
for z in np.arange(0.036, 0.081, 0.008):                                  # the eyelets
    for k in (-1, 1):
        boot_c.fill("#9C9298", np.hypot(BU - k * 0.0088, BZ - z) - 0.0011)
boot_c.fill(TIGHTS, boot_c.band(y_of(0.1033), 1))
part(boot_l, boot_c, "leg-left")
part(mirror(boot_l, "boot-r"), boot_c, "leg-right")

# ---- hair: swept up and back, short and neat at the nape, parted down the back; the fringe to her right -----
# pulled back tight: narrower than Tifa's hair, close over the head, so the buns stand out beside it
hair = Hair((0, 0.024, 0.468), (0.120, 0.126, 0.132), HAIR, flare=0.02, flare_depth=0.06, tuck=0.10, tuck_from=0.05, tuck_to=0.10, dome=2.2)
COLS, CLUMP = 84, 6


def hem(az):
    """The cap's hem: the hairline on her left forehead, above the ears, then a neat edge at the nape."""
    return float(np.interp(az, [-180, -150, -120, -106, -100, -75, -50, -20, 20, 29, 46, 60, 75, 90, 100, 106, 120, 150, 180],
                           [.377, .380, .392, .410, .452, .455, .500, .520, .535, .525, .515, .500, .485, .468, .452, .410, .392, .380, .377]))


hair.cap(hem, cols=COLS, rows=12, rim_depth=0.014, ridges=(COLS // CLUMP, 0.05, 40, 0.0), parting=179, grow=(0.3, 1.0),
         paint_grow=(0.1, 3.0), highlight=0.20, partings=0.35, parting_color="#1C1412", sweep=0.4)
hair.blade("fringe-a", [(0.045, 0.585), (0.010, 0.556), (-0.020, 0.518), (-0.032, 0.484), (-0.036, 0.457)],
           [.020, .072, .062, .040, .004], [.008, .022, .024, .018, .005], 11, seg=8, steps=3, strands=3)
hair.blade("fringe-b", [(0.015, 0.592), (-0.020, 0.565), (-0.046, 0.525), (-0.062, 0.484), (-0.068, 0.448)],
           [.020, .078, .066, .044, .004], [.008, .022, .024, .018, .005], 12, seg=8, steps=3, strands=3)
for s, name in ((-1, "lock-right"), (1, "lock-left")):
    hair.blade(name, [(s * 0.094, -0.046, 0.548), (s * 0.110, -0.030, 0.500), (s * 0.114, -0.021, 0.452), (s * 0.110, -0.016, 0.410)],
               [.016, .046, .040, .003], [.004, .016, .018, .003], 17 + s, seg=8, steps=3, strands=3)

# ---- the buns: white silk covers on two buns behind the top of the head, a gold-edged frill round each,
# two ribbons hanging from each to the shoulders
silk = Canvas("bun", 0.25, 0.10, 1400, WHITE)
silk.shade(0.88 + 0.14 * np.sin(np.pi * silk.Y / silk.height))
for k in range(8):                                                        # the cloth gathered toward the frill
    t = (silk.X / silk.width * 8 - k)
    silk.shade(1 - 0.06 * np.exp(-(t / 0.08) ** 2) * np.clip(1 - silk.Y / silk.height, 0, 1))
frill_c = Canvas("frill", 0.25, 0.012, 1400, WHITE)
frill_c.fill(GOLD, frill_c.band(0.70 * frill_c.height, frill_c.height))
frill_c.shade(0.85 + 0.20 * np.abs(np.sin(frill_c.X / frill_c.width * math.pi * 14)))
ribbon_c = Canvas("bun-ribbon", 0.05, 0.18, 1400, WHITE)
rX, rY = ribbon_c.X, ribbon_c.Y
ribbon_c.shade(0.90 + 0.10 * np.sin(np.pi * rX / ribbon_c.width))
ribbon_c.fill(GOLD, np.minimum(np.abs(rX - 0.06 * ribbon_c.width), np.abs(rX - 0.44 * ribbon_c.width)) - 0.0010)   # gold down both edges of the broad face
for dx, dy in ((0, 0), (-0.0028, -0.0028), (0.0028, -0.0028), (0, -0.0055)):                                          # a gold club near the end
    ribbon_c.fill(GOLD, np.hypot(rX - (0.25 * ribbon_c.width + dx), rY - (0.150 + dy)) - 0.0019)
BUN = Vector((0.1340, 0.0600, 0.5280))
out = (BUN - Vector((0, hair.c.y, hair.c.z))).normalized()
bun = ellipsoid("bun-l", BUN, (0.0420, 0.0420, 0.0440), 16, 8)
part(bun, silk, "head")
part(mirror(bun, "bun-r"), silk, "head")
# the frill: a wavy ring round where the bun meets the hair, facing out along ``out``
side = out.cross(Vector((0, 0, 1))).normalized()
up = side.cross(out).normalized()
frill_rows = []
for r, lift in ((0.0320, -0.0150), (0.0410, -0.0105), (0.0460, -0.0070)):
    row = []
    for i in range(36):
        t = 2 * math.pi * i / 36
        rr = r * (1 + (0.10 if r > 0.035 else 0.0) * math.sin(t * 9))
        row.append(BUN + out * lift + (side * math.cos(t) + up * math.sin(t)) * rr)
    frill_rows.append(row)
frill = surface("bun-frill-l", frill_rows, inside=BUN - out * 0.05)
part(frill, frill_c, "head")
part(mirror(frill, "bun-frill-r"), frill_c, "head")
for k, (dy, dx, end) in enumerate(((-0.010, 0.000, 0.330), (0.012, 0.010, 0.345))):
    top = BUN + Vector((0.006 + dx, dy, -0.032))
    pts = [top, top + Vector((0.010, 0.000, -0.050)), top + Vector((0.016, -0.004, -0.110)), Vector((top.x + 0.020, top.y - 0.006, end))]
    o = sweep(f"bun-ribbon-l{k}", pts, [0.020, 0.021, 0.022, 0.022], [0.0018] * 4, lambda c: c - Vector((0.35, -0.94, 0)), seg=4, steps=2, tip=False)   # facing forward, a little out
    part(o, ribbon_c, "head")
    part(mirror(o, f"bun-ribbon-r{k}"), ribbon_c, "head")

# the head as a whole as on Tifa: the crown at 0.600 makes her 0.618 tall, as the office expects
scale_parts(HEAD_PARTS + ("bun",), HEAD_PIVOT, 1.07)
assemble("chunli", occlusion_size=2048, samples=32, fade_face_seam=True)
