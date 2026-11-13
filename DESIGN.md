---
name: Obliryx
description: Interfaccia italiana per esaminare riscontri e scegliere il prossimo passo.
colors:
  primary: "#1759ad"
  primary-hover: "#104785"
  canvas: "#fff"
  surface: "#f4f6f8"
  text: "#202b38"
  muted: "#526171"
  line: "#ced6df"
  field-border: "#8594a5"
  hover: "#e9eff6"
  active: "#dbe6f4"
  selected: "#eaf1fa"
  danger: "#a52c25"
  danger-surface: "#fcece8"
  warning: "#765000"
  warning-surface: "#fbf1d8"
  success: "#25633a"
typography:
  headline:
    fontFamily: "Segoe UI, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 650
    lineHeight: 1.25
  title:
    fontFamily: "Segoe UI, sans-serif"
    fontSize: "1.35rem"
    fontWeight: 650
    lineHeight: 1.35
  body:
    fontFamily: "Segoe UI, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Segoe UI, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
  small:
    fontFamily: "Segoe UI, sans-serif"
    fontSize: "0.75rem"
rounded:
  badge: "3px"
  status: "4px"
  field: "5px"
  button: "6px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  xxl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.canvas}"
    rounded: "{rounded.button}"
    padding: "8px 14px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-secondary:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.text}"
    rounded: "{rounded.button}"
    padding: "8px 14px"
  button-text:
    backgroundColor: "transparent"
    textColor: "{colors.primary}"
    rounded: "{rounded.button}"
  navigation-current:
    backgroundColor: "#e2ebf6"
    textColor: "#114c94"
    rounded: "{rounded.button}"
    padding: "10px"
  severity-high:
    backgroundColor: "{colors.danger-surface}"
    textColor: "{colors.danger}"
    rounded: "{rounded.badge}"
    padding: "3px 6px"
  field:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.text}"
    rounded: "{rounded.field}"
    padding: "8px 10px"
  finding-selected:
    backgroundColor: "{colors.selected}"
    textColor: "{colors.text}"
    padding: "20px 16px"
  notice:
    backgroundColor: "{colors.surface}"
    padding: "14px 16px"
---

# Design System: Obliryx

## Overview

**Creative North Star: "Archivio personale"**

Interfaccia desktop italiana sobria, con Segoe UI, superfici bianche e grigio chiaro, testo grafite e accento blu. La gerarchia privilegia prove, provenienza e prossimo passo; i controlli mantengono una forma familiare per Windows.

La documentazione descrive `frontend/src/style.css` e `frontend/src/main.tsx`. I token nel frontmatter sono estratti dall'implementazione; non attestano da soli la verifica del comportamento assistivo o della distribuzione desktop.

**Key Characteristics:**
- Gerarchia leggibile e densità operativa contenuta.
- Superfici piatte, separatori sottili, accento riservato alle azioni e agli stati.
- Etichette italiane, stati testuali e anteprime strutturate.

## Colors

### Primary

Il blu operativo identifica le azioni principali, il focus e i pulsanti testuali; la variante più scura segnala il passaggio del puntatore. La selezione usa un fondo azzurro pallido. La navigazione corrente aggiunge testo blu scuro e bordo azzurro.

### Neutral

Il bianco ospita il lavoro; il grigio chiaro separa navigazione, avvisi e introduzione all'archivio. Grafite per il testo, grigio ardesia per metadati e descrizioni, bordo chiaro per suddivisioni e bordo più marcato per i campi.

### Semantic states

Rosso e fondo rosato distinguono gravità alta ed errori; ocra e fondo crema distinguono gravità media. Verde per lo stato di archivio aperto. La gravità bassa usa un'etichetta grigia. Ogni stato conserva un nome testuale.

## Typography

Un solo stack Segoe UI con fallback sans-serif. Il corpo base è definito sulla radice; l'interlinea del token body descrive i paragrafi, non un reset globale. Titoli di pagina e dettaglio seguono headline e title. I sottotitoli interni usano il corpo con peso 650; le etichette dei campi usano label e i metadati small.

L'introduzione all'archivio usa un titolo più ampio (2.25rem, interlinea 1.3), ridotto a 1.875rem sotto la soglia intermedia. Il marchio testuale usa 1.5rem, peso 700 e spaziatura −0.03em. Date con cifre tabulari. Nessun carattere display o monospace distinto.

## Layout

La shell usa una colonna di navigazione (224px) e uno spazio di lavoro fluido, senza larghezza massima globale. Il contenuto ha margini interni di 36px, con 20px in basso. L'intestazione precede attività, moduli e contenuto. Ricerca e filtri formano una barra; il campo di ricerca occupa il doppio dello spazio degli altri campi.

Il pannello riscontri divide elenco e dettaglio nel rapporto 0.8:1.2, con minimi rispettivi di 260px e 320px. L'elenco scorre autonomamente, con altezza massima legata alla finestra. Il dettaglio scorre con la pagina. Il dettaglio delle procedure broker usa un'altra griglia con elenco e lettura affiancati. I moduli operativi arrivano a 560px; i contenitori operativi a 850px.

A partire da 1600px i margini di lavoro diventano 40px 56px e i minimi dei pannelli 320px e 480px. Fino a 1100px la navigazione scende a 190px, i margini a 24px, i filtri vanno a capo e riscontri e procedure passano a una colonna. Selezionare un riscontro nasconde l'elenco e porta il focus al titolo del dettaglio; “Torna all'elenco” ripristina il focus sulla riga. Fino a 700px la navigazione passa sopra il contenuto, senza icone, e le coppie etichetta/valore si impilano. L'indicatore “Archivio aperto” nell'intestazione viene nascosto a questa soglia; il blocco archivio resta nella navigazione.

L'apertura dell'archivio ha introduzione e modulo affiancati nel rapporto 1.15:0.85, poi impilati fino a 700px. Il ritmo ricorrente segue gli spazi del frontmatter, con respiro maggiore per introduzioni e stati vuoti.

## Elevation & Depth

Nessuna ombra. La profondità è data da fondi tonali e bordi, senza pannelli fluttuanti. L'attività corrente usa un fondo azzurro chiarissimo e un bordo distinto; le anteprime al suo interno tornano bianche e scorrono oltre 360px di altezza.

## Shapes

Contenitori e righe mantengono angoli retti. Solo controlli, indicatore archivio e badge hanno raggi piccoli, definiti nel frontmatter. I pulsanti hanno altezza minima 40px, i campi 42px. Le icone sono SVG lineari di 20px con tratto 1.6, senza contenuto decorativo aggiuntivo.

## Components

### Buttons

Secondario bianco con bordo, primario blu con testo bianco, testuale senza bordo e allineato a sinistra. Passaggio e pressione cambiano il fondo. Il primario ha un proprio colore hover; lo stato disabilitato usa opacità 0.55 e cursore non disponibile. Il focus visibile dei controlli usa contorno blu di 3px con distanza 3px.

Solo il colore di fondo dei pulsanti transisce (140ms ease-out), quando il sistema non richiede movimento ridotto. Nessuna traslazione o animazione d'ingresso.

### Inputs / Fields

Campi bianchi con bordo più marcato, etichetta sopra e distanza interna all'etichetta di 7px. La ricerca ha un suggerimento testuale; i dati riservati usano campi password. Errori mostrati come avvisi testuali, non come uno stile di errore del singolo campo.

### Navigation

Cinque pulsanti con icona e nome; lo stato corrente usa `aria-current`, fondo azzurro e bordo. Il piede contiene “Blocca archivio”. La navigazione si dispone in righe a capo nella vista stretta. Il collegamento “Vai al contenuto” compare al focus.

### Findings and status labels

Righe piatte, separate da un bordo, con organizzazione, gravità, oggetto, iscrizione e data. L'oggetto viene troncato su una riga; organizzazioni e valori del dettaglio possono andare a capo. La selezione è anche espressa da `aria-pressed`. I badge di gravità sono etichette informative, senza interazione.

### Notices and operations

Avvisi neutri dentro la lettura, contenitore bordato per il modulo, fondo azzurro per l'attività. La scelta di un'operazione porta focus e scorrimento al titolo; una richiesta interattiva porta il focus al campo. Anteprime e risultati sono coppie etichetta/valore, liste o testo, senza interpretazione HTML. Gli stati di attività e il conteggio riscontri hanno annunci live; gli errori hanno ruolo alert.

### Confirmations

Le richieste di approvazione mostrano contesto, anteprima quando presente, campo “Digita CONFERMO” e pulsante specifico per il passaggio. Non si riducono a un pulsante generico. Le azioni aggiuntive stanno in un'espansione con summary, lasciando evidente il prossimo passo.

## Do's and Don'ts

### Do:
- **Do** conservare Segoe UI, superfici piatte e gerarchia italiana della versione implementata.
- **Do** accompagnare gravità, selezioni ed esiti con testo o stato semantico.
- **Do** mantenere focus visibile, ritorno all'elenco e valori lunghi leggibili.
- **Do** preservare le anteprime e le conferme distinte prima delle azioni esterne.

### Don't:
- **Don't** sostituire prove e provenienza con punteggi inventati.
- **Don't** aggiungere ombre decorative, gradienti o animazioni d'ingresso alla direzione sobria approvata.
- **Don't** rappresentare un invio accettato come prova della rimozione.
