// Someone's face (D-113): their head photo when they have one, else their desk's icon — or the
// name's initial — on the desk's colour. Round, at the size asked.
import { avatarPhoto, personName } from "@/people";

import { ROLE_ICON } from "./model";

const ROLE_COLOUR: Record<string, string> = {
  ceo: "#7c5cff",
  editor_in_chief: "#d64545",
  news_intelligence: "#8a6d1f",
  editor: "#e07b39",
  writer: "#2f9e6e",
  analyst: "#2f6fe0",
  researcher: "#0f9bb3",
  marketing: "#c2489a",
};

export function Face({
  name,
  role,
  avatarKey,
  size = 32,
}: {
  name: string;
  role: string;
  avatarKey?: string | null;
  size?: number;
}) {
  const photo = avatarPhoto(avatarKey);
  const box = { width: size, height: size };
  if (photo)
    return (
      // a 256-px square from /public: next/image would add nothing here but a loader
      <img src={photo} alt="" aria-hidden="true" style={box} className="shrink-0 rounded-full object-cover" data-testid="face-photo" />
    );
  return (
    <span
      aria-hidden="true"
      style={{ ...box, background: ROLE_COLOUR[role] ?? "#6b7280", fontSize: size * 0.45 }}
      className="flex shrink-0 items-center justify-center rounded-full font-semibold text-white"
    >
      {ROLE_ICON[role] ?? personName(name).slice(0, 1)}
    </span>
  );
}
