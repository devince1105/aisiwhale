# Shinobu, Animal Crossing style (D-210): built as the others are, on Tifa's proportions (head, body, arms,
# height); the hair, the face and the dress come from avatars-source/q/Shinobu.jpg (front),
# back/shinobu.jpg and stand-side/shinobu.jpg. Needs lib.py and figure.py. Near-black hair turning
# purple toward the ends, parted in the middle, to the shoulders, with a big butterfly ornament on the
# back of the head whose upper wings show above it from the front; purple eyes; the dark Demon Slayer
# uniform - gold buttons, a white collar, a white belt - under the butterfly haori, open at the front,
# white to mint to pink with black veins and black hems dotted white, wide sleeves; baggy trousers
# gathered at the calf, patterned leg wraps, purple tabi on white-soled sandals; the sword's hilt at her
# left hip. The 9999 version: the budget goes on the hair, the butterfly, the haori and its sleeves, and
# what stands off the uniform - the collar, the buttons, the belt and buckle, the sword.
reset("shinobu")
fit_arms()
PARTS.clear()

SKIN, HAIR, HAIR_END = "#FCD8BE", "#2E2228", "#6A4690"
JACKET, PANTS, SEAM = "#3E2C48", "#3A2843", "#2A1E32"
WHITE, MINT, PINK, VEIN, BLACK = "#F5EEF2", "#C6EBDB", "#F2B0D6", "#2A2430", "#2C2630"
GOLD, TEAL, ORANGE, LILAC, PURPLE = "#E8A94A", "#3F7C76", "#D9702E", "#A57FD0", "#6E3E98"


def net(cv, X, Y, period=0.030, slope=3.6, w=0.0004, color=VEIN, alpha=1.0):
    """The butterfly's veins: two families of steep lines crossing into long diamonds."""
    d = np.full(X.shape, 1e3)
    for k in (1, -1):
        t = (X * slope + k * Y) / math.hypot(slope, 1) / period
        d = np.minimum(d, np.abs(t - np.round(t)) * period)
    cv.fill(color, d - w, alpha=alpha)


def dotted_band(cv, X, Y, y0, y1, spacing=0.012, r=0.0034):
    """A black band from y0 to y1 with white dots along its middle."""
    cv.fill(BLACK, cv.band(y0, y1))
    t = X / spacing
    cv.fill(WHITE, np.hypot((t - np.round(t)) * spacing, Y - (y0 + y1) / 2) - r)


def purple_ends(cv, frac):
    """Hair darkening to purple over the part of the canvas ``frac`` (0 at the root, 1 at the ends) marks."""
    cv.put(HAIR_END, np.clip((frac - 0.55) / 0.40, 0, 1) ** 1.3 * 0.85)


# ---- head (Tifa's), purple eyes ---------------------------------------------------------------------------
head, face = ac_head(SKIN, seg=32, rings=14)
ac_face(face, colors={"iris": "#43296A", "brow": "#4A3640"})
x0, z0 = FACE_BOX[:2]
for s in (1, -1):
    cx, cz = s * 0.055, 0.437
    e = face.ellipse(cx - x0, cz - z0, 0.0235, 0.0232)
    iris = np.maximum(face.ellipse(cx + 0.0070 - x0, cz - 0.0005 - z0, 0.0152, 0.0222), e + 0.0018)
    face.put("#8C68C4", 0.8 * face.cover(iris) * np.clip((cz - z0 + 0.004 - face.Y) / 0.020, 0, 1) ** 1.2)
part(head, face, "head")
ac_ears(SKIN, radii=(0.034, 0.024, 0.031), seg=10, rings=7, soft_fold=True)
ac_nose()

# ---- torso: the jacket above the belt, the trousers below ---------------------------------------------------
TORSO = [(0.183, .032, .026, .022), (0.192, .049, .036, .022), (0.205, .057, .041, .021), (0.220, .054, .040, .020),
         (0.236, .0475, .038, .018), (0.250, .046, .039, .016), (0.258, .0465, .040, .0145), (0.272, .049, .044, .011),
         (0.280, .0495, .044, .011), (0.295, .050, .044, .012), (0.303, .0488, .042, .013), (0.312, .047, .040, .014),
         (0.322, .034, .030, .014), (0.330, .021, .021, .010), (0.352, .0185, .0185, .006)]


def bust(deg, z):
    """A small bust either side of the front, the seat behind."""
    mounds = sum(math.exp(-((deg - c) / 23) ** 2) for c in (-25, 25))
    seat = sum(math.exp(-((abs(deg) - c) / 28) ** 2) for c in (150,))
    return (0.008 * min(1.0, mounds) * smooth(0.258, 0.278, z) * (1 - smooth(0.286, 0.318, z))
            + 0.006 * seat * smooth(0.181, 0.194, z) * (1 - smooth(0.208, 0.236, z)))


torso = surface("torso", bulged_rings(TORSO, 28, bust), start=(0, .022, 0.178), end=(0, .006, 0.354))
body = Canvas("torso", 2 * math.pi * 0.047, 0.20, 2300, JACKET)
y_of, Z = along(torso, [p[0] for p in TORSO], body)
DEG = (body.X / body.width - 0.5) * 360
zs = [p[0] for p in TORSO]
RX = np.interp(Z, zs, [p[1] for p in TORSO])
XS = np.sin(np.radians(DEG)) * RX
FRONT = np.cos(np.radians(DEG)) > 0
fz = lambda d: np.where(FRONT, d, 1e3)
body.fill(PANTS, body.band(-1, y_of(0.240)))
body.fill(SEAM, fz(polyline(XS, Z, [(0, 0.318), (0, 0.183)], 0.0005)))                   # the jacket's front, the trousers' crease
body.fill(SEAM, np.abs(np.abs(DEG) - 90) * np.pi / 180 * RX - 0.0005, alpha=0.6)
body.fill(WHITE, fz(np.maximum(np.abs(XS - 0.040) - 0.0060, np.abs(Z - 0.2990) - 0.0016)))   # a white tab on her left breast
part(torso, body, "torso")


def torso_ring(z, k, seg=24):
    return ring((0, float(np.interp(z, zs, [p[3] for p in TORSO])), z), float(np.interp(z, zs, [p[1] for p in TORSO])) + k,
                float(np.interp(z, zs, [p[2] for p in TORSO])) + k, seg)


# the stand collar, white along its top; the white belt and its buckle; three gold buttons
collar_c = Canvas("collar", 2 * math.pi * 0.025, 0.022, 2400, JACKET)
collar_c.fill(WHITE, collar_c.band(0.64 * collar_c.height, collar_c.height))
collar_c.shade(0.85 + 0.25 * collar_c.Y / collar_c.height)
COLLAR_Z = [(0.3195, .0300, .0285, .0130), (0.3215, .0290, .0278, .0126), (0.3395, .0262, .0252, .0102), (0.3412, .0248, .0238, .0100),
            (0.3414, .0232, .0222, .0100)]
part(surface("collar", [ring((0, cy, z), rx, ry, 24) for z, rx, ry, cy in COLLAR_Z]), collar_c, "torso")
belt_c = Canvas("belt", 2 * math.pi * 0.05, 0.016, 2400, WHITE)
belt_c.shade(0.88 + 0.16 * np.sin(np.pi * belt_c.Y / belt_c.height))
part(surface("belt", [torso_ring(z, k, 32) for z, k in ((0.2385, 0.0004), (0.2395, 0.0026), (0.2515, 0.0026), (0.2525, 0.0004))]), belt_c, "torso")
buckle_c = Canvas("buckle", 0.03, 0.02, 2000, "#E4DDE2")
bd = buckle_c.box(0.0045, 0.0035, 0.0255, 0.0165, 0.0012)
buckle_c.fill("#A9A0AA", np.abs(bd) - 0.0006)
buckle_c.fill("#B8AFB8", buckle_c.box(0.0120, 0.0080, 0.0180, 0.0120, 0.0006))
BUCKLE_AT = on_profile(TORSO, 0, 0.2455, 0.0040, bulge=bust)
buckle = ellipsoid("buckle", BUCKLE_AT, (0.0100, 0.0018, 0.0068), 12, 4, power=8)
project_front(buckle, -0.015, BUCKLE_AT.z - 0.010, 0.03, 0.02)
part(buckle, buckle_c, "torso")
button_c = Canvas("button", 0.03, 0.015, 1600, GOLD)
button_c.shade(0.75 + 0.45 * button_c.Y / button_c.height)
button_c.put("#FFF2C8", 0.8 * np.exp(-((button_c.X / button_c.width - 0.44) / 0.06) ** 2 - ((button_c.Y / button_c.height - 0.72) / 0.10) ** 2))
for i, z in enumerate((0.3115, 0.2885, 0.2655)):
    part(ellipsoid(f"button-{i}", on_profile(TORSO, 0, z, 0.0018, bulge=bust), (0.0040, 0.0026, 0.0040), 10, 4), button_c, "torso")

# the sword's hilt at her left hip, under the haori's edge: a teal grip angled up across her, an orange guard
grip_c = Canvas("grip", 0.03, 0.06, 1600, TEAL)
gX, gY = grip_c.X, grip_c.Y
for k in (1, -1):                                                         # the wrapping's diamonds
    t = (gX * 1.0 + k * gY) / 0.0080
    grip_c.fill("#7FB7AE", np.abs(t - np.round(t)) * 0.0080 - 0.0007)
grip_c.fill("#2C2A32", grip_c.band(0.90 * grip_c.height, grip_c.height))   # the pommel
GUARD_AT = Vector((0.0400, -0.0520, 0.2500))
POMMEL = Vector((0.0160, -0.0660, 0.3020))
grip = sweep("sword-grip", [GUARD_AT, (GUARD_AT + POMMEL) / 2, POMMEL], [0.0090] * 3, [0.0090] * 3, lambda c: c + Vector((0, 1, 0)),
             seg=8, steps=2, tip=False)
part(grip, grip_c, "torso")
guard_c = Canvas("guard", 0.03, 0.03, 1600, ORANGE)
for a in range(4):                                                        # four petals, like a butterfly's wings
    t = math.radians(45 + 90 * a)
    guard_c.fill("#F29A55", guard_c.ellipse(0.015 + 0.0058 * math.cos(t), 0.015 + 0.0058 * math.sin(t), 0.0042, 0.0042))
    guard_c.fill("#9A4718", np.abs(guard_c.ellipse(0.015 + 0.0058 * math.cos(t), 0.015 + 0.0058 * math.sin(t), 0.0042, 0.0042)) - 0.0004)
guard = ellipsoid("sword-guard", GUARD_AT, (0.0105, 0.0105, 0.0016), 12, 3)
project_front(guard, GUARD_AT.x - 0.015, GUARD_AT.y - 0.015, 0.03, 0.03, axes=(0, 1))
turn(guard, GUARD_AT, Vector((0, 0, 1)).rotation_difference((POMMEL - GUARD_AT).normalized()).to_euler())
part(guard, guard_c, "torso")

# ---- the haori: open at the front, the gap widening toward the hem ----------------------------------------
# rows from the hem up: z, radius across, radius front to back, centre y, half-angle of the opening
HAORI = [(0.130, .080, .068, .020, 32), (0.150, .078, .066, .020, 31), (0.175, .075, .064, .020, 29), (0.200, .071, .062, .019, 27),
         (0.225, .066, .059, .018, 25), (0.250, .061, .057, .016, 24), (0.270, .0605, .0575, .013, 23), (0.290, .0595, .0565, .013, 22),
         (0.305, .0565, .052, .014, 21), (0.316, .050, .045, .014, 20), (0.3255, .0355, .0335, .013, 19)]
SPAN = 40
rows = []
for z, rx, ry, cy, a0 in HAORI:
    row = []
    for i in range(SPAN + 1):
        d = math.radians(a0 + (360 - 2 * a0) * i / SPAN)                 # from her left front edge round the back to her right
        row.append(Vector((math.sin(d) * rx, cy - math.cos(d) * ry, z)))
    rows.append(row)
haori = surface("haori", rows, closed=False, inside=(0, 0.016, 0.24))
rim(haori, 0.0028, lambda co: Vector((0, 0.016, co.z)))
coat = Canvas("haori", 0.36, 0.21, 1800, WHITE)
y_of, HZ = along(haori, [p[0] for p in HAORI], coat)
coat.put(MINT, np.clip(1 - np.abs(HZ - 0.225) / 0.050, 0, 1) ** 1.2 * 0.85)
coat.put(PINK, np.clip((0.200 - HZ) / 0.050, 0, 1) ** 1.1 * 0.9)
net(coat, coat.X, coat.Y)
coat.fill(WHITE, np.minimum(coat.X, coat.width - coat.X) - 0.0075)          # the plain band down each front edge
coat.fill(WHITE, coat.band(y_of(0.3215), coat.height + 1))                   # and round the neck
dotted_band(coat, coat.X, coat.Y, y_of(0.130) - 0.01, y_of(0.143))


def haori_w(co):
    """The front panels' lower half follows the legs, as a skirt's does; the rest stays with the torso."""
    k = 0.6 * smooth(0.215, 0.130, co.z) * smooth(0.025, -0.060, co.y)
    left = smooth(-0.03, 0.03, co.x)
    return {"leg-left": k * left, "leg-right": k * (1 - left), "torso": 1 - k}


part(haori, coat, haori_w)

# ---- arms: the jacket's dark sleeves, bare hands; the haori's wide sleeves over them -----------------------
ARM = [(0.048, .0165, .0165), (0.060, .0195, .0195), (0.075, .0190, .0190), (0.090, .0180, .0180), (0.110, .0172, .0172),
       (0.130, .0168, .0168), (0.148, .0170, .0170), (0.156, .0195, .0190), (0.162, .0238, .0228), (0.172, .0262, .0250),
       (0.186, .0264, .0252), (0.198, .0248, .0235), (0.207, .0208, .0195), (0.2125, .0140, .0130)]
AY, AZ = 0.017, 0.292
arm_l = surface("arm-l", [ring((x, AY, AZ), ry, rz, 14, plane="YZ", power=2.2) for x, ry, rz in ARM],
                start=(0.040, AY, AZ), end=(0.2155, AY, AZ))
sleeve = Canvas("arm", 2 * math.pi * 0.024, 0.176, 3200, JACKET)
y_of, AXP = along(arm_l, [p[0] for p in ARM], sleeve)
sleeve.fill(SEAM, sleeve.band(y_of(0.1500), y_of(0.1500) + 0.0008))
sleeve.fill(SKIN, sleeve.band(y_of(0.1530), sleeve.height + 1))
part(arm_l, sleeve, arm_weights("left"))
part(mirror(arm_l, "arm-r"), sleeve, arm_weights("right"))
thumb = ellipsoid("thumb-l", (0.184, AY - 0.024, AZ + 0.004), (0.011, 0.010, 0.010), 6, 4)
knuckle = Canvas("thumb", 0.03, 0.03, 1000, SKIN)
part(thumb, knuckle, "forearm-left")
part(mirror(thumb, "thumb-r"), knuckle, "forearm-right")

SLEEVE = [(0.046, .028, .028), (0.060, .032, .033), (0.080, .0355, .0370), (0.100, .0370, .0390), (0.120, .0380, .0400), (0.1405, .0385, .0410)]
haori_sleeve = surface("sleeve-l", [ring((x, AY, AZ - 0.002), ry, rz, 18, plane="YZ") for x, ry, rz in SLEEVE])
rim(haori_sleeve, 0.0028, lambda co: Vector((co.x, AY, AZ)))
cuff = Canvas("sleeve", 2 * math.pi * 0.036, 0.10, 2000, WHITE)
y_of, SXP = along(haori_sleeve, [p[0] for p in SLEEVE], cuff)
cuff.put(MINT, np.clip(1 - np.abs(SXP - 0.100) / 0.030, 0, 1) * 0.8)
cuff.put(PINK, np.clip((SXP - 0.110) / 0.020, 0, 1) * 0.9)
net(cuff, cuff.X, cuff.Y)
dotted_band(cuff, cuff.X, cuff.Y, y_of(0.1285), cuff.height + 0.01)
part(haori_sleeve, cuff, arm_weights("left"))
part(mirror(haori_sleeve, "sleeve-r"), cuff, arm_weights("right"))

# ---- legs: sandal, tabi, leg wrap and the baggy trousers in one, from the sole to the hip -------------------
# rows: z, centre x, radius across, radius front to back, centre y, squareness
LEGP = [(0.000, .041, .0250, .0440, .006, 2.4), (0.004, .041, .0272, .0465, .006, 2.4), (0.008, .041, .0272, .0465, .006, 2.4),
        (0.0095, .041, .0258, .0450, .006, 2.4), (0.022, .041, .0255, .0400, .009, 2.3), (0.034, .041, .0240, .0320, .014, 2.1),
        (0.046, .040, .0228, .0262, .018, 2.0), (0.060, .040, .0236, .0246, .020, 2.0), (0.075, .0395, .0244, .0250, .021, 2.0),
        (0.0855, .039, .0246, .0252, .021, 2.0), (0.0880, .039, .0290, .0296, .021, 2.0), (0.0940, .039, .0340, .0346, .021, 2.0),
        (0.1100, .039, .0372, .0378, .021, 2.0), (0.1350, .038, .0368, .0372, .021, 2.0), (0.1650, .036, .0345, .0350, .021, 2.0),
        (0.1900, .034, .0320, .0326, .021, 2.0), (0.2050, .034, .0280, .0285, .021, 2.0)]
leg_l = surface("leg-l", [ring((x, cy, z), rx, ry, 16, power=p) for z, x, rx, ry, cy, p in LEGP],
                start=(0.041, 0.006, 0.0), end=(0.034, 0.021, 0.209))
leg_c = Canvas("leg", 2 * math.pi * 0.033, 0.25, 2000, PANTS)
y_of, LZ = along(leg_l, [p[0] for p in LEGP], leg_c)
LDEG = (leg_c.X / leg_c.width - 0.5) * 360
leg_c.shade(1 + 0.10 * np.sin(np.radians(LDEG * 5)) * (LZ > 0.088))       # the trousers' soft folds
for d in range(-150, 180, 30):                                            # gathered into the cuff
    leg_c.fill(SEAM, np.maximum(np.abs(LDEG - d) * np.pi / 180 * 0.03 - 0.0004, np.maximum(LZ - 0.100, 0.088 - LZ)), alpha=0.7)
wrap = (LZ > 0.0455) & (LZ < 0.0875)
leg_c.fill(WHITE, np.maximum(0.0455 - LZ, LZ - 0.0875))                    # the leg wrap: white, pink toward the ankle, veined
leg_c.put(PINK, np.clip((0.068 - LZ) / 0.020, 0, 1) * 0.9 * wrap)
leg_c.put(MINT, 0.5 * np.exp(-((LZ - 0.072) / 0.008) ** 2) * wrap)
grid = np.full(LZ.shape, 1e3)
for k in (1, -1):
    t = (leg_c.X * 2.2 + k * leg_c.Y) / math.hypot(2.2, 1) / 0.016
    grid = np.minimum(grid, np.abs(t - np.round(t)) * 0.016)
leg_c.fill(VEIN, np.where(wrap, grid - 0.0004, 1e3))
leg_c.fill("#3C2A4C", np.maximum(0.0085 - LZ, LZ - 0.0455))                # purple tabi
leg_c.fill(LILAC, np.where(np.abs(LDEG) < 80, np.abs(LZ - (0.0200 + 0.0060 * np.cos(np.radians(LDEG)))) - 0.0030, 1e3))   # the sandal's strap
leg_c.fill("#ECE6EC", LZ - 0.0085)                                         # the sole
leg_c.fill("#B9AFC0", np.abs(LZ - 0.0085) - 0.0005)
part(leg_l, leg_c, "leg-left")
part(mirror(leg_l, "leg-r"), leg_c, "leg-right")

# ---- hair: parted in the middle, to the shoulders, purple toward the ends ----------------------------------
# the hair's centre a little back and its depth less than Tifa's, so that with no fringe it lies close over
# the forehead rather than standing off it like a visor
hair = Hair((0, 0.034, 0.468), (0.134, 0.122, 0.120), HAIR, flare=0.10, flare_depth=0.08, tuck=0.0, dome=2.2)
COLS, CLUMP = 96, 6
LEN = {3: .006, 4: .003, 5: .008, 6: .004, 7: .005, 8: -.030, 9: .005, 10: .007, 11: .003, 12: .006}     # the middle one behind stops short


def hem(az):
    """The cap's hem: from the parting down to each temple, over the tops of the ears, then to the
    shoulders, each clump coming to a point."""
    edge = float(np.interp(abs(az), [0, 8, 18, 30, 45, 58, 70, 84, 96, 104, 110, 125, 150, 180],
                           [.542, .536, .520, .498, .472, .455, .446, .430, .425, .420, .315, .302, .300, .302]))
    if abs(az) >= 108:
        t = az * COLS / 360 / CLUMP + 0.5
        u, k = t % 1, int(t // 1) % (COLS // CLUMP)
        edge += 0.022 * (1 - math.sin(math.pi * u) ** 0.7) - LEN.get(k, 0.0) * math.sin(math.pi * u)
    return edge


hair.cap(hem, cols=COLS, rows=13, rim_depth=0.014, ridges=(COLS // CLUMP, 0.12, 40, 0.5), parting=0, weights=hang(0.30, 0.38), grow=(0.35, 1.0),
         paint_grow=(0.1, 3.5), highlight=0.26, partings=0.55, parting_color="#140D12")
cap_c = PARTS[-1][1]
# purple below 0.43 or so: each pixel's height, from the cap's own rows (v runs from the crown to the hem)
AZ_ = cap_c.X / cap_c.width * 360 - 180
HEM = np.vectorize(hem)(AZ_)
polar = lambda z: np.where(z >= hair.c.z, np.arccos(np.clip((z - hair.c.z) / hair.r.z, -1, 1)), math.pi / 2 + (hair.c.z - z) / hair.r.z)
PH = polar(HEM) * np.clip(cap_c.Y / cap_c.height, 0, 1)
CZ = np.where(PH <= math.pi / 2, hair.c.z + hair.r.z * np.cos(PH), hair.c.z - (PH - math.pi / 2) * hair.r.z)
cap_c.put(HAIR_END, np.clip((0.420 - CZ) / 0.090, 0, 1) ** 1.2 * 0.85)
for s, name in ((-1, "lock-right"), (1, "lock-left")):
    hair.blade(name, [(s * 0.090, -0.050, 0.540), (s * 0.108, -0.036, 0.495), (s * 0.114, -0.026, 0.450), (s * 0.111, -0.020, 0.405),
                      (s * 0.102, -0.016, 0.366)],
               [.016, .052, .050, .040, .003], [.004, .018, .022, .020, .003], 17 + s, seg=8, steps=3, strands=3)
    purple_ends(PARTS[-1][1], PARTS[-1][1].Y / PARTS[-1][1].height)

# ---- the butterfly on the back of the head: purple-rimmed wings dotted white, pale veined inside ------------
B = Vector((0, hair.c.y + hair.r.y * 0.948 * 1.04 + 0.012, 0.512))  # on the hair behind, where its clumps stand out
bfly = Canvas("butterfly", 0.20, 0.22, 2000, PURPLE)
BX, BZ = bfly.X - 0.10, bfly.Y + 0.40 - B.z                         # from the butterfly's body
WINGS = [((0.060, 0.050), 0.050, 0.027, -40), ((0.030, -0.035), 0.040, 0.019, 60)]   # centre, half length, half width, tilt


def wing_frame(cx, cz, a, c, tilt, X, Z):
    """Coordinates along and across a wing, and a signed distance to its edge (negative inside)."""
    t = math.radians(-tilt)
    u = (X - cx) * math.cos(t) + (Z - cz) * math.sin(t)
    v = -(X - cx) * math.sin(t) + (Z - cz) * math.cos(t)
    k = np.sqrt((u / a) ** 2 + (v / c) ** 2) + 1e-9
    return u, v, (k - 1) * min(a, c)


AXB = np.abs(BX)
for (cx, cz), a, c, tilt in WINGS:
    u, v, d = wing_frame(cx, cz, a, c, tilt, AXB, BZ)
    inner = d + 0.0075
    bfly.put(MINT, np.clip(-inner / 0.004, 0, 1) * np.clip(np.hypot(AXB, BZ) / 0.07, 0.2, 1))
    bfly.put(WHITE, np.clip(-inner / 0.004, 0, 1) * np.clip(1 - np.hypot(AXB, BZ) / 0.05, 0, 1) * 0.8)
    ang = np.arctan2(v, u)                                         # veins: out from the body, and a few across
    vein = np.minimum(np.abs(np.sin(ang * 3)) * np.hypot(u, v) - 0.0005, np.abs(np.hypot(u, v) - 0.6 * a) - 0.0004)
    bfly.fill(VEIN, np.maximum(vein, inner))
    ring_t = np.arctan2(v / c, u / a)                               # white dots round the purple rim
    n = 16 if a > 0.045 else 11
    q = ring_t / (2 * math.pi) * n
    dot = np.hypot((q - np.round(q)) * 2 * math.pi / n * (a + c) / 2, d + 0.0038) - 0.0021
    bfly.fill(WHITE, dot)
part_list = []
for i, ((cx, cz), a, c, tilt) in enumerate(WINGS):
    w = ellipsoid(f"butterfly-{i}", (B.x + cx, B.y, B.z + cz), (a, 0.0022, c), 16, 4, power=2.3)
    turn(w, (B.x + cx, B.y, B.z + cz), (0, math.radians(tilt), 0))
    project_front(w, B.x - 0.10, 0.40, 0.20, 0.22)
    turn(w, B, (0, 0, -0.30 if i == 0 else -0.12))                  # folded forward round the head, the upper more
    part(w, bfly, "head")
    part(mirror(w, f"butterfly-{i}r"), bfly, "head")
body_ = ellipsoid("butterfly-body", B + Vector((0, 0.002, 0)), (0.0060, 0.0070, 0.0230), 10, 5)
project_front(body_, B.x - 0.10, 0.40, 0.20, 0.22)
part(body_, bfly, "head")

# the head as a whole as on Tifa: the butterfly's wings at 0.600 make her 0.618 tall, as the office expects
scale_parts(HEAD_PARTS + ("butterfly",), HEAD_PIVOT, 1.07)
assemble("shinobu", occlusion_size=2048, samples=32, fade_face_seam=True)
