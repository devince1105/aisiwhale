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

/** The staff who have a head photo (D-113): ``/avatars/<avatar_key>.jpg``. */
const PHOTOS = new Set(["tifa", "ada", "sayla", "rei", "mari", "shinobu", "ami", "chunli"]);

/** An agent's head photo, or null: then the screen shows the desk's icon or an initial. */
export function avatarPhoto(avatarKey: string | null | undefined): string | null {
  return avatarKey && PHOTOS.has(avatarKey) ? `/avatars/${avatarKey}.jpg` : null;
}
