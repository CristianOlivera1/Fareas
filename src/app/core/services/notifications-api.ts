import { Injectable } from '@angular/core';

import { BaseApi } from '../api/api-url';
import type {
  NotificationList,
  NotificationUnreadCount,
} from '../models/notification';

@Injectable({
  providedIn: 'root',
})
export class NotificationsApi extends BaseApi {
  unreadCount() {
    return this.get<NotificationUnreadCount>('/notifications/unread-count');
  }

  list(params?: { limit?: number; before_id?: number; unread_only?: boolean }) {
    return this.get<NotificationList>('/notifications', params);
  }

  markRead(id: number) {
    return this.post<NotificationUnreadCount>(`/notifications/${id}/read`);
  }

  markAllRead() {
    return this.post<NotificationUnreadCount>('/notifications/read-all');
  }
}
