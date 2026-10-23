import { Injectable } from '@angular/core';

import { BaseApi, ListParams, Page } from '../api/api-url';

export interface AuditEntry {
  readonly id: number;
  readonly action: string;
  readonly entity: string;
  readonly entity_id: number | null;
  readonly actor_id: number | null;
  readonly actor_name: string | null;
  readonly actor_role: string | null;
  readonly old_value: unknown;
  readonly new_value: unknown;
  readonly ip_address: string | null;
  readonly created_at: string | null;
}

export interface AuditFilters extends ListParams {
  readonly action?: string | null;
  readonly entity?: string | null;
  readonly actor_role?: string | null;
  readonly since?: string | null;
}

@Injectable({ providedIn: 'root' })
export class AuditApi extends BaseApi {
  list(filters: AuditFilters) {
    return this.get<Page<AuditEntry>>('/audit-log', filters);
  }
}
