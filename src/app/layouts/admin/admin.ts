import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { Sidebar } from '../admin-layout/components/sidebar/sidebar';
import { Header } from '../admin-layout/components/header/header';

@Component({
  selector: 'app-admin-layout',
  imports: [Sidebar, Header, RouterOutlet],
  templateUrl: './admin.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AdminLayout {}
