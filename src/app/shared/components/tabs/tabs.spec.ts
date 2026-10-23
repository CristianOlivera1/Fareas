import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Tabs } from './tabs';

describe('Tabs', () => {
  let fixture: ComponentFixture<Tabs>;
  let component: Tabs;

  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [Tabs] }).compileComponents();
    fixture = TestBed.createComponent(Tabs);
    component = fixture.componentInstance;
    fixture.componentRef.setInput('tabs', [
      { id: 'first', label: 'Primera' },
      { id: 'second', label: 'Segunda' },
    ]);
    fixture.componentRef.setInput('activeTab', 'first');
    fixture.detectChanges();
  });

  it('renders the selected tab and associates its panel', () => {
    const selectedTab = fixture.nativeElement.querySelector('[role="tab"][aria-selected="true"]');

    expect(selectedTab.textContent).toContain('Primera');
    expect(selectedTab.getAttribute('aria-controls')).toBe('tabs-panel-first');
  });

  it('emits the selected tab when activated', () => {
    const selection = vi.fn();
    component.activeTabChange.subscribe(selection);

    component.selectTab('second');

    expect(selection).toHaveBeenCalledWith('second');
  });

  it('moves selection and keyboard focus to the next tab', () => {
    const selection = vi.fn();
    component.activeTabChange.subscribe(selection);
    const event = new KeyboardEvent('keydown', { key: 'ArrowRight', cancelable: true });

    component.onKeydown(event, 0);

    expect(event.defaultPrevented).toBe(true);
    expect(selection).toHaveBeenCalledWith('second');
    expect(document.activeElement).toBe(fixture.nativeElement.querySelectorAll('[role="tab"]')[1]);
  });
});
