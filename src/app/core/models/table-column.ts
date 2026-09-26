export interface TableColumn {
  id: string;
  header: string;
  align?: 'left' | 'center' | 'right';
  width?: string;
  hiddenOnMobile?: boolean;
}
