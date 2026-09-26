import { ChangeDetectionStrategy, Component, CUSTOM_ELEMENTS_SCHEMA, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../../core/services/auth/auth';

@Component({
  selector: 'app-login',
  imports: [ReactiveFormsModule],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './login.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Login {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  readonly showPassword = signal(false);
  readonly isSubmitting = signal(false);
  readonly errorMessage = signal('');

  readonly form = this.fb.nonNullable.group({
    username: ['', [Validators.required, Validators.minLength(3)]],
    password: ['', [Validators.required, Validators.minLength(6)]],
  });

  togglePassword(): void {
    this.showPassword.update((v) => !v);
  }

  fieldError(field: 'username' | 'password'): string {
    const control = this.form.get(field);
    if (!control || !control.touched || !control.errors) return '';
    if (control.errors['required']) return 'Este campo es requerido.';
    if (control.errors['minlength'])
      return field === 'username' ? 'Mínimo 3 caracteres.' : 'Mínimo 6 caracteres.';
    return '';
  }

  onSubmit(): void {
    if (this.form.invalid || this.isSubmitting()) {
      this.form.markAllAsTouched();
      return;
    }
    this.isSubmitting.set(true);
    this.errorMessage.set('');

    // Static mock: any valid form logs in after a short delay.
    setTimeout(() => {
      const username = this.form.getRawValue().username;
      this.auth.login(username);
      this.isSubmitting.set(false);
      void this.router.navigate(['/admin/dashboard']);
    }, 450);
  }
}
