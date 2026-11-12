/**
 * Suggests first / middle / last names from a full name: first word is the first name, last word
 * the last name, anything between is the middle name. (Stored as given_name, family_name = middle,
 * other_names = last.) It is only a guess, so the edit form
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
    family_name: parts.slice(1, -1).join(' '),
    other_names: parts[parts.length - 1],
  };
}
