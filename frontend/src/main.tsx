import React, {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {api, Boot, Finding, Job, Operation, Request, Status, filterFindings, label} from './bridge';
import './style.css';
import {Workflow} from './workflow';

const pages = [['findings', 'Riscontri'], ['import', 'Importa e monitora'], ['search', 'Ricerche'], ['brokers', 'Procedure broker'], ['archive', 'Archivio']];
const date = (s: unknown) => typeof s === 'string' && !Number.isNaN(Date.parse(s)) ? new Date(s).toLocaleDateString('it-IT') : '—';
const message = (e: unknown) => e instanceof Error ? e.message : 'Operazione non riuscita.';

function DataView({value}: {value: unknown}) {
  if (value == null) return <span>—</span>;
  if (Array.isArray(value)) return value.length ? <ul className="data-list">{value.map((v, i) => <li key={i}><DataView value={v}/></li>)}</ul> : <p>Nessun elemento.</p>;
  if (typeof value === 'object') return <dl className="data">{Object.entries(value).map(([key, v]) => <div key={key}><dt>{label(key)}</dt><dd><DataView value={v}/></dd></div>)}</dl>;
  return <span className="value">{typeof value === 'boolean' ? (value ? 'Sì' : 'No') : label(value)}</span>;
}

function Icon({name}: {name: string}) {
  const paths: Record<string, string> = {
    findings: 'M4 5h16v15H4z M8 3v4 M16 3v4 M8 11h8 M8 15h5',
    import: 'M12 3v12 M7 10l5 5 5-5 M4 16v5h16v-5',
    search: 'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14 M15 15l6 6',
    brokers: 'M3 21h18 M5 21V9h14v12 M3 9l9-6 9 6 M9 12v5 M15 12v5',
    archive: 'M4 8h16v13H4z M3 3h18v5H3z M9 12h6',
    lock: 'M6 10h12v11H6z M8 10V7a4 4 0 0 1 8 0v3 M12 14v3',
  };
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] || paths.findings}/></svg>;
}

function Unlock({boot, onOpen, fail}: {boot: Boot; onOpen: (created: boolean) => void; fail: (e: unknown) => void}) {
  const [create, setCreate] = useState(true);
  const [path, setPath] = useState(boot.default_path);
  const [busy, setBusy] = useState(false);
  async function choose() { try { const p = await api('choose_path', create ? 'save' : 'open'); if (p) setPath(p); } catch(e) { fail(e); } }
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget; const fields = new FormData(form);
    setBusy(true);
    const pending = api('unlock', path, String(fields.get('password')), create, String(fields.get('repeated') || ''));
    form.reset(); // Remove secret DOM values immediately; never persist them.
    try { const result = await pending; onOpen(result.created); } catch(e) { fail(e); } finally { setBusy(false); }
  }
  return <main className="welcome">
    <div className="welcome-copy"><div className="brand">Obliryx<span>Archivio personale</span></div>
      <h1>Capisci dove compaiono i tuoi dati.<br/>Scegli come intervenire.</h1>
      <p>Raccogli i riscontri dalla tua posta e dalle fonti che verifichi. Esamina le prove e prepara le tue richieste, un passo alla volta.</p>
      <ul className="principles"><li>Archivio cifrato sul tuo dispositivo.</li><li>Ogni contatto esterno richiede la tua conferma.</li><li>Un invio accettato non dimostra la rimozione.</li></ul>
      <p className="muted">Nessun account Obliryx. Le ricerche esterne richiedono credenziali proprie, inserite soltanto quando servono.</p>
    </div>
    <section className="unlock" aria-labelledby="unlock-title"><h2 id="unlock-title">Il tuo archivio</h2>
      <div className="switch" role="group" aria-label="Scegli archivio"><button type="button" aria-pressed={create} onClick={() => setCreate(true)}>Crea nuovo</button><button type="button" aria-pressed={!create} onClick={() => setCreate(false)}>Apri esistente</button></div>
      <form onSubmit={submit} autoComplete="off">
        <label>Percorso dell’archivio<input value={path} onChange={e => setPath(e.target.value)} required/></label>
        <button type="button" className="text-button" onClick={choose}>Scegli {create ? 'destinazione' : 'file'}…</button>
        <label>Passphrase<input key={`pass-${create}`} name="password" type="password" required minLength={12} autoComplete="off"/></label>
        {create && <label>Ripeti la passphrase<input name="repeated" type="password" required minLength={12} autoComplete="off"/></label>}
        <p className="notice">{create ? 'Scegli almeno 12 caratteri. Conserva la passphrase in un luogo sicuro: se la perdi non potrai recuperare i riscontri.' : 'Usa la passphrase di questo archivio. Il registro degli invii resta sul dispositivo e verrà controllato prima di nuovi invii.'}</p>
        <button className="primary" disabled={busy}>{busy ? 'Apertura in corso…' : create ? 'Crea archivio' : 'Apri archivio'}</button>
      </form>
    </section>
  </main>;
}

function OperationForm({operation, finding, launch, cancel, fail}: {operation: Operation; finding?: Finding; launch: (id: string, params: Record<string, string>) => void; cancel: () => void; fail: (e: unknown) => void}) {
  const [values, setValues] = useState<Record<string, string>>(Object.fromEntries(operation.fields.map(f => [f.key, f.default || f.choices?.[0] || ''])));
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {heading.current?.focus(); heading.current?.scrollIntoView({block:'start'});}, []);
  return <section className="operation" aria-label={operation.label}>
    <h2 ref={heading} tabIndex={-1}>{operation.label}</h2><p className="muted">{finding ? `Riscontro: ${finding.controller || finding.sender || 'Organizzazione da verificare'}. ` : ''}Le eventuali letture esterne e gli invii saranno approvati separatamente.</p>
    {operation.id === 'check-breach' && <p className="notice">HIBP associa un indirizzo a incidenti noti. Le categorie dell’incidente non dimostrano quali dati fossero nel tuo record. Il prefisso richiede un piano compatibile.</p>}
    {operation.id === 'search-web' && <p className="notice">Brave riceverà l’identificativo completo. I risultati sono transitori: verifica la pagina originale prima di registrare un riscontro.</p>}
    <form onSubmit={e => {e.preventDefault(); launch(operation.id, {...values, ...(finding ? {id: finding.id} : {})});}} autoComplete="off">
      {operation.fields.map(f => <div key={f.key}><label>{f.label}{!f.required && ' (facoltativo)'}
        {f.choices ? <select value={values[f.key]} onChange={e => setValues({...values, [f.key]: e.target.value})}>{f.choices.map(c => <option key={c} value={c}>{c ? label(c) : 'Nessuno'}</option>)}</select>
          : <input type={f.kind === 'number' ? 'number' : 'text'} value={values[f.key]} required={f.required} onChange={e => setValues({...values, [f.key]: e.target.value})}/>}</label>
        {['path', 'save'].includes(f.kind) && <div className="buttons">{(f.kind === 'save' ? ['save'] : ['open', 'folder']).map(mode => <button type="button" className="text-button" key={mode} onClick={async () => {try {const p = await api('choose_path', mode); if(p) setValues({...values, [f.key]: p});} catch(e) {fail(e);}}}>{mode === 'folder' ? 'Scegli cartella…' : 'Scegli file…'}</button>)}</div>}
      </div>)}
      <div className="buttons"><button className="primary">Continua</button><button type="button" onClick={cancel}>Annulla</button></div>
    </form>
  </section>;
}

function Question({job, request, fail}: {job: Job; request: Request; fail: (e: unknown) => void}) {
  const field = useRef<HTMLInputElement>(null); const [busy, setBusy] = useState(false);
  useEffect(() => {field.current?.focus();}, [request.id]);
  return <form className="question" onSubmit={async e => {e.preventDefault(); if(busy) return; const answer = field.current?.value || ''; if(field.current) field.current.value = ''; setBusy(true); try { await api('respond', job.id!, request.id, answer); } catch(e) {fail(e); setBusy(false);}}} autoComplete="off">
    <h3>{request.kind === 'approval' ? 'Controlla prima di confermare' : 'Completa questo passaggio'}</h3>
    <p id="question-label">{request.label}</p>
    {request.preview != null && <div className="preview"><DataView value={request.preview}/></div>}
    <label>{request.kind === 'approval' ? 'Digita CONFERMO per approvare questo passaggio' : 'La tua risposta'}
      <input ref={field} type={request.secret ? 'password' : 'text'} autoComplete="off" aria-describedby="question-label" required={request.kind === 'approval'} pattern={request.kind === 'approval' ? 'CONFERMO' : undefined}/></label>
    <p className="muted">{request.secret ? 'Questo valore è transitorio e non viene salvato nei log. ' : ''}Il passaggio scade dopo 5 minuti.</p>
    <button className="primary" disabled={busy}>{request.kind === 'approval' ? 'Approva questo passaggio' : 'Continua'}</button>
  </form>;
}

function App() {
  const [boot, setBoot] = useState<Boot>(); const [status, setStatus] = useState<Status>();
  const [page, setPage] = useState('findings'); const [error, setError] = useState('');
  const [items, setItems] = useState<Finding[]>([]); const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<string>(); const [query, setQuery] = useState('');
  const [source, setSource] = useState(''); const [level, setLevel] = useState(''); const [enrollment, setEnrollment] = useState('');
  const [operation, setOperation] = useState<Operation>(); const [catalog, setCatalog] = useState<Record<string, unknown>>();
  const [broker, setBroker] = useState<Record<string, unknown>>(); const [loading, setLoading] = useState(false);
  const [dismissed, setDismissed] = useState<string>();
  const previous = useRef(''); const alive = useRef(true); const session = useRef(0);
  const detailHeading = useRef<HTMLHeadingElement>(null);
  const rowRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const fail = (e: unknown) => setError(message(e));
  const finding = items.find(f => f.id === selected);
  const busy = status?.job.status === 'running';

  async function refresh(offset = 0) {
    const generation = session.current; setLoading(true);
    try { const result = await api('findings', offset, 500); if(generation === session.current) {setItems(old => offset ? [...old, ...result.items] : result.items); setTotal(result.total);} } catch(e) { if(generation === session.current) fail(e); } finally {setLoading(false);}
  }
  function clearSession() { session.current++; setItems([]); setTotal(0); setSelected(undefined); setOperation(undefined); setBroker(undefined); setCatalog(undefined); setQuery(''); setError(''); previous.current = ''; }
  useEffect(() => {
    alive.current = true; let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      if (!window.pywebview) { timer = setTimeout(poll, 250); return; }
      try {
        const config = await api('bootstrap'); if(alive.current) setBoot(config);
        const next = await api('status'); if(!alive.current) return;
        setStatus(old => {if(old?.unlocked && !next.unlocked) clearSession(); return next;});
        const key = `${next.unlocked}-${next.job.id}-${next.job.status}`;
        if(next.unlocked && next.job.status !== 'running' && key !== previous.current) { previous.current = key; await refresh(); }
      } catch(e) {if(alive.current) fail(e);}
      timer = setTimeout(poll, 400);
    }
    void poll();
    let touched = 0;
    const touch = () => {if(Date.now() - touched > 3000 && window.pywebview) {touched = Date.now(); void api('touch');}};
    window.addEventListener('pointerdown', touch); window.addEventListener('keydown', touch);
    return () => {alive.current = false; clearTimeout(timer); window.removeEventListener('pointerdown', touch); window.removeEventListener('keydown', touch);};
  }, []);

  async function launch(id: string, parameters: Record<string, string>) {
    setError(''); try {const result = await api('start', id, parameters); setOperation(undefined); setDismissed(undefined); const next = await api('status'); setStatus(next); return result;} catch(e) {fail(e);}
  }
  async function lock() {clearSession(); try {await api('lock'); setStatus(await api('status'));} catch(e) {fail(e);}}
  async function navigate(next: string) {setPage(next); setOperation(undefined); setError(''); if(next === 'brokers') {try {setCatalog(await api('catalog'));} catch(e) {fail(e);}}}
  const choose = (id: string) => {const op = boot?.operations.find(o => o.id === id); if(op) {setOperation(op); setError('');}};
  const visible = filterFindings(items, query, source, level, enrollment);
  useEffect(() => {
    if(selected && window.matchMedia('(max-width:1100px)').matches) {detailHeading.current?.focus(); detailHeading.current?.scrollIntoView({block:'start'});}
  }, [selected]);
  function backToList() {const id = selected; setSelected(undefined); requestAnimationFrame(() => {if(id) {rowRefs.current[id]?.focus(); rowRefs.current[id]?.scrollIntoView({block:'nearest'});}});}
  useEffect(() => {
    const dropped = (event: Event) => {
      const path = (event as CustomEvent<string>).detail;
      if(page === 'import' && !busy && typeof path === 'string') void launch(path.toLowerCase().endsWith('.mbox') ? 'import-mbox' : 'import-eml', {path});
    };
    window.addEventListener('obliryx-drop', dropped);
    return () => window.removeEventListener('obliryx-drop', dropped);
  }, [page, busy]);

  if (!boot || !status) return <main className="starting"><h1>Obliryx</h1><p role="status">Apertura dell’interfaccia locale…</p>{error && <p role="alert">{error}</p>}</main>;
  if (!status.unlocked) return <>{error && <div className="global-error" role="alert">{error}<button onClick={() => setError('')}>Chiudi avviso</button></div>}<Unlock boot={boot} fail={fail} onOpen={async created => {setPage(created ? 'import' : 'findings'); setStatus(await api('status'));}}/></>;

  return <div className="shell"><a className="skip" href="#main">Vai al contenuto</a>
    <aside className="sidebar"><div className="brand">Obliryx<span>Archivio personale</span></div>
      <nav aria-label="Navigazione principale">{pages.map(([id, title]) => <button key={id} aria-current={page === id ? 'page' : undefined} onClick={() => void navigate(id)}><Icon name={id}/>{title}</button>)}</nav>
      <div className="sidebar-foot"><p>Solo sul tuo dispositivo</p><button onClick={() => void lock()}><Icon name="lock"/>Blocca archivio</button><small>{boot.version} · sviluppo</small></div>
    </aside>
    <main id="main" className="workspace">
      <header className="page-header"><div><h1>{pages.find(p => p[0] === page)?.[1]}</h1><p>{page === 'findings' ? 'Dalle prove alla prossima azione.' : page === 'import' ? 'Parti dalla posta che hai già.' : page === 'search' ? 'Verifica le fonti, conservando il contesto.' : page === 'archive' ? 'Le tue copie, la tua passphrase, i tuoi invii.' : 'Canali ufficiali da verificare prima dell’uso.'}</p></div><span className="archive-status">Archivio aperto</span></header>
      {error && <div className="error" role="alert">{error}<button onClick={() => setError('')}>Chiudi avviso</button></div>}
      {status.job.id && dismissed !== status.job.id && <section className="activity" aria-label="Attività corrente"><div className="activity-head"><p role="status">{status.job.phase}</p>{busy ? <button onClick={() => void api('cancel', status.job.id!).catch(fail)}>Annulla / arresta</button> : <button onClick={() => setDismissed(status.job.id!)}>Chiudi attività</button>}</div>
        {status.job.request && <Question key={status.job.request.id} job={status.job} request={status.job.request} fail={fail}/>}
        {status.job.result != null && <details open={!busy}><summary>Risultato {busy ? 'parziale' : 'dell’attività'}</summary><DataView value={status.job.result}/></details>}
        {status.job.status === 'completed' && <p className="muted">Se è stato eseguito un invio, controlla l’esito tecnico: la rimozione richiede una verifica separata.</p>}
      </section>}
      {operation && !busy && <OperationForm key={`${operation.id}-${selected}`} operation={operation} finding={operation.group === 'detail' ? finding : undefined} launch={(id, params) => void launch(id, params)} cancel={() => setOperation(undefined)} fail={fail}/>}
      {page === 'findings' && <>
        <div className="toolbar"><label className="search-field">Cerca nei riscontri<input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Organizzazione, mittente o oggetto"/></label>
          <label>Fonte<select value={source} onChange={e => setSource(e.target.value)}><option value="">Tutte le fonti</option>{[...new Set(items.map(f => f.source))].map(s => <option key={s} value={s}>{label(s)}</option>)}</select></label>
          <label>Gravità<select value={level} onChange={e => setLevel(e.target.value)}><option value="">Tutte</option>{['alta','media','bassa'].map(s => <option key={s}>{s}</option>)}</select></label>
          <label>Iscrizione<select value={enrollment} onChange={e => setEnrollment(e.target.value)}><option value="">Tutte</option>{['da_verificare','riconosciuta','non_riconosciuta'].map(s => <option key={s} value={s}>{label(s)}</option>)}</select></label>
        </div>
        <div className="list-heading"><p aria-live="polite">{visible.length} riscontri visualizzati · {total} nell’archivio</p><div className="buttons"><button disabled={busy} onClick={() => void refresh()}>Aggiorna</button><button disabled={busy} onClick={() => choose('campaigns')}>Raggruppa campagne</button></div></div>
        {loading && <p role="status">Lettura dei riscontri…</p>}
        {!total && !loading ? <section className="empty"><Icon name="findings"/><h2>Il primo riscontro parte da una fonte.</h2><p>Importa un file EML, una cartella o un’esportazione MBOX. Potrai poi esaminare mittenti, prove e canali disponibili.</p><button className="primary" onClick={() => void navigate('import')}>Importa la tua posta</button><button onClick={() => void navigate('search')}>Registra una fonte verificata</button></section> : <div className={`split ${finding ? 'has-selection' : ''}`}>
          <section className="finding-list" aria-label="Elenco riscontri">{!visible.length && <p className="empty-small">Nessun riscontro corrisponde ai filtri.</p>}{visible.map(f => <button className="finding-row" ref={node => {rowRefs.current[f.id] = node;}} key={f.id} aria-pressed={selected === f.id} onClick={() => {setSelected(f.id); setOperation(undefined);}}><span className="row-top"><strong>{f.controller || f.sender || 'Organizzazione da verificare'}</strong><span className={`severity ${f.gravita}`}>{f.gravita}</span></span><span className="subject">{f.subject || label(f.source)}</span><span className="row-bottom"><span>{label(f.enrollment)}</span><time>{date(f.recorded_at)}</time></span></button>)}
            {items.length < total && <button disabled={busy || loading} onClick={() => void refresh(items.length)}>Carica altri riscontri</button>}
          </section>
          {finding ? <article className="finding-detail" aria-label="Dettaglio riscontro"><button className="back" onClick={backToList}>Torna all’elenco</button><p className="muted">{label(finding.source)} · {date(finding.recorded_at)}</p><h2 ref={detailHeading} tabIndex={-1}>{finding.controller || finding.sender || 'Organizzazione da verificare'}</h2><p>{finding.subject}</p><p className="notice">{finding.motivo} La presenza di un messaggio non dimostra acquisto dei dati o assenza di consenso.</p>
            <section className="next-step"><h3>Il prossimo passo</h3><p>{finding.enrollment === 'da_verificare' ? 'Indica se riconosci questa iscrizione, prima di scegliere come intervenire.' : !finding.routes.length ? 'Documenta il contatto ufficiale o cerca un canale alla fonte.' : 'Esamina il canale e prepara la richiesta più adatta.'}</p><button className="primary" disabled={busy} onClick={() => choose(finding.enrollment === 'da_verificare' ? 'review' : !finding.routes.length ? 'document' : 'draft')}>{finding.enrollment === 'da_verificare' ? 'Rivedi l’iscrizione' : !finding.routes.length ? 'Documenta le prove e il contatto' : 'Prepara una richiesta'}</button></section>
            <h3>Prove e provenienza</h3><DataView value={{mittente_dichiarato: finding.sender, fonte: finding.source_url, categorie: finding.data_types, prova: finding.evidence, titolare_revisionato: finding.controller_reviews, confronto_posta: finding.mail_matches}}/>
            <h3>Canali disponibili</h3>{finding.routes.length ? finding.routes.map((r, i) => <div className="route" key={i}><strong>Canale {i + 1} · {label(r.kind)}</strong><p className="value">{String(r.value || '')}</p><p className="muted">{r.confirmed_at ? 'Pertinenza confermata manualmente. Non abilita il one-click.' : 'Verifica provenienza e pertinenza prima di agire.'}</p></div>) : <p>Nessun canale individuato. Cerca sul sito ufficiale indipendentemente dal messaggio.</p>}
            <details><summary>Altre azioni sul riscontro</summary><div className="action-list">{boot.operations.filter(o => o.group === 'detail').map(o => <button disabled={busy} key={o.id} onClick={() => choose(o.id)}>{o.label}</button>)}</div></details>
            <h3>Storico ed esiti</h3><p className="muted">“Invio accettato” è una risposta tecnica. Gli esiti dichiarati e i controlli alla fonte restano separati.</p><DataView value={{invii: finding.azioni, esiti_dichiarati: finding.outcomes, controlli_web: finding.web_checks}}/>
          </article> : <section className="detail-placeholder"><h2>Ogni riscontro ha una storia.</h2><p>Scegline uno per esaminare le prove, verificare il titolare e decidere il prossimo passo.</p></section>}
        </div>}
      </>}
      {['import', 'search', 'archive'].includes(page) && <>
        {page === 'import' && <div className="intro"><h2>Analizza una copia della tua posta</h2><p>I messaggi originali rimangono nei file di partenza. L’importazione locale non contatta i mittenti. Per IMAP verranno mostrati server e dati di accesso prima del collegamento.</p><div className="dropzone" onDragOver={e => e.preventDefault()} onDrop={e => e.preventDefault()}><Icon name="import"/><p>Trascina qui un file EML o MBOX</p><button disabled={busy} onClick={async () => {try {const path = await api('choose_path', 'open'); if(path) void launch(path.toLowerCase().endsWith('.mbox') ? 'import-mbox' : 'import-eml', {path});} catch(e) {fail(e);}}}>Scegli file…</button></div></div>}
        {page === 'search' && <p className="intro">Confronta un tuo dato sul dispositivo oppure consulta una fonte esterna. I valori cercati e le chiavi dei provider vengono chiesti al momento. I risultati dei motori richiedono verifica indipendente.</p>}
        {page === 'archive' && <div className="intro"><p className="value">{status.path}</p><p>Il registro degli invii rimane sul dispositivo e non viene incluso nei backup. Dopo un ripristino può essere richiesta una riconciliazione prima di nuovi invii.</p><p>Blocco automatico dopo 15 minuti senza interazioni e al blocco di Windows. Le copie precedenti al cambio passphrase conservano la loro passphrase originale.</p></div>}
        <div className="operation-list">{boot.operations.filter(o => o.group === page).map(o => <button disabled={busy} key={o.id} onClick={() => choose(o.id)}><span>{o.label}</span><span aria-hidden="true">→</span></button>)}</div>
      </>}
      {page === 'brokers' && <div className="broker-layout"><div className="operation-list">{(catalog?.procedures as Record<string, unknown>[] || []).map(p => <button key={String(p.id)} onClick={async () => {try {setBroker(await api('catalog', String(p.id)));} catch(e) {fail(e);}}}><span>{String(p.controller)}</span><span>Manuale</span></button>)}</div><section>{broker ? <><h2>{String(broker.controller)}</h2><p className="notice">La presenza nel catalogo non dimostra che questo soggetto abbia i tuoi dati. Verifica la procedura alla fonte; l’app non la esegue automaticamente.</p><DataView value={broker}/></> : <p className="muted">Scegli una procedura per leggere istruzioni, fonte ufficiale e revisione.</p>}</section></div>}
      <footer>Obliryx conserva riscontri e decisioni. Gli effetti presso i servizi esterni richiedono verifiche alla fonte.</footer>
    </main>
  </div>;
}

function DesktopRoot() {
  const [legacy, setLegacy] = useState(false);
  return legacy ? <><div className="legacy-return"><button onClick={async()=>{await api('lock'); setLegacy(false);}}>Torna alla ricerca Web</button></div><App/></> : <Workflow onLegacy={()=>setLegacy(true)}/>;
}

createRoot(document.getElementById('root')!).render(<DesktopRoot/>);
