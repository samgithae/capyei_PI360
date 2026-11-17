export interface Enrollment {
  id: string;
  programme: string;
  cohort: string;
  course: string;
  institution: string;
  enrollment_no: string;
  extra?: Record<string, string>;
  status: string;
  enrolled_on: string | null;
  completed_on: string | null;
  exit_reason?: string;
}
export interface Detail {
  archived: boolean;
  id: string;
  name: string;
  gender: string;
  age: number | null;
  status: string;
  county: string;
  given_name?: string;
  family_name?: string;
  other_names?: string;
  date_of_birth?: string | null;
  age_basis_date?: string | null;
  enrollments: Enrollment[];
  residences: {
    county: string;
    sub_county: string;
    ward: string;
    current: boolean;
  }[];
  contacts?: { kind: string; value: string; primary: boolean }[];
}

export const shortDate = (d?: string | null) => (d ? d.slice(0, 10) : '');
export const monthsText = (n: number) => {
  const y = Math.floor(n / 12);
  const m = n % 12;
  return (
    [y ? `${y} yr` : '', m ? `${m} mo` : ''].filter(Boolean).join(' ') || '0 mo'
  );
};
