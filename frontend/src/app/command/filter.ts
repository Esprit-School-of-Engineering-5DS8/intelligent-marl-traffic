/** Lower case, without accents: "resultats" finds "Résultats". */
export function normalize(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

/** The commands whose text contains every word of the query, in their original order. */
export function filterCommands<T extends { label: string; hint?: string; keywords?: string }>(
  commands: T[],
  query: string,
): T[] {
  const words = normalize(query).split(/\s+/).filter(Boolean);
  if (!words.length) return commands;
  return commands.filter((c) => {
    const text = normalize(`${c.label} ${c.hint ?? ""} ${c.keywords ?? ""}`);
    return words.every((w) => text.includes(w));
  });
}
