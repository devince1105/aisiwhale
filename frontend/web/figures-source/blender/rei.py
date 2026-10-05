# Rei, Animal Crossing style (D-204): built as Tifa and Ada are, on Tifa's proportions (head, body, arms, height);
# only the hair, the face and the dress come from the reference. Needs lib.py and figure.py. From
# avatars-source/q/Rei.jpg (front), back/rei.jpg and stand-side/rei.jpg: a pale-blue bob - a fringe of
# pointed clumps, a lock either side of the face to the chin, the ears showing beneath, the back in
# pointed clumps to the nape - with the two white interface clips; red eyes; the white plugsuit - a red
# collar, orange over the shoulders, "00" on the chest, the red core with a green plate either side,
# black upper arms with a white shoulder pad and a grey disk, cuffs with an orange tag, white mitts,
# black stripes over the hips front and back, a plate with "0" on the back, white boots on black soles.
# The 9999 version: the budget goes on the hair's clumps and fringe, and on what stands off the suit -
# the collar, the orange pieces, the disks, the core and plates, the cuffs and tags, the clips.
reset("rei")
fit_arms()
PARTS.clear()

SKIN, HAIR = "#FCD7BE", "#ADBEF0"
SUIT, SEAM = "#F4F1F3", "#C4BEC8"
BLACK = "#2E2A31"
ORANGE, ORANGE_LIGHT, ORANGE_DARK = "#EE7A22", "#F8A548", "#B9541A"
RED, RED_DARK, RED_LIGHT = "#B8262B", "#82191E", "#E25A52"
GREEN, GREEN_LIGHT, GREEN_DARK = "#4E9446", "#86C46E", "#2F6A30"
GREY, GREY_DARK = "#8A8590", "#45414B"


def polyline(PX, PZ, pts, r, samples=24):
    """Distance (minus r) from every (PX, PZ) to a smooth line through ``pts`` - for painting in the
    figure's own coordinates on a part whose canvas is wrapped round it."""
    P = [np.array(p, dtype=np.float64) for p in pts]
    curve = []
    for i in range(len(P) - 1):
        p0, p1, p2, p3 = P[max(i - 1, 0)], P[i], P[i + 1], P[min(i + 2, len(P) - 1)]
        for k in range(samples):
            t = k / samples
            curve.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    curve.append(P[-1])
    d = np.full(PX.shape, 1e3)
    for a, b in zip(curve, curve[1:]):
        ab = b - a
        t = np.clip(((PX - a[0]) * ab[0] + (PZ - a[1]) * ab[1]) / max(ab @ ab, 1e-12), 0, 1)
        d = np.minimum(d, np.hypot(PX - (a[0] + ab[0] * t), PZ - (a[1] + ab[1] * t)))
    return d - r


def project_front(o, x0, z0, width, height):
    """UVs straight from the front: a small part whose face is painted as it is seen."""
    for l in o.data.loops:
        co = o.data.vertices[l.vertex_index].co
        o.data.uv_layers[0].data[l.index].uv = ((co.x - x0) / width, (co.z - z0) / height)
    return o


# hip stripes, front and back (her left side; the right is the mirror): in the figure's x and z,
# drawn on the hips and the thighs alike
STRIPES_FRONT = [[(0.0590, 0.210), (0.0525, 0.192), (0.0365, 0.175)], [(0.0610, 0.187), (0.0550, 0.168), (0.0390, 0.151)]]
STRIPES_BACK = [[(0.0575, 0.230), (0.0510, 0.213), (0.0350, 0.198)], [(0.0600, 0.209), (0.0540, 0.191), (0.0370, 0.177)]]


def stripes(cv, AX, Z, front):
    d = np.full(AX.shape, 1e3)
    for pts in STRIPES_FRONT:
        d = np.minimum(d, np.where(front, polyline(AX, Z, pts, 0.0034), 1e3))
    for pts in STRIPES_BACK:
        d = np.minimum(d, np.where(front, 1e3, polyline(AX, Z, pts, 0.0034)))
    cv.fill(BLACK, d)


# ---- head (Tifa's), red eyes, a small smile -----------------------------------------------------------
head, face = ac_head(SKIN, seg=32, rings=14)
ac_face(face, colors={"iris": "#4A1A1E", "brow": "#5A5263", "mouth": SKIN})
x0, z0 = FACE_BOX[:2]
for s in (1, -1):
    cx, cz = s * 0.055, 0.437
    e = face.ellipse(cx - x0, cz - z0, 0.0235, 0.0232)
    iris = np.maximum(face.ellipse(cx + 0.0070 - x0, cz - 0.0005 - z0, 0.0152, 0.0222), e + 0.0018)
    glow = np.clip((cz - z0 + 0.006 - face.Y) / 0.020, 0, 1)                  # the lower half of the iris lit red
    face.put("#9C3234", 0.85 * face.cover(iris) * glow ** 1.2)
    face.put("#C8524A", 0.35 * face.cover(iris) * np.clip((cz - z0 - 0.010 - face.Y) / 0.008, 0, 1))
face.fill("#5E3328", face.stroke([(-0.0115 - x0, 0.4000 - z0), (-0.005 - x0, 0.3968 - z0), (0.005 - x0, 0.3968 - z0),
                                  (0.0115 - x0, 0.4000 - z0)], 0.0011, 0.0011, 0.0014))
part(head, face, "head")
ac_ears(SKIN, center=(0.106, 0.040, 0.403), radii=(0.028, 0.019, 0.026), seg=10, rings=7, soft_fold=True)
ac_nose(color="#F99254")

# ---- torso: the suit, with hips (no skirt over them) -----------------------------------------------------
TORSO = [(0.183, .032, .026, .022), (0.192, .049, .036, .022), (0.205, .057, .041, .021), (0.220, .054, .040, .020),
         (0.236, .0475, .038, .018), (0.250, .046, .039, .016), (0.258, .0465, .040, .0145), (0.272, .049, .044, .011),
         (0.280, .0495, .044, .011), (0.295, .050, .044, .012), (0.303, .0488, .042, .013), (0.312, .047, .040, .014),
         (0.322, .034, .030, .014), (0.330, .021, .021, .010), (0.352, .0185, .0185, .006)]


def bust(deg, z):
    """The suit's shape off the plain loft: a bust either side of the front, the seat behind."""
    mounds = sum(math.exp(-((deg - c) / 23) ** 2) for c in (-25, 25))
    seat = sum(math.exp(-((abs(deg) - c) / 28) ** 2) for c in (150,))
    return (0.014 * min(1.0, mounds) * smooth(0.258, 0.278, z) * (1 - smooth(0.286, 0.318, z))
            + 0.009 * seat * smooth(0.181, 0.194, z) * (1 - smooth(0.208, 0.236, z)))


torso = surface("torso", bulged_rings(TORSO, 28, bust), start=(0, .022, 0.178), end=(0, .006, 0.354))
body = Canvas("torso", 2 * math.pi * 0.047, 0.20, 2300, SUIT)
y_of, Z = along(torso, [p[0] for p in TORSO], body)
DEG = (body.X / body.width - 0.5) * 360                                   # 0 = front, + toward her left
zs = [p[0] for p in TORSO]
RX, RY, CY = (np.interp(Z, zs, [p[k] for p in TORSO]) for k in (1, 2, 3))
XS = np.sin(np.radians(DEG)) * RX                                         # where each pixel is, seen from the front
AX = np.abs(XS)
FRONT = np.cos(np.radians(DEG)) > 0
fz = lambda d: np.where(FRONT, d, 1e3)
bz = lambda d: np.where(FRONT, 1e3, d)
# seams: down the middle to the crotch, the V of the hips, under the chest, down the sides
body.fill(SEAM, fz(polyline(XS, Z, [(0, 0.229), (0, 0.183)], 0.0005)))
body.fill(SEAM, fz(polyline(AX, Z, [(0.050, 0.226), (0.030, 0.205), (0.010, 0.189), (0.0, 0.184)], 0.0005)))
body.fill(SEAM, fz(polyline(AX, Z, [(0.042, 0.254), (0.030, 0.242), (0.014, 0.232), (0.0, 0.229)], 0.0005)))
body.fill(SEAM, np.abs(np.abs(DEG) - 90) * np.pi / 180 * RX - 0.0005 + np.maximum(Z - 0.290, 0) * 10)
body.fill(SEAM, bz(polyline(XS, Z, [(0, 0.270), (0, 0.183)], 0.0005)))
# "00" on the chest, the black ring round the core and the line down from it
for k in (-1, 1):
    digit = np.maximum(np.abs(XS - k * 0.0054) - 0.0042, np.abs(Z - 0.292) - 0.0066)
    body.fill(BLACK, fz(np.abs(digit + 0.0018) - 0.0009))
body.fill(BLACK, fz(np.hypot(XS, Z - 0.265) - 0.0086))
body.fill(BLACK, fz(polyline(XS, Z, [(0, 0.262), (0, 0.231)], 0.0008)))
body.fill(BLACK, fz(np.hypot(XS, Z - 0.231) - 0.0013))
# the collar's red V and the black tabs beside it
body.fill(RED, fz(np.maximum(np.abs(XS) - 0.0055 * np.clip((Z - 0.3205) / 0.010, 0, 1), np.abs(Z - 0.326) - 0.006)))
for k in (-1, 1):
    body.fill(BLACK, fz(polyline(XS, Z, [(k * 0.0135, 0.3215), (k * 0.0205, 0.3195)], 0.0011)))
# black from under the orange to the armpit, down the sides under the arms, and from the back plate out
body.fill(BLACK, polyline(AX, Z, [(0.040, 0.300), (0.045, 0.287), (0.047, 0.274)], 0.0014))
side = np.maximum(np.abs(np.abs(DEG) - 92) - 22 * np.clip((Z - 0.248) / 0.03, 0, 1), np.maximum(Z - 0.302, 0.248 - Z))
body.fill(BLACK, side * np.pi / 180 * 0.047)
body.fill(BLACK, bz(polyline(AX, Z, [(0.016, 0.274), (0.030, 0.262), (0.044, 0.254)], 0.0024)))
stripes(body, AX, Z, FRONT)
part(torso, body, "torso")

# the red collar standing off the neck
def torso_ring(z, k, seg=24):
    return ring((0, float(np.interp(z, zs, [p[3] for p in TORSO])), z), float(np.interp(z, zs, [p[1] for p in TORSO])) + k,
                float(np.interp(z, zs, [p[2] for p in TORSO])) + k, seg)


collar_c = Canvas("collar", 2 * math.pi * 0.024, 0.016, 2400, RED)
collar_c.shade(0.80 + 0.32 * np.sin(np.pi * collar_c.Y / collar_c.height) ** 0.6)
collar_c.put(RED_LIGHT, 0.35 * np.exp(-((collar_c.Y / collar_c.height - 0.62) / 0.12) ** 2))
part(surface("collar", [torso_ring(z, k) for z, k in ((0.3285, 0.0004), (0.3300, 0.0036), (0.3415, 0.0032), (0.3430, 0.0004))]), collar_c, "torso")

# the orange pieces over the shoulders, black-edged
CHEST = Vector((0, 0.014, 0.27))
orange_c = Canvas("orange", 0.03, 0.30, 1400, ORANGE)
ou = orange_c.X / orange_c.width
orange_c.put(ORANGE_LIGHT, 0.6 * np.exp(-((ou - 0.25) / 0.10) ** 2))
orange_c.fill(BLACK, np.minimum(np.abs(ou - 0.0), np.minimum(np.abs(ou - 0.5), np.abs(ou - 1.0))) * orange_c.width - 0.0016)
for s in (1, -1):
    flat_strap(f"orange-{'l' if s > 0 else 'r'}", [(s * 48, 0.290), (s * 49, 0.303), (s * 55, 0.313), (s * 72, 0.3195), (s * 90, 0.321),
                                                    (s * 108, 0.3195), (s * 125, 0.313), (s * 131, 0.303), (s * 132, 0.290)],
               TORSO, CHEST, orange_c, width=0.0125, thick=0.0022, bulge=bust)

# the core: a red ball in its black ring; the green plates either side, under the chest
core_c = Canvas("core", 0.04, 0.02, 1600, RED)
core_c.shade(0.72 + 0.4 * core_c.Y / core_c.height)
core_c.put("#FFE2DA", 0.85 * np.exp(-((core_c.X / core_c.width - 0.43) / 0.05) ** 2 - ((core_c.Y / core_c.height - 0.76) / 0.08) ** 2))
part(ellipsoid("core", on_profile(TORSO, 0, 0.265, 0.0032, bulge=bust), (0.0066, 0.0046, 0.0066), 12, 6), core_c, "torso")
green_c = Canvas("green", 0.04, 0.02, 1600, GREEN)
green_c.shade(0.80 + 0.35 * green_c.Y / green_c.height)
green_c.fill(GREEN_LIGHT, green_c.band(0.66 * green_c.height, 0.74 * green_c.height), alpha=0.7)
for s in (1, -1):
    at = on_profile(TORSO, s * 33, 0.2525, 0.0014, bulge=bust)
    frame_buckle(f"green-{'l' if s > 0 else 'r'}", at, s * 33, green_c, (0.0112, 0.0016, 0.0056))

# the plate on the back, a "0" on it
plate_c = Canvas("plate", 0.03, 0.05, 2000, SUIT)
pd = plate_c.box(0.0092, 0.0145, 0.0208, 0.0355, 0.0022)
plate_c.fill(BLACK, np.abs(pd + 0.0007) - 0.0007)
plate_c.fill(RED_DARK, plate_c.box(0.0105, 0.0085, 0.0195, 0.0100, 0.0005))
plate_c.fill(SEAM, np.abs(plate_c.box(0.0012, 0.0022, 0.0288, 0.0478, 0.004)) - 0.0004)
PLATE = on_profile(TORSO, 180, 0.297, 0.0024)
plate = ellipsoid("plate", PLATE, (0.0140, 0.0028, 0.0235), 12, 4, power=6)
project_front(plate, PLATE.x - 0.015, PLATE.z - 0.025, 0.03, 0.05)
part(turn(plate, PLATE, (0, 0, math.pi)), plate_c, "torso")

# ---- arms: black upper arms with a white shoulder pad, white forearms, cuffs, white mitts ----------------
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
pad = 0.017 * np.clip(1 - (AXP - 0.050) / 0.046, 0, 1) ** 0.8              # the shoulder pad, a drop pointing down the arm
vee = 0.014 * np.clip((AXP - 0.103) / 0.015, 0, 1)                         # the forearm's white coming up in a V
panel = np.maximum.reduce([0.055 - AXP, AXP - 0.118 + 0.010 * (off_top / (0.5 * sleeve.width)), pad - off_top, vee - off_top])
sleeve.fill(BLACK, panel)
sleeve.fill(ORANGE, np.maximum(np.abs(AXP - 0.0525) - 0.0035, off_top - 0.020))       # the orange coming over the shoulder
sleeve.fill(BLACK, np.maximum(np.abs(off_top - pad) - 0.0006, np.maximum(AXP - 0.096, 0.055 - AXP)))   # the pad's edge
sleeve.fill(SEAM, sleeve.band(y_of(0.1595), y_of(0.1595) + 0.0007))        # where the mitt begins
part(arm_l, sleeve, arm_weights("left"))
part(mirror(arm_l, "arm-r"), sleeve, arm_weights("right"))
thumb = ellipsoid("thumb-l", (0.184, AY - 0.024, AZ + 0.004), (0.011, 0.010, 0.010), 6, 4)
knuckle = Canvas("thumb", 0.03, 0.03, 1000, SUIT)
part(thumb, knuckle, "forearm-left")
part(mirror(thumb, "thumb-r"), knuckle, "forearm-right")

arm_r = lambda x: float(np.interp(x, [p[0] for p in ARM], [p[1] for p in ARM]))
# the grey disk on the shoulder pad, the cuff, its orange tag
disk_c = Canvas("disk", 0.04, 0.012, 1600, GREY)
dv = disk_c.Y / disk_c.height
disk_c.fill(GREY_DARK, disk_c.band(0.64 * disk_c.height, 0.70 * disk_c.height))
disk_c.fill("#A39FA8", disk_c.band(0.70 * disk_c.height, 0.86 * disk_c.height))
disk_c.fill(GREY_DARK, disk_c.band(0.86 * disk_c.height, disk_c.height))
disk_at = Vector((0.063, AY - math.sin(0.35) * (arm_r(0.063) + 0.0012), AZ + math.cos(0.35) * (arm_r(0.063) + 0.0012)))
disk = turn(ellipsoid("disk-l", disk_at, (0.0064, 0.0064, 0.0020), 12, 5), disk_at, (0.35, 0, 0))
cuff = wrap_band("cuff-l", (AY, AZ), arm_r, 0.146, 0.1575, seg=14, plane="YZ", rise=0.0026)
cuff_c = Canvas("cuff", 2 * math.pi * 0.022, 0.014, 2000, SUIT)
cuff_c.shade(0.9 + 0.12 * np.sin(np.pi * cuff_c.Y / cuff_c.height))
tag_c = Canvas("tag", 0.03, 0.012, 1600, ORANGE)
tag_c.fill(ORANGE_LIGHT, tag_c.band(0.55 * tag_c.height, tag_c.height))
tag_c.fill(ORANGE_DARK, tag_c.band(0, 0.25 * tag_c.height))
tag_r = arm_r(0.152) + 0.0026 + 0.0010
tag_at = Vector((0.1518, AY - math.sin(0.55) * tag_r, AZ + math.cos(0.55) * tag_r))
tag = turn(ellipsoid("tag-l", tag_at, (0.0042, 0.0040, 0.0011), 8, 4, power=6), tag_at, (0.55, 0, 0))
fin_c = Canvas("fin", 0.04, 0.04, 1000, BLACK)
fin_c.put("#5A5560", 0.5 * np.exp(-((fin_c.X / fin_c.width - 0.25) / 0.08) ** 2))
fin = sweep("fin-l", [(0.100, AY, AZ + 0.012), (0.111, AY, AZ + 0.020), (0.125, AY, AZ + 0.028)], [0.017, 0.010, 0.0], [0.004, 0.003, 0.001],
            lambda c: c + Vector((0, 1, 0)), seg=6, steps=2)
for name, o, cv in (("disk", disk, disk_c), ("cuff", cuff, cuff_c), ("tag", tag, tag_c), ("fin", fin, fin_c)):
    part(o, cv, arm_weights("left") if name == "disk" else "forearm-left")
    part(mirror(o, name + "-r"), cv, arm_weights("right") if name == "disk" else "forearm-right")

# ---- legs: the suit and the boot in one, from the sole to the hip ------------------------------------------
# rows: z, centre x, radius across, radius front to back, centre y, squareness
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
stripes(leg_c, LX_, LZ, LFRONT)
# the knee pad's outline
leg_c.fill(SEAM, np.where(np.abs(LDEG) < 70, polyline(LDEG * np.pi / 180 * 0.022, LZ,
                                                     [(-0.0125, 0.110), (-0.0062, 0.133), (0.0062, 0.133), (0.0125, 0.110)], 0.0005), 1e3))
# the boot: its top edge, a black tab either side of the front, the black sole coming up round the toe
leg_c.fill(SEAM, np.abs(LZ - 0.064) - 0.0004)
for d in (-42, 42):
    tab = np.maximum(np.abs(LDEG - d) * np.pi / 180 * 0.023 - 0.0032 * np.clip((0.0635 - LZ) / 0.010, 0, 1), np.maximum(LZ - 0.0635, 0.0535 - LZ))
    leg_c.fill(BLACK, tab)
sole_top = 0.0075 + 0.012 * np.exp(-((np.abs(LDEG) - 52) / 26) ** 2) * (np.abs(LDEG) < 90) + 0.004 * np.exp(-((np.abs(LDEG) - 180) / 30) ** 2)
leg_c.fill(BLACK, LZ - sole_top)
leg_c.fill("#4A4550", np.abs(LZ - sole_top) - 0.0005, alpha=0.6)
part(leg_l, leg_c, "leg-left")
part(mirror(leg_l, "leg-r"), leg_c, "leg-right")

# ---- hair: a bob of pointed clumps ---------------------------------------------------------------------
# One mass from the crown, full on top, flaring a little and turning in at the ends; above the ears at the
# sides, down to the nape behind in about twenty clumps that come to points. A fringe of five pointed
# clumps, the middle one longest, between the eyes; a lock either side of the face to the chin, in front
# of the ear.
hair = Hair((0, 0.030, 0.455), (0.140, 0.135, 0.1452), HAIR, flare=0.04, flare_depth=0.03, tuck=0.20, tuck_from=0.045, tuck_to=0.100,
            dome=2.4)
COLS, CLUMP = 96, 6
PHASE = 0.5


def bob(az):
    """The cap's hem: the hairline over the forehead, over the top of the ears at the sides, then the
    nape, each clump coming to a point."""
    edge = float(np.interp(abs(az), [0, 20, 32, 46, 60, 70, 80, 88, 100, 106, 112, 124, 180],
                           [.540, .532, .517, .499, .480, .470, .452, .428, .422, .400, .372, .360, .354]))
    if abs(az) >= 104:
        u = (az * COLS / 360 / CLUMP + PHASE) % 1
        edge += 0.040 * abs(2 * u - 1) ** 0.9
    return edge


hair.cap(bob, cols=COLS, rows=13, rim_depth=0.016, ridges=(COLS // CLUMP, 0.13, 40, PHASE), parting=None,
         highlight=0.14, partings=0.24, parting_color="#6878BC", crown_shade=(0.16, 0.35))
FRINGE = [("fringe-c", [(0.004, 0.590), (0.004, 0.556), (0.002, 0.512), (0.000, 0.472), (-0.001, 0.444)], [.020, .060, .054, .030, .002]),
          ("fringe-r1", [(-0.022, 0.588), (-0.026, 0.553), (-0.030, 0.512), (-0.032, 0.482), (-0.033, 0.460)], [.020, .056, .050, .028, .002]),
          ("fringe-l1", [(0.030, 0.588), (0.029, 0.553), (0.026, 0.514), (0.023, 0.482), (0.020, 0.456)], [.020, .054, .048, .026, .002]),
          ("fringe-r2", [(-0.048, 0.584), (-0.058, 0.552), (-0.066, 0.522), (-0.070, 0.501), (-0.071, 0.486)], [.020, .056, .050, .028, .002]),
          ("fringe-l2", [(0.054, 0.584), (0.062, 0.552), (0.067, 0.524), (0.069, 0.503), (0.069, 0.489)], [.020, .056, .050, .028, .002]),
          ("fringe-r3", [(-0.070, 0.575), (-0.084, 0.545), (-0.093, 0.515), (-0.097, 0.492), (-0.098, 0.474)], [.018, .050, .044, .026, .002])]
for i, (name, pts, widths) in enumerate(FRINGE):
    hair.blade(name, pts, widths, [.004, .018, .020, .014, .003], 11 + i, seg=8, steps=3, strands=3)
for s, name in ((-1, "lock-right"), (1, "lock-left")):
    hair.blade(name, [(s * 0.094, -0.046, 0.548), (s * 0.110, -0.031, 0.500), (s * 0.114, -0.021, 0.450), (s * 0.110, -0.016, 0.400),
                      (s * 0.097, -0.014, 0.350)],
               [.018, .054, .048, .036, .002], [.004, .018, .022, .020, .003], 17 + s, seg=8, steps=3, strands=3)

# the interface clips: white pods lying on the hair at the sides of the crown, a black chevron and a red dot
clip_c = Canvas("clip", 0.04, 0.06, 1600, "#FCFBFC")
cu, cv_ = clip_c.X - 0.02, clip_c.Y - 0.03                                # from the pod's middle
clip_c.shade(1 - 0.10 * np.clip(np.hypot(cu / 0.013, cv_ / 0.024), 0, 1) ** 3)
clip_c.fill(BLACK, clip_c.stroke([(0.0245, 0.0505), (0.0230, 0.0470), (0.0175, 0.0330), (0.0205, 0.0180)], 0.0015))
clip_c.fill(RED, clip_c.ellipse(0.0275, 0.0360, 0.0012, 0.0012))
CLIP_AZ, CLIP_Z = math.radians(52), 0.532
k = hair.scale(CLIP_Z) * 1.03
CLIP = Vector((hair.c.x + hair.r.x * k * math.sin(CLIP_AZ), hair.c.y - hair.r.y * k * math.cos(CLIP_AZ), CLIP_Z))
CLIP += Vector((math.sin(CLIP_AZ), -math.cos(CLIP_AZ), 0.35)).normalized() * 0.008
clip = ellipsoid("clip-l", CLIP, (0.0140, 0.0075, 0.0260), 12, 6)
project_front(clip, CLIP.x - 0.02, CLIP.z - 0.03, 0.04, 0.06)
part(turn(clip, CLIP, (-0.45, 0, CLIP_AZ)), clip_c, "head")
part(mirror(clip, "clip-r"), clip_c, "head")

# the head as a whole as on Tifa; the crown at 0.600 makes her as tall as the others (0.618), as the office expects
scale_parts(HEAD_PARTS + ("clip",), HEAD_PIVOT, 1.07)
assemble("rei", occlusion_size=2048, samples=32, fade_face_seam=True)
