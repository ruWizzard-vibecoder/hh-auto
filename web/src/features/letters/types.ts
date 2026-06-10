export type LetterStatus = 'pending' | 'approved' | 'no_letter' | 'sent' | 'rejected';

export interface LetterVacancy {
  id: number;
  hh_id: string;
  title: string;
  company_name: string | null;
  url: string | null;
  relevance_score: number | null;
  salary_from: number | null;
  salary_to: number | null;
  salary_currency: string | null;
  employment: string | null;
  schedule: string | null;
  description: string | null;
  matched_skills: string[];
  missing_skills: string[];
}

export interface Letter {
  id: number;
  status: LetterStatus;
  generated_text: string;
  edited_text: string | null;
  resume_id: string | null;
  generated_at: string | null;
  reviewed_at: string | null;
  vacancy: LetterVacancy;
}

export interface LettersListResponse {
  letters: Letter[];
  counts: Record<LetterStatus, number>;
  employment_counts: Partial<Record<'full' | 'part' | 'project', number>>;
  resume_names: Record<string, string>;
  total_returned: number;
}

export interface LettersListQuery {
  status?: LetterStatus | null;
  employment?: 'full' | 'part' | 'project' | null;
  sort?: 'date' | 'score';
  q?: string;
  group?: 'company' | null;
}
