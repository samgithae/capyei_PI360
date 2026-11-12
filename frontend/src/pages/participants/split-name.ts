/**
 * Suggests given / family / other names from a full name: first word is the given name, last word
 * the family name, anything between goes to other names. It is only a guess, so the edit form
 * shows it for staff to correct before saving.
 */
export function splitName(full: string): {
  given_name: string;
  family_name: string;
  other_names: string;
} {
  const parts = full.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0)
    return { given_name: '', family_name: '', other_names: '' };
  if (parts.length === 1)
    return { given_name: parts[0], family_name: '', other_names: '' };
  return {
    given_name: parts[0],
    family_name: parts[parts.length - 1],
    other_names: parts.slice(1, -1).join(' '),
  };
}
