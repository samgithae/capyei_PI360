import { OFFICER_GUIDES } from './content-officer';
import { STAFF_GUIDES } from './content-staff';
import { YOUTH_GUIDES } from './content-youth';
import type { Guide } from './guides';

/** Order matters for "start here": the first start guide a reader qualifies for is shown. */
export const ALL_GUIDES: Guide[] = [
  ...STAFF_GUIDES,
  ...OFFICER_GUIDES,
  ...YOUTH_GUIDES,
];
