import type { Guide } from './guides';

const YOUTH = ['youth.self_service'];

export const YOUTH_GUIDES: Guide[] = [
  {
    slug: 'youth-start',
    title: 'Welcome: what you can do here',
    summary: 'Your page, what staff can see, and what you can change.',
    group: 'Getting started',
    needs: YOUTH,
    start: true,
    to: { path: '/me', label: 'Open my profile' },
    steps: [
      'Your page is called My profile. It shows your qualifications, skills, work experience and when you are available.',
      'You can add or change these. Staff who work on your placement can see them.',
      'Staff use this information to suggest opportunities. A person decides who is referred; nothing is automatic.',
      'You can only see your own record, never anyone else’s.',
    ],
    why: 'The more accurate your details are, the better the opportunities your officer can suggest for you.',
    related: ['youth-consent', 'youth-add-skills'],
    updated: '2026-11',
  },
  {
    slug: 'youth-consent',
    title: 'The consent notice',
    summary: 'What you agree to before your profile is shown.',
    group: 'Getting started',
    needs: YOUTH,
    to: { path: '/me', label: 'Open my profile' },
    steps: [
      'The first time you sign in, you see a short notice explaining how your information is used.',
      'Read it, then choose "I understand and agree". Your profile opens after that.',
      'If the notice changes later, you will be asked to agree again.',
      'To correct or remove something you cannot change yourself, ask your officer.',
    ],
    updated: '2026-11',
  },
  {
    slug: 'youth-add-skills',
    title: 'Add or update your skills and availability',
    summary: 'Tell us what you can do and when you can start.',
    group: 'Youth',
    needs: YOUTH,
    to: { path: '/me', label: 'Open my profile' },
    steps: [
      'On My profile, choose Edit.',
      'Add your highest qualification, the skills you have and how well you know them, and any work experience.',
      'Say when you can start and what kind of work suits you.',
      'Fill only what you know. Leaving something empty is fine; it is shown as "not given", never as a failure.',
      'Choose Save.',
    ],
    why: 'What you add is marked "self-reported" until staff check it. Staff may then mark it verified. If staff have verified an entry you cannot delete it.',
    related: ['youth-consent'],
    updated: '2026-11',
  },
];
