import { firstValueFrom } from 'rxjs';
import type { Observable } from 'rxjs';

import type { Page } from '../../core/api/api-url';

const PAGE_SIZE = 100;

export async function fetchAllPages<T>(
  load: (params: { page_size: number; page?: number }) => Observable<Page<T>>,
): Promise<T[]> {
  const first = await firstValueFrom(load({ page_size: PAGE_SIZE }));
  const items = [...first.items];
  const pages = Math.ceil(first.total / PAGE_SIZE);
  for (let page = 2; page <= pages; page += 1) {
    const next = await firstValueFrom(load({ page_size: PAGE_SIZE, page }));
    items.push(...next.items);
  }
  return items;
}
