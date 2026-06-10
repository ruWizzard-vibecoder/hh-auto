import ky from 'ky';

/* ky-инстанс для FastAPI бэка. В dev все /api/* запросы Next прокидывает через rewrites из next.config.ts.
   В prod (standalone) то же — обе службы за одним Nginx или systemd reverse-proxy. */

export const api = ky.create({
  prefix: '/',
  timeout: 30_000,
  retry: { limit: 1, methods: ['get'] },
});

/* Convenience: get JSON of a typed shape from a path. */
export async function getJson<T>(path: string): Promise<T> {
  return api.get(path).json<T>();
}

export async function postJson<T = unknown>(path: string, body?: unknown): Promise<T> {
  return api.post(path, body ? { json: body } : undefined).json<T>();
}
