# The office's head photos (D-113)

The originals the operator supplied, 1024 × 1024. What the site serves are square crops of the
face at 256 × 256, in `public/avatars/<avatar_key>.jpg` (`tifa`, `ada`, `sayla`, `rei`, `mari`,
`shinobu`, `ami`, `chunli`) — each agent's `avatar_key` names its photo.

To replace one: put the new original here and crop it the same way (a square around the face
with the hair's top and the chin in, resized to 256 px).

## Back views (D-123)

`back/<avatar_key>.jpg` are the operator's back views, 1024 × 1024. The office's standees show
them while the camera is at a figure's back: `public/figures-back/<avatar_key>.webp`, lifted out
with `lift.swift` (macOS Vision), cropped to the figure and scaled to 512 px high, as the fronts in
`public/figures/` are.

## Seated views (D-124)

`sit-front/` and `sit-back/` are the operator's seated pictures (sitting on nothing, so the office's
own chair takes her), 1024 × 1024. Served as `public/figures-sit/` and `public/figures-sit-back/`,
made the same way as the back views.

## Walking, from the side (D-125)

`walk/<avatar_key>.jpg` hold two frames side by side (the stride, and the step between), facing
right, 1376 × 768. Split at the white divider, lifted, and scaled per pair so the taller frame is
512 px: `public/figures-walk/<avatar_key>-1.webp` and `-2.webp`. Walking left, the office mirrors them.

## Standing, from the side (D-126)

`stand-side/<avatar_key>.jpg` hold two frames side by side, facing left then right, 1376 × 768 (no
Ada yet; `sayia.jpg` was renamed `sayla.jpg`). Made like the walking frames:
`public/figures-side/<avatar_key>-left.webp` and `-right.webp`.
