import React, {useEffect, useRef, useState} from 'react';
import {api, ActionPlan, WebItem, WorkflowState, workflowLabels, workflowStep} from './bridge';
import './workflow.css';

const steps = ['I tuoi dati', 'Analisi', 'Risultati', 'Riepilogo', 'Interventi'];
const initial: WorkflowState = {phase:'input', busy:false, message:'', sources:[], items:[], operations:[], assistance:null, history:[], error:null, processed:0, total:0};
const statusLabel = (value: string) => workflowLabels[value] || value;

export function Workflow({onLegacy}: {onLegacy: () => void}) {
  const [state, setState] = useState(initial);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const [hideError, setHideError] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [plan, setPlan] = useState<ActionPlan>();
  const [approved, setApproved] = useState(false);
  const [pending, setPending] = useState(false);
  const [finished, setFinished] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const fail = (e: unknown) => setError(e instanceof Error ? e.message : 'Operazione non riuscita. Riprova.');
  async function open() {
    setError(''); setPending(true);
    try {setState(await api('workflow_open')); setReady(true);} catch(e) {fail(e);} finally {setPending(false);}
  }
  useEffect(() => {
    let active = true, polling = false;
    const start = () => {if(active) void open();};
    if(window.pywebview) start(); else window.addEventListener('pywebviewready', start, {once:true});
    const timer = window.setInterval(async () => {
      if(!window.pywebview || polling) return;
      polling = true;
      try {const next = await api('workflow_status'); if(active) {setState(next); if(next.unlocked === false) setReady(false);}} catch(e) {if(active) fail(e);} finally {polling=false;}
    }, 600);
    const touch = () => {if(window.pywebview) void api('touch').catch(()=>{});};
    window.addEventListener('pointerdown', touch); window.addEventListener('keydown', touch);
    return () => {active=false; clearInterval(timer); window.removeEventListener('pywebviewready', start); window.removeEventListener('pointerdown', touch); window.removeEventListener('keydown', touch);};
  }, []);
  useEffect(() => {heading.current?.focus();}, [state.phase]);
  useEffect(() => {setHideError(false);}, [error, state.error]);
  async function action(work: () => Promise<unknown>) {
    setPending(true); setError('');
    try {await work(); setState(await api('workflow_status'));} catch(e) {fail(e);} finally {setPending(false);}
  }
  async function analyze(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form).entries()) as Record<string,string>;
    await action(async () => {await api('workflow_analyze', values); form.reset(); setSelected([]); setPlan(undefined); setApproved(false); setFinished(false);});
  }
  async function review() {
    await action(async () => {setPlan(await api('workflow_plan', selected)); setApproved(false);});
  }
  const toggle = (id: string) => setSelected(old => old.includes(id) ? old.filter(v=>v!==id) : [...old,id]);
  const link = (id: string) => void action(()=>api('workflow_link', id));
  const step = workflowStep(state.phase);
  const busy = pending || state.busy;
  function itemRows(items: WebItem[], title: string, description: string) {
    return <section className="web-group" aria-label={title}>
      <div className="web-group-title"><h2>{title} <span>{items.length}</span></h2>{items.length > 0 && <button disabled={busy} onClick={()=>setSelected(old=>Array.from(new Set([...old,...items.map(i=>i.id)])))}>Seleziona il gruppo</button>}</div>
      <p className="muted">{description}</p>
      {items.length ? items.map(item=><article className="web-result" key={item.id}>
        <label className="web-select"><input type="checkbox" checked={selected.includes(item.id)} disabled={busy} onChange={()=>toggle(item.id)}/><span>{item.title}</span></label>
        <div className="web-result-body"><p className={`web-state ${item.status === 'observed' ? 'observed' : ''}`}>{statusLabel(item.status)}</p>
          <p>{item.matches?.map(m=>m.masked).join(' · ')}</p>
          <p className="muted">{item.reason}</p><p>{item.effect}</p>
          {item.browser_only && <p className="web-warning">Vale soltanto per il browser in cui salvi la preferenza; usa il tuo browser abituale.</p>}
          <div className="web-source-line"><span className="value">{item.url}</span><time>{item.checked_at?.slice(0,10)}</time></div>
          <button className="text-button" disabled={pending} onClick={()=>link(item.id)}>Apri fonte ufficiale nel browser esterno</button>
        </div>
      </article>) : <p className="web-empty">Nessuna presenza verificata da mostrare. Controlla lo stato delle fonti qui sopra.</p>}
    </section>;
  }
  return <div className="privacy-app">
    <header className="privacy-header"><div className="brand">Obliryx<span>Cerca le tue tracce. Scegli come intervenire.</span></div>
      <div className="buttons"><button disabled={busy} onClick={()=>void action(async()=>{await api('lock'); onLegacy();})}>Apri archivio precedente</button>{ready && <button onClick={()=>void action(()=>api('lock'))}>Chiudi sessione</button>}</div>
    </header>
    <nav className="workflow-steps" aria-label="Fasi del percorso"><ol>{steps.map((s,i)=><li key={s} aria-current={step===i?'step':undefined}><span>{i+1}</span>{s}</li>)}</ol></nav>
    <main className="privacy-main" id="main">
      {!hideError && (error || state.error) && <div role="alert" className="error"><p>{error || state.error}</p><button onClick={()=>setHideError(true)}>Chiudi avviso</button></div>}
      {!ready ? <section className="web-intro"><h1 ref={heading} tabIndex={-1}>Le tue tracce sul Web, un passo alla volta.</h1><p>Lo storico si apre con il tuo account Windows. Nessun archivio da creare e nessuna password aggiuntiva.</p><button className="primary" disabled={pending} onClick={()=>void open()}>{pending?'Apertura della sessione…':'Apri sessione'}</button></section> : <>
      {state.phase === 'input' && <section className="web-intro"><h1 ref={heading} tabIndex={-1}>Quali dati vuoi cercare?</h1><p>Inserisci almeno un identificativo che ti appartiene. La città aiuta a distinguere chi ha il tuo stesso nome.</p>
        <form className="identity-form" onSubmit={analyze} autoComplete="off">
          <div className="identity-grid"><label>Email<input name="email" type="email" maxLength={254}/></label><label>Telefono<input name="phone" type="tel" maxLength={32}/></label><label>Nome e cognome<input name="name" maxLength={254}/></label><label>Username<input name="username" maxLength={254}/></label><label>Città <span className="muted">(facoltativa)</span><input name="city" maxLength={254}/></label></div>
          <div className="notice"><strong>Prima dell’analisi</strong><p>L’app cerca automaticamente nei profili pubblici GitHub (email, nome e username) e in Wikipedia italiana. Gli identificativi cercati vengono comunicati a queste fonti; nome e città possono essere combinati su GitHub. Il telefono viene cercato soltanto in Wikipedia.</p><p>La copertura è limitata a questi contenuti pubblici. DuckDuckGo resta disponibile tramite link nel browser esterno. Nessun dato viene inviato ai broker durante l’analisi. I valori inseriti restano nella sessione e non vengono salvati nello storico.</p></div>
          <button className="primary" disabled={busy} type="submit">Avvia analisi</button>
        </form>
      </section>}
      {state.phase === 'analysis' && <section><h1 ref={heading} tabIndex={-1}>Analisi delle fonti</h1><p role="status">{state.message || 'Preparazione della ricerca…'}</p><progress max={state.total || 1} value={state.processed}/><p className="muted">{state.processed} di {state.total} ricerche elaborate</p><button onClick={()=>void action(()=>api('workflow_cancel'))}>Annulla analisi</button></section>}
      {['results','approval','execution','done'].includes(state.phase) && state.sources.length > 0 && <details className="source-coverage" key={state.phase}><summary>Copertura della ricerca · {state.sources.filter(s=>s.status==='complete').length} di {state.sources.length} ricerche consultate</summary>
        {state.sources.map(source=><div className="coverage-row" key={source.id}><strong>{source.title} · {source.masked}</strong><span>{statusLabel(source.status)}</span><p>{source.reason}</p><button className="text-button" onClick={()=>link(source.id)}>Apri ricerca nel browser esterno</button></div>)}
        <p className="muted">Una fonte non disponibile o nessuna corrispondenza osservata non dimostrano che i tuoi dati siano assenti dal Web.</p>
      </details>}
      {state.phase === 'results' && <section><h1 ref={heading} tabIndex={-1}>Scegli dove intervenire</h1><p>Verifica le corrispondenze. Le procedure dei broker sono separate dalle presenze effettivamente osservate.</p>
        {itemRows(state.items.filter(i=>i.kind==='presence' && i.status==='observed'), 'Presenze trovate', 'Il testo corrisponde a un dato inserito. L’identità della persona e il contesto restano da verificare.')}
        {state.items.some(i=>i.kind==='presence' && i.status!=='observed') && itemRows(state.items.filter(i=>i.kind==='presence' && i.status!=='observed'), 'Pagine da verificare', 'Pagine bloccate, non disponibili o senza una corrispondenza osservata.')}
        {itemRows(state.items.filter(i=>i.kind==='broker'), 'Broker: possesso non verificato', 'Canali pubblicati dai titolari per Italia e UE. La presenza in questo elenco non prova che abbiano i tuoi dati.')}
        <details className="manual-check"><summary>Hai trovato una pagina con i tuoi dati?</summary><p>Inserisci il suo indirizzo HTTPS: l’app confronterà il testo visibile con i dati della sessione nel browser integrato.</p><form onSubmit={e=>{e.preventDefault(); const form=e.currentTarget; const url=String(new FormData(form).get('url')); void action(async()=>{await api('workflow_inspect',url); form.reset();});}}><label>Indirizzo della pagina<input name="url" type="url" required placeholder="https://…"/></label><button disabled={busy}>Verifica pagina</button></form></details>
        <div className="workflow-actions"><p>{selected.length} risultati selezionati</p><button disabled={!selected.length || busy} className="primary" onClick={()=>void review()}>Controlla gli interventi selezionati</button></div>
      </section>}
      {state.phase === 'approval' && plan && <section><h1 ref={heading} tabIndex={-1}>Controlla prima di approvare</h1><p>Prima le procedure automatiche, poi quelle che richiedono la tua presenza. Questa approvazione vale soltanto per le operazioni elencate.</p>
        <div className="planned-actions">{plan.actions.map(a=><article key={a.id}><h2>{a.title}</h2><p>{a.effect}</p><p className="value">Destinazione: {a.destination}</p><p className="muted">{a.mode==='automatic'?'Esecuzione automatica verificata':'Procedura manuale o assistita'}</p>{Object.entries(a.fields).length ? <dl className="data">{Object.entries(a.fields).map(([k,v])=><div key={k}><dt>{k} da trasmettere</dt><dd>{v}</dd></div>)}</dl> : <p className="muted">Nessun identificativo compilato o trasmesso automaticamente dall’app. Il sito riceve i normali dati di connessione.</p>}{a.browser_only && <p className="web-warning">Preferenza del browser; non è una cancellazione dei tuoi dati.</p>}</article>)}</div>
        <label className="batch-approval"><input type="checkbox" checked={approved} onChange={e=>setApproved(e.target.checked)}/>Approvo gli interventi e i dati indicati in questo riepilogo.</label>
        <div className="buttons"><button disabled={busy} onClick={()=>void action(async()=>{await api('workflow_edit_selection');setPlan(undefined);setApproved(false);})}>Modifica selezione</button><button disabled={!approved || busy} className="primary" onClick={()=>void action(()=>api('workflow_execute',plan.id))}>Avvia gli interventi approvati</button></div>
      </section>}
      {['execution','done'].includes(state.phase) && <section><h1 ref={heading} tabIndex={-1}>{state.phase==='done'?'Esito degli interventi':'Interventi in corso'}</h1><p role="status">{state.message}</p>
        {state.assistance && <section className="assisted-step" aria-label="Verifica assistita"><h2>{state.assistance.title}</h2><p className="value">Sito: {state.assistance.domain}</p><p>Completa CAPTCHA o altre verifiche nella finestra del browser integrato. Continua quando hai terminato; se la procedura cambia, l’app non effettua nuovi invii automatici.</p><div className="buttons"><button onClick={()=>void action(()=>api('workflow_browser'))}>Mostra pagina</button><button className="primary" disabled={pending} onClick={()=>void action(()=>api('workflow_respond',state.assistance!.request_id,'continue'))}>Continua</button><button disabled={pending} onClick={()=>void action(()=>api('workflow_respond',state.assistance!.request_id,'skip'))}>Salta</button></div></section>}
        <div className="planned-actions">{state.operations.map(a=><article key={a.id}><h2>{a.title}</h2><p>{statusLabel(a.status)}</p>{a.reason && <p className="muted">{a.reason}</p>}<p>{a.effect}</p><button className="text-button" onClick={()=>link(a.id)}>{a.channel==='email'?'Prepara bozza nel programma di posta':'Apri collegamento diretto nel browser esterno'}</button></article>)}</div>
        {state.busy ? <button onClick={()=>void action(()=>api('workflow_cancel'))}>Annulla le operazioni rimanenti</button> : <button className="primary" disabled={pending} onClick={()=>void action(async()=>{await api('lock'); setFinished(true); setSelected([]); setPlan(undefined); await open();})}>Nuova ricerca</button>}
        <p className="notice">Una richiesta accettata è distinta dalla rimozione verificata. Un esito incerto non viene ritentato automaticamente.</p>
      </section>}
      {state.history.length>0 && <details className="workflow-history"><summary>Storico locale · {state.history.length} riscontri recenti</summary>{state.history.map(h=><div key={h.id} className="coverage-row"><strong>{h.title}</strong><time>{h.checked_at?.slice(0,10)}</time><p>{statusLabel(h.status)}{h.actions.map(a=>' · '+statusLabel(a.status)).join('')}</p></div>)}</details>}
      </>}
      {finished && !ready && <p role="status">Sessione precedente chiusa. Puoi iniziare una nuova ricerca.</p>}
    </main><footer className="privacy-footer">Sul tuo dispositivo · Nessuna API a pagamento · Le verifiche riguardano solo le fonti consultabili.</footer>
  </div>;
}
