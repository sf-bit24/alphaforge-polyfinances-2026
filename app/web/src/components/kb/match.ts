import type { KbItem, Locale } from "@/lib/contract/schemas";
import { okfTypeLabel } from "@/lib/i18n/okf-types";

/** Lower case, without accents, typographic apostrophes as straight ones: « Série » matches « serie », « d’une » matches « d'une ». */
const fold = (text: string) =>
  text
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .replace(/[’‘]/g, "'")
    .toLowerCase();

/**
 * The documents of the list that contain `query` in their key, title, description or type, the
 * type being searched both raw (« Data Series ») and as displayed in `locale` (« Série de données »).
 */
export function matchingItems(items: KbItem[], query: string, locale: Locale): KbItem[] {
  const needle = fold(query.trim());
  if (!needle) return items;
  return items.filter((item) => {
    const type = item.type ?? "";
    const fields = [item.key, item.title ?? "", item.description ?? "", type, type ? okfTypeLabel(type, locale) : ""];
    return fields.some((field) => fold(field).includes(needle));
  });
}
