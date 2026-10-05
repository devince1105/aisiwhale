# Ada, Animal Crossing style (D-199): built as Tifa (D-198) is, on her proportions - the owner keeps all
# the SG to Tifa's; Ada's own reference draws her legs too long. Needs lib.py and figure.py. Dress and
# hair from avatars-source/q/Ada.jpg (front), back/ada.jpg and stand-side/ada.jpg: a chin-length bob
# swept from a parting on her left, a red ribbed sleeveless turtleneck under a shoulder harness with
# two pouches, a belted black pencil skirt slit on her left, a holster on her left thigh, sheer dark
# tights, short fingerless gloves, black heels. The 9999 version (D-200): the budget's 10,000 triangles
# go where they show - the bob sculpted into fat clumps ending in points, the harness, belt, buckles,
# pouches and holster standing off the body; pointed stilettos with crossed straps, after photos the owner sent.
reset("ada")
fit_arms()
PARTS.clear()

# the reference reads black and red: every dark keeps red at or above blue, so nothing turns lilac
SKIN, HAIR = "#FBCDB0", "#2B2124"
RED, RED_DARK, COLLAR = "#A31F2C", "#7A1622", "#8A1C28"
STRAP, LEATHER, SKIRT, BELT = "#231D21", "#271F22", "#2A2125", "#211B1E"
TIGHTS_DARK, TIGHTS_LIGHT, SHOE = "#30221F", "#5E4038", "#171214"
METAL, METAL_DARK = "#8E8A90", "#5F5A60"

# ---- head (Tifa's), with her face but no earrings -----------------------------------------------------
head, face = ac_head(SKIN)
ac_face(face)
part(head, face, "head")
ac_ears(SKIN, center=(0.112, 0.040, 0.414), radii=(0.040, 0.024, 0.034), soft_fold=True)   # poking out through the bob
ac_nose()

# ---- torso: the turtleneck --------------------------------------------------------------------------------
TORSO = [(0.190, .050, .042, .022), (0.215, .047, .040, .020), (0.236, .0455, .038, .018), (0.250, .046, .039, .016),
         (0.272, .049, .044, .011), (0.295, .050, .044, .012), (0.312, .047, .040, .014), (0.322, .034, .030, .014),
         (0.330, .021, .021, .010), (0.352, .0185, .0185, .006)]
torso = surface("torso", [ring((0, cy, z), rx, ry, 20) for z, rx, ry, cy in TORSO], start=(0, .022, 0.186), end=(0, .006, 0.354))
body = Canvas("torso", 2 * math.pi * 0.047, 0.19, 2300, SKIN)
y_of, Z = along(torso, [p[0] for p in TORSO], body)
DEG = (body.X / body.width - 0.5) * 360                                   # 0 = front, + toward her left
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
part(torso, body, "torso")

# the turtleneck's rolled collar
COLLAR_Z = [(0.3205, .0365, .0325, .014), (0.3255, .0330, .0300, .0125), (0.3330, .0262, .0252, .0105),
            (0.3410, .0240, .0236, .0085), (0.3475, .0215, .0212, .0070)]
roll = Canvas("collar", 2 * math.pi * 0.03, 0.03, 2400, COLLAR)
roll.shade(1 - 0.12 * (0.5 + 0.5 * np.sin(2 * math.pi * roll.X / 0.0028)))      # the ribbing
roll.shade(0.85 + 0.25 * np.sin(np.pi * roll.Y / roll.height))                  # rounder in the middle
part(surface("collar", [ring((0, cy, z), rx, ry, 20) for z, rx, ry, cy in COLLAR_Z]), roll, "torso")


# ---- the harness: flat leather bands lying on the body, gunmetal buckles ---------------------------------
on = on_profile
CHEST = Vector((0, 0.014, 0.27))         # straps face away from here: outward round the body, up over the shoulder
strap_c = strap_canvas(STRAP, "#3A3236")
strap = lambda name, pts: flat_strap(name, pts, TORSO, CHEST, strap_c)
buckle_c = buckle_canvas(METAL, METAL_DARK, STRAP)
buckle = lambda name, at, deg, size=(0.0060, 0.0010, 0.0068), weights="torso": frame_buckle(name, at, deg, buckle_c, size, weights)


for s in (1, -1):
    side = "l" if s > 0 else "r"
    # down the front from the chest strap, over the top of the shoulder, down the back to the back strap
    strap(f"harness-{side}", [(s * 58, 0.258), (s * 57, 0.290), (s * 56, 0.303), (s * 68, 0.311), (s * 90, 0.313),
                              (s * 112, 0.311), (s * 128, 0.300), (s * 134, 0.268)])
    buckle(f"keeper-{side}", on(TORSO, s * 56, 0.298, 0.0030), s * 56, (0.0060, 0.0009, 0.0034))
strap("chest-strap", [(d, 0.263) for d in (-64, -45, -25, 0, 25, 45, 64)])
strap("back-strap", [(d, 0.272) for d in (128, 150, 180, 210, 232)])
buckle("chest-buckle", on(TORSO, 36, 0.263, 0.0026), 36)
buckle("back-buckle", on(TORSO, 180, 0.272, 0.0026), 180)

# the pouches on the harness, at the sides of her chest: boxes with a flap, the chest strap across their
# lower third
pouch_c = Canvas("pouch", 0.08, 0.04, 1600, LEATHER)
pouch_c.shade(0.85 + 0.25 * pouch_c.Y / pouch_c.height)
flap = 0.62 * pouch_c.height
pouch_c.fill("#30272A", pouch_c.band(flap, pouch_c.height))                # the flap, a little lighter
pouch_c.fill("#141012", pouch_c.band(flap - 0.0005, flap + 0.0004))         # its edge
pouch_c.fill("#4A4144", np.maximum(pouch_c.band(flap + 0.0012, flap + 0.0016), np.sin(pouch_c.X / 0.0012 * math.pi) - 0.2), alpha=0.6)
pouch_c.fill(METAL, pouch_c.ellipse(0.5 * pouch_c.width, 0.78 * pouch_c.height, 0.0016, 0.0016))   # the snap
pouch = ellipsoid("pouch-l", (0.045, -0.021, 0.274), (0.0095, 0.0080, 0.0170), 8, 5, power=7)
part(pouch, pouch_c, "torso")
part(mirror(pouch, "pouch-r"), pouch_c, "torso")

# ---- arms: bare, with short fingerless gloves ---------------------------------------------------------
ARM = [(0.048, .0165, .0165), (0.062, .0195, .0195), (0.080, .0185, .0185), (0.100, .0172, .0172), (0.122, .0166, .0166),
       (0.1420, .0162, .0162), (0.1425, .0205, .0200), (0.1555, .0210, .0204), (0.1560, .0262, .0252), (0.1700, .0285, .0272),
       (0.1860, .0276, .0262), (0.1865, .0245, .0225), (0.196, .0244, .0222), (0.2035, .0230, .0208), (0.2085, .0200, .0180),
       (0.2115, .0140, .0126)]
AY, AZ = 0.017, 0.292
arm_l = surface("arm-l", [ring((x, AY, AZ), ry, rz, 12, plane="YZ", power=2.2) for x, ry, rz in ARM],
                start=(0.040, AY, AZ), end=(0.2155, AY, AZ))
sleeve = Canvas("arm", 2 * math.pi * 0.024, 0.176, 3200, SKIN)
y_of, _ = along(arm_l, [p[0] for p in ARM], sleeve)
top = 0.5 * sleeve.width                                                  # u = 0.5 is the top of the arm
sleeve.fill(STRAP, sleeve.band(y_of(0.1425), y_of(0.1558)))               # the cuff: a plain thick band
sleeve.fill("#3A3236", sleeve.band(y_of(0.1425), y_of(0.1425) + 0.0010))
sleeve.fill(METAL, sleeve.ellipse(0.75 * sleeve.width, y_of(0.149), 0.0016, 0.0016))    # a snap on its outer side
sleeve.fill(LEATHER, sleeve.band(y_of(0.1558), y_of(0.1863)))             # the glove over the hand
sleeve.fill("#3A3034", sleeve.band(y_of(0.1558), y_of(0.1558) + 0.0012))
sleeve.fill("#141012", sleeve.band(y_of(0.1848), y_of(0.1863)))
sleeve.fill("#141012", sleeve.ellipse(top, y_of(0.1715), 0.0098, 0.0062))  # the opening on the back of the hand
sleeve.fill(SKIN, sleeve.ellipse(top, y_of(0.1715), 0.0085, 0.0050))
for u in (0.34, 0.45, 0.56, 0.67):                                        # between the fingers
    sleeve.fill("#DDA07E", sleeve.stroke([(u * sleeve.width, y_of(0.190)), (u * sleeve.width, y_of(0.209))], 0.0008))
arm_w = arm_weights
part(arm_l, sleeve, arm_w("left"))
part(mirror(arm_l, "arm-r"), sleeve, arm_w("right"))
thumb = ellipsoid("thumb-l", (0.184, AY - 0.024, AZ + 0.004), (0.011, 0.010, 0.010), 6, 4)
knuckle = Canvas("thumb", 0.03, 0.03, 1000, SKIN)
part(thumb, knuckle, "forearm-left")
part(mirror(thumb, "thumb-r"), knuckle, "forearm-right")

# ---- skirt: a belted pencil skirt, slit up the front of her left thigh and at her right side ------------
SKIRT_Z = [(0.166, .067, .056, .022), (0.178, .0668, .0558, .0215), (0.190, .066, .055, .021), (0.214, .062, .052, .020),
           (0.232, .056, .047, .019), (0.246, .050, .043, .018)]
skirt = surface("skirt", [ring((0, cy, z), rx, ry, 32) for z, rx, ry, cy in SKIRT_Z])
cloth = Canvas("skirt", 2 * math.pi * 0.062, 0.085, 2400, SKIRT)
y_of, Z = along(skirt, [p[0] for p in SKIRT_Z], cloth)
SDEG = (cloth.X / cloth.width - 0.5) * 360
cloth.shade(0.92 + 0.14 * np.cos(np.radians(SDEG)) ** 2)                   # a dull sheen down the front and back
HOLSTER_DEG = 72                                                          # where the holster's drop strap runs
for d, half, top_z in ((42, 0.0065, 0.205), (-88, 0.0030, 0.185)):
    x = (0.5 + d / 360) * cloth.width
    gap = np.maximum(np.abs(cloth.X - x) - half * np.clip((y_of(top_z) - cloth.Y) / (y_of(top_z) - y_of(0.166)), 0, 1),
                     cloth.Y - y_of(top_z))
    cloth.fill(TIGHTS_DARK, gap)
    cloth.fill("#120E10", np.abs(gap) - 0.0007)
for d in (-90, 90):                                                       # side seams
    if abs(d - HOLSTER_DEG) > 25:
        cloth.fill("#1E171A", cloth.column((0.5 + d / 360) * cloth.width - 0.0005, (0.5 + d / 360) * cloth.width + 0.0005))
cloth.fill("#1E171A", cloth.band(y_of(0.166), y_of(0.166) + 0.0012))
hx = (0.5 + HOLSTER_DEG / 360) * cloth.width                              # the holster's drop strap
cloth.fill(STRAP, np.maximum(np.abs(cloth.X - hx) - 0.0035, cloth.Y - y_of(0.230)))


def skirt_w(co):
    """The hem follows the legs (it lifts over the thighs when she sits, and swings with them when she
    walks); the belt and the middle of the back stay with the torso."""
    front = 1.0 if abs(co.x) > 0.035 else min(1.0, max(0.0, -(co.y - 0.02) / 0.07)) ** 0.6
    k = 0.8 * smooth(0.222, 0.166, co.z) * front
    left = smooth(-0.03, 0.03, co.x)
    return {"leg-left": k * left, "leg-right": k * (1 - left), "torso": 1 - k}


part(skirt, cloth, skirt_w)

# the belt, standing off the skirt, with its buckles
BELT_Z = [(z, rx + k, ry + k, cy) for (z, rx, ry, cy), k in
          zip([(0.2280, .0573, .0482, .0191), (0.2290, .0571, .0480, .0191), (0.2455, .0503, .0433, .0180), (0.2465, .0500, .0430, .0180)],
              (0.0006, 0.0026, 0.0026, 0.0006))]
leather_belt = Canvas("belt", 2 * math.pi * 0.054, 0.02, 2400, BELT)
leather_belt.fill("#30282B", leather_belt.band(0.0018, 0.0024))
leather_belt.fill("#30282B", leather_belt.band(leather_belt.height - 0.0024, leather_belt.height - 0.0018))
part(surface("belt", [ring((0, cy, z), rx, ry, 32) for z, rx, ry, cy in BELT_Z]), leather_belt, "torso")
for d, w in ((40, 0.0078), (-36, 0.0062)):
    buckle(f"belt-buckle{d}", on(BELT_Z, d, 0.2372, 0.0012), d, (w, 0.0010, 0.0072))

# ---- legs in sheer tights; a holster on her left thigh ------------------------------------------------
LX, LY = 0.037, 0.022
LEG = [(0.032, .0120), (0.040, .0136), (0.050, .0150), (0.068, .0190), (0.088, .0222), (0.106, .0212), (0.124, .0232),
       (0.148, .0272), (0.172, .0288), (0.186, .0270), (0.200, .0225)]
leg_l = surface("leg-l", [ring((LX, LY, z), r, r * 1.05, 12) for z, r in LEG], start=(LX, LY, 0.030), end=(LX, LY, 0.203))
nylon = Canvas("leg", 2 * math.pi * 0.025, 0.18, 2200, TIGHTS_DARK)
y_of, _ = along(leg_l, [p[0] for p in LEG], nylon)
front = np.clip(np.cos(np.radians((nylon.X / nylon.width - 0.5) * 360)), 0, 1)
nylon.put(TIGHTS_LIGHT, 0.75 * front ** 1.6)                              # sheer: the skin shows most where it faces you
nylon.put("#6E4A40", 0.25 * np.exp(-((nylon.Y - y_of(0.106)) / 0.008) ** 2) * front)   # the knee
part(leg_l, nylon, "leg-left")
part(mirror(leg_l, "leg-r"), nylon, "leg-right")

# two straps round the thigh: the holster's, buckled, at the hem; a plain garter below
leg_r = lambda z: float(np.interp(z, [p[0] for p in LEG], [p[1] for p in LEG]))


def thigh_strap(name, z0, z1):
    return wrap_band(name, (LX, LY), leg_r, z0, z1, squash=1.05)


band_c = Canvas("thigh-strap", 2 * math.pi * 0.03, 0.01, 2000, STRAP)
band_c.shade(0.85 + 0.3 * np.sin(np.pi * band_c.Y / band_c.height))
part(thigh_strap("holster-strap", 0.155, 0.163), band_c, "leg-left")
part(thigh_strap("garter", 0.132, 0.140), band_c, "leg-left")
r159 = leg_r(0.159) + 0.0026
buckle("thigh-buckle", Vector((LX + r159 * math.sin(math.radians(20)), LY - r159 * 1.05 * math.cos(math.radians(20)), 0.159)), 20,
       (0.0052, 0.0009, 0.0052), weights="leg-left")
# the holster: a box seen broad-side from the front-left, overlapping the outer front of the thigh, a
# flap and a snap on top
gun = Canvas("holster", 0.12, 0.08, 1200, LEATHER)
gun.shade(0.82 + 0.3 * gun.Y / gun.height)
gun.fill("#30272A", gun.band(0.74 * gun.height, gun.height))               # the flap
gun.fill("#141012", gun.band(0.74 * gun.height - 0.0005, 0.74 * gun.height + 0.0004))
gun.fill("#4A4144", np.maximum(gun.band(0.74 * gun.height + 0.0012, 0.74 * gun.height + 0.0016), np.sin(gun.X / 0.0012 * math.pi) - 0.2), alpha=0.6)
gun.fill(METAL, gun.ellipse(0.5 * gun.width, 0.86 * gun.height, 0.0018, 0.0018))
HOLSTER_AT = (LX + 0.028, LY - 0.0195, 0.160)
holster = ellipsoid("holster", HOLSTER_AT, (0.0065, 0.0130, 0.040), 8, 6, power=8)
part(turn(holster, HOLSTER_AT, (0, 0, -0.61)), gun, "leg-left")

# ---- heels: pointed d'Orsay stilettos with crossed straps (after the photos the owner sent) -------------
# The foot and shoe are one smooth form lofted from the pointed toe to the heel, the sole rising from the
# ball onto a tall heel; the shoe is painted on it - a black patent toe cap and heel counter, open at the
# arch on both sides, two straps crossing over the instep - with a buckled strap round the ankle and a
# thin stiletto under the heel.
TIP_Y = -0.0445
FOOT = [(-0.0425, .0024, .0020, 2.0), (-0.0400, .0055, .0042, 2.0), (-0.0360, .0090, .0064, 2.05), (-0.0310, .0122, .0082, 2.1),
        (-0.0250, .0147, .0095, 2.2), (-0.0180, .0164, .0103, 2.3), (-0.0100, .0168, .0107, 2.35), (-0.0040, .0164, .0111, 2.4),
        (0.0020, .0158, .0118, 2.4), (0.0080, .0152, .0123, 2.3), (0.0140, .0148, .0125, 2.2), (0.0200, .0146, .0125, 2.2),
        (0.0260, .0145, .0122, 2.2), (0.0310, .0140, .0116, 2.3), (0.0350, .0126, .0103, 2.4), (0.0385, .0098, .0083, 2.4),
        (0.0405, .0058, .0053, 2.4)]
sole = lambda y: float(np.interp(y, [TIP_Y, -0.012, 0.004, 0.020, 0.0418], [0, 0, 0.012, 0.025, 0.031]))
spring = lambda y: float(np.interp(y, [TIP_Y, -0.036, -0.028], [0.0022, 0.0010, 0]))      # the point tips up a little
centre = lambda y, rz: sole(y) + spring(y) + rz
shoe = surface("shoe-l", [ring((LX, y, centre(y, rz)), rx, rz, 16, plane="XZ", power=p) for y, rx, rz, p in FOOT],
               start=(LX, TIP_Y, sole(TIP_Y) + spring(TIP_Y) + 0.0012), end=(LX, 0.0418, sole(0.0418) + 0.0048))
lacquer = Canvas("shoe", 2 * math.pi * 0.016, 0.09, 2400, TIGHTS_DARK)
y_of, FY = along(shoe, [p[0] for p in FOOT], lacquer)
U = lacquer.X / lacquer.width                                              # 0 underneath, 0.25 the inner side, 0.5 on top, 0.75 outside
c = np.cos(2 * math.pi * U)
HIGH = (1 - np.sign(c) * np.abs(c) ** (2 / 2.4)) / 2                     # 0 at the sole, 1 on top
# how high the shoe comes up, as a share of the foot's height: all of the toe cap, a thin sole along the
# open arch, then the heel counter rising round the back (1.1 where closed: at exactly 1 the top line of
# the foot would sit on the edge, half painted)
cover = np.interp(FY, [TIP_Y, -0.0105, -0.0085, 0.010, 0.020, 0.028, 0.034, 0.042], [1.1, 1.1, 0.10, 0.08, 0.10, 0.55, 0.85, 1.1])
edge = (HIGH - cover) * 0.024                                               # metres above the shoe's edge
lacquer.put(TIGHTS_LIGHT, 0.75 * np.exp(-((U - 0.5) / 0.14) ** 2))        # sheer tights, lightest down the instep
lacquer.fill(SHOE, edge)
lacquer.fill("#0A0708", np.abs(edge + 0.0003) - 0.0005)                    # the bound edge of the opening
lacquer.put("#1A1416", 0.45 * np.clip(1 - edge / 0.0018, 0, 1) * (edge > 0))          # the shoe's shadow on the foot
# the crossed straps over the instep: from the toe cap's edge on each side, up across the foot to the
# ankle on the other
for u0, u1 in ((0.30, 0.68), (0.70, 0.32)):
    pts = [(u0 * lacquer.width, y_of(-0.006)), (0.5 * lacquer.width + (u1 - u0) * 0.08 * lacquer.width, y_of(0.004)),
           (u1 * lacquer.width, y_of(0.013))]
    lacquer.fill(SHOE, lacquer.stroke(pts, 0.0011))
    lacquer.fill("#0A0708", np.abs(lacquer.stroke(pts, 0.0011)) - 0.00025, alpha=0.7)
# black patent: a long bright streak down the toe, a softer one on the heel counter
lacquer.put("#D9D3DA", 0.85 * np.exp(-((U - 0.56) / 0.03) ** 2 - ((FY + 0.026) / 0.008) ** 2) * (edge < 0))
lacquer.put("#6A6168", 0.5 * np.exp(-((U - 0.5) / 0.06) ** 2 - ((FY - 0.037) / 0.004) ** 2) * (edge < 0))
lacquer.fill("#2C2427", np.where(HIGH < 0.04, -1.0, 1.0))                   # the sole underneath
part(shoe, lacquer, "leg-left")
part(mirror(shoe, "shoe-r"), lacquer, "leg-right")
# the ankle strap, buckled on the outside
part(thigh_strap("ankle-strap", 0.043, 0.048), band_c, "leg-left")
part(mirror(PARTS[-1][0], "ankle-strap-r"), band_c, "leg-right")
ra = leg_r(0.0455) + 0.0024
for s_, w in ((1, "leg-left"), (-1, "leg-right")):
    buckle(f"ankle-buckle{s_}", Vector((s_ * (LX + ra), LY, 0.0455)), s_ * 90, (0.0032, 0.0008, 0.0032), weights=w)
# the stiletto: a thin heel, a little curved, under the back of the heel
HEEL = [(0.000, .0020, .0020, .0385), (0.004, .0021, .0021, .0384), (0.014, .0024, .0024, .0378), (0.024, .0032, .0034, .0368),
        (0.0345, .0056, .0062, .0355)]                                     # its top runs up into the shoe
heel = surface("heel-l", [ring((LX, cy, z), rx, ry, 8) for z, rx, ry, cy in HEEL], start=(LX, 0.0385, 0.0))
heel_c = Canvas("heel", 2 * math.pi * 0.004, 0.036, 1600, SHOE)
heel_c.fill("#2C2427", heel_c.band(0, 0.0018))                            # the top lift
heel_c.put("#6A6168", 0.5 * np.exp(-((heel_c.X / heel_c.width - 0.5) / 0.1) ** 2))     # a shine down the front
part(heel, heel_c, "leg-left")
part(mirror(heel, "heel-r"), heel_c, "leg-right")

# ---- hair: a helmet bob ----------------------------------------------------------------------------------
# One mass from the crown, fuller on top, coming down beside the face and round the back to chin level
# with the ears poking out through it, its ends turning under to points; about twenty fat clumps with
# dark partings, one at the middle of the nape. The fringe is two clumps swept from the parting across her right brow; a lock runs between
# each eye and ear.
hair = Hair((0, 0.024, 0.468), (0.134, 0.130, 0.132), HAIR, flare=0.0, flare_depth=0.05, tuck=0.12, tuck_from=0.07, tuck_to=0.125,
            dome=2.4)
COLS, CLUMP = 100, 5                     # columns, and columns to a clump
PHASE = 0.5                              # a clump's middle, not a parting, at the nape


def bob(az):
    """The cap's hem: the hairline over the face; from beside the eyes round the back the bob's ends at
    chin level, each clump coming to a point, the ears poking out through it."""
    edge = float(np.interp(az, [-180, -100, -88, -78, -70, -50, -20, 20, 29, 46, 60, 70, 78, 88, 100, 180],
                           [.358, .352, .362, .420, .470, .500, .520, .535, .525, .500, .475, .470, .420, .362, .352, .358]))
    if abs(az) >= 88:
        u = (az * COLS / 360 / CLUMP + PHASE) % 1
        edge += 0.026 * abs(2 * u - 1)
    return edge


hair.cap(bob, cols=COLS, rows=13, rim_depth=0.016, ridges=(COLS // CLUMP, 0.11, 40, PHASE))
# the fringe: the leading clump's tip over the inner corner of her right eye, the second's at the outer
# corner, a sliver of brow and forehead between them
hair.blade("fringe-a", [(0.048, 0.585), (0.018, 0.556), (-0.012, 0.520), (-0.026, 0.492), (-0.032, 0.470)],
           [.016, .062, .044, .020, .002], [.004, .020, .022, .016, .003], 11, seg=8, steps=4, strands=3)
hair.blade("fringe-b", [(0.018, 0.592), (-0.022, 0.567), (-0.052, 0.530), (-0.072, 0.484), (-0.082, 0.448)],
           [.016, .066, .050, .026, .002], [.004, .018, .020, .015, .003], 12, seg=8, steps=4, strands=3)
# between each eye and its ear: on her right down to the jaw, on her left a short point at mid-ear
hair.blade("lock-right", [(-0.095, -0.045, 0.548), (-0.110, -0.030, 0.500), (-0.113, -0.020, 0.450), (-0.110, -0.015, 0.400),
                          (-0.100, -0.012, 0.350)],
           [.014, .040, .034, .026, .003], [.004, .018, .022, .020, .003], 13, seg=8, steps=4, strands=2)
hair.blade("lock-left", [(0.095, -0.045, 0.548), (0.110, -0.028, 0.500), (0.112, -0.015, 0.455), (0.108, -0.005, 0.420)],
           [.014, .036, .028, .003], [.004, .016, .018, .003], 14, seg=8, steps=4, strands=2)

# the head as a whole as on Tifa
scale_parts(HEAD_PARTS, HEAD_PIVOT, 1.07)
assemble("ada", occlusion_size=2048, samples=32)
