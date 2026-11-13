import {describe, expect, it} from 'vitest';
import {api, filterFindings, Finding, label, workflowLabels, workflowStep} from './bridge';

describe('local finding review', () => {
  const items = [
    {id:'1', controller:'Organizzazione sintetica', sender:'news@example.invalid', source:'messaggio_importato', enrollment:'da_verificare', gravita:'media'},
    {id:'2', controller:'Altro soggetto', source:'pagina_verificata', enrollment:'riconosciuta', gravita:'bassa'},
  ] as Finding[];
  it('combines search and independent filters without altering source data', () => {
    expect(filterFindings(items, 'SINTETICA', 'messaggio_importato', 'media', 'da_verificare').map(f=>f.id)).toEqual(['1']);
    expect(filterFindings(items, 'SINTETICA', '', 'bassa', '')).toEqual([]);
    expect(items).toHaveLength(2);
  });
  it('keeps technical acceptance distinct from removal and unknown delivery', () => {
    expect(label('accepted')).toBe('Invio accettato');
    expect(label('delivery_unknown')).toBe('Esito incerto');
    expect(label('rimozione_dichiarata')).toBe('Rimozione dichiarata');
  });
  it('propagates bridge rejection without returning its value', async () => {
    Object.assign(globalThis, {window:{pywebview:{api:{status:async()=>({ok:false,error:'Archivio bloccato'})}}}});
    await expect(api('status')).rejects.toThrow('Archivio bloccato');
  });
  it('keeps workflow stages sequential and completion in the fifth stage', () => {
    expect(['input','analysis','results','approval','execution','done'].map(workflowStep)).toEqual([0,1,2,3,4,4]);
    expect(workflowLabels.holding_unknown).toContain('non verificato');
    expect(workflowLabels.delivery_unknown).toContain('nessun nuovo tentativo');
    expect(workflowLabels.accepted).toContain('rimozione da verificare');
  });
});
