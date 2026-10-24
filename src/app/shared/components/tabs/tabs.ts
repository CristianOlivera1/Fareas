import {
  ChangeDetectionStrategy,
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  input,
  output,
  viewChildren,
} from '@angular/core';
import type { ElementRef } from '@angular/core';

export interface TabOption {
  readonly id: string;
  readonly label: string;
  readonly icon?: string;
  readonly badge?: string | number;
  readonly badgeTone?: 'neutral' | 'success';
}

@Component({
  selector: 'app-tabs',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './tabs.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class Tabs {
  readonly tabs = input.required<readonly TabOption[]>();
  readonly activeTab = input.required<string>();
  readonly activeTabChange = output<string>();
  readonly idPrefix = input('tabs');
  readonly ariaLabel = input('Secciones');

  private readonly tabButtons = viewChildren<ElementRef<HTMLButtonElement>>('tabButton');

  tabId(tabId: string): string {
    return `${this.idPrefix()}-tab-${tabId}`;
  }

  panelId(tabId: string): string {
    return `${this.idPrefix()}-panel-${tabId}`;
  }

  selectTab(tabId: string): void {
    this.activeTabChange.emit(tabId);
  }

  onKeydown(event: KeyboardEvent, index: number): void {
    const tabs = this.tabs();
    if (tabs.length === 0) return;

    let nextIndex: number;
    if (event.key === 'ArrowRight') {
      nextIndex = (index + 1) % tabs.length;
    } else if (event.key === 'ArrowLeft') {
      nextIndex = (index - 1 + tabs.length) % tabs.length;
    } else if (event.key === 'Home') {
      nextIndex = 0;
    } else if (event.key === 'End') {
      nextIndex = tabs.length - 1;
    } else {
      return;
    }

    event.preventDefault();
    this.selectTab(tabs[nextIndex].id);
    this.tabButtons()[nextIndex]?.nativeElement.focus();
  }
}
