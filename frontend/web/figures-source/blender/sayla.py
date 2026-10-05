# Sayla, Animal Crossing style (D-206): built as the others are, on Tifa's proportions (head, body, arms,
# height); the hair, the face and the dress come from avatars-source/q/Sayla.jpg (front), back/sayla.jpg
# and stand-side/sayla.jpg. Needs lib.py and figure.py. Long straight blonde hair parted on her left -
# the fringe swept across her right brow, a lock either side of the face, one curtain down her back to
# the shoulder blades, the ears showing - and the pink Federation uniform: a black stand collar edged in
# red with gold piping down the front, red shoulder boards with gold stripes, a white badge on either
# side of the chest, a black belt with a gold buckle, the jacket flaring into a short skirt, turned-back
# cuffs, white tights, pink boots with turned cuffs. The 9999 version: the budget goes on the hair's
# clumps, the curtain and the locks, and on what stands off the uniform - the collar, the shoulder
# boards, the badges, the belt and buckle, the skirt's hem and the cuffs.
reset("sayla")
fit_arms()
PARTS.clear()

SKIN, HAIR = "#FBCFAD", "#EAC46E"
JACKET, JACKET_DARK, JACKET_LIGHT, CUFF = "#E2737F", "#C25468", "#F08C90", "#CC5A70"
COLLAR, COLLAR_RIM, GOLD, GOLD_DARK = "#2E2729", "#962A22", "#EDB547", "#B9862A"
BOARD, BADGE, BADGE_EDGE = "#A63A22", "#F1EBE8", "#CFC4C2"
BELT, TIGHTS, PINK_BOOT, BOOT_DARK, BOOT_LIGHT, SOLE = "#3A3236", "#F3E7E1", "#D45A70", "#A9405A", "#E27A8C", "#6E4446"

# ---- head (Tifa's) ------------------------------------------------------------------------------------
head, face = ac_head(SKIN, seg=32, rings=14)
ac_face(face)
part(head, face, "head")
ac_ears(SKIN, radii=(0.034, 0.024, 0.031), seg=10, rings=7, soft_fold=True)
ac_nose()

# ---- torso: the jacket ----------------------------------------------------------------------------------
_T = [(0.190, .050, .042, .022), (0.215, .047, .040, .020), (0.236, .0455, .038, .018), (0.250, .046, .039, .016),
      (0.272, .049, .044, .011), (0.295, .050, .044, .012), (0.312, .047, .040, .014), (0.322, .034, .030, .014),
      (0.330, .021, .021, .010), (0.352, .0185, .0185, .006)]
TORSO = [(z, *(float(np.interp(z, [p[0] for p in _T], [p[k] for p in _T])) for k in (1, 2, 3)))
         for z in (0.190, 0.236, 0.250, 0.258, 0.272, 0.280, 0.295, 0.303, 0.312, 0.322, 0.330, 0.352)]


def bust(deg, z):
    """Her bust under the jacket: a mound either side of the front."""
    mounds = sum(math.exp(-((deg - c) / 24) ** 2) for c in (-25, 25))
    return 0.012 * min(1.0, mounds) * smooth(0.252, 0.272, z) * (1 - smooth(0.282, 0.318, z))


torso = surface("torso", bulged_rings(TORSO, 28, bust), start=(0, .022, 0.186), end=(0, .006, 0.354))
body = Canvas("torso", 2 * math.pi * 0.047, 0.19, 2300, JACKET)
y_of, Z = along(torso, [p[0] for p in TORSO], body)
DEG = (body.X / body.width - 0.5) * 360                                   # 0 = front, + toward her left
zs = [p[0] for p in TORSO]
RX = np.interp(Z, zs, [p[1] for p in TORSO])
XS = np.sin(np.radians(DEG)) * RX                                         # where each pixel is, seen from the front
FRONT = np.cos(np.radians(DEG)) > 0
fz = lambda d: np.where(FRONT, d, 1e3)
bz = lambda d: np.where(FRONT, 1e3, d)
body.shade(0.93 + 0.08 * np.cos(np.radians(DEG)) ** 2)
# the opening under the collar: gold piping in a V over a white shirt, then one gold line down to the belt
v = np.maximum(np.abs(XS) - 0.0075 * np.clip((Z - 0.296) / 0.020, 0, 1), np.maximum(0.296 - Z, Z - 0.320))
body.fill("#F6EEEA", fz(v))
for k in (-1, 1):
    body.fill(GOLD, fz(polyline(XS, Z, [(k * 0.0080, 0.318), (0.0, 0.2955)], 0.0010)))
body.fill(GOLD, fz(polyline(XS, Z, [(0.0, 0.2965), (0.0, 0.230)], 0.0011)))
# seams: down over the bust from the shoulders, down the sides, the middle of the back
for k in (-1, 1):
    body.fill(JACKET_DARK, fz(polyline(XS, Z, [(k * 0.031, 0.318), (k * 0.036, 0.290), (k * 0.031, 0.262), (k * 0.026, 0.232)], 0.0005)), alpha=0.7)
    body.fill(JACKET_DARK, bz(polyline(XS, Z, [(k * 0.030, 0.318), (k * 0.032, 0.280), (k * 0.024, 0.232)], 0.0005)), alpha=0.7)
body.fill(JACKET_DARK, np.abs(np.abs(DEG) - 90) * np.pi / 180 * RX - 0.0005, alpha=0.6)
body.fill(JACKET_DARK, bz(np.abs(XS) - 0.0005), alpha=0.6)
part(torso, body, "torso")

# the stand collar: black, its top edge red, gold piping either side of the opening at the front
COLLAR_Z = [(0.3145, .0310, .0290, .0135), (0.3175, .0300, .0285, .0130), (0.3395, .0274, .0264, .0106), (0.3418, .0262, .0252, .0104),
            (0.3420, .0244, .0234, .0104)]
collar_c = Canvas("collar", 2 * math.pi * 0.029, 0.032, 2400, COLLAR)
cu = (collar_c.X / collar_c.width - 0.5) * 360                             # degrees from the front
collar_c.shade(0.85 + 0.25 * collar_c.Y / collar_c.height)
collar_c.fill(COLLAR_RIM, collar_c.band(0.82 * collar_c.height, collar_c.height))
collar_c.fill(GOLD, np.abs(np.abs(cu) - 7.5) * np.pi / 180 * 0.029 - 0.0011)
collar_c.fill("#1A1416", np.abs(cu) * np.pi / 180 * 0.029 - 0.0004)
part(surface("collar", [ring((0, cy, z), rx, ry, 24) for z, rx, ry, cy in COLLAR_Z]), collar_c, "torso")

# the shoulder boards: red, two gold stripes across, lying on the slope of each shoulder
board_c = Canvas("board", 0.03, 0.03, 1600, BOARD)
for x in (0.0128, 0.0172):
    board_c.fill(GOLD, board_c.column(x - 0.0014, x + 0.0014))
board_c.fill("#7A2618", np.abs(board_c.box(0.0058, 0.0068, 0.0242, 0.0232, 0.0015)) - 0.0004, alpha=0.7)
BOARD_AT = Vector((0.0412, 0.0130, 0.3192))
board = ellipsoid("board-l", BOARD_AT, (0.0090, 0.0085, 0.0018), 8, 4, power=8)
project_front(board, BOARD_AT.x - 0.015, BOARD_AT.y - 0.015, 0.03, 0.03, axes=(0, 1))
part(turn(board, BOARD_AT, (0, 0.60, 0)), board_c, arm_weights("left"))
part(mirror(board, "board-r"), board_c, arm_weights("right"))

# a white badge on either side of the chest
badge_c = Canvas("badge", 0.04, 0.02, 1600, BADGE)
bu, bv = np.abs(badge_c.X / badge_c.width - 0.5), np.abs(badge_c.Y / badge_c.height - 0.5)
badge_c.fill(BADGE_EDGE, np.minimum(0.098 - bu, 0.36 - bv) * badge_c.width)      # its edges, round the front face
badge_c.shade(1.0 + 0.04 * (0.5 - badge_c.Y / badge_c.height))
for s in (1, -1):
    frame_buckle(f"badge-{'l' if s > 0 else 'r'}", on_profile(TORSO, s * 31, 0.2875, 0.0012, bulge=bust), s * 31, badge_c,
                 (0.0135, 0.0014, 0.0078), tilt=(-0.30, 0))

# ---- skirt: the jacket flaring from the belt, open down the front -------------------------------------------
SKIRT_Z = [(0.160, .078, .068, .024), (0.172, .0735, .0640, .023), (0.188, .0670, .0585, .021), (0.205, .0600, .0520, .020),
           (0.222, .0535, .0465, .019), (0.236, .0495, .0425, .018), (0.244, .0482, .0412, .018)]
skirt = surface("skirt", [ring((0, cy, z), rx, ry, 40) for z, rx, ry, cy in SKIRT_Z])
rim(skirt, 0.003, lambda co: Vector((0, 0.020, co.z)))
cloth = Canvas("skirt", 2 * math.pi * 0.066, 0.095, 2200, JACKET)
y_of, SZ = along(skirt, [p[0] for p in SKIRT_Z], cloth)
SDEG = (cloth.X / cloth.width - 0.5) * 360
cloth.shade(1 + 0.07 * np.sin(np.radians(SDEG * 7)) * np.clip((0.236 - SZ) / 0.07, 0, 1))      # soft folds toward the hem
cloth.shade(0.93 + 0.08 * np.cos(np.radians(SDEG)) ** 2)
cloth.fill(JACKET_DARK, np.abs(SDEG) * np.pi / 180 * 0.06 - 0.0006)              # the opening down the front
cloth.put(JACKET_DARK, 0.25 * np.clip(1 - np.abs(SDEG) * np.pi / 180 * 0.06 / 0.004, 0, 1) * (SDEG > 0))   # the overlap's shadow
for d in (-90, 90, 180):
    cloth.fill(JACKET_DARK, np.abs(np.abs(SDEG) - abs(d)) * np.pi / 180 * 0.06 - 0.0005, alpha=0.6)
cloth.fill(JACKET_DARK, np.abs(SZ - 0.1645) - 0.0004, alpha=0.6)            # the hem's stitching


def skirt_w(co):
    """The front of the hem follows the legs (it lifts over the thighs when she sits, and swings when she
    walks); the top and the back stay with the torso."""
    k = 0.6 * smooth(0.222, 0.160, co.z) * smooth(0.025, -0.050, co.y)
    left = smooth(-0.03, 0.03, co.x)
    return {"leg-left": k * left, "leg-right": k * (1 - left), "torso": 1 - k}


part(skirt, cloth, skirt_w)

# the belt over the join, a gold buckle at the front
BELT_Z = [(0.2300, .0488, .0412, .0180), (0.2312, .0506, .0430, .0180), (0.2528, .0506, .0432, .0168), (0.2540, .0482, .0412, .0168)]
belt_c = Canvas("belt", 2 * math.pi * 0.05, 0.024, 2400, BELT)
for y in (0.0035, 0.0205):
    belt_c.fill("#544A50", belt_c.band(y - 0.0003, y + 0.0003), alpha=0.7)
part(surface("belt", [ring((0, cy, z), rx, ry, 36) for z, rx, ry, cy in BELT_Z]), belt_c, "torso")
buckle_c = Canvas("gold-buckle", 0.04, 0.03, 2000, GOLD)
gd = buckle_c.box(0.0050, 0.0050, 0.0350, 0.0250, 0.0015)
buckle_c.fill(GOLD_DARK, np.abs(gd) - 0.0006)
buckle_c.fill("#D9A23C", buckle_c.box(0.0085, 0.0080, 0.0315, 0.0220, 0.0010))
buckle_c.put("#FFF0B8", 0.6 * np.exp(-((buckle_c.Y / buckle_c.height - 0.70) / 0.08) ** 2) * (gd < 0))
BUCKLE_AT = Vector((0, 0.0174 - 0.0432 - 0.0016, 0.2420))
buckle = ellipsoid("buckle", BUCKLE_AT, (0.0150, 0.0024, 0.0100), 12, 4, power=8)
project_front(buckle, -0.020, BUCKLE_AT.z - 0.015, 0.04, 0.03)
part(buckle, buckle_c, "torso")

# ---- arms: pink sleeves to the wrist, wide turned-back cuffs, bare hands -----------------------------------
ARM = [(0.048, .0165, .0165), (0.062, .0198, .0198), (0.080, .0190, .0190), (0.100, .0180, .0180), (0.122, .0174, .0174),
       (0.140, .0172, .0172), (0.152, .0172, .0170), (0.156, .0215, .0205), (0.164, .0250, .0238), (0.176, .0264, .0251),
       (0.188, .0262, .0249), (0.199, .0246, .0233), (0.207, .0206, .0193), (0.2125, .0140, .0130)]
AY, AZ = 0.017, 0.292
arm_l = surface("arm-l", [ring((x, AY, AZ), ry, rz, 14, plane="YZ", power=2.2) for x, ry, rz in ARM],
                start=(0.040, AY, AZ), end=(0.2155, AY, AZ))
sleeve = Canvas("arm", 2 * math.pi * 0.024, 0.176, 3200, JACKET)
y_of, AXP = along(arm_l, [p[0] for p in ARM], sleeve)
sleeve.shade(0.92 + 0.10 * np.sin(np.pi * sleeve.X / sleeve.width) ** 2)
sleeve.fill(JACKET_DARK, np.abs(AXP - 0.0565) - 0.0005, alpha=0.7)          # the shoulder seam
sleeve.fill(SKIN, sleeve.band(y_of(0.1535), sleeve.height + 1))
part(arm_l, sleeve, arm_weights("left"))
part(mirror(arm_l, "arm-r"), sleeve, arm_weights("right"))
thumb = ellipsoid("thumb-l", (0.184, AY - 0.024, AZ + 0.004), (0.011, 0.010, 0.010), 6, 4)
knuckle = Canvas("thumb", 0.03, 0.03, 1000, SKIN)
part(thumb, knuckle, "forearm-left")
part(mirror(thumb, "thumb-r"), knuckle, "forearm-right")
arm_r = lambda x: float(np.interp(x, [p[0] for p in ARM], [p[1] for p in ARM]))
cuff = wrap_band("cuff-l", (AY, AZ), arm_r, 0.127, 0.1545, seg=16, plane="YZ", rise=0.0042)
cuff_c = Canvas("cuff", 2 * math.pi * 0.023, 0.03, 2000, CUFF)
cuff_c.shade(0.88 + 0.18 * np.sin(np.pi * cuff_c.Y / cuff_c.height) ** 0.5)
cuff_c.fill(JACKET_DARK, np.abs(cuff_c.Y - 0.22 * cuff_c.height) - 0.0004, alpha=0.7)   # where it turns back
part(cuff, cuff_c, "forearm-left")
part(mirror(cuff, "cuff-r"), cuff_c, "forearm-right")

# ---- legs in white tights ----------------------------------------------------------------------------------
LX, LY = 0.040, 0.022
LEG = [(0.080, .0232), (0.100, .0240), (0.125, .0230), (0.150, .0244), (0.172, .0254), (0.190, .0225)]
leg_l = surface("leg-l", [ring((LX, LY, z), r, r, 14) for z, r in LEG], start=(LX, LY, 0.078), end=(LX, LY, 0.193))
tights = Canvas("leg", 2 * math.pi * 0.025, 0.125, 2200, TIGHTS)
y_of, _ = along(leg_l, [p[0] for p in LEG], tights)
tights.shade(0.92 + 0.08 * np.cos(np.radians((tights.X / tights.width - 0.5) * 360)) ** 2)
tights.put("#E3CFC8", 0.35 * np.exp(-((tights.Y - y_of(0.125)) / 0.008) ** 2))   # the knee
part(leg_l, tights, "leg-left")
part(mirror(leg_l, "leg-r"), tights, "leg-right")

# ---- boots: pink, a round toe, a thin dark sole, a turned cuff at the top -----------------------------------
BOOT = [(0.0000, .0290, .0480, .0100, 2.4), (0.0030, .0312, .0502, .0100, 2.4), (0.0075, .0312, .0502, .0100, 2.4),
        (0.0090, .0298, .0488, .0100, 2.4), (0.0200, .0305, .0478, .0090, 2.3), (0.0330, .0300, .0445, .0105, 2.3),
        (0.0440, .0285, .0385, .0160, 2.2), (0.0520, .0272, .0330, .0205, 2.1), (0.0580, .0266, .0298, .0225, 2.0),
        (0.0790, .0264, .0284, .0228, 2.0), (0.0800, .0270, .0290, .0228, 2.0), (0.0845, .0298, .0316, .0226, 2.0),
        (0.0985, .0300, .0318, .0225, 2.0), (0.1035, .0255, .0272, .0225, 2.0)]
boot_l = surface("boot-l", [ring((LX, cy, z), rx, ry, 16, power=p) for z, rx, ry, cy, p in BOOT],
                 start=(LX, 0.010, 0.0), end=(LX, 0.0225, 0.097))
leather = Canvas("boot", 2 * math.pi * 0.034, 0.20, 2200, PINK_BOOT)
y_of, BZ = along(boot_l, [p[0] for p in BOOT], leather)
BDEG = (leather.X / leather.width - 0.5) * 360
leather.shade(0.86 + 0.14 * np.clip(BZ / 0.05, 0, 1))                      # darker toward the sole
leather.fill(SOLE, leather.band(-1, y_of(0.0082)))
seam = np.interp(np.abs(BDEG), [0, 40, 100, 180], [.044, .046, .052, .052])  # where the toe cap meets the upper
leather.fill(BOOT_DARK, np.maximum(np.abs(BZ - seam) - 0.0005, np.abs(BDEG) - 105), alpha=0.6)
leather.fill(BOOT_DARK, leather.band(y_of(0.0790), y_of(0.0815)))          # the crease under the turned cuff
leather.fill(BOOT_LIGHT, leather.band(y_of(0.0815), y_of(0.0985)), alpha=0.45)
leather.fill(TIGHTS, leather.band(y_of(0.1033), 1))
part(boot_l, leather, "leg-left")
part(mirror(boot_l, "boot-r"), leather, "leg-right")

# ---- hair -------------------------------------------------------------------------------------------------
# One mass: a cap from a parting above her left temple, sculpted into clumps, behind the ears and down her
# back as one curtain to the shoulder blades, longest at the sides, each clump ending in a point; two
# blades of fringe swept across her right brow; a long lock in front of her right ear forward over the
# shoulder, a shorter one in front of her left.
hair = Hair((0, 0.024, 0.468), (0.134, 0.130, 0.132), HAIR, flare=0.13, flare_depth=0.07, tuck=0.09, tuck_from=0.12, tuck_to=0.21)
COLS, CLUMP = 84, 7
LEN = {2: .006, 3: .010, 4: .004, 5: .013, 6: .016, 7: .011, 8: .005, 9: .012, 10: .007}     # each clump down the back its own length


def hem(az):
    """The cap's hem: the hairline on her left forehead, above the ears, then the curtain, each clump
    ending in a point."""
    edge = float(np.interp(az, [-180, -150, -130, -116, -108, -104, -75, -50, -20, 20, 29, 46, 60, 75, 90, 104, 108, 116, 130, 150, 180],
                           [.274, .270, .258, .252, .262, .452, .455, .500, .520, .535, .525, .515, .500, .485, .468, .452, .262, .252, .258, .270, .274]))
    if abs(az) >= 108:
        t = az * COLS / 360 / CLUMP + 0.5
        u, k = t % 1, int(t // 1) % (COLS // CLUMP)
        edge += 0.030 * (1 - math.sin(math.pi * u) ** 0.6) - LEN.get(k, 0.0) * math.sin(math.pi * u)
    return edge


back = hang(0.28, 0.37)
hair.cap(hem, cols=COLS, rows=17, ridges=(COLS // CLUMP, 0.15, 40, 0.5), weights=back, grow=(0.45, 1.1),
         paint_grow=(0.15, 4.0), highlight=0.22, partings=0.42, side_fade=True, parting_color="#B98D45", sweep=0.35,
         crown_shade=(0.18, 0.35))
hair.blade("fringe-a", [(0.045, 0.585), (0.010, 0.556), (-0.020, 0.518), (-0.032, 0.484), (-0.034, 0.462)],
           [.020, .075, .065, .042, .004], [.008, .022, .024, .018, .005], 11, seg=8, steps=4, strands=3)
hair.blade("fringe-b", [(0.015, 0.592), (-0.020, 0.565), (-0.046, 0.525), (-0.060, 0.482), (-0.064, 0.442)],
           [.020, .080, .068, .045, .004], [.008, .022, .024, .018, .005], 12, seg=8, steps=4, strands=3)
hair.blade("lock-right", [(-0.030, 0.590), (-0.085, 0.555), (-0.108, 0.510), (-0.110, -0.016, 0.455), (-0.110, -0.014, 0.405),
                          (-0.103, -0.020, 0.368), (-0.094, -0.030, 0.338), (-0.084, -0.031, 0.310), (-0.070, -0.030, 0.285)],
           [.016, .070, .066, .062, .060, .056, .048, .034, .003], [.004, .018, .022, .022, .022, .020, .018, .014, .003], 13,
           weights=hang(0.30, 0.35), seg=8, steps=3, strands=4)
hair.blade("lock-left", [(0.088, 0.548), (0.112, 0.505), (0.120, -0.010, 0.455), (0.116, -0.012, 0.405), (0.106, -0.018, 0.365),
                         (0.094, -0.024, 0.335)],
           [.014, .050, .048, .044, .032, .003], [.004, .016, .018, .018, .016, .003], 14, seg=8, steps=3, strands=3)

# the head as a whole as on Tifa: the crown at 0.600 makes her 0.618 tall, as the office expects
scale_parts(HEAD_PARTS, HEAD_PIVOT, 1.07)
assemble("sayla", occlusion_size=2048, samples=32, fade_face_seam=True)
