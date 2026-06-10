'use client';

import * as React from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, X, Pencil, FileX, ExternalLink, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { approveLetter, editAndApprove, noLetterAction, rejectLetter } from './api';
import { EditDialog } from './edit-dialog';
import type { Letter, LettersListResponse } from './types';

interface Props {
  letter: Letter;
  resumeName: string | null;
  listQueryKey: unknown[];
}

function scoreClass(score: number | null) {
  if (score === null) return 'text-ink-3';
  if (score >= 0.7) return 'text-sage';
  if (score >= 0.5) return 'text-gold';
  return 'text-brick';
}

function formatSalary(v: Letter['vacancy']): string | null {
  if (!v.salary_from && !v.salary_to) return null;
  const from = v.salary_from ?? '?';
  const to = v.salary_to ?? '?';
  return `${from}–${to} ${v.salary_currency ?? ''}`.trim();
}

export function LetterCard({ letter, resumeName, listQueryKey }: Props) {
  const qc = useQueryClient();
  const [editOpen, setEditOpen] = React.useState(false);
  const text = letter.edited_text || letter.generated_text;
  const v = letter.vacancy;

  /* Optimistic mutation: snapshot the list, remove the letter, revert on error. */
  type Snapshot = { prev?: LettersListResponse };

  const snapshotAndRemove = async (): Promise<Snapshot> => {
    await qc.cancelQueries({ queryKey: listQueryKey });
    const prev = qc.getQueryData<LettersListResponse>(listQueryKey);
    if (prev) {
      qc.setQueryData<LettersListResponse>(listQueryKey, {
        ...prev,
        letters: prev.letters.filter((l) => l.id !== letter.id),
      });
    }
    return { prev };
  };

  const restoreSnapshot = (ctx: Snapshot | undefined) => {
    if (ctx?.prev) qc.setQueryData(listQueryKey, ctx.prev);
  };

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ['letters'] });
    qc.invalidateQueries({ queryKey: ['pending-letters'] });
  };

  const approveMut = useMutation({
    mutationFn: () => approveLetter(letter.id),
    onMutate: snapshotAndRemove,
    onError: (_e, _v, ctx) => { restoreSnapshot(ctx); toast.error('не удалось одобрить'); },
    onSuccess: () => toast.success('письмо одобрено'),
    onSettled: invalidateAll,
  });

  const noLetterMut = useMutation({
    mutationFn: () => noLetterAction(letter.id),
    onMutate: snapshotAndRemove,
    onError: (_e, _v, ctx) => { restoreSnapshot(ctx); toast.error('не удалось сохранить'); },
    onSuccess: () => toast.success('отклик без письма'),
    onSettled: invalidateAll,
  });

  const rejectMut = useMutation({
    mutationFn: () => rejectLetter(letter.id),
    onMutate: snapshotAndRemove,
    onError: (_e, _v, ctx) => { restoreSnapshot(ctx); toast.error('не удалось отклонить'); },
    onSuccess: () => toast.success('письмо отклонено'),
    onSettled: invalidateAll,
  });

  const editMut = useMutation({
    mutationFn: (newText: string) => editAndApprove(letter.id, newText),
    onMutate: async (newText) => {
      await qc.cancelQueries({ queryKey: listQueryKey });
      const prev = qc.getQueryData<LettersListResponse>(listQueryKey);
      if (prev) {
        qc.setQueryData<LettersListResponse>(listQueryKey, {
          ...prev,
          letters: prev.letters.map((l) =>
            l.id === letter.id
              ? { ...l, edited_text: newText, status: 'approved' as const }
              : l
          ),
        });
      }
      return { prev };
    },
    onError: (_e, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(listQueryKey, ctx.prev);
      toast.error('не удалось сохранить');
    },
    onSuccess: () => {
      toast.success('письмо сохранено и одобрено');
      setEditOpen(false);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['letters'] });
      qc.invalidateQueries({ queryKey: ['pending-letters'] });
    },
  });

  const busy =
    approveMut.isPending ||
    noLetterMut.isPending ||
    rejectMut.isPending ||
    editMut.isPending;

  const salary = formatSalary(v);

  return (
    <>
      <article
        className={cn(
          'relative bg-paper border-t-2 border-t-hairline-bold border-b border-b-hairline ' +
            'mb-7 pl-[30px] pr-6 py-5 flex flex-col gap-4',
          busy && 'opacity-60 pointer-events-none'
        )}
      >
        <span className="absolute left-0 top-0 w-[3px] h-full bg-vermilion" aria-hidden />

        <header className="flex items-start justify-between gap-6">
          <div className="flex-1 min-w-0">
            <h3 className="font-display italic font-semibold text-[22px] leading-tight tracking-[-0.005em] text-ink m-0 mb-1.5">
              <a
                href={v.url ?? '#'}
                target="_blank"
                rel="noreferrer"
                className="text-ink border-b border-dotted border-ink-3 pb-px hover:text-vermilion hover:border-vermilion"
              >
                {v.title}
              </a>
              {v.company_name && (
                <span className="not-italic font-normal text-ink-2 font-sans text-[15px] ml-2">
                  @ {v.company_name}
                </span>
              )}
            </h3>

            <div className="font-mono text-[11.5px] text-ink-2 tracking-[0.04em] flex flex-wrap gap-x-3.5 gap-y-1 items-center mt-1">
              <span>
                оценка{' '}
                <span className={cn('font-semibold num', scoreClass(v.relevance_score))}>
                  {v.relevance_score !== null
                    ? `${(v.relevance_score * 100).toFixed(0)}%`
                    : '—'}
                </span>
              </span>
              {resumeName && (
                <>
                  <span className="text-ink-4">│</span>
                  <span>
                    резюме <Badge variant="resume">{resumeName}</Badge>
                  </span>
                </>
              )}
              {salary && (
                <>
                  <span className="text-ink-4">│</span>
                  <span>зп {salary}</span>
                </>
              )}
              {v.employment === 'part' && (
                <>
                  <span className="text-ink-4">│</span>
                  <Badge variant="parttime">Частичная</Badge>
                </>
              )}
              {v.employment === 'project' && (
                <>
                  <span className="text-ink-4">│</span>
                  <Badge variant="project">Проект</Badge>
                </>
              )}
              <span className="text-ink-4">│</span>
              <a
                href={v.url ?? '#'}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-ink-2 border-b border-dotted border-ink-3 hover:text-vermilion hover:border-vermilion"
              >
                hh.ru <ExternalLink className="size-3" />
              </a>
            </div>

            {v.matched_skills.length > 0 && (
              <div className="font-mono text-[11px] tracking-[0.02em] leading-snug mt-1.5 text-sage">
                + {v.matched_skills.join(' · ')}
              </div>
            )}
            {v.missing_skills.length > 0 && (
              <div className="font-mono text-[11px] tracking-[0.02em] leading-snug text-brick opacity-90">
                − {v.missing_skills.join(' · ')}
              </div>
            )}

            {v.description && (
              <details className="mt-2.5 text-[13px] group">
                <summary className="font-mono text-[11px] uppercase tracking-[0.1em] text-ink-3 cursor-pointer pb-1 border-b border-dotted border-ink-4 w-max inline-flex items-center gap-1 hover:text-vermilion list-none">
                  <ChevronDown className="size-3 transition-transform group-open:rotate-180" />
                  описание вакансии
                </summary>
                <div
                  className="pt-3.5 pb-1 text-ink-2 leading-[1.65] text-[13px] mt-1 border-t border-hairline max-h-[360px] overflow-y-auto"
                  dangerouslySetInnerHTML={{ __html: v.description }}
                />
              </details>
            )}
          </div>

          <Badge variant={letter.status}>{letter.status}</Badge>
        </header>

        <div
          className={cn(
            'font-mono text-[13px] leading-[1.75] text-ink whitespace-pre-wrap break-words ' +
              'bg-paper-sink border border-hairline border-l-[3px] border-l-gold p-5'
          )}
        >
          {text}
        </div>

        {letter.status === 'pending' && (
          <div className="flex flex-wrap gap-2 items-center pt-1 border-t border-hairline">
            <Button
              variant="primary"
              onClick={() => approveMut.mutate()}
              disabled={busy}
            >
              <Check className="size-4" /> Одобрить
            </Button>
            <Button
              variant="secondary"
              onClick={() => setEditOpen(true)}
              disabled={busy}
            >
              <Pencil className="size-4" /> Редактировать
            </Button>
            <Button
              variant="outline"
              onClick={() => noLetterMut.mutate()}
              disabled={busy}
            >
              <FileX className="size-4" /> Без письма
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                if (confirm('Отклонить это письмо?')) rejectMut.mutate();
              }}
              disabled={busy}
            >
              <X className="size-4" /> Отклонить
            </Button>
          </div>
        )}
      </article>

      <EditDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        initialText={text}
        title={v.title}
        company={v.company_name}
        onSave={(newText) => editMut.mutate(newText)}
        saving={editMut.isPending}
      />
    </>
  );
}
