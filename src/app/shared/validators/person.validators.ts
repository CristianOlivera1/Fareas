import type { AbstractControl, ValidationErrors, ValidatorFn } from '@angular/forms';

export const INSTITUTIONAL_EMAIL_DOMAIN = 'unamba.edu.pe';
export const DNI_PATTERN = /^\d{8}$/;

const PERU_WHATSAPP_PATTERN = /^9\d{8}$/;

export const nonBlank: ValidatorFn = (control: AbstractControl): ValidationErrors | null =>
  String(control.value ?? '').trim().length > 0 ? null : { blank: true };

export const institutionalEmail: ValidatorFn = (
  control: AbstractControl,
): ValidationErrors | null => {
  const value = String(control.value ?? '').trim().toLowerCase();
  if (!value || !value.includes('@')) return null;
  return value.endsWith(`@${INSTITUTIONAL_EMAIL_DOMAIN}`) ? null : { institutional: true };
};

export function normalizeWhatsapp(value: string): string {
  const digits = value.replace(/\D/g, '');
  return digits.startsWith('51') && digits.length === 12 ? digits.slice(2) : digits;
}

export const peruWhatsapp: ValidatorFn = (control: AbstractControl): ValidationErrors | null => {
  const value = String(control.value ?? '').trim();
  if (!value) return null;
  return PERU_WHATSAPP_PATTERN.test(normalizeWhatsapp(value)) ? null : { whatsapp: true };
};
