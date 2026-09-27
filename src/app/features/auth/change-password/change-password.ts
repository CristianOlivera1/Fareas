import { ChangeDetectionStrategy, Component, CUSTOM_ELEMENTS_SCHEMA, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthService } from '../../../core/services/auth/auth';
import { UiInput } from '../../../shared/components/ui-input/ui-input';
import { UiButton } from '../../../shared/components/ui-button/ui-button';

@Component({
  selector: 'app-change-password',
  imports: [ReactiveFormsModule, UiInput, UiButton],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './change-password.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ChangePassword {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  readonly isSubmitting = signal(false);
  readonly errorMessage = signal('');
  readonly isForced = this.auth.mustChangePassword;

  readonly form = this.fb.nonNullable.group({
    current_password: ['', [Validators.required, Validators.minLength(6)]],
    new_password: ['', [Validators.required, Validators.minLength(8)]],
    confirm_password: ['', [Validators.required, Validators.minLength(8)]],
  });

  fieldError(field: 'current_password' | 'new_password' | 'confirm_password'): string {
    const control = this.form.get(field);
    if (!control || !control.touched || !control.errors) return '';
    if (control.errors['required']) return 'Este campo es obligatorio.';
    if (control.errors['minlength']) {
      return field === 'current_password' ? 'Mínimo 6 caracteres.' : 'Mínimo 8 caracteres.';
    }
    return '';
  }

  onSubmit(): void {
    if (this.form.invalid || this.isSubmitting()) {
      this.form.markAllAsTouched();
      return;
    }

    const { current_password, new_password, confirm_password } = this.form.getRawValue();

    if (new_password !== confirm_password) {
      this.errorMessage.set('Las contraseñas nuevas no coinciden.');
      return;
    }

    if (current_password === new_password) {
      this.errorMessage.set('La nueva contraseña debe ser diferente a la actual.');
      return;
    }

    this.isSubmitting.set(true);
    this.errorMessage.set('');

    this.auth.changePassword({ current_password, new_password }).subscribe({
      next: () => {
        this.isSubmitting.set(false);
        void this.router.navigate(['/admin/dashboard']);
      },
      error: (err: HttpErrorResponse) => {
        this.isSubmitting.set(false);
        this.errorMessage.set(
          err.error?.detail ?? 'No se pudo cambiar la contraseña. Intenta de nuevo.',
        );
      },
    });
  }
}
