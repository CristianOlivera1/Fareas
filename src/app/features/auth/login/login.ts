import { ChangeDetectionStrategy, Component, CUSTOM_ELEMENTS_SCHEMA, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthService } from '../../../core/services/auth/auth';
import { UiInput } from '../../../shared/components/ui-input/ui-input';
import { UiButton } from '../../../shared/components/ui-button/ui-button';

@Component({
  selector: 'app-login',
  imports: [ReactiveFormsModule, UiInput, UiButton, RouterLink],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './login.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Login implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  readonly isSubmitting = signal(false);
  readonly errorMessage = signal('');
  readonly infoMessage = signal('');

  readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.minLength(3)]],
    password: ['', [Validators.required, Validators.minLength(6)]],
  });

  ngOnInit(): void {
    const reason = this.route.snapshot.queryParamMap.get('reason');
    if (reason === 'session_expired') {
      this.infoMessage.set('Tu sesión expiró. Inicia sesión nuevamente.');
    }
    if (reason === 'password_changed') {
      this.infoMessage.set('Contraseña actualizada correctamente. Inicia sesión con tu nueva clave.');
    }
  }

  fieldError(field: 'email' | 'password'): string {
    const control = this.form.get(field);
    if (!control || !control.touched || !control.errors) return '';
    if (control.errors['required']) return 'Este campo es obligatorio.';
    if (control.errors['minlength'])
      return field === 'email' ? 'Mínimo 3 caracteres.' : 'Mínimo 6 caracteres.';
    return '';
  }

  onSubmit(): void {
    if (this.form.invalid || this.isSubmitting()) {
      this.form.markAllAsTouched();
      return;
    }

    this.isSubmitting.set(true);
    this.errorMessage.set('');
    this.infoMessage.set('');

    const { email, password } = this.form.getRawValue();

    this.auth.login({ email, password }).subscribe({
      next: (res) => {
        this.isSubmitting.set(false);
        if (res.user.must_change_password) {
          void this.router.navigate(['/auth/change-password']);
        } else {
          void this.router.navigate(['/admin/dashboard']);
        }
      },
      error: (err: HttpErrorResponse) => {
        this.isSubmitting.set(false);
        if (err.status === 429) {
          this.errorMessage.set(
            err.error?.detail ?? 'Demasiados intentos. Espera un momento.',
          );
        } else if (err.status === 401) {
          this.errorMessage.set('Credenciales incorrectas o usuario inactivo.');
        } else if (err.status === 0) {
          this.errorMessage.set('No se puede conectar al servidor. Verifica tu conexión.');
        } else {
          this.errorMessage.set(
            err.error?.detail ?? 'Ocurrió un error inesperado. Intenta de nuevo.',
          );
        }
      },
    });
  }
}
