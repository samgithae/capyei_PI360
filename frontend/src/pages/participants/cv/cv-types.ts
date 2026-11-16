// Shapes of the CV document (GET .../cv) and of the saved profile records (GET .../profile).
// The CV is what an employer sees; the profile records are what the youth edits.

export interface Opt {
  id: string;
  name: string;
}

export interface CvDoc {
  name: string;
  name_parts: { first: string; middle: string; last: string };
  headline: string;
  has_photo: boolean;
  contact: {
    phone: string;
    email: string;
    location: string;
    county: string;
    sub_county: string;
  };
  summary: string;
  education: {
    level: string;
    course: string;
    institution: string;
    field_of_study: string;
    grade: string;
    period: string;
    currently_studying: boolean;
  }[];
  experience: {
    title: string;
    employer: string;
    employment_type: string;
    period: string;
    duration: string;
    responsibilities: string;
    achievements: string;
  }[];
  no_work_experience: boolean;
  practical: {
    organisation: string;
    role: string;
    kind: string;
    period: string;
    description: string;
  }[];
  skills: { name: string; level: string }[];
  certifications: {
    name: string;
    issuer: string;
    year: number | null;
    expiry: string;
  }[];
  languages: { language: string; level: string }[];
  preferences: {
    roles: string[];
    sectors: string[];
    counties: string[];
    work_patterns: string[];
    available_from: string;
    willing_to_relocate: boolean | null;
  } | null;
  completeness: {
    percent: number;
    missing: { key: string; label: string; hint: string }[];
    suggestions: string[];
  };
}

export interface Fact {
  id: string | null;
  source: 'staff' | 'youth' | 'import' | null;
  verified: boolean;
  verified_by: string;
}
export interface Qualification extends Fact {
  level_id: string;
  level: string;
  title: string;
  institution: string;
  field_of_study: string;
  grade: string;
  grade_id: string | null;
  start_year: number | null;
  year_awarded: number | null;
  currently_studying: boolean;
}
export interface SkillRow extends Fact {
  skill_id: string;
  skill: string;
  proficiency: number;
}
export interface Experience extends Fact {
  role_title: string;
  employer_name: string;
  sector_id: string | null;
  sector: string;
  months: number;
  employment_type: string;
  start_date: string | null;
  end_date: string | null;
  is_current: boolean;
  responsibilities: string;
  achievements: string;
}
export interface Certification extends Fact {
  name: string;
  issuer: string;
  year_obtained: number | null;
  expiry_date: string | null;
}
export interface Practical extends Fact {
  organisation: string;
  role: string;
  kind: string;
  start_date: string | null;
  end_date: string | null;
  description: string;
}
export interface LanguageRow extends Fact {
  language: string;
  proficiency: string;
}
export interface Readiness extends Fact {
  available_from: string | null;
  work_patterns: string[];
  interest_sector_ids: string[];
  interest_sectors: string[];
  summary: string;
  preferred_roles: string[];
  preferred_county_ids: string[];
  preferred_counties: string[];
  willing_to_relocate: boolean | null;
  no_work_experience: boolean;
}
export interface ProfileOptions {
  levels: Opt[];
  grades: (Opt & { level_id: string; rank: number })[];
  skills: (Opt & { category?: string })[];
  sectors: Opt[];
  work_patterns: Opt[];
  employment_types: Opt[];
  practical_kinds: Opt[];
  language_levels: Opt[];
  languages: string[];
  counties: Opt[];
}
export interface CvProfileData {
  qualifications: Qualification[];
  skills: SkillRow[];
  experience: Experience[];
  certifications: Certification[];
  practical: Practical[];
  languages: LanguageRow[];
  readiness: Readiness;
  options: ProfileOptions;
}

/** Which repeatable section a save replaces. The API takes the whole list of that section. */
export type Section =
  | 'qualifications'
  | 'skills'
  | 'experience'
  | 'certifications'
  | 'practical'
  | 'languages';

/** Where the data lives: a youth reads their own, staff read one by id. */
export interface CvPaths {
  profile: string;
  cv: string;
  pdf: string;
  photo: string;
  save: string;
  /** Where the skills pick-list is served for this audience. */
  skills: string;
  self: boolean;
}

export const cvPaths = (id: string, self: boolean): CvPaths =>
  self
    ? {
        profile: '/youth/me',
        cv: '/youth/cv',
        pdf: '/youth/cv.pdf',
        photo: '/youth/photo',
        save: '/youth/profile',
        skills: '/youth/skills',
        self,
      }
    : {
        profile: `/participants/${id}/profile`,
        cv: `/participants/${id}/cv`,
        pdf: `/participants/${id}/cv.pdf`,
        photo: `/participants/${id}/photo`,
        save: `/participants/${id}/profile`,
        skills: '/participants/skills',
        self,
      };
