export interface Vacancy {
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
  status: string;
  recommended_resume_id: string | null;
  published_at: string | null;
}

export interface VacanciesResponse {
  vacancies: Vacancy[];
  total: number;
  page: number;
  per_page: number;
  has_more: boolean;
  employment_counts: Partial<Record<'full' | 'part' | 'project', number>>;
  resume_names: Record<string, string>;
}
