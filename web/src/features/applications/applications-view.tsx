'use client';

import * as React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter, useSearchParams, usePathname } from 'next/navigation';
import { toast } from 'sonner';
import { ExternalLink, RotateCw } from 'lucide-react';
import { PageMast } from '@/components/ui/page-mast';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { api, getJson } from '@/lib/api';
import { cn } from '@/lib/utils';

interface AppRow {
  id: number;
  status: string;
  applied_at: string | null;
  applied_via: string | null;
  resume_id: string | null;
  vacancy: { id: number; title: string; company_name: string | null; url: string | null } | null;
}

interface AppsResponse {
  applications: AppRow[];
  counts: Record<string, number>;
  total: number;
  resume_names: Record<string, string>;
}

const PILLS = [
  { key: 'sent',     label: 'Отправлены' },
  { key: 'viewed',   label: 'Просмотрены' },
  { key: 'invited',  label: 'Приглашения' },
  { key: 'declined', label: 'Отказы' },
  { key: null,       label: 'Все' },
] as const;

export function ApplicationsView() {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const qc = useQueryClient();
  const status = sp.get('status');
  const q = sp.get('q') ?? '';

  const { data, isLoading } = useQuery({
    queryKey: ['applications', { status, q }],
    queryFn: () => {
      const u = new URLSearchParams();
      if (status) u.set('status', status);
      if (q) u.set('q', q);
      const qs = u.toString();
      return getJson<AppsResponse>(`api/applications.json${qs ? `?${qs}` : ''}`);
    },
    refetchInterval: 120_000,
  });

  const refreshMut = useMutation({
    mutationFn: () => api.post('api/pipeline/status-check'),
    onSuccess: () => {
      toast.success('проверка статусов запущена');
      // Server checks negotiations on hh.ru — takes ~30s to finish, then refetch
      setTimeout(() => qc.invalidateQueries({ queryKey: ['applications'] }), 30_000);
    },
    onError: () => toast.error('не удалось запустить проверку'),
  });

  const pushParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(sp.toString());
    if (value === null || value === '') next.delete(key);
    else next.set(key, value);
    router.push(`${pathname}${next.toString() ? `?${next.toString()}` : ''}`);
  };

  return (
    <>
      <PageMast title="Отклики" count={data ? String(data.total) : undefined} subtitle="ОТПРАВЛЕНО · ОТСЛЕЖИВАЕТСЯ" />

      <div className="flex items-end gap-4 mb-1 flex-wrap">
        <div className="flex-1 min-w-[260px]">
          <SearchInput value={q} onChange={(v) => pushParam('q', v || null)} />
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => refreshMut.mutate()}
          disabled={refreshMut.isPending}
          title="Дёргает hh.ru через Playwright — может занять до минуты"
          className="mb-4"
        >
          <RotateCw className={cn('size-4', refreshMut.isPending && 'animate-spin')} />
          Проверить статусы
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-1.5 pb-3 mb-4">
        {PILLS.map((p) => {
          const cnt = p.key ? data?.counts[p.key] : undefined;
          return (
            <Pill key={p.key ?? 'all'} active={status === p.key} onClick={() => pushParam('status', p.key)}>
              {p.label}
              {cnt !== undefined && <span className="num text-ink-3 ml-1">·{cnt}</span>}
            </Pill>
          );
        })}
      </div>

      {isLoading && !data && (
        <p className="font-mono text-[11px] tracking-[0.1em] uppercase text-ink-3 py-8">
          ···  загрузка откликов  ···
        </p>
      )}

      {data && data.applications.length === 0 && (
        <p className="font-mono text-[11px] tracking-[0.1em] uppercase text-ink-3 py-8">
          ···  откликов нет  ···
        </p>
      )}

      {data && data.applications.length > 0 && (
        <div className="border-y-2 border-hairline-bold overflow-x-auto my-3.5">
          <table className="w-full border-collapse text-[13.5px]">
            <thead>
              <tr>
                {['Вакансия', 'Компания', 'Резюме', 'Статус', 'Отправлено', 'Способ'].map((h) => (
                  <th key={h} className="text-left py-2.5 px-3.5 font-mono text-[10.5px] font-semibold uppercase tracking-[0.14em] text-ink-3 border-b border-hairline bg-paper-sink sticky top-0 z-[2]">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.applications.map((a, i) => (
                <tr key={a.id} className={cn('group hover:bg-paper-edge', i % 2 ? 'bg-white/[0.012]' : '')}>
                  <td className="p-2.5 px-3 border-b border-hairline align-top group-hover:shadow-[inset_2px_0_0_var(--color-vermilion)]">
                    {a.vacancy ? (
                      <a href={a.vacancy.url ?? '#'} target="_blank" rel="noreferrer" className="font-medium text-ink border-b border-dotted border-ink-3 hover:text-vermilion hover:border-vermilion inline-flex items-center gap-1">
                        {a.vacancy.title}
                        <ExternalLink className="size-3 opacity-60" />
                      </a>
                    ) : '—'}
                  </td>
                  <td className="p-2.5 px-3 border-b border-hairline align-top text-ink-2">{a.vacancy?.company_name || '—'}</td>
                  <td className="p-2.5 px-3 border-b border-hairline align-top">
                    {a.resume_id && data.resume_names[a.resume_id] ? (
                      <Badge variant="resume">{data.resume_names[a.resume_id]}</Badge>
                    ) : '—'}
                  </td>
                  <td className="p-2.5 px-3 border-b border-hairline align-top">
                    <Badge variant={a.status as never}>{a.status}</Badge>
                  </td>
                  <td className="p-2.5 px-3 border-b border-hairline align-top num">
                    {a.applied_at ? formatDate(a.applied_at) : '—'}
                  </td>
                  <td className="p-2.5 px-3 border-b border-hairline align-top text-ink-3 text-[12px]">
                    {a.applied_via || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function formatDate(iso: string) {
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const HH = String(d.getHours()).padStart(2, '0');
  const MM = String(d.getMinutes()).padStart(2, '0');
  return `${dd}.${mm} ${HH}:${MM}`;
}

function Pill({ children, active, onClick }: { children: React.ReactNode; active?: boolean; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1.5 border rounded-[2px] font-sans font-medium tracking-[0.01em] transition-colors leading-snug px-3.5 py-1.5 text-[12.5px]',
        active ? 'bg-ink text-paper border-ink font-semibold' : 'text-ink-2 border-hairline-bold hover:text-ink hover:border-ink-3',
      )}
    >
      {children}
    </button>
  );
}

function SearchInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [local, setLocal] = React.useState(value);
  React.useEffect(() => setLocal(value), [value]);
  return (
    <form className="mb-3.5" onSubmit={(e) => { e.preventDefault(); onChange(local); }}>
      <input
        type="search"
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        placeholder="поиск по названию или компании…"
        className="w-full bg-paper border-0 border-b-2 border-hairline-bold py-3 px-1 font-display italic text-[18px] text-ink placeholder:text-ink-3 placeholder:italic focus:outline-none focus:border-vermilion transition-colors"
      />
    </form>
  );
}
