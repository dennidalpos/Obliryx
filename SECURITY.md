# Security Policy

## Supported versions

È supportato solo l'ultimo commit del ramo `main`. La versione 0.1.0.dev0 è sperimentale.

## Reporting a vulnerability

Non aprire issue pubbliche per problemi di sicurezza.

Usa la segnalazione privata di GitHub: apri la scheda **Security** di questo repository e scegli **Report a vulnerability**. Indica versione, sistema operativo, operazione e comportamento osservato, usando una riproduzione sintetica. Non allegare dati personali, messaggi originali, archivi o credenziali; oscura anche parametri degli URL, percorsi personali e contenuto delle anteprime.

Non è dichiarato un tempo garantito di risposta. Le correzioni confermate arrivano su `main` e sono rese pubbliche dopo il rilascio della correzione.

## Scope notes

- Una vulnerabilità che consente accesso ai dati o invii non autorizzati ha priorità.
- I test sintetici non qualificano ogni provider reale.
- La build pubblica desktop richiede firma Authenticode e collaudo su Windows pulito; una build locale non firmata non equivale a una release qualificata.
