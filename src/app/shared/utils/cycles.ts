const ROMANOS = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'];

export const CYCLES: readonly number[] = Array.from({ length: 10 }, (_, index) => index + 1);

export function toRoman(cycle: number): string {
  return ROMANOS[cycle] ?? String(cycle);
}

export function cycleLabel(cycle: number): string {
  return `Ciclo ${toRoman(cycle)}`;
}
