import { ChangeDetectionStrategy, Component, CUSTOM_ELEMENTS_SCHEMA, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { AuthService } from '../../../core/services/auth/auth';
import { ROLE_LABELS } from '../../../core/models/user';
import { PageHeader } from '../../../shared/components/page-header/page-header';
import { UiAlert } from '../../../shared/components/ui-alert/ui-alert';
import { UiButton } from '../../../shared/components/ui-button/ui-button';
import { UiInput } from '../../../shared/components/ui-input/ui-input';

@Component({
  selector: 'app-profile-page',
  imports: [ReactiveFormsModule, PageHeader, UiAlert, UiButton, UiInput],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './profile.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProfilePage {
  readonly auth = inject(AuthService);
  private readonly fb = inject(FormBuilder);

  readonly loading = signal(false);
  readonly loadError = signal('');
  readonly isSubmitting = signal(false);
  readonly errorMessage = signal('');
  readonly successMessage = signal('');

  readonly user = this.auth.currentUser;
  readonly roleLabel = (): string => {
    const role = this.user()?.role;
    return role ? ROLE_LABELS[role] : 'Sin rol';
  };

  readonly form = this.fb.nonNullable.group({
    current_password: ['', [Validators.required, Validators.minLength(6)]],
    new_password: ['', [Validators.required, Validators.minLength(8)]],
    confirm_password: ['', [Validators.required, Validators.minLength(8)]],
  });

  constructor() {
    this.refresh();
  }

  refresh(): void {
    this.loading.set(true);
    this.loadError.set('');
    this.auth.me().subscribe({
      next: () => this.loading.set(false),
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.loadError.set(
          err.error?.detail ?? 'No se pudo actualizar tu información. Intenta de nuevo.',
        );
      },
    });
  }

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
    this.successMessage.set('');

    this.auth.changePassword({ current_password, new_password }).subscribe({
      next: () => {
        this.isSubmitting.set(false);
        this.successMessage.set('Contraseña actualizada correctamente.');
        this.form.reset({
          current_password: '',
          new_password: '',
          confirm_password: '',
        });
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
