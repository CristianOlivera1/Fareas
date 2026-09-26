export interface MockUser {
  username: string;
  role: 'admin' | 'attendant';
  ruc?: string;
}

export interface NavItem {
  label: string;
  route: string;
  icon: string;
  tooltip: string;
}
