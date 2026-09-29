// Everyone in the office (T-405): one avatar per seated agent. React renders this only when the
// roster changes (useRoster's selector is a string), so the thousand events of a busy day do not
// re-render it; each avatar reads its own state from the store in the frame loop. Name and status
// tags are HeadTags (T-406).
//
// **Inside a department, only its people are drawn** (ARCHITECTURE_V2 §14.7, T-600): entering a
// room is meant to show that room's work, and eight avatars in the background are the thing the
// operator stepped in to get away from. The building stays — the desks and the floor of the rest
// of the company are still there — and the strip says how many people are elsewhere, so nobody
// silently disappears.
import { useGLTF } from "@react-three/drei";
import { Suspense, useMemo } from "react";

import { figureBackPhoto, figurePhoto, figureSitBackPhoto, figureSidePhotos, figureSitPhoto, figureThinkPhotos, figureWaitPhotos, figureWalkPhotos } from "@/people";
import { useUi, type EnteredDepartment } from "@/stores/ui";

import { characterUrl } from "../assets/characters";
import { outfitFor } from "../assets/outfits";
import type { Seat } from "../scene/layout";
import { AgentAvatar } from "./AgentAvatar";
import { useRoster, type Member } from "./roster";
import type { Pictures } from "./Standee";

export { rosterKey } from "./roster";

/** Her standee's pictures, or null: then she is drawn as the dressed model. */
function picturesOf(avatar: string | null | undefined): Pictures | null {
  const stand = figurePhoto(avatar);
  return stand
    ? {
        stand,
        standBack: figureBackPhoto(avatar),
        sit: figureSitPhoto(avatar),
        sitBack: figureSitBackPhoto(avatar),
        walk: figureWalkPhotos(avatar),
        standSide: figureSidePhotos(avatar),
        thinkSit: figureThinkPhotos(avatar)?.[1],
        waitStand: figureWaitPhotos(avatar)?.[0],
        waitSit: figureWaitPhotos(avatar)?.[1],
      }
    : null;
}

function LoadedAvatar({ member, seat }: { member: Member; seat: Seat }) {
  const gltf = useGLTF(characterUrl(member.character), false);
  const model = useMemo(() => ({ scene: gltf.scene, animations: gltf.animations }), [gltf]);
  return (
    <AgentAvatar
      agentId={member.id}
      seat={seat}
      model={model}
      outfit={outfitFor(member.avatar)}
      figure={picturesOf(member.avatar)}
    />
  );
}

/** Who is drawn: the entered room's people, or everybody when standing on the whole floor. */
export function membersInRoom(
  members: readonly Member[],
  entered: EnteredDepartment | null,
): Member[] {
  if (!entered) return [...members];
  return members.filter((m) => (m.department ?? m.office_zone_key) === entered.key);
}

export function Agents() {
  const { members, seats } = useRoster();
  const entered = useUi((s) => s.focusedDepartment);
  const here = membersInRoom(members, entered);
  return (
    <>
      {here.map((member) => {
        const seat = seats.get(member.id);
        if (!seat) return null; // no desk left: on the 2D board only
        return (
          <Suspense key={member.id} fallback={null}>
            <LoadedAvatar member={member} seat={seat} />
          </Suspense>
        );
      })}
    </>
  );
}
