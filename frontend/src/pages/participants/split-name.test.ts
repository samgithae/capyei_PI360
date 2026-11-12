import { describe, expect, it } from 'vitest';
import { splitName } from './split-name';

describe('splitName', () => {
  it('takes first as given, last as family, middle as other', () => {
    expect(splitName('Ashley Wambui Gicharu')).toEqual({
      given_name: 'Ashley',
      family_name: 'Gicharu',
      other_names: 'Wambui',
    });
  });
  it('handles two words, one word and extra spaces', () => {
    expect(splitName('  Jane   Doe ')).toEqual({
      given_name: 'Jane',
      family_name: 'Doe',
      other_names: '',
    });
    expect(splitName('Madonna').family_name).toBe('');
    expect(splitName('').given_name).toBe('');
  });
});
