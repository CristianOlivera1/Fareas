import { FormControl } from '@angular/forms';
import {
  DNI_PATTERN,
  institutionalEmail,
  normalizeWhatsapp,
  nonBlank,
  peruWhatsapp,
} from './person.validators';

describe('person validators', () => {
  it('accepts only an eight-digit DNI', () => {
    expect(DNI_PATTERN.test('12345678')).toBe(true);
    expect(DNI_PATTERN.test('1234567')).toBe(false);
  });

  it('rejects blank names', () => {
    expect(nonBlank(new FormControl('   '))).toEqual({ blank: true });
    expect(nonBlank(new FormControl('Ana Torres'))).toBeNull();
  });

  it('requires the institutional email domain', () => {
    expect(institutionalEmail(new FormControl('ana@unamba.edu.pe'))).toBeNull();
    expect(institutionalEmail(new FormControl('ana@gmail.com'))).toEqual({
      institutional: true,
    });
  });

  it('normalizes a Peruvian country prefix and validates the national mobile number', () => {
    expect(normalizeWhatsapp('+51 983 000 000')).toBe('983000000');
    expect(peruWhatsapp(new FormControl('+51 983 000 000'))).toBeNull();
    expect(peruWhatsapp(new FormControl('983000000'))).toBeNull();
    expect(peruWhatsapp(new FormControl('883000000'))).toEqual({ whatsapp: true });
  });
});
