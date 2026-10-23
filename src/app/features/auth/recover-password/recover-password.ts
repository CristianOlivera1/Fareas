import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  DestroyRef,
  inject,
  signal,
} from '@angular/core';
import {
  FormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import type { AbstractControl, ValidationErrors } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthService } from '../../../core/services/auth/auth';
import { UiInput } from '../../../shared/components/ui-input/ui-input';
import { UiButton } from '../../../shared/components/ui-button/ui-button';
import {
  INSTITUTIONAL_EMAIL_DOMAIN,
  institutionalEmail,
} from '../../../shared/validators/person.validators';

type RecoverStep = 'email' | 'otp' | 'reset';

const PASSWORD_PATTERN = /^(?=.*[A-Za-z])(?=.*\d).{8,}$/;
const DEFAULT_RESEND_SECONDS = 60;

function passwordsMatch(group: AbstractControl): ValidationErrors | null {
  const newPassword = group.get('new_password')?.value;
  const confirmPassword = group.get('confirm_password')?.value;
  if (!confirmPassword) return null;
  return newPassword === confirmPassword ? null : { mismatch: true };
}

@Component({
  selector: 'app-recover-password',
  imports: [ReactiveFormsModule, UiInput, UiButton, RouterLink],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './recover-password.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RecoverPassword {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly step = signal<RecoverStep>('email');
  readonly isSubmitting = signal(false);
  readonly errorMessage = signal('');
  readonly successMessage = signal('');
  readonly resendIn = signal(0);
  readonly codeRejected = signal(false);

  readonly emailForm = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email, institutionalEmail]],
  });

  readonly otpForm = this.fb.nonNullable.group({
    code: ['', [Validators.required, Validators.pattern(/^\d{6}$/)]],
  });

  readonly resetForm = this.fb.nonNullable.group(
    {
      new_password: [
        '',
        [Validators.required, Validators.minLength(8), Validators.pattern(PASSWORD_PATTERN)],
      ],
      confirm_password: ['', [Validators.required, Validators.minLength(8)]],
    },
    { validators: passwordsMatch },
  );

  private recoveryEmail = '';
  private resendTimer: ReturnType<typeof setInterval> | null = null;

  constructor() {
    this.destroyRef.onDestroy(() => this.clearResendTimer());

    this.emailForm.controls.email.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((value) => {
        const normalized = value.trim().toLowerCase();
        if (normalized !== value) {
          this.emailForm.controls.email.setValue(normalized);
        }
      });

    this.otpForm.controls.code.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((value) => {
        const digits = value.replace(/\D/g, '').slice(0, 6);
        if (digits !== value) {
          this.otpForm.controls.code.setValue(digits);
        }
      });
  }

  emailFieldError(): string {
    const control = this.emailForm.get('email');
    if (!control || !control.touched || !control.errors) return '';
    if (control.errors['required']) return 'Este campo es obligatorio.';
    if (control.errors['email']) return 'Ingresa un correo válido.';
    if (control.errors['institutional']) {
      return `Usa tu correo institucional (@${INSTITUTIONAL_EMAIL_DOMAIN}).`;
    }
    return '';
  }

  submitEmail(): void {
    if (this.emailForm.invalid || this.isSubmitting()) {
      this.emailForm.markAllAsTouched();
      return;
    }

    const email = this.emailForm.getRawValue().email.trim().toLowerCase();
    this.emailForm.controls.email.setValue(email);
    if (email === this.recoveryEmail && this.resendIn() > 0) {
      this.errorMessage.set(`Espera ${this.resendIn()} s antes de solicitar otro código.`);
      return;
    }
    if (email !== this.recoveryEmail) {
      this.resendIn.set(0);
    }

    this.isSubmitting.set(true);
    this.errorMessage.set('');
    this.successMessage.set('');
    this.codeRejected.set(false);
    this.recoveryEmail = email;

    this.auth.recoverRequest({ email }).subscribe({
      next: (res) => {
        this.isSubmitting.set(false);
        this.successMessage.set(res.message);
        this.startResendCooldown(res.resend_in ?? DEFAULT_RESEND_SECONDS);
        this.step.set('otp');
      },
      error: (err: HttpErrorResponse) => {
        this.isSubmitting.set(false);
        this.errorMessage.set(
          err.error?.detail ?? 'No se pudo procesar la solicitud.',
        );
      },
    });
  }

  otpFieldError(): string {
    const control = this.otpForm.get('code');
    if (!control || !control.touched || !control.errors) return '';
    if (control.errors['required']) return 'Ingresa el código de 6 dígitos.';
    if (control.errors['pattern']) return 'El código debe tener exactamente 6 dígitos.';
    return '';
  }

  submitOtp(): void {
    if (this.otpForm.invalid || this.isSubmitting()) {
      this.otpForm.markAllAsTouched();
      return;
    }

    this.isSubmitting.set(true);
    this.errorMessage.set('');
    this.successMessage.set('');

    const { code } = this.otpForm.getRawValue();

    this.auth.verifyOtp({ email: this.recoveryEmail, code }).subscribe({
      next: (res) => {
        this.isSubmitting.set(false);
        this.successMessage.set(res.message);
        this.step.set('reset');
      },
      error: (err: HttpErrorResponse) => {
        this.isSubmitting.set(false);
        if (err.status === 429) {
          this.errorMessage.set('Demasiados intentos. Solicita un nuevo código.');
        } else {
          this.errorMessage.set(
            err.error?.detail ?? 'Código incorrecto o expirado.',
          );
        }
      },
    });
  }

  resetFieldError(field: 'new_password' | 'confirm_password'): string {
    const control = this.resetForm.get(field);
    if (!control || !control.touched) return '';
    if (field === 'confirm_password' && this.resetForm.errors?.['mismatch']) {
      return 'Las contraseñas no coinciden.';
    }
    if (!control.errors) return '';
    if (control.errors['required']) return 'Este campo es obligatorio.';
    if (control.errors['minlength']) return 'Mínimo 8 caracteres.';
    if (control.errors['pattern']) return 'Usa al menos 8 caracteres con letras y números.';
    return '';
  }

  submitReset(): void {
    if (this.resetForm.invalid || this.isSubmitting()) {
      this.resetForm.markAllAsTouched();
      return;
    }

    const { new_password } = this.resetForm.getRawValue();

    this.isSubmitting.set(true);
    this.errorMessage.set('');
    this.successMessage.set('');
    this.codeRejected.set(false);

    this.auth
      .resetPassword({
        email: this.recoveryEmail,
        code: this.otpForm.getRawValue().code,
        new_password,
      })
      .subscribe({
        next: () => {
          this.isSubmitting.set(false);
          void this.router.navigate(['/login'], {
            queryParams: { reason: 'password_changed' },
          });
        },
        error: (err: HttpErrorResponse) => {
          this.isSubmitting.set(false);
          const detail = err.error?.detail ?? 'No se pudo restablecer la contraseña.';
          this.errorMessage.set(detail);
          this.codeRejected.set(err.status === 400 && /c[oó]digo/i.test(detail));
        },
      });
  }

  resendCode(): void {
    if (this.isSubmitting() || this.resendIn() > 0) return;

    this.errorMessage.set('');
    this.successMessage.set('');
    this.codeRejected.set(false);
    this.isSubmitting.set(true);

    this.auth.recoverRequest({ email: this.recoveryEmail }).subscribe({
      next: (res) => {
        this.isSubmitting.set(false);
        this.successMessage.set(res.message);
        this.startResendCooldown(res.resend_in ?? DEFAULT_RESEND_SECONDS);
        this.otpForm.reset();
      },
      error: (err: HttpErrorResponse) => {
        this.isSubmitting.set(false);
        this.errorMessage.set(err.error?.detail ?? 'No se pudo reenviar el código.');
      },
    });
  }

  goBackToEmail(): void {
    this.clearResendTimer();
    this.resendIn.set(0);
    this.otpForm.reset();
    this.step.set('email');
    this.errorMessage.set('');
    this.successMessage.set('');
    this.codeRejected.set(false);
  }

  private startResendCooldown(seconds: number): void {
    this.clearResendTimer();
    this.resendIn.set(Math.max(1, Math.ceil(seconds)));
    this.resendTimer = setInterval(() => {
      const next = this.resendIn() - 1;
      if (next <= 0) {
        this.resendIn.set(0);
        this.clearResendTimer();
        return;
      }
      this.resendIn.set(next);
    }, 1000);
  }

  private clearResendTimer(): void {
    if (this.resendTimer !== null) {
      clearInterval(this.resendTimer);
      this.resendTimer = null;
    }
  }

  get maskedEmail(): string {
    if (!this.recoveryEmail) return '';
    const [user, domain] = this.recoveryEmail.split('@');
    if (!domain) return this.recoveryEmail;
    const visible = user.slice(0, 2);
    return `${visible}${'•'.repeat(Math.max(user.length - 2, 3))}@${domain}`;
  }
}
