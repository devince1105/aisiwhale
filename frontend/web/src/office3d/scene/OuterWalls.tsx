// The diorama's two tall walls, each its own meshes (D-119), so the camera can go all the way
// round: a wall the camera has gone behind is hidden — as a doll's house opens the side you look
// in from — and comes back when the camera returns. Everything else about them (windows, their
// glow, the pictures) is as it was when they were part of the merged office.
import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import type { Group } from "three";

import type { Palette } from "../palette";
import { OUTER_WALLS, outerWallParts, wallInTheWay, windowGlassParts, type OuterWall } from "./furniture";
import { buildGeometry } from "./kit";

function Wall({ side, palette }: { side: OuterWall; palette: Palette }) {
  const group = useRef<Group>(null);
  const [lit, neon, windows] = useMemo(() => {
    const glow = new Set(palette.glow);
    const parts = outerWallParts(side, palette);
    const glowing = parts.filter((p) => glow.has(p.color));
    return [
      buildGeometry(parts.filter((p) => !glow.has(p.color))),
      glowing.length ? buildGeometry(glowing) : null,
      buildGeometry(windowGlassParts(palette, side)),
    ];
  }, [side, palette]);
  useEffect(
    () => () => {
      lit.dispose();
      neon?.dispose();
      windows.dispose();
    },
    [lit, neon, windows],
  );
  useFrame(({ camera }) => {
    if (group.current) group.current.visible = !wallInTheWay(side, camera.position);
  });
  const light = palette.lighting;
  return (
    <group ref={group} name={`wall-${side}`}>
      <mesh geometry={lit} castShadow receiveShadow>
        <meshStandardMaterial vertexColors roughness={0.6} />
      </mesh>
      {neon ? (
        <mesh geometry={neon} castShadow>
          <meshBasicMaterial vertexColors toneMapped={false} />
        </mesh>
      ) : null}
      <mesh geometry={windows}>
        <meshStandardMaterial vertexColors emissive={light.windowGlow} emissiveIntensity={light.windowGlowIntensity} roughness={0.1} />
      </mesh>
    </group>
  );
}

export function OuterWalls({ palette }: { palette: Palette }) {
  return (
    <>
      {OUTER_WALLS.map((side) => (
        <Wall key={side} side={side} palette={palette} />
      ))}
    </>
  );
}
