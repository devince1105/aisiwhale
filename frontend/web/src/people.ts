// A person's name in the reader's language (D-112). The office's staff are named in both
// languages, "Tifa｜蒂法" — English, then Chinese — and each screen shows only its own: Chinese
// in a Chinese interface, English in an English one. A name with one part is shown as it is.

/** The back office's language: Chinese, until it has an English interface. */
export const ADMIN_LANG = "zh-TW";

const SEPARATOR = /\s*[｜|]\s*/;

export function personName(name: string | null | undefined, lang: string = ADMIN_LANG): string {
  if (!name) return "";
  const [english, chinese] = name.split(SEPARATOR);
  if (!chinese) return name;
  return lang.startsWith("zh") ? chinese : english;
}

/** The staff who have a picture (D-113, D-118): their Q-version head, ``/avatars/<key>.webp``, and
 * their full figure for the office, ``/figures/<key>.webp`` — both cut out of one Q-version
 * portrait (``avatars-source/q``), transparent around them. */
const PHOTOS = new Set(["tifa", "ada", "sayla", "rei", "mari", "shinobu", "ami", "chunli"]);

/** An agent's head photo, or null: then the screen shows the desk's icon or an initial. */
export function avatarPhoto(avatarKey: string | null | undefined): string | null {
  return avatarKey && PHOTOS.has(avatarKey) ? `/avatars/${avatarKey}.webp` : null;
}

/** Someone's full figure, standing, for the office (D-118); null for the rest. */
export function figurePhoto(avatarKey: string | null | undefined): string | null {
  return avatarKey && PHOTOS.has(avatarKey) ? `/figures/${avatarKey}.webp` : null;
}

/** Her seated figures, front and back (D-124): sitting on nothing, so that she sits in the
 * office's own chair. */
export function figureSitPhoto(avatarKey: string | null | undefined): string | null {
  return avatarKey && PHOTOS.has(avatarKey) ? `/figures-sit/${avatarKey}.webp` : null;
}

export function figureSitBackPhoto(avatarKey: string | null | undefined): string | null {
  return avatarKey && PHOTOS.has(avatarKey) ? `/figures-sit-back/${avatarKey}.webp` : null;
}

/** The same figure from behind (D-123), for when the camera is at her back; cut out of the
 * operator's back views (``avatars-source/back``) the same way. */
export function figureBackPhoto(avatarKey: string | null | undefined): string | null {
  return avatarKey && PHOTOS.has(avatarKey) ? `/figures-back/${avatarKey}.webp` : null;
}
