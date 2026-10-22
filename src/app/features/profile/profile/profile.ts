import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  DestroyRef,
  computed,
  inject,
  signal,
} from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AuthService } from '../../../core/services/auth/auth';
import { ROLE_LABELS } from '../../../core/models/user';
import { PageHeader } from '../../../shared/components/page-header/page-header';
import { UiAlert } from '../../../shared/components/ui-alert/ui-alert';
import { UiButton } from '../../../shared/components/ui-button/ui-button';
import { UiInput } from '../../../shared/components/ui-input/ui-input';
import { extractDetail } from '../../../shared/utils/api-error';

type PasswordStep = 1 | 2 | 3;
type PasswordField = 'current_password' | 'otp_code' | 'new_password' | 'confirm_password';

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
  private readonly destroyRef = inject(DestroyRef);

  readonly loading = signal(false);
  readonly loadError = signal('');
  readonly isSendingOtp = signal(false);
  readonly isVerifyingOtp = signal(false);
  readonly isSubmitting = signal(false);
  readonly errorMessage = signal('');
  readonly successMessage = signal('');

  readonly step = signal<PasswordStep>(1);
  readonly maskedEmail = signal('');
  readonly resendSeconds = signal(0);
  readonly otpExpiresIn = signal(600);
  readonly otpExpiresMinutes = computed(() => Math.ceil(this.otpExpiresIn() / 60));

  readonly steps = [
    { id: 1, label: 'Identidad' },
    { id: 2, label: 'Código' },
    { id: 3, label: 'Nueva clave' },
  ] as const;

  readonly user = this.auth.currentUser;
  readonly roleLabel = (): string => {
    const role = this.user()?.role;
    return role ? ROLE_LABELS[role] : 'Sin rol';
  };

  readonly resendLabel = computed(() => {
    const seconds = this.resendSeconds();
    return seconds > 0 ? `Reenviar en ${seconds} s` : 'Reenviar código';
  });

  readonly form = this.fb.nonNullable.group({
    current_password: ['', [Validators.required, Validators.minLength(6)]],
    otp_code: ['', [Validators.required, Validators.pattern(/^\d{6}$/)]],
    new_password: ['', [Validators.required, Validators.minLength(8)]],
    confirm_password: ['', [Validators.required, Validators.minLength(8)]],
  });

  private resendTimer: ReturnType<typeof setInterval> | null = null;

  constructor() {
    this.refresh();

    // El input del OTP solo acepta dígitos y nunca supera 6 caracteres, incluso
    // si el usuario pega texto desde el portapapeles.
    this.form.controls.otp_code.valueChanges
      .pipe(takeUntilDestroyed())
      .subscribe((value) => {
        const digits = value.replace(/\D/g, '').slice(0, 6);
        if (digits !== value) {
          this.form.controls.otp_code.setValue(digits, { emitEvent: false });
        }
      });

    this.destroyRef.onDestroy(() => this.stopResendTimer());
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

  fieldError(field: PasswordField): string {
    const control = this.form.get(field);
    if (!control || !control.touched || !control.errors) return '';
    if (control.errors['required']) return 'Este campo es obligatorio.';
    if (control.errors['pattern']) return 'Ingresa los 6 dígitos del código.';
    if (control.errors['minlength']) {
      return field === 'current_password' ? 'Mínimo 6 caracteres.' : 'Mínimo 8 caracteres.';
    }
    return '';
  }

  sendOtp(): void {
    if (this.isSendingOtp() || this.isVerifyingOtp()) return;

    const current = this.form.controls.current_password;
    current.markAsTouched();
    if (current.invalid) return;

    this.errorMessage.set('');
    this.successMessage.set('');
    this.isSendingOtp.set(true);

    this.auth.requestChangePasswordOtp({ current_password: current.value }).subscribe({
      next: (response) => {
        this.isSendingOtp.set(false);
        this.maskedEmail.set(response.email);
        this.otpExpiresIn.set(response.expires_in);
        this.step.set(2);
        this.form.controls.otp_code.reset('');
        this.startResendTimer(response.resend_in);
        this.focusField('profile-otp-code');
      },
      error: (err: HttpErrorResponse) => {
        this.isSendingOtp.set(false);
        this.errorMessage.set(extractDetail(err));
      },
    });
  }

  resendOtp(): void {
    if (this.resendSeconds() > 0 || this.isSendingOtp() || this.isVerifyingOtp()) return;
    this.sendOtp();
  }

  verifyOtp(): void {
    if (this.isVerifyingOtp() || this.isSendingOtp()) return;

    const code = this.form.controls.otp_code;
    code.markAsTouched();
    if (code.invalid) return;

    this.errorMessage.set('');
    this.isVerifyingOtp.set(true);

    this.auth.verifyChangePasswordOtp({ code: code.value }).subscribe({
      next: () => {
        this.isVerifyingOtp.set(false);
        this.step.set(3);
        this.focusField('profile-new-password');
      },
      error: (err: HttpErrorResponse) => {
        this.isVerifyingOtp.set(false);
        this.errorMessage.set(extractDetail(err));
        if (err.status === 429) {
          // El backend invalidó el código tras agotar los intentos.
          this.restart();
          this.errorMessage.set(extractDetail(err));
        }
      },
    });
  }

  onSubmit(): void {
    // Enter en cualquier paso avanza el flujo (los botones visibles también
    // llaman a estos métodos; el guard de cada uno evita dobles envíos).
    if (this.step() === 1) {
      this.sendOtp();
      return;
    }
    if (this.step() === 2) {
      this.verifyOtp();
      return;
    }
    if (this.isSubmitting()) return;

    const { current_password, otp_code, new_password, confirm_password } =
      this.form.getRawValue();

    this.form.controls.new_password.markAsTouched();
    this.form.controls.confirm_password.markAsTouched();
    if (this.form.controls.new_password.invalid || this.form.controls.confirm_password.invalid) {
      return;
    }

    if (new_password !== confirm_password) {
      this.errorMessage.set('Las contraseñas nuevas no coinciden.');
      return;
    }
    if (current_password === new_password) {
      this.errorMessage.set('La nueva contraseña debe ser diferente a la actual.');
      return;
    }
    if (!otp_code) {
      this.step.set(2);
      this.errorMessage.set('Solicita y verifica un código antes de continuar.');
      return;
    }

    this.isSubmitting.set(true);
    this.errorMessage.set('');
    this.successMessage.set('');

    this.auth.changePassword({ current_password, new_password }).subscribe({
      next: () => {
        this.isSubmitting.set(false);
        this.successMessage.set(
          'Contraseña actualizada. Usa tu nueva clave la próxima vez que inicies sesión.',
        );
        this.resetFlow();
      },
      error: (err: HttpErrorResponse) => {
        this.isSubmitting.set(false);
        const detail = extractDetail(err);
        this.errorMessage.set(detail);
        if (/código|verifica/i.test(detail)) {
          this.step.set(2);
          this.focusField('profile-otp-code');
        }
      },
    });
  }

  restart(): void {
    if (this.isSendingOtp() || this.isVerifyingOtp() || this.isSubmitting()) return;
    this.stopResendTimer();
    this.resendSeconds.set(0);
    this.step.set(1);
    this.form.controls.otp_code.reset('');
    this.errorMessage.set('');
    this.focusField('profile-current-password');
  }

  private resetFlow(): void {
    this.stopResendTimer();
    this.resendSeconds.set(0);
    this.step.set(1);
    this.maskedEmail.set('');
    this.form.reset({
      current_password: '',
      otp_code: '',
      new_password: '',
      confirm_password: '',
    });
  }

  private startResendTimer(seconds: number): void {
    this.stopResendTimer();
    this.resendSeconds.set(Math.max(0, Math.floor(seconds)));
    this.resendTimer = setInterval(() => {
      const next = this.resendSeconds() - 1;
      this.resendSeconds.set(Math.max(0, next));
      if (next <= 0) this.stopResendTimer();
    }, 1000);
  }

  private stopResendTimer(): void {
    if (this.resendTimer !== null) {
      clearInterval(this.resendTimer);
      this.resendTimer = null;
    }
  }

  private focusField(id: string): void {
    setTimeout(() => document.getElementById(id)?.focus(), 0);
  }
}
