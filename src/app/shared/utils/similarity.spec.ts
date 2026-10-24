import { rankBySimilarity, similarity } from './similarity';

describe('similarity', () => {
  it('ignores case, accents and spacing', () => {
    expect(similarity('LAB 305', 'lab305')).toBe(1);
    expect(similarity('Mamaní Vilca', 'MAMANI VILCA')).toBe(1);
  });

  it('scores a one-letter typo high and different codes lower', () => {
    expect(similarity('TSTUI9O1', 'TSTUI901')).toBeGreaterThan(0.7);
    expect(similarity('AGG2', 'AGG3')).toBeLessThan(0.7);
  });

  it('ranks the closest candidates first and drops weak ones', () => {
    const rooms = ['LAB 305', 'LAB 306', 'AULA 104'];
    const ranked = rankBySimilarity('LAB 3O5', rooms, (room) => room, { min: 0.6 });

    expect(ranked[0].item).toBe('LAB 305');
    expect(ranked.map((entry) => entry.item)).not.toContain('AULA 104');
  });

  it('returns nothing for empty input', () => {
    expect(similarity('', 'LAB 305')).toBe(0);
    expect(rankBySimilarity(null, ['LAB 305'], (room) => room)).toEqual([]);
  });
});
