import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { Avatar, initialsOf } from './avatar';

@Component({
  imports: [Avatar],
  template: `<app-avatar [name]="name()" [src]="src()" />`,
})
class Host {
  readonly name = signal('Raul Montesinos');
  readonly src = signal<string | null>(null);
}

describe('initialsOf', () => {
  it('uses the first letter of the first two words', () => {
    expect(initialsOf('Raul Montesinos Valdivia')).toBe('RM');
  });

  it('handles single names and empty values', () => {
    expect(initialsOf('Lucía')).toBe('LU');
    expect(initialsOf('  ')).toBe('U');
    expect(initialsOf(null)).toBe('U');
  });
});

describe('Avatar', () => {
  function render() {
    const fixture = TestBed.createComponent(Host);
    fixture.detectChanges();
    return fixture;
  }

  it('shows initials when there is no photo', () => {
    const fixture = render();
    const element: HTMLElement = fixture.nativeElement;
    expect(element.querySelector('img')).toBeNull();
    expect(element.textContent?.trim()).toBe('RM');
  });

  it('shows the photo when a url is provided', () => {
    const fixture = render();
    fixture.componentInstance.src.set('https://cdn.example/a.jpg');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('img')?.getAttribute('src')).toBe('https://cdn.example/a.jpg');
  });

  it('falls back to initials when the image fails and recovers on a new url', () => {
    const fixture = render();
    fixture.componentInstance.src.set('https://cdn.example/expired.jpg');
    fixture.detectChanges();
    fixture.nativeElement.querySelector('img').dispatchEvent(new Event('error'));
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('img')).toBeNull();
    expect(fixture.nativeElement.textContent.trim()).toBe('RM');

    fixture.componentInstance.src.set('https://cdn.example/fresh.jpg');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('img')).not.toBeNull();
  });
});
