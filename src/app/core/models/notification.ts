export type NotificationSeverity = 'info' | 'success' | 'warning' | 'danger';

export interface AppNotification {
  readonly id: number;
  readonly kind: string;
  readonly title: string;
  readonly message: string;
  readonly link: string | null;
  readonly severity: NotificationSeverity;
  readonly read: boolean;
  readonly created_at: string;
}

export interface NotificationList {
  readonly items: AppNotification[];
  readonly unread: number;
}

export interface NotificationUnreadCount {
  readonly count: number;
}
