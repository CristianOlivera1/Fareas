export function normalizeText(value: string | null | undefined): string {
  return (value ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

export function compactText(value: string | null | undefined): string {
  return normalizeText(value).replace(/ /g, '');
}

function bigrams(value: string): Map<string, number> {
  const counts = new Map<string, number>();
  for (let index = 0; index < value.length - 1; index += 1) {
    const pair = value.slice(index, index + 2);
    counts.set(pair, (counts.get(pair) ?? 0) + 1);
  }
  return counts;
}

function dice(left: string, right: string): number {
  if (!left || !right) return 0;
  if (left === right) return 1;
  if (left.length < 2 || right.length < 2) return 0;
  const first = bigrams(left);
  const second = bigrams(right);
  let overlap = 0;
  for (const [pair, count] of first) overlap += Math.min(count, second.get(pair) ?? 0);
  return (2 * overlap) / (left.length - 1 + (right.length - 1));
}

function tokenOverlap(left: string, right: string): number {
  const first = left.split(' ').filter((token) => token.length > 1);
  const second = right.split(' ').filter((token) => token.length > 1);
  if (first.length === 0 || second.length === 0) return 0;
  const shared = first.filter((token) =>
    second.some((other) => token === other || (token.length >= 4 && other.length >= 4 && dice(token, other) >= 0.8)),
  ).length;
  return shared / Math.min(first.length, second.length);
}

export function similarity(left: string | null | undefined, right: string | null | undefined): number {
  const first = normalizeText(left);
  const second = normalizeText(right);
  if (!first || !second) return 0;
  if (first === second) return 1;
  const compactFirst = first.replace(/ /g, '');
  const compactSecond = second.replace(/ /g, '');
  if (compactFirst === compactSecond) return 1;
  return Math.max(dice(compactFirst, compactSecond), tokenOverlap(first, second) * 0.95);
}

export interface Ranked<T> {
  readonly item: T;
  readonly score: number;
}

export function rankBySimilarity<T>(
  query: string | null | undefined,
  items: readonly T[],
  textOf: (item: T) => string,
  options: { min?: number; limit?: number } = {},
): Ranked<T>[] {
  const min = options.min ?? 0.6;
  const limit = options.limit ?? 3;
  return items
    .map((item) => ({ item, score: similarity(query, textOf(item)) }))
    .filter((entry) => entry.score >= min)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);
}
