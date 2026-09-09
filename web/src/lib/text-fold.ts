/** Remove acentos/diacríticos para busca (José ≈ jose). */
export function foldAccents(s: string): string {
  return String(s || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

export function matchesFolded(haystack: string, needle: string): boolean {
  const n = foldAccents(needle).trim();
  if (!n) return true;
  return foldAccents(haystack).includes(n);
}
