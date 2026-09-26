import { Component, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { AccordionModule } from 'primeng/accordion';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, AccordionModule],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App {
  protected readonly title = signal('fareas');
}
