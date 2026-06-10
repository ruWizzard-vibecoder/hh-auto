export interface DashboardStats {
  total_vacancies: number;
  pending_letters: number;
  applications_sent: number;
  applications_today: number;
  viewed: number;
  invited: number;
  scored: number;
  letters_total: number;
  approved: number;
  responded: number;
}

export interface EventLogEntry {
  id: number;
  created_at: string | null;
  event_type: string;
  details: Record<string, unknown> | null;
  error_message: string | null;
}
