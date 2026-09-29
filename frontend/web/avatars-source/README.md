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
