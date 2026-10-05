# Mari, Animal Crossing style (D-207): built as the others are, on Tifa's proportions (head, body, arms,
# height); the hair, the face and the dress come from avatars-source/q/Mari.jpg (front), back/mari.jpg
# and stand-side/mari.jpg. Needs lib.py and figure.py. Brown hair parted on her left, the fringe in
# pointed locks over her right brow, a lock either side of the face, the back parted down the middle and
# gathered low into two tails with red bands; a blue headband with a white clip at each end; red glasses;
# green eyes; the pink plugsuit - a navy collar, "05" front and back, the red core, white panels down the
# sides of the chest, black stripes over the ribs, hips and legs, black upper arms with a disk at the
# shoulder, black wrist bands with a red tag, black fingers, black soles. The 9999 version: the budget goes
# on the hair (the cap's clumps, the fringe, the tails), the glasses, the headband and clips, and on what
# stands off the suit - the collar, the core, the disks, the wrist bands and tags.
reset("mari")
fit_arms()
PARTS.clear()

SKIN, HAIR = "#FCD6B6", "#4A2E27"
SUIT, SEAM, BLACK, WHITE = "#F29AA8", "#D27F90", "#3E3A4E", "#F4F0F6"
RED, RED_LIGHT, NAVY = "#B0303A", "#E05A5E", "#3E4E9E"
FRAME, FRAME_LIGHT, BAND, TIE = "#9A3438", "#C2585A", "#4258AE", "#9A2E3C"
DISK, DISK_DARK = "#B48EA4", "#6E5868"


def convex(PX, PZ, pts):
    """Signed distance (roughly) to a convex polygon, its corners anticlockwise."""
    d = np.full(PX.shape, -1e3)
    for (ax, az), (bx, bz) in zip(pts, pts[1:] + pts[:1]):
        ex, ez = bx - ax, bz - az
        n = math.hypot(ex, ez)
        d = np.maximum(d, ((PX - ax) * ez - (PZ - az) * ex) / n)
    return d


def glyph(cv, U, Z, ch, cx, cz, color, h=0.0066, w=0.0042, r=0.0010):
    """A "0" or a "5", drawn at (cx, cz) in the viewer's u (to the right) and z (up)."""
    if ch == "0":
        box = np.maximum(np.abs(U - cx) - w, np.abs(Z - cz) - h)
        cv.fill(color, np.abs(box + r * 1.6) - r)
    else:
        cv.fill(color, polyline(U, Z, [(cx + w - r, cz + h - r), (cx - w + r, cz + h - r)], r, samples=4))
        cv.fill(color, polyline(U, Z, [(cx - w + r, cz + h - r), (cx - w + r, cz + 0.0008)], r, samples=4))
        cv.fill(color, polyline(U, Z, [(cx - w + r, cz + 0.0008), (cx + 0.0012, cz + 0.0012), (cx + w - r, cz - 0.0022),
                                       (cx + 0.0010, cz - h + r), (cx - w + r, cz - h + r * 1.4)], r))


# ---- head (Tifa's), green eyes ------------------------------------------------------------------------
head, face = ac_head(SKIN, seg=32, rings=14)
ac_face(face, colors={"iris": "#3E5130", "brow": "#4E362C"})
x0, z0 = FACE_BOX[:2]
for s in (1, -1):
    cx, cz = s * 0.055, 0.437
    e = face.ellipse(cx - x0, cz - z0, 0.0235, 0.0232)
    iris = np.maximum(face.ellipse(cx + 0.0070 - x0, cz - 0.0005 - z0, 0.0152, 0.0222), e + 0.0018)
    face.put("#6E8A46", 0.8 * face.cover(iris) * np.clip((cz - z0 + 0.004 - face.Y) / 0.020, 0, 1) ** 1.2)   # the lower iris lit green
part(head, face, "head")
ac_ears(SKIN, radii=(0.034, 0.024, 0.031), seg=10, rings=7, soft_fold=True)
ac_nose()

# ---- the glasses: two rounded frames standing off the face, a bridge, arms back to the ears ---------------
def face_y(x, z):
    """The front of the head at (x, z): HEAD_PROFILE's superellipse."""
    zs = [p[0] for p in HEAD_PROFILE]
    rx, ry, pw = (float(np.interp(z, zs, [p[k] for p in HEAD_PROFILE])) for k in (1, 2, 3))
    return HEAD_Y - ry * max(0.0, 1 - abs(x / rx) ** pw) ** (1 / pw)


def rounded_rect(cx, cz, a, b, rc, n):
    """Points round a rounded rectangle (and the outward normal at each), anticlockwise from the right."""
    pts = []
    for k in range(n):
        t = 2 * math.pi * k / n
        dx, dz = math.cos(t), math.sin(t)
        # a superellipse with the corners rounded to about rc
        p = 2 + 2 * min(a, b) / rc
        sx, sz = math.copysign(abs(dx) ** (2 / p), dx), math.copysign(abs(dz) ** (2 / p), dz)
        pts.append((cx + a * sx, cz + b * sz))
    out = []
    for k, (x, z) in enumerate(pts):
        (xa, za), (xb, zb) = pts[k - 1], pts[(k + 1) % n]
        tx, tz = xb - xa, zb - za
        L = math.hypot(tx, tz)
        out.append(((x, z), (tz / L, -tx / L)))
    return out


EYE_X, EYE_Z = 0.055, 0.437
LENS_Y = face_y(EYE_X, EYE_Z) - 0.011
lens_y = lambda x: LENS_Y + 0.25 * (face_y(x, EYE_Z) - face_y(EYE_X, EYE_Z))
frame_c = Canvas("frame", 0.25, 0.02, 1400, FRAME)
frame_c.put(FRAME_LIGHT, 0.6 * np.exp(-((frame_c.Y / frame_c.height - 0.3) / 0.12) ** 2))
rim_rows = []
W, D = 0.0024, 0.0022                    # half the rim's width across, half its depth front to back
path = rounded_rect(EYE_X, EYE_Z, 0.0360, 0.0270, 0.010, 20)
for side_k, depth_k in ((-1, -1), (1, -1), (1, 1), (-1, 1), (-1, -1)):
    rim_rows.append([Vector((x + nx * W * side_k, lens_y(x) + D * depth_k, z + nz * W * side_k)) for (x, z), (nx, nz) in path])
lens = surface("glasses-l", rim_rows, inside=(EYE_X, LENS_Y, EYE_Z))
part(lens, frame_c, "head")
part(mirror(lens, "glasses-r"), frame_c, "head")
bridge = sweep("glasses-bridge", [(0.0192, lens_y(0.0192), 0.4430), (0.0, LENS_Y - 0.003, 0.4455), (-0.0192, lens_y(0.0192), 0.4430)],
               [0.0040] * 3, [0.0036] * 3, lambda c: c + Vector((0, 0, -1)), seg=6, steps=2, tip=False)
part(bridge, frame_c, "head")
temple = sweep("glasses-arm-l", [(0.0905, lens_y(0.0905), 0.4460), (0.1030, -0.050, 0.4475), (0.1065, -0.012, 0.4460), (0.1065, 0.022, 0.4400)],
               [0.0034] * 4, [0.0030] * 4, lambda c: c + Vector((-1, 0, 0)), seg=6, steps=2, tip=False)
part(temple, frame_c, "head")
part(mirror(temple, "glasses-arm-r"), frame_c, "head")

# ---- torso: the suit ---------------------------------------------------------------------------------------
TORSO = [(0.183, .032, .026, .022), (0.192, .049, .036, .022), (0.205, .057, .041, .021), (0.220, .054, .040, .020),
         (0.236, .0475, .038, .018), (0.250, .046, .039, .016), (0.258, .0465, .040, .0145), (0.272, .049, .044, .011),
         (0.280, .0495, .044, .011), (0.295, .050, .044, .012), (0.303, .0488, .042, .013), (0.312, .047, .040, .014),
         (0.322, .034, .030, .014), (0.330, .021, .021, .010), (0.352, .0185, .0185, .006)]


def bust(deg, z):
    """The suit's shape off the plain loft: a bust either side of the front, the seat behind."""
    mounds = sum(math.exp(-((deg - c) / 23) ** 2) for c in (-25, 25))
    seat = sum(math.exp(-((abs(deg) - c) / 28) ** 2) for c in (150,))
    return (0.015 * min(1.0, mounds) * smooth(0.258, 0.278, z) * (1 - smooth(0.286, 0.318, z))
            + 0.010 * seat * smooth(0.181, 0.194, z) * (1 - smooth(0.208, 0.236, z)))


# the stripes over the hips and thighs (her left side; the right is the mirror), in the figure's x and z
HIPS_FRONT = [[(0.060, 0.232), (0.0575, 0.205), (0.053, 0.178), (0.046, 0.143)], [(0.034, 0.222), (0.027, 0.203), (0.021, 0.188)]]
HIPS_BACK = [[(0.054, 0.232), (0.0605, 0.205), (0.0560, 0.175), (0.040, 0.149)], [(0.047, 0.228), (0.038, 0.205), (0.027, 0.184)]]


def hips(cv, AX, Z, front):
    d = np.full(AX.shape, 1e3)
    for pts in HIPS_FRONT:
        d = np.minimum(d, np.where(front, polyline(AX, Z, pts, 0.0030), 1e3))
    for pts in HIPS_BACK:
        d = np.minimum(d, np.where(front, 1e3, polyline(AX, Z, pts, 0.0030)))
    cv.fill(BLACK, d)


torso = surface("torso", bulged_rings(TORSO, 28, bust), start=(0, .022, 0.178), end=(0, .006, 0.354))
body = Canvas("torso", 2 * math.pi * 0.047, 0.20, 2300, SUIT)
y_of, Z = along(torso, [p[0] for p in TORSO], body)
DEG = (body.X / body.width - 0.5) * 360                                   # 0 = front, + toward her left
zs = [p[0] for p in TORSO]
RX = np.interp(Z, zs, [p[1] for p in TORSO])
XS = np.sin(np.radians(DEG)) * RX                                         # where each pixel is, seen from the front
AX = np.abs(XS)
FRONT = np.cos(np.radians(DEG)) > 0
fz = lambda d: np.where(FRONT, d, 1e3)
bz = lambda d: np.where(FRONT, 1e3, d)
# seams
body.fill(SEAM, fz(polyline(XS, Z, [(0, 0.255), (0, 0.183)], 0.0005)))
body.fill(SEAM, fz(polyline(AX, Z, [(0.045, 0.226), (0.028, 0.205), (0.010, 0.189), (0.0, 0.184)], 0.0005)))
body.fill(SEAM, bz(polyline(XS, Z, [(0, 0.255), (0, 0.183)], 0.0005)))
# the collar's V, the dark bars over the shoulders
body.fill(NAVY, fz(np.maximum(np.abs(XS) - 0.0050 * np.clip((Z - 0.3220) / 0.008, 0, 1), np.abs(Z - 0.326) - 0.004)))
for k, color in ((0.0, BLACK), (0.0055, "#6A2A36")):
    body.fill(color, polyline(AX, Z, [(0.0185 + k, 0.3285), (0.0270 + k, 0.3170), (0.0335 + k, 0.3040)], 0.0013))
# "05" on the chest, the black ring round the core
glyph(body, np.where(FRONT, XS, 1e3), Z, "0", -0.0052, 0.2965, BLACK)
glyph(body, np.where(FRONT, XS, 1e3), Z, "5", 0.0052, 0.2965, BLACK)
body.fill(BLACK, fz(np.hypot(XS, Z - 0.265) - 0.0088))
# the white panels down the sides of the chest, black-edged, and the black and white stripes over the ribs
fin = [(0.0590, 0.3000), (0.0450, 0.3060), (0.0360, 0.2500)]
body.fill(BLACK, fz(convex(AX, Z, fin) - 0.0016))
body.fill(WHITE, fz(convex(AX, Z, fin)))
for i, (a, b, color) in enumerate((((0.0560, 0.2700), (0.0400, 0.2440), BLACK), ((0.0570, 0.2560), (0.0430, 0.2330), WHITE),
                                   ((0.0575, 0.2440), (0.0445, 0.2220), BLACK), ((0.0575, 0.2320), (0.0465, 0.2140), BLACK))):
    body.fill(color, fz(polyline(AX, Z, [a, b], 0.0018 if color == BLACK else 0.0013)))
# behind: "05" between two black bars, the shoulder-blade panels running in to the spine, small chevrons
glyph(body, np.where(FRONT, 1e3, -XS), Z, "0", -0.0052, 0.3050, BLACK)
glyph(body, np.where(FRONT, 1e3, -XS), Z, "5", 0.0052, 0.3050, BLACK)
for k in (-1, 1):
    body.fill(BLACK, bz(polyline(XS, Z, [(k * 0.0165, 0.3150), (k * 0.0165, 0.2950)], 0.0012)))
body.fill(BLACK, bz(polyline(AX, Z, [(0.0300, 0.3180), (0.0310, 0.2950), (0.0230, 0.2750), (0.0080, 0.2560)], 0.0024)))
body.fill(BLACK, bz(polyline(AX, Z, [(0.0330, 0.2660), (0.0270, 0.2470)], 0.0026)))
# black down the sides under the arms
side = np.maximum(np.abs(np.abs(DEG) - 92) - 20 * np.clip((Z - 0.250) / 0.03, 0, 1), np.maximum(Z - 0.302, 0.250 - Z))
body.fill(BLACK, side * np.pi / 180 * 0.047)
hips(body, AX, Z, FRONT)
part(torso, body, "torso")


def torso_ring(z, k, seg=24):
    return ring((0, float(np.interp(z, zs, [p[3] for p in TORSO])), z), float(np.interp(z, zs, [p[1] for p in TORSO])) + k,
                float(np.interp(z, zs, [p[2] for p in TORSO])) + k, seg)


# the navy collar standing off the neck
collar_c = Canvas("collar", 2 * math.pi * 0.024, 0.016, 2400, NAVY)
collar_c.shade(0.80 + 0.32 * np.sin(np.pi * collar_c.Y / collar_c.height) ** 0.6)
collar_c.put("#6A7CCB", 0.35 * np.exp(-((collar_c.Y / collar_c.height - 0.62) / 0.12) ** 2))
part(surface("collar", [torso_ring(z, k) for z, k in ((0.3305, 0.0004), (0.3320, 0.0034), (0.3415, 0.0030), (0.3430, 0.0004))]), collar_c, "torso")

# the core: a red ball in its black ring
core_c = Canvas("core", 0.04, 0.02, 1600, RED)
core_c.shade(0.72 + 0.4 * core_c.Y / core_c.height)
core_c.put("#FFE2DA", 0.85 * np.exp(-((core_c.X / core_c.width - 0.43) / 0.05) ** 2 - ((core_c.Y / core_c.height - 0.76) / 0.08) ** 2))
part(ellipsoid("core", on_profile(TORSO, 0, 0.265, 0.0032, bulge=bust), (0.0066, 0.0046, 0.0066), 12, 6), core_c, "torso")

# ---- arms: black upper arms below a pink shoulder pad, pink forearms, black wrist bands, black fingers -------
ARM = [(0.048, .0165, .0165), (0.060, .0195, .0195), (0.075, .0190, .0190), (0.090, .0180, .0180), (0.110, .0172, .0172),
       (0.130, .0168, .0168), (0.148, .0170, .0170), (0.156, .0195, .0190), (0.162, .0238, .0228), (0.172, .0262, .0250),
       (0.186, .0264, .0252), (0.198, .0248, .0235), (0.207, .0208, .0195), (0.2125, .0140, .0130)]
AY, AZ = 0.017, 0.292
arm_l = surface("arm-l", [ring((x, AY, AZ), ry, rz, 14, plane="YZ", power=2.2) for x, ry, rz in ARM],
                start=(0.040, AY, AZ), end=(0.2155, AY, AZ))
sleeve = Canvas("arm", 2 * math.pi * 0.024, 0.176, 3200, SUIT)
y_of, AXP = along(arm_l, [p[0] for p in ARM], sleeve)
U = sleeve.X / sleeve.width                                               # 0 underneath, 0.25 the front, 0.5 on top, 0.75 behind
off_top = np.abs(U - 0.5) * sleeve.width                                  # metres round from the top line
pad = 0.017 * np.clip(1 - (AXP - 0.050) / 0.040, 0, 1) ** 0.8              # the shoulder pad, a drop pointing down the arm
panel = np.maximum.reduce([0.056 - AXP, AXP - 0.112 + 0.012 * (off_top / (0.5 * sleeve.width)), pad - off_top])
sleeve.fill(BLACK, panel)
sleeve.fill(SEAM, np.maximum(np.abs(off_top - pad) - 0.0005, np.maximum(AXP - 0.090, 0.056 - AXP)))   # the pad's edge
sleeve.fill(SEAM, sleeve.band(y_of(0.1595), y_of(0.1595) + 0.0007))        # where the glove begins
# the fingers curled under: black over the end of the hand and round its front
sleeve.fill(BLACK, np.where(AXP > 0.170, 0.192 - AXP - 0.012 * np.clip(1 - np.abs(U - 0.25) / 0.22, 0, 1), 1.0))
part(arm_l, sleeve, arm_weights("left"))
part(mirror(arm_l, "arm-r"), sleeve, arm_weights("right"))
thumb = ellipsoid("thumb-l", (0.184, AY - 0.024, AZ + 0.004), (0.011, 0.010, 0.010), 6, 4)
knuckle = Canvas("thumb", 0.03, 0.03, 1000, SUIT)
part(thumb, knuckle, "forearm-left")
part(mirror(thumb, "thumb-r"), knuckle, "forearm-right")

arm_r = lambda x: float(np.interp(x, [p[0] for p in ARM], [p[1] for p in ARM]))
# the disk on the shoulder pad, the black wrist band and its red tag
disk_c = Canvas("disk", 0.04, 0.012, 1600, DISK)
disk_c.fill(DISK_DARK, disk_c.band(0.64 * disk_c.height, 0.70 * disk_c.height))
disk_c.fill("#CBA9BB", disk_c.band(0.70 * disk_c.height, 0.86 * disk_c.height))
disk_c.fill(DISK_DARK, disk_c.band(0.86 * disk_c.height, disk_c.height))
disk_at = Vector((0.061, AY - math.sin(0.35) * (arm_r(0.061) + 0.0012), AZ + math.cos(0.35) * (arm_r(0.061) + 0.0012)))
disk = turn(ellipsoid("disk-l", disk_at, (0.0062, 0.0062, 0.0020), 12, 5), disk_at, (0.35, 0, 0))
cuff = wrap_band("cuff-l", (AY, AZ), arm_r, 0.141, 0.152, seg=14, plane="YZ", rise=0.0026)
cuff_c = Canvas("cuff", 2 * math.pi * 0.022, 0.014, 2000, BLACK)
cuff_c.shade(0.9 + 0.25 * np.sin(np.pi * cuff_c.Y / cuff_c.height))
tag_c = Canvas("tag", 0.03, 0.012, 1600, RED)
tag_c.fill(RED_LIGHT, tag_c.band(0.55 * tag_c.height, tag_c.height))
tag_r = arm_r(0.1465) + 0.0026 + 0.0010
tag_at = Vector((0.1465, AY - math.sin(0.55) * tag_r, AZ + math.cos(0.55) * tag_r))
tag = turn(ellipsoid("tag-l", tag_at, (0.0036, 0.0034, 0.0010), 8, 4, power=6), tag_at, (0.55, 0, 0))
for name, o, cv in (("disk", disk, disk_c), ("cuff", cuff, cuff_c), ("tag", tag, tag_c)):
    part(o, cv, arm_weights("left") if name == "disk" else "forearm-left")
    part(mirror(o, name + "-r"), cv, arm_weights("right") if name == "disk" else "forearm-right")

# ---- legs: the suit and the boot in one, from the sole to the hip (Rei's) -----------------------------------
LEGP = [(0.000, .041, .0262, .0470, .004, 2.4), (0.003, .041, .0292, .0502, .004, 2.4), (0.0095, .041, .0304, .0514, .004, 2.4),
        (0.017, .041, .0302, .0502, .005, 2.3), (0.028, .041, .0293, .0452, .009, 2.2), (0.039, .041, .0279, .0370, .014, 2.1),
        (0.050, .041, .0264, .0300, .018, 2.0), (0.060, .040, .0252, .0264, .020, 2.0), (0.068, .0395, .0240, .0246, .021, 2.0),
        (0.085, .0385, .0246, .0250, .021, 2.0), (0.100, .0375, .0240, .0244, .021, 2.0), (0.118, .0365, .0226, .0230, .021, 2.0),
        (0.135, .0355, .0236, .0240, .021, 2.0), (0.155, .0345, .0262, .0266, .021, 2.0), (0.175, .0340, .0282, .0286, .021, 2.0),
        (0.192, .0340, .0286, .0290, .021, 2.0), (0.205, .0340, .0255, .0260, .021, 2.0)]
leg_l = surface("leg-l", [ring((x, cy, z), rx, ry, 16, power=p) for z, x, rx, ry, cy, p in LEGP],
                start=(0.041, 0.004, 0.0), end=(0.034, 0.021, 0.209))
leg_c = Canvas("leg", 2 * math.pi * 0.03, 0.24, 2000, SUIT)
y_of, LZ = along(leg_l, [p[0] for p in LEGP], leg_c)
LDEG = (leg_c.X / leg_c.width - 0.5) * 360                                 # 0 = front, + outward
lzs = [p[0] for p in LEGP]
LCX, LRX = (np.interp(LZ, lzs, [p[k] for p in LEGP]) for k in (1, 2))
LX_ = LCX + np.sin(np.radians(LDEG)) * LRX
LFRONT = np.cos(np.radians(LDEG)) > 0
hips(leg_c, LX_, LZ, LFRONT)
LU = LDEG * np.pi / 180 * 0.023                                            # metres round from the front
# black slashes either side of the knee, one down the outside of the shin, and behind the knee
for pts in ([(-0.0150, 0.1200), (-0.0120, 0.1030)], [(0.0140, 0.1210), (0.0110, 0.1035)], [(0.0300, 0.1080), (0.0310, 0.0780)],
            [(0.0450, 0.1220), (0.0480, 0.0980)], [(0.0560, 0.1060), (0.0560, 0.0880)]):
    leg_c.fill(BLACK, polyline(LU, LZ, pts, 0.0020, samples=4))
leg_c.fill(SEAM, np.where(np.abs(LDEG) < 70, polyline(LU, LZ, [(-0.0125, 0.110), (-0.0062, 0.133), (0.0062, 0.133), (0.0125, 0.110)], 0.0005), 1e3))
# the boot: its top edge, the black sole coming up round the toe
leg_c.fill(SEAM, np.abs(LZ - 0.064) - 0.0004)
sole_top = 0.0075 + 0.012 * np.exp(-((np.abs(LDEG) - 52) / 26) ** 2) * (np.abs(LDEG) < 90) + 0.004 * np.exp(-((np.abs(LDEG) - 180) / 30) ** 2)
leg_c.fill(BLACK, LZ - sole_top)
leg_c.fill("#5A5468", np.abs(LZ - sole_top) - 0.0005, alpha=0.6)
part(leg_l, leg_c, "leg-left")
part(mirror(leg_l, "leg-r"), leg_c, "leg-right")

# ---- hair -------------------------------------------------------------------------------------------------
# One mass from a crown parted on her left: over the forehead under the fringe, above the ears, the back
# parted down the middle and drawn in to the nape, where it gathers into two red bands low at either side;
# the tails hang from them to the waist, splaying out. Three pointed locks of fringe over her right brow, a
# lock in front of each ear to the chin.
hair = Hair((0, 0.024, 0.468), (0.134, 0.130, 0.129), HAIR, flare=0.06, flare_depth=0.06, tuck=0.16, tuck_from=0.06, tuck_to=0.12, dome=2.2)
COLS, CLUMP = 84, 6


def hem(az):
    """The cap's hem: the hairline on her left forehead, above the ears, then the nape."""
    return float(np.interp(az, [-180, -150, -125, -110, -104, -75, -50, -20, 20, 29, 46, 60, 75, 90, 104, 110, 125, 150, 180],
                           [.350, .352, .360, .375, .452, .455, .500, .520, .535, .525, .515, .500, .485, .468, .452, .375, .360, .352, .350]))


hair.cap(hem, cols=COLS, rows=11, ridges=(COLS // CLUMP, 0.12, 40, 0.0), parting=179, grow=(0.35, 1.0), paint_grow=(0.1, 3.5),
         highlight=0.26, partings=0.55, parting_color="#2A1A16", sweep=0.6, crown_shade=(0.30, 0.35))
hair.blade("fringe-a", [(0.045, 0.585), (0.010, 0.556), (-0.016, 0.518), (-0.028, 0.484), (-0.031, 0.458)],
           [.020, .070, .060, .036, .004], [.008, .022, .024, .018, .005], 11, seg=8, steps=3, strands=3)
hair.blade("fringe-b", [(0.015, 0.592), (-0.022, 0.565), (-0.046, 0.525), (-0.058, 0.488), (-0.062, 0.462)],
           [.020, .076, .064, .040, .004], [.008, .022, .024, .018, .005], 12, seg=8, steps=3, strands=3)
hair.blade("fringe-c", [(-0.020, 0.588), (-0.060, 0.560), (-0.086, 0.522), (-0.097, 0.494), (-0.100, 0.470)],
           [.018, .064, .056, .034, .004], [.008, .020, .022, .016, .005], 13, seg=8, steps=3, strands=3)
for s, name in ((-1, "lock-right"), (1, "lock-left")):
    hair.blade(name, [(s * 0.094, -0.046, 0.548), (s * 0.112, -0.030, 0.500), (s * 0.117, -0.022, 0.450), (s * 0.113, -0.018, 0.400),
                      (s * 0.100, -0.016, 0.352)],
               [.018, .050, .046, .034, .002], [.004, .018, .022, .020, .003], 17 + s, seg=8, steps=3, strands=3)

# the back gathered into each band, the band, the tail
TIE_AT = Vector((0.086, 0.066, 0.334))
tie_c = Canvas("tie", 0.12, 0.02, 1400, TIE)
tie_c.shade(0.85 + 0.3 * np.abs(np.sin(tie_c.Y / tie_c.height * math.pi)))
for s, side in ((1, "l"), (-1, "r")):
    hair.mass(f"mass-{side}", [(s * 0.050, 0.098, 0.445), (s * 0.068, 0.096, 0.400), (s * 0.080, 0.080, 0.358), (s * 0.086, 0.068, 0.340)],
              [.100, .090, .060, .034], [.046, .052, .046, .032], 8, hang(0.32, 0.40), 0.14, 0.24, 21 + s, tip=False)
    part(sweep(f"tie-{side}", [(s * 0.0858, 0.0662, 0.3400), (s * 0.0866, 0.0660, 0.3290)], [.036, .036], [.034, .034], hair.axis, seg=10, tip=False),
         tie_c, "torso")
    hair.mass(f"tail-{side}", [(s * 0.0866, 0.0660, 0.3300), (s * 0.0960, 0.0660, 0.3020), (s * 0.1100, 0.0620, 0.2640),
                               (s * 0.1240, 0.0560, 0.2250), (s * 0.1340, 0.0520, 0.1880)],
              [.036, .066, .070, .050, .004], [.034, .054, .052, .036, .004], 8, "torso", 0.16, 0.19, 25 + s)

# the headband: lying on the hair from above one ear to above the other, a little forward of the crown,
# lifted where the clumps stand out (they grow in below the crown); its top at 0.600 is her height
BAND_Y = hair.c.y - 0.012
band_pts = []
for phi in np.radians(np.linspace(-80, 80, 13)):
    sx, sz = math.sin(phi), math.cos(phi)
    t = (abs(sx) ** hair.dome + abs(sz) ** hair.dome) ** (-1 / hair.dome)
    r = Vector((sx * hair.r.x * t, 0, sz * hair.r.z * t))
    band_pts.append(Vector((hair.c.x, BAND_Y, hair.c.z)) + r * (1 + 0.030 * smooth(0.35, 1.0, abs(phi))) + r.normalized() * 0.0012)
band_c = Canvas("headband", 0.03, 0.36, 1200, BAND)
band_c.put("#6E86D4", 0.5 * np.exp(-((band_c.X / band_c.width - 0.25) / 0.10) ** 2))
band = sweep("headband", band_pts, [0.0125] * len(band_pts), [0.0034] * len(band_pts), Vector((hair.c.x, BAND_Y, hair.c.z)), seg=6, steps=2, tip=False)
part(band, band_c, "head")

# a white clip at each end of the headband: a rounded triangle pointing forward, a black chevron on it
clip_c = Canvas("clip", 0.05, 0.05, 1400, "#FAFAF8")
clip_c.shade(1 - 0.10 * np.clip(np.hypot(clip_c.X - 0.025, clip_c.Y - 0.025) / 0.02, 0, 1) ** 2)
clip_c.fill(BLACK, clip_c.stroke([(0.0300, 0.0330), (0.0185, 0.0250), (0.0300, 0.0170)], 0.0016))
tri = [(-0.0170, 0.0), (0.0130, -0.0150), (0.0130, 0.0150)]


def rounded_tri(k, r=0.0045, n=8):
    """The triangle's outline rounded by ``r`` at each corner, scaled by k, in the plane's (x, z)."""
    pts = []
    for i, (vx, vz) in enumerate(tri):
        (px, pz), (qx, qz) = tri[i - 1], tri[(i + 1) % 3]
        a0 = math.atan2(-(vx - px), vz - pz)                 # outward normal of the edge coming in
        a1 = math.atan2(-(qx - vx), qz - vz)                 # and of the edge going out
        if a1 < a0:
            a1 += 2 * math.pi
        cx_, cz_ = vx * 0.72, vz * 0.72                      # the corner's centre, pulled in
        for j in range(n):
            a = a0 + (a1 - a0) * j / (n - 1)
            pts.append((k * (cx_ + r * math.cos(a)), k * (cz_ + r * math.sin(a))))
    return pts


phi = math.radians(78)
end = band_pts[-1]
out = Vector((math.sin(phi), 0, math.cos(phi)))
CLIP = end + out * 0.006 + Vector((0, -0.010, -0.012))
rows = [[Vector((CLIP.x + x, CLIP.y + y, CLIP.z + z)) for x, z in rounded_tri(k)] for k, y in ((0.80, -0.0040), (1.0, -0.0022), (1.0, 0.0022), (0.80, 0.0040))]
clip = surface("clip-l", [list(reversed(r)) for r in rows], start=(CLIP.x, CLIP.y - 0.0042, CLIP.z), end=(CLIP.x, CLIP.y + 0.0042, CLIP.z))
project_front(clip, CLIP.x - 0.025, CLIP.z - 0.025, 0.05, 0.05)
turn(clip, CLIP, (0, 0, math.pi / 2))                       # its face out to her left, its point forward
turn(clip, CLIP, (0, -(math.pi / 2 - phi), 0))              # tipped up with the side of the head
turn(clip, CLIP, (0, 0, -0.45))                            # and turned a little toward the front, as in the front view
part(clip, clip_c, "head")
part(mirror(clip, "clip-r"), clip_c, "head")

# the head as a whole as on Tifa: the crown at 0.600 makes her 0.618 tall, as the office expects
scale_parts(HEAD_PARTS + ("glasses", "headband", "clip"), HEAD_PIVOT, 1.07)
assemble("mari", occlusion_size=2048, samples=32, fade_face_seam=True)
