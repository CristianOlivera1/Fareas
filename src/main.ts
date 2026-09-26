import { bootstrapApplication } from '@angular/platform-browser';
import 'iconify-icon';
import { appConfig } from './app/app.config';
import { App } from './app/app';

bootstrapApplication(App, appConfig).catch((err) => console.error(err));
