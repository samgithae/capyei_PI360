import { describe, expect, it } from 'vitest';
import { splitName } from './split-name';

describe('splitName', () => {
  it('takes first as first name, last as last name, middle as middle name', () => {
    expect(splitName('Ashley Wambui Gicharu')).toEqual({
      given_name: 'Ashley',
      family_name: 'Wambui',
      other_names: 'Gicharu',
    });
  });
  it('handles two words, one word and extra spaces', () => {
    expect(splitName('  Jane   Doe ')).toEqual({
      given_name: 'Jane',
      family_name: '',
      other_names: 'Doe',
    });
    expect(splitName('Madonna').other_names).toBe('');
    expect(splitName('').given_name).toBe('');
  });
});
