/** Summaries are often « Label : value »; the row already shows the label, so drop it once. */
export function withoutLabel(label: string, value: string): string {
  const match = /^(.+?)\s?:\s+(.+)$/su.exec(value);
  return match?.[1] && match[2] && match[1].trim().toLocaleLowerCase() === label.toLocaleLowerCase() ? match[2] : value;
}
