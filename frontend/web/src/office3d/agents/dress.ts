// Dressing a figure (D-115): its own copy of the palette, and the vertices an outfit's rules pick
// pointed at spare cells of that copy, painted in the outfit's colours with the shading of the
// cell they came from. The model's shared geometry, material and texture are never touched: the
// clone gets its own geometry and material, so every other figure stays as it was.
import { BufferAttribute, CanvasTexture, type Material, type Mesh, type MeshStandardMaterial, type Object3D, type SkinnedMesh } from "three";

import type { Outfit, Paint } from "../assets/outfits";

const COLS = 16;
const ROWS = 4;
/** Cells the palette leaves black (its top two rows, but for the pink pair at the left of the
 * second): room for an outfit's colours. */
export const SPARE_CELLS: [number, number][] = [
  ...Array.from({ length: COLS }, (_, c): [number, number] => [0, c]),
  ...Array.from({ length: COLS - 2 }, (_, c): [number, number] => [1, c + 2]),
];

/** The face's features: the flat plane at the front of the head, below the fringe. */
const FACE_Z = 0.16;
const FACE_TOP = 0.53;

export function cellOf(u: number, v: number): string {
  return `${Math.min(ROWS - 1, Math.floor(v * ROWS))}:${Math.min(COLS - 1, Math.floor(u * COLS))}`;
}

function partOf(mesh: Mesh): "head" | "body" | null {
  return mesh.name.startsWith("head") ? "head" : mesh.name.startsWith("body") ? "body" : null;
}

/** The bone that moves a vertex most, by name (a head-mesh is the head's). */
function boneOf(mesh: Mesh, i: number): string | null {
  const skinned = mesh as SkinnedMesh;
  const joints = mesh.geometry.getAttribute("skinIndex");
  const weights = mesh.geometry.getAttribute("skinWeight");
  if (!skinned.isSkinnedMesh || !joints || !weights) return null;
  let best = 0;
  for (let k = 1; k < 4; k++) if (weights.getComponent(i, k) > weights.getComponent(i, best)) best = k;
  return skinned.skeleton?.bones[joints.getComponent(i, best)]?.name ?? null;
}

/** Which rule, if any, repaints vertex ``i`` of ``mesh``. */
export function ruleFor(
  paints: readonly Paint[],
  part: "head" | "body",
  cell: string,
  bone: string | null,
  position: [number, number, number],
): number {
  return paints.findIndex(
    (p) =>
      p.cells.includes(cell) &&
      (!p.parts || p.parts.includes(part)) &&
      (!p.bones || (bone !== null && p.bones.includes(bone))) &&
      !(p.notFace && part === "head" && Math.abs(position[2] - FACE_Z) < 0.006 && position[1] < FACE_TOP),
  );
}

function hexRgb(hex: string): [number, number, number] {
  const n = Number.parseInt(hex.replace("#", ""), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** The palette with each rule's colour painted into its spare cell, shaded like its first cell. */
function paintPalette(image: CanvasImageSource & { width: number; height: number }, paints: readonly Paint[]): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = image.width;
  canvas.height = image.height;
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(image, 0, 0);
  const cw = canvas.width / COLS;
  const ch = canvas.height / ROWS;
  paints.forEach((paint, n) => {
    const [row, col] = paint.cells[0].split(":").map(Number);
    const source = ctx.getImageData(col * cw, row * ch, cw, ch);
    const px = source.data;
    let sum = 0;
    for (let i = 0; i < px.length; i += 4) sum += px[i] * 0.299 + px[i + 1] * 0.587 + px[i + 2] * 0.114;
    const mean = sum / (px.length / 4) || 1;
    const [r, g, b] = hexRgb(paint.color);
    for (let i = 0; i < px.length; i += 4) {
      const shade = (px[i] * 0.299 + px[i + 1] * 0.587 + px[i + 2] * 0.114) / mean; // keep the cell's gradient
      px[i] = Math.min(255, r * shade);
      px[i + 1] = Math.min(255, g * shade);
      px[i + 2] = Math.min(255, b * shade);
    }
    const [sr, sc] = SPARE_CELLS[n];
    ctx.putImageData(source, sc * cw, sr * ch);
  });
  return canvas;
}

/** Dress ``body`` (a clone of a figure) in ``outfit``. Returns what to dispose with it. */
export function dress(body: Object3D, outfit: Outfit): { dispose: () => void } {
  const owned: { dispose: () => void }[] = [];
  let texture: CanvasTexture | null = null;
  const material = new Map<Material, Material>();
  body.traverse((object) => {
    const mesh = object as Mesh;
    const part = mesh.isMesh ? partOf(mesh) : null;
    if (!part) return;
    const original = mesh.material as MeshStandardMaterial;
    const map = original.map;
    if (!map?.image) return;
    if (!texture) {
      texture = new CanvasTexture(paintPalette(map.image as HTMLImageElement, outfit.paints));
      texture.flipY = map.flipY;
      texture.colorSpace = map.colorSpace;
      texture.magFilter = map.magFilter;
      texture.minFilter = map.minFilter;
      texture.generateMipmaps = map.generateMipmaps;
      owned.push(texture);
    }
    if (!material.has(original)) {
      const copy = original.clone();
      copy.map = texture;
      material.set(original, copy);
      owned.push(copy);
    }
    mesh.material = material.get(original)!;

    // the geometry is the model's, shared by every figure: this one gets its own UVs
    const geometry = mesh.geometry.clone();
    const uv = geometry.getAttribute("uv") as BufferAttribute;
    const position = geometry.getAttribute("position");
    const next = new Float32Array(uv.array as ArrayLike<number>);
    for (let i = 0; i < uv.count; i++) {
      const u = uv.getX(i);
      const v = uv.getY(i);
      const rule = ruleFor(outfit.paints, part, cellOf(u, v), boneOf(mesh, i), [
        position.getX(i),
        position.getY(i),
        position.getZ(i),
      ]);
      if (rule < 0) continue;
      const [sr, sc] = SPARE_CELLS[rule];
      // the same place inside the spare cell as inside its own: the gradient carries over
      next[i * 2] = (sc + ((u * COLS) % 1)) / COLS;
      next[i * 2 + 1] = (sr + ((v * ROWS) % 1)) / ROWS;
    }
    geometry.setAttribute("uv", new BufferAttribute(next, 2));
    mesh.geometry = geometry;
    owned.push(geometry);
  });
  return { dispose: () => owned.forEach((o) => o.dispose()) };
}
