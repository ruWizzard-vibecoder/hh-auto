import { api, getJson } from '@/lib/api';
import type { Letter, LettersListQuery, LettersListResponse } from './types';

function buildSearch(p: LettersListQuery): string {
  const sp = new URLSearchParams();
  if (p.status) sp.set('status', p.status);
  if (p.employment) sp.set('employment', p.employment);
  if (p.sort && p.sort !== 'date') sp.set('sort', p.sort);
  if (p.q) sp.set('q', p.q);
  return sp.toString();
}

export async function fetchLetters(params: LettersListQuery): Promise<LettersListResponse> {
  const qs = buildSearch(params);
  const url = `api/letters${qs ? `?${qs}` : ''}`;
  return getJson<LettersListResponse>(url);
}

export async function approveLetter(id: number): Promise<Letter> {
  return api.post(`api/letters/${id}/approve`).json<Letter>();
}

export async function noLetterAction(id: number): Promise<Letter> {
  return api.post(`api/letters/${id}/no-letter`).json<Letter>();
}

export async function rejectLetter(id: number): Promise<Letter> {
  return api.post(`api/letters/${id}/reject`).json<Letter>();
}

export async function editAndApprove(id: number, edited_text: string): Promise<Letter> {
  return api.post(`api/letters/${id}/edit`, { json: { edited_text } }).json<Letter>();
}

export async function bulkApprove(threshold: number): Promise<{ updated: number }> {
  return api.post('api/letters/bulk-approve', { json: { threshold } }).json();
}

export async function bulkNoLetter(threshold: number): Promise<{ updated: number }> {
  return api.post('api/letters/bulk-no-letter', { json: { threshold } }).json();
}

export async function bulkReject(threshold: number): Promise<{ updated: number }> {
  return api.post('api/letters/bulk-reject', { json: { threshold } }).json();
}
