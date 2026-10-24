import { compactText, rankBySimilarity } from './similarity';

const ROOM_PATTERN = /^([a-z]*?)([0-9oi]*[0-9][0-9oi]*)$/;

export interface RoomParts {
  readonly prefix: string;
  readonly number: string;
}

export function splitRoomCode(code: string | null | undefined): RoomParts {
  const compact = compactText(code);
  const found = ROOM_PATTERN.exec(compact);
  if (!found) return { prefix: compact, number: '' };
  return { prefix: found[1], number: found[2].replace(/o/g, '0').replace(/i/g, '1') };
}

export function matchRooms<T extends { readonly code: string }>(
  code: string | null | undefined,
  rooms: readonly T[],
  limit = 2,
): T[] {
  const { prefix, number } = splitRoomCode(code);
  if (number) {
    const sameNumber = rooms.filter((room) => splitRoomCode(room.code).number === number);
    if (sameNumber.length > 0) {
      return rankBySimilarity(prefix, sameNumber, (room) => splitRoomCode(room.code).prefix, {
        min: 0,
        limit,
      }).map((entry) => entry.item);
    }
  }
  return rankBySimilarity(code, rooms, (room) => room.code, { min: 0.6, limit }).map(
    (entry) => entry.item,
  );
}
