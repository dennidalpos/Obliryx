export type Reply<T> = {ok: true; value: T} | {ok: false; error: string};
export type Field = {key: string; label: string; kind: string; choices: string[] | null; default: string; required: boolean};
export type Operation = {id: string; label: string; group: string; fields: Field[]};
export type Finding = {id: string; controller?: string; sender?: string; source: string; subject?: string; recorded_at?: string; enrollment: string; gravita: string; motivo: string; routes: Record<string, unknown>[]; azioni: Record<string, unknown>[]; [key: string]: unknown};
export type Request = {id: string; kind: 'field' | 'approval'; label: string; preview: unknown; secret: boolean};
export type Job = {id: string | null; status: string; phase: string; request: Request | null; result: unknown; error: string | null};
export type Status = {unlocked: boolean; path: string | null; job: Job};
export type Boot = {version: string; default_path: string; operations: Operation[]};

type Bridge = {
  bootstrap(): Promise<Reply<Boot>>;
  unlock(path: string, password: string, create: boolean, repeated: string): Promise<Reply<{path: string; created: boolean}>>;
  status(): Promise<Reply<Status>>;
  findings(offset: number, limit: number): Promise<Reply<{items: Finding[]; total: number}>>;
  catalog(id?: string): Promise<Reply<Record<string, unknown>>>;
  start(operation: string, parameters: Record<string, string>): Promise<Reply<{id: string}>>;
  respond(job: string, request: string, answer: string): Promise<Reply<null>>;
  cancel(job: string): Promise<Reply<null>>;
  lock(): Promise<Reply<null>>;
  touch(): Promise<Reply<null>>;
  choose_path(mode: string): Promise<Reply<string | null>>;
};
declare global { interface Window { pywebview?: {api: Bridge} } }

export async function api<K extends keyof Bridge>(method: K, ...args: Parameters<Bridge[K]>): Promise<Awaited<ReturnType<Bridge[K]>> extends Reply<infer T> ? T : never> {
  if (!window.pywebview) throw new Error('Avvia questa interfaccia dall’app Obliryx desktop. Il browser di sviluppo non apre il tuo archivio.');
  const fn = window.pywebview.api[method] as (...a: unknown[]) => Promise<Reply<unknown>>;
  const reply = await fn(...args);
  if (!reply.ok) throw new Error(reply.error);
  return reply.value as Awaited<ReturnType<Bridge[K]>> extends Reply<infer T> ? T : never;
}

export const labels: Record<string, string> = {
  messaggio_importato: 'Posta importata', pagina_verificata: 'Pagina verificata', riscontro_manual: 'Riscontro manuale', hibp: 'Have I Been Pwned',
  da_verificare: 'Da verificare', riconosciuta: 'Riconosciuta', non_riconosciuta: 'Non riconosciuta',
  accepted: 'Invio accettato', delivery_unknown: 'Esito incerto', rejected: 'Invio rifiutato',
  rimozione_dichiarata: 'Rimozione dichiarata', dato_non_osservato: 'Dato non osservato', dato_osservato: 'Dato osservato',
  ricomparsa: 'Ricomparsa', non_verificabile: 'Non verificabile', inviata: 'Inviata (dichiarazione)',
  web_manual: 'Canale manuale', unsubscribe_candidate: 'Candidato da verificare', one_click_candidate: 'One-click da verificare',
  email_header: 'Canale email', web_header: 'Link nelle intestazioni', web_body: 'Link nel messaggio',
  diretto: 'Email completa', prefisso: 'Prefisso hash — piano compatibile richiesto',
  'app-password': 'Password per app', xoauth2: 'Token OAuth già ottenuto',
};
export const label = (value: unknown): string => typeof value === 'string' ? (labels[value] || value.replaceAll('_', ' ')) : String(value ?? '—');

export function filterFindings(items: Finding[], query: string, source: string, level: string, enrollment: string) {
  const needle = query.trim().toLocaleLowerCase('it');
  return items.filter(f => (!needle || [f.controller, f.sender, f.subject].some(v => v?.toLocaleLowerCase('it').includes(needle)))
    && (!source || f.source === source) && (!level || f.gravita === level) && (!enrollment || f.enrollment === enrollment));
}
