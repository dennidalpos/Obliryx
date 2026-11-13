# Contribuire a Obliryx

Usa Python 3.11 o successivo per la CLI; per il packaging Windows usa Python 3.13 x64, Node 22 LTS e Inno Setup 6. Installa le dipendenze come descritto nel README. Il frontend vive in `frontend/`: `npm ci --ignore-scripts`, `npm test`, `npm run build`.

Esegui `python -m unittest discover -s tests -v`, `python -m pip check` e `python -I -m obliryx --help`. Per i test browser installa l’extra `demo` e Chromium con `python -m playwright install chromium`. I test del bridge desktop funzionano anche senza WebView2; il collaudo nativo Windows è distinto.

Le prove devono usare dati sintetici e server locali. Non allegare posta, database, passphrase, token, chiavi API o indirizzi reali a issue e pull request. Non contattare provider reali dai test. Mantieni separati esiti tecnici e rimozioni osservate, anteprime e approvazioni. Non aggirare il registro invii per semplificare la UI.

Per il catalogo broker verifica la fonte ufficiale e aggiorna versione, revisione e impronta con `review_fingerprint`; esegui i test del catalogo. Descrivi nella PR cosa cambia, le prove eseguite e i limiti osservati. Per problemi di sicurezza consulta SECURITY.md.
