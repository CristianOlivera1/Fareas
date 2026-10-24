import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-logo',
  imports: [RouterLink],
  templateUrl: './app-logo.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AppLogo {
  readonly compact = input(false);
  readonly route = input('/login');
}
