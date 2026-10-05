/** Stable rows prevent fixed-size HTML cards from colliding in a force cluster. */
export function cardLayout(ids: string[], aspect: number): Map<string, {x: number; y: number}> {
  const sorted = [...ids].sort();
  const columns = Math.max(1, Math.ceil(Math.sqrt(sorted.length * Math.max(0.5, aspect) / 1.5)));
  return new Map(sorted.map((id, index) => [id, {
    x: (index % columns) * 1.5,
    y: -Math.floor(index / columns),
  }]));
}
