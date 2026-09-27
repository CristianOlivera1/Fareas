export type UserRole = 'admin' | 'docente' | 'estudiante';

export const ROLE_LABELS: Record<UserRole, string> = {
  admin: 'Administrador',
  docente: 'Docente',
  estudiante: 'Estudiante',
};

export interface UserOut {
  readonly id: number;
  readonly role: UserRole;
  readonly full_name: string;
  readonly email: string;
  readonly must_change_password: boolean;
}

export interface LoginResponse {
  readonly access_token: string;
  readonly token_type: string;
  readonly user: UserOut;
}

export interface LoginRequest {
  readonly email: string;
  readonly password: string;
}

export interface ChangePasswordRequest {
  readonly current_password: string;
  readonly new_password: string;
}

export interface RecoverRequest {
  readonly email: string;
}

export interface VerifyOtpRequest {
  readonly email: string;
  readonly code: string;
}

export interface ResetPasswordRequest {
  readonly email: string;
  readonly code: string;
  readonly new_password: string;
}

export interface MessageResponse {
  readonly message: string;
}

export interface SessionUser {
  readonly id: number;
  readonly full_name: string;
  readonly email: string;
  readonly role: UserRole;
  readonly must_change_password: boolean;
}

export interface NavItem {
  label: string;
  route: string;
  icon: string;
  tooltip: string;
}
