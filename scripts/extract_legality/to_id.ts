/** Showdown-compatible toId: lowercase, strip non-alphanumeric. */
export function toId(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, "");
}
