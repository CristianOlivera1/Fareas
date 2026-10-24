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
import type { AbstractControl, ValidationErrors } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { DialogModule } from 'primeng/dialog';
import { AuthService } from '../../../core/services/auth/auth';
import { ROLE_LABELS } from '../../../core/models/user';
import { Avatar } from '../../../shared/components/avatar/avatar';
import { PageHeader } from '../../../shared/components/page-header/page-header';
import { UiAlert } from '../../../shared/components/ui-alert/ui-alert';
import { UiButton } from '../../../shared/components/ui-button/ui-button';
import { UiInput } from '../../../shared/components/ui-input/ui-input';
import { extractDetail } from '../../../shared/utils/api-error';

const AVATAR_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const AVATAR_MAX_MB = 5;
const PASSWORD_PATTERN = /^(?=.*[A-Za-z])(?=.*\d).+$/;

type PasswordStep = 1 | 2 | 3;
type PasswordField = 'current_password' | 'otp_code' | 'new_password' | 'confirm_password';

function passwordsMatch(control: AbstractControl): ValidationErrors | null {
  const password = control.parent?.get('new_password')?.value;
  if (!control.value || !password) return null;
  return control.value === password ? null : { mismatch: true };
}

@Component({
  selector: 'app-profile-page',
  imports: [ReactiveFormsModule, PageHeader, UiAlert, UiButton, UiInput, DialogModule, Avatar],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './profile.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProfilePage {
  readonly auth = inject(AuthService);
  private readonly fb = inject(FormBuilder);
  private readonly destroyRef = inject(DestroyRef);

  readonly avatarBusy = signal(false);
  readonly avatarError = signal('');
  readonly loading = signal(false);
  readonly loadError = signal('');
  readonly isSendingOtp = signal(false);
  readonly isVerifyingOtp = signal(false);
  readonly isSubmitting = signal(false);
  readonly errorMessage = signal('');
  readonly successMessage = signal('');
  readonly securityDialogVisible = signal(false);

  readonly step = signal<PasswordStep>(1);
  readonly maskedEmail = signal('');
  readonly resendSeconds = signal(0);
  readonly otpExpiresIn = signal(600);
  readonly otpExpiresMinutes = computed(() => Math.ceil(this.otpExpiresIn() / 60));
  readonly isPasswordFlowBusy = computed(
    () => this.isSendingOtp() || this.isVerifyingOtp() || this.isSubmitting(),
  );

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
    current_password: ['', [Validators.required, Validators.minLength(6), Validators.maxLength(128)]],
    otp_code: ['', [Validators.required, Validators.pattern(/^\d{6}$/)]],
    new_password: [
      '',
      [
        Validators.required,
        Validators.minLength(8),
        Validators.maxLength(128),
        Validators.pattern(PASSWORD_PATTERN),
      ],
    ],
    confirm_password: [
      '',
      [Validators.required, Validators.minLength(8), Validators.maxLength(128), passwordsMatch],
    ],
  });

  private resendTimer: ReturnType<typeof setInterval> | null = null;

  constructor() {
    this.refresh();

    this.form.controls.otp_code.valueChanges
      .pipe(takeUntilDestroyed())
      .subscribe((value) => {
        const digits = value.replace(/\D/g, '').slice(0, 6);
        if (digits !== value) {
          this.form.controls.otp_code.setValue(digits, { emitEvent: false });
        }
      });

    this.form.controls.new_password.valueChanges
      .pipe(takeUntilDestroyed())
      .subscribe(() => {
        this.form.controls.confirm_password.updateValueAndValidity({ emitEvent: false });
      });

    this.destroyRef.onDestroy(() => this.stopResendTimer());
  }

  onAvatarSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    input.value = '';
    if (!file) return;

    const invalid = this.avatarProblem(file);
    this.avatarError.set(invalid);
    if (invalid) return;

    this.avatarBusy.set(true);
    this.auth.uploadAvatar(file).subscribe({
      next: () => this.avatarBusy.set(false),
      error: (err) => {
        this.avatarBusy.set(false);
        this.avatarError.set(extractDetail(err));
      },
    });
  }

  removeAvatar(): void {
    this.avatarBusy.set(true);
    this.avatarError.set('');
    this.auth.removeAvatar().subscribe({
      next: () => this.avatarBusy.set(false),
      error: (err) => {
        this.avatarBusy.set(false);
        this.avatarError.set(extractDetail(err));
      },
    });
  }

  private avatarProblem(file: File): string {
    if (!AVATAR_TYPES.includes(file.type)) return 'La foto debe ser JPG, PNG o WEBP.';
    if (file.size > AVATAR_MAX_MB * 1024 * 1024) return `La foto no puede superar ${AVATAR_MAX_MB} MB.`;
    return '';
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

  openSecurityDialog(): void {
    if (this.isPasswordFlowBusy()) return;
    this.resetFlow();
    this.errorMessage.set('');
    this.successMessage.set('');
    this.securityDialogVisible.set(true);
  }

  closeSecurityDialog(): void {
    if (this.isPasswordFlowBusy()) return;
    this.securityDialogVisible.set(false);
  }

  onSecurityDialogVisibilityChange(visible: boolean): void {
    if (!visible && this.isPasswordFlowBusy()) return;
    this.securityDialogVisible.set(visible);
  }

  onSecurityDialogHide(): void {
    if (this.isPasswordFlowBusy()) return;
    this.securityDialogVisible.set(false);
    this.clearPasswordFlow();
  }

  onSecurityDialogShow(): void {
    const fieldId: Record<PasswordStep, string> = {
      1: 'profile-current-password',
      2: 'profile-otp-code',
      3: 'profile-new-password',
    };
    this.focusField(fieldId[this.step()]);
  }

  private clearPasswordFlow(): void {
    this.resetFlow();
    this.errorMessage.set('');
    this.successMessage.set('');
  }

  fieldError(field: PasswordField): string {
    const control = this.form.get(field);
    if (!control || (!control.touched && !control.value) || !control.errors) return '';
    if (control.errors['required']) return 'Este campo es obligatorio.';
    if (control.errors['maxlength']) return 'No puede superar los 128 caracteres.';
    if (control.errors['serverPolicy'] || (field === 'new_password' && control.errors['pattern'])) {
      return 'Usa entre 8 y 128 caracteres, con al menos una letra y un número.';
    }
    if (control.errors['pattern']) return 'Ingresa los 6 dígitos del código.';
    if (control.errors['mismatch']) return 'Las contraseñas no coinciden.';
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
          this.restart();
          this.errorMessage.set(extractDetail(err));
        }
      },
    });
  }

  onSubmit(): void {
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
        if (err.status === 422 && /new_password/i.test(detail)) {
          const password = this.form.controls.new_password;
          password.setErrors({ ...password.errors, serverPolicy: true });
          password.markAsTouched();
          this.errorMessage.set('');
          return;
        }
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
