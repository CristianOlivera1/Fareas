import { ChangeDetectionStrategy, Component, CUSTOM_ELEMENTS_SCHEMA, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthService } from '../../../core/services/auth/auth';
import { UiInput } from '../../../shared/components/ui-input/ui-input';
import { UiButton } from '../../../shared/components/ui-button/ui-button';

type RecoverStep = 'email' | 'otp' | 'reset';

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

  readonly step = signal<RecoverStep>('email');
  readonly isSubmitting = signal(false);
  readonly errorMessage = signal('');
  readonly successMessage = signal('');

  readonly emailForm = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
  });

  readonly otpForm = this.fb.nonNullable.group({
    code: ['', [Validators.required, Validators.pattern(/^\d{6}$/)]],
  });

  readonly resetForm = this.fb.nonNullable.group({
    new_password: ['', [Validators.required, Validators.minLength(8)]],
    confirm_password: ['', [Validators.required, Validators.minLength(8)]],
  });

  private recoveryEmail = '';


  emailFieldError(): string {
    const control = this.emailForm.get('email');
    if (!control || !control.touched || !control.errors) return '';
    if (control.errors['required']) return 'Este campo es obligatorio.';
    if (control.errors['email']) return 'Ingresa un correo válido.';
    return '';
  }

  submitEmail(): void {
    if (this.emailForm.invalid || this.isSubmitting()) {
      this.emailForm.markAllAsTouched();
      return;
    }

    this.isSubmitting.set(true);
    this.errorMessage.set('');

    const { email } = this.emailForm.getRawValue();
    this.recoveryEmail = email;

    this.auth.recoverRequest({ email }).subscribe({
      next: (res) => {
        this.isSubmitting.set(false);
        this.successMessage.set(res.message);
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
    if (!control || !control.touched || !control.errors) return '';
    if (control.errors['required']) return 'Este campo es obligatorio.';
    if (control.errors['minlength']) return 'Mínimo 8 caracteres.';
    return '';
  }

  submitReset(): void {
    if (this.resetForm.invalid || this.isSubmitting()) {
      this.resetForm.markAllAsTouched();
      return;
    }

    const { new_password, confirm_password } = this.resetForm.getRawValue();

    if (new_password !== confirm_password) {
      this.errorMessage.set('Las contraseñas no coinciden.');
      return;
    }

    this.isSubmitting.set(true);
    this.errorMessage.set('');

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
          this.errorMessage.set(
            err.error?.detail ?? 'No se pudo restablecer la contraseña.',
          );
        },
      });
  }


  resendCode(): void {
    this.errorMessage.set('');
    this.successMessage.set('');
    this.isSubmitting.set(true);

    this.auth.recoverRequest({ email: this.recoveryEmail }).subscribe({
      next: (res) => {
        this.isSubmitting.set(false);
        this.successMessage.set(res.message);
        this.otpForm.reset();
      },
      error: () => {
        this.isSubmitting.set(false);
        this.errorMessage.set('No se pudo reenviar el código.');
      },
    });
  }

  goBackToEmail(): void {
    this.step.set('email');
    this.errorMessage.set('');
    this.successMessage.set('');
  }

  get maskedEmail(): string {
    if (!this.recoveryEmail) return '';
    const [user, domain] = this.recoveryEmail.split('@');
    if (!domain) return this.recoveryEmail;
    const visible = user.slice(0, 2);
    return `${visible}${'•'.repeat(Math.max(user.length - 2, 3))}@${domain}`;
  }
}
