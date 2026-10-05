# Ada, Animal Crossing style (D-199): built as Tifa (D-198) is, on her proportions - the owner keeps all
# the SG to Tifa's; Ada's own reference draws her legs too long. Needs lib.py and figure.py. Dress and
# hair from avatars-source/q/Ada.jpg (front), back/ada.jpg and stand-side/ada.jpg: a chin-length bob
# swept from a parting on her left, a red ribbed sleeveless turtleneck under a shoulder harness with
# two pouches, a belted black pencil skirt slit on her left, a holster on her left thigh, sheer dark
# tights, short fingerless gloves, black pumps.
reset("ada")
PARTS.clear()

SKIN, HAIR = "#FBCDB0", "#3D3238"
RED, RED_DARK, COLLAR = "#A52A33", "#7E1D27", "#8E2330"
STRAP, LEATHER, SKIRT, BELT = "#2F2B33", "#332A2D", "#352B2F", "#2A2428"
TIGHTS_DARK, TIGHTS_LIGHT, SHOE = "#3C2A28", "#7A5044", "#29222A"
METAL = "#B9B4B8"

# ---- head (Tifa's), with her face but no earrings -----------------------------------------------------
head, face = ac_head(SKIN)
ac_face(face, brows=(False, True))          # her right brow is under the fringe
part(head, face, "head")
ac_ears(SKIN)
ac_nose()

# ---- torso: the turtleneck, the harness ---------------------------------------------------------------
TORSO = [(0.190, .050, .042, .022), (0.215, .047, .040, .020), (0.236, .0455, .038, .018), (0.250, .046, .039, .016),
         (0.272, .049, .044, .011), (0.295, .050, .044, .012), (0.312, .047, .040, .014), (0.322, .034, .030, .014),
         (0.330, .021, .021, .010), (0.352, .0185, .0185, .006)]
torso = surface("torso", [ring((0, cy, z), rx, ry, 16) for z, rx, ry, cy in TORSO], start=(0, .022, 0.186), end=(0, .006, 0.354))
body = Canvas("torso", 2 * math.pi * 0.047, 0.19, 2300, SKIN)
y_of, Z = along(torso, [p[0] for p in TORSO], body)
DEG = (body.X / body.width - 0.5) * 360                                   # 0 = front, + toward her left
xd = lambda deg: (0.5 + deg / 360) * body.width
# how far across from the middle each pixel is, so the armholes can be cut by it
XW = np.abs(np.interp(Z, [p[0] for p in TORSO], [p[1] for p in TORSO]) * np.sin(np.radians(DEG)))
armhole = np.interp(XW, [0, 0.022, 0.030, 0.040, 0.050, 0.07], [1, 1, 0.332, 0.312, 0.300, 0.296])
inside = np.maximum(Z - armhole, 0.230 - Z)
body.fill(RED, inside)
body.shade(np.where(inside < 0, 1 - 0.09 * (0.5 + 0.5 * np.sin(2 * math.pi * body.X / 0.0032)), 1.0))   # the ribbing
body.fill(COLLAR, np.maximum(inside, 0.3345 - Z))                          # the turned-down collar
body.fill(RED_DARK, np.abs(Z - 0.3345) - 0.0006)
body.fill(RED_DARK, np.where(XW > 0.024, np.abs(Z - armhole) - 0.0007, 1.0), alpha=0.8)    # the armhole's edge
body.fill(SKIRT, body.band(-1, y_of(0.232)))                               # under the skirt
for s in (1, -1):
    # a harness strap: down the front, over the shoulder, down the back
    body.fill(STRAP, body.stroke([(xd(s * 58), y_of(0.250)), (xd(s * 57), y_of(0.290)), (xd(s * 54), y_of(0.310)),
                                  (xd(s * 64), y_of(0.3215)), (xd(s * 90), y_of(0.325)), (xd(s * 116), y_of(0.3215)),
                                  (xd(s * 126), y_of(0.310)), (xd(s * 123), y_of(0.290)), (xd(s * 122), y_of(0.264))], 0.0044))
    for d, z in ((57, 0.302), (123, 0.300)):                               # their keepers
        x, y = xd(s * d), y_of(z)
        body.fill(METAL, body.box(x - 0.005, y - 0.003, x + 0.005, y + 0.003, 0.0008))
        body.fill(STRAP, body.box(x - 0.0032, y - 0.0015, x + 0.0032, y + 0.0015, 0.0004))
body.fill(STRAP, np.maximum(body.band(y_of(0.2475), y_of(0.2555)), np.abs(DEG) - 60))         # across the front
body.fill(STRAP, np.maximum(body.band(y_of(0.2620), y_of(0.2700)), 120 - np.abs(DEG)))        # across the back
for d, z in ((22, 0.2515), (180, 0.266), (-180, 0.266)):
    x, y = xd(d), y_of(z)
    body.fill(METAL, body.box(x - 0.0058, y - 0.0058, x + 0.0058, y + 0.0058, 0.001))
    body.fill(STRAP, body.box(x - 0.0034, y - 0.0034, x + 0.0034, y + 0.0034, 0.0005))
    body.fill(METAL, body.box(x - 0.0008, y - 0.0034, x + 0.0008, y + 0.0034))
part(torso, body, "torso")

# the pouches on the harness, at the sides of her chest
pouch_c = Canvas("pouch", 0.08, 0.04, 1600, LEATHER)
pouch_c.fill("#24201F", pouch_c.band(0.62 * pouch_c.height, 0.64 * pouch_c.height))           # the flap's edge
pouch_c.fill("#4A4144", pouch_c.ellipse(0.5 * pouch_c.width, 0.75 * pouch_c.height, 0.0018, 0.0018))   # a snap
pouch_c.shade(0.85 + 0.25 * pouch_c.Y / pouch_c.height)
pouch = ellipsoid("pouch-l", (0.045, -0.021, 0.272), (0.0105, 0.0085, 0.0185), 8, 5, power=3.5)
part(pouch, pouch_c, "torso")
part(mirror(pouch, "pouch-r"), pouch_c, "torso")

# ---- arms: bare, with short fingerless gloves ---------------------------------------------------------
ARM = [(0.048, .0165, .0165), (0.062, .0195, .0195), (0.080, .0185, .0185), (0.100, .0172, .0172), (0.122, .0166, .0166),
       (0.1420, .0162, .0162), (0.1425, .0205, .0200), (0.1555, .0210, .0204), (0.1560, .0262, .0252), (0.1700, .0285, .0272),
       (0.1860, .0276, .0262), (0.1865, .0245, .0225), (0.202, .0238, .0215), (0.210, .0180, .0162)]
AY, AZ = 0.017, 0.292
arm_l = surface("arm-l", [ring((x, AY, AZ), ry, rz, 12, plane="YZ", power=2.2) for x, ry, rz in ARM],
                start=(0.040, AY, AZ), end=(0.2155, AY, AZ))
sleeve = Canvas("arm", 2 * math.pi * 0.024, 0.176, 3200, SKIN)
y_of, _ = along(arm_l, [p[0] for p in ARM], sleeve)
top = 0.5 * sleeve.width                                                  # u = 0.5 is the top of the arm
sleeve.fill(STRAP, sleeve.band(y_of(0.1425), y_of(0.1558)))               # the cuff, buckled on top
sleeve.fill(METAL, sleeve.box(top - 0.0045, y_of(0.1435), top + 0.0045, y_of(0.1548), 0.0008))
sleeve.fill(STRAP, sleeve.box(top - 0.0026, y_of(0.1455), top + 0.0026, y_of(0.1528), 0.0004))
sleeve.fill(LEATHER, sleeve.band(y_of(0.1558), y_of(0.1863)))             # the glove over the hand
sleeve.fill("#4A3E40", sleeve.band(y_of(0.1558), y_of(0.1558) + 0.0012))
sleeve.fill("#1E191B", sleeve.band(y_of(0.1848), y_of(0.1863)))
sleeve.fill("#1E191B", sleeve.ellipse(top, y_of(0.1715), 0.0068, 0.0058))  # the opening on the back of the hand
sleeve.fill(SKIN, sleeve.ellipse(top, y_of(0.1715), 0.0055, 0.0045))
for u in (0.34, 0.45, 0.56, 0.67):                                        # between the fingers
    sleeve.fill("#DDA07E", sleeve.stroke([(u * sleeve.width, y_of(0.190)), (u * sleeve.width, y_of(0.209))], 0.0008))
arm_w = lambda side: (lambda co: {f"arm-{side}": smooth(0.062, 0.100, abs(co.x)), "torso": 1 - smooth(0.062, 0.100, abs(co.x))})
part(arm_l, sleeve, arm_w("left"))
part(mirror(arm_l, "arm-r"), sleeve, arm_w("right"))
thumb = ellipsoid("thumb-l", (0.184, AY - 0.024, AZ + 0.004), (0.011, 0.010, 0.010), 6, 4)
knuckle = Canvas("thumb", 0.03, 0.03, 1000, SKIN)
part(thumb, knuckle, "arm-left")
part(mirror(thumb, "thumb-r"), knuckle, "arm-right")

# ---- skirt: a belted pencil skirt, slit up the front of her left thigh --------------------------------
SKIRT_Z = [(0.166, .067, .056, .022), (0.190, .066, .055, .021), (0.214, .062, .052, .020), (0.232, .056, .047, .019),
           (0.246, .050, .043, .018)]
skirt = surface("skirt", [ring((0, cy, z), rx, ry, 32) for z, rx, ry, cy in SKIRT_Z])
cloth = Canvas("skirt", 2 * math.pi * 0.062, 0.085, 2400, SKIRT)
y_of, Z = along(skirt, [p[0] for p in SKIRT_Z], cloth)
SDEG = (cloth.X / cloth.width - 0.5) * 360
cloth.shade(0.92 + 0.14 * np.cos(np.radians(SDEG)) ** 2)                   # a dull sheen down the front and back
slit = (0.5 + 30 / 360) * cloth.width
gap = np.maximum(np.abs(cloth.X - slit) - 0.0035 * np.clip((y_of(0.200) - cloth.Y) / (y_of(0.200) - y_of(0.166)), 0, 1),
                 cloth.Y - y_of(0.200))
cloth.fill(TIGHTS_DARK, gap)
cloth.fill("#211B1E", np.abs(gap) - 0.0007)
for d in (90, -90):                                                       # side seams
    cloth.fill("#2A2226", cloth.column((0.5 + d / 360) * cloth.width - 0.0005, (0.5 + d / 360) * cloth.width + 0.0005))
cloth.fill("#2A2226", cloth.band(y_of(0.166), y_of(0.166) + 0.0012))
cloth.fill(BELT, cloth.band(y_of(0.2285), y_of(0.246)))                   # the belt
for z in (0.2295, 0.2445):
    cloth.fill("#3D3539", cloth.band(y_of(z) - 0.0004, y_of(z) + 0.0004))
for d, w in ((10, 0.0075), (-34, 0.0055)):                                # its buckles
    x, y = (0.5 + d / 360) * cloth.width, y_of(0.2372)
    cloth.fill(METAL, cloth.box(x - w, y - 0.0068, x + w, y + 0.0068, 0.0012))
    cloth.fill(BELT, cloth.box(x - w + 0.0022, y - 0.0046, x + w - 0.0022, y + 0.0046, 0.0006))
    cloth.fill(METAL, cloth.box(x - 0.0008, y - 0.0046, x + 0.0008, y + 0.0046))
hx = (0.5 + 52 / 360) * cloth.width                                       # the holster's drop strap
cloth.fill(STRAP, np.maximum(np.abs(cloth.X - hx) - 0.0035, cloth.Y - y_of(0.230)))


def skirt_w(co):
    """The front of the hem follows the legs a little (so it lifts over the thighs when she sits); the
    belt and the back stay with the torso."""
    k = 0.5 * smooth(0.214, 0.166, co.z) * min(1.0, max(0.0, -(co.y - 0.02) / 0.07)) ** 0.6
    left = smooth(-0.03, 0.03, co.x)
    return {"leg-left": k * left, "leg-right": k * (1 - left), "torso": 1 - k}


part(skirt, cloth, skirt_w)

# ---- legs in sheer tights; a holster on her left thigh ------------------------------------------------
LX, LY = 0.037, 0.022
LEG = [(0.034, .0150), (0.050, .0152), (0.068, .0190), (0.088, .0222), (0.106, .0212), (0.124, .0232), (0.148, .0272),
       (0.172, .0288), (0.205, .0280)]
leg_l = surface("leg-l", [ring((LX, LY, z), r, r * 1.05, 12) for z, r in LEG], start=(LX, LY, 0.032), end=(LX, LY, 0.207))
nylon = Canvas("leg", 2 * math.pi * 0.025, 0.18, 2200, TIGHTS_DARK)
y_of, _ = along(leg_l, [p[0] for p in LEG], nylon)
front = np.clip(np.cos(np.radians((nylon.X / nylon.width - 0.5) * 360)), 0, 1)
nylon.put(TIGHTS_LIGHT, 0.85 * front ** 1.6)                              # sheer: the skin shows most where it faces you
nylon.put("#8B5D4E", 0.25 * np.exp(-((nylon.Y - y_of(0.106)) / 0.008) ** 2) * front)   # the knee
part(leg_l, nylon, "leg-left")
part(mirror(leg_l, "leg-r"), nylon, "leg-right")

garter = Canvas("garter", 2 * math.pi * 0.03, 0.01, 2000, STRAP)
garter.fill(METAL, garter.box(0.5 * garter.width - 0.004, 0.0015, 0.5 * garter.width + 0.004, 0.0085, 0.0008))
garter.fill(STRAP, garter.box(0.5 * garter.width - 0.0022, 0.0032, 0.5 * garter.width + 0.0022, 0.0068, 0.0004))
part(surface("garter", [ring((LX, LY, z), 0.0292, 0.0306, 16) for z in (0.140, 0.149)]), garter, "leg-left")
gun = Canvas("holster", 0.12, 0.08, 1200, LEATHER)
gun.shade(0.82 + 0.3 * gun.Y / gun.height)
gun.fill("#1F1A1B", gun.band(0.70 * gun.height, 0.72 * gun.height))          # the flap
gun.fill("#4A4144", gun.ellipse(0.5 * gun.width, 0.82 * gun.height, 0.0022, 0.0022))
part(ellipsoid("holster", (LX + 0.034, LY + 0.004, 0.158), (0.0085, 0.0175, 0.034), 8, 6, power=3.5), gun, "leg-left")

# ---- pumps: a rounded toe, a low back, a block heel -------------------------------------------------
down = lambda c: c + Vector((0, 0, 1))                                    # their broad side faces up and down
pump = sweep("pump-l", [(LX, 0.046, 0.032), (LX, 0.030, 0.028), (LX, 0.008, 0.019), (LX, -0.012, 0.0125), (LX, -0.026, 0.0105)],
             [.028, .038, .042, .041, .028], [.024, .030, .026, .021, .017], down, seg=12, tip=False)
gloss = Canvas("pump", 0.14, 0.10, 1600, SHOE)
gloss.put("#6A5F66", 0.6 * np.exp(-((gloss.X / gloss.width - 0.68) / 0.05) ** 2) * np.clip(gloss.Y / gloss.height - 0.3, 0, 1))  # a shine along the toe
gloss.fill(TIGHTS_DARK, np.maximum(np.abs(gloss.X / gloss.width - 0.75) - 0.16, gloss.Y / gloss.height - 0.42) * gloss.width)  # the instep shows
part(pump, gloss, "leg-left")
part(mirror(pump, "pump-r"), gloss, "leg-right")
heel = ellipsoid("heel-l", (LX, 0.040, 0.011), (0.0085, 0.0075, 0.011), 8, 4, power=4)
heel_c = Canvas("heel", 0.06, 0.03, 1000, SHOE)
part(heel, heel_c, "leg-left")
part(mirror(heel, "heel-r"), heel_c, "leg-right")

# ---- hair: a bob ----------------------------------------------------------------------------------------
# One mass from the crown: the cap comes down behind the ears to her jaw all round, standing out from
# the head and ending in points; the fringe sweeps from the parting across her right brow; short locks
# in front of the ears.
hair = Hair((0, 0.024, 0.468), (0.134, 0.130, 0.132), HAIR, flare=0.17, flare_depth=0.07, tuck=0.10, tuck_from=0.08, tuck_to=0.14)


COLS = 48


CLUMP = 4            # columns to a clump of the bob's ends


def bob(az):
    """The cap's hem: the hairline over the face, above the ears, then the bob's ends - each clump
    longest at its middle and curving up to the partings either side, so the ends come to soft points."""
    edge = float(np.interp(az, [-180, -112, -100, -75, -50, -20, 20, 29, 46, 60, 75, 100, 112, 180],
                           [.335, .332, .455, .455, .500, .520, .535, .525, .500, .465, .455, .455, .332, .335]))
    if abs(az) >= 110:
        u = (az * COLS / 360 / CLUMP) % 1
        edge += 0.020 * (1 - math.sin(math.pi * u) ** 0.8)
    return edge


hair.cap(bob, cols=COLS, rows=10, rim_depth=0.032)
hair.blade("fringe-a", [(0.048, 0.585), (0.018, 0.556), (-0.012, 0.520), (-0.030, 0.488), (-0.040, 0.462)],
           [.016, .070, .056, .032, .003], [.004, .017, .017, .013, .003], 11)
hair.blade("fringe-b", [(0.018, 0.592), (-0.022, 0.567), (-0.052, 0.530), (-0.072, 0.484), (-0.082, 0.440)],
           [.016, .072, .058, .034, .003], [.004, .017, .017, .013, .003], 12)
# in front of the ears: on her right the fringe's edge carries on down past the cheek to the jaw, on her
# left a short lock to the eye
hair.blade("lock-right", [(-0.088, 0.548), (-0.114, 0.505), (-0.120, 0.460), (-0.116, 0.410), (-0.108, 0.372)],
           [.014, .048, .040, .030, .003], [.004, .016, .016, .013, .003], 13)
hair.blade("lock-left", [(0.088, 0.548), (0.112, 0.505), (0.123, 0.465), (0.118, 0.430)],
           [.014, .046, .036, .003], [.004, .016, .014, .003], 14)

# the head as a whole as on Tifa
scale_parts(HEAD_PARTS, HEAD_PIVOT, 1.07)
assemble("ada", occlusion_size=2048, samples=32)
