import { matchRooms, splitRoomCode } from './room-match';

const ROOMS = [{ code: 'LAB 104' }, { code: 'AULA 104' }, { code: 'LAB 305' }];

describe('room matching', () => {
  it('separates prefix and number, fixing OCR letters inside the number', () => {
    expect(splitRoomCode('Aula 1O4')).toEqual({ prefix: 'aula', number: '104' });
  });

  it('matches by number when the prefix differs', () => {
    expect(matchRooms('AULA 305', ROOMS)[0].code).toBe('LAB 305');
  });

  it('prefers the same prefix when several rooms share the number', () => {
    expect(matchRooms('AULA 104', ROOMS)[0].code).toBe('AULA 104');
    expect(matchRooms('LAB 104', ROOMS)[0].code).toBe('LAB 104');
  });

  it('returns nothing for an unknown room', () => {
    expect(matchRooms('AULA 999', ROOMS)).toEqual([]);
  });
});
