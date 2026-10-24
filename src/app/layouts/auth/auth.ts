import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { AppLogo } from '../../shared/components/app-logo/app-logo';

@Component({
  selector: 'app-auth-layout',
  imports: [RouterOutlet, AppLogo],
  templateUrl: './auth.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class AuthLayout {}
