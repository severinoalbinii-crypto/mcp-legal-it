# MCP Legal IT — GitHub OAuth su Render (proposta non ancora distribuita)

Questo ramo introduce autenticazione GitHub OAuth e autorizzazione per singoli utenti.

## Variabili Render (Environment > Add Environment Variable)

- `MCP_TRANSPORT=http` (gia impostato nel Dockerfile)
- `GITHUB_CLIENT_ID`: Client ID della tua app OAuth GitHub (non segreto)
- `GITHUB_CLIENT_SECRET`: **nuovo** Client Secret, soltanto su Render; NON in GitHub, screenshot o chat
- `MCP_PUBLIC_BASE_URL=https://mcp-legal-it.onrender.com`
- `MCP_ALLOWED_GITHUB_USERS=severinoalbinii-crypto`

Se manca una variabile necessaria, il processo remoto si rifiuta di partire: non e previsto fallback a No Auth. Il trasporto locale `stdio` rimane invariato.

## GitHub OAuth App

- Homepage: `https://mcp-legal-it.onrender.com`
- Callback: `https://mcp-legal-it.onrender.com/auth/callback`
- Accesso consentito: solo l'account GitHub specificato in `MCP_ALLOWED_GITHUB_USERS` (login con confronto case-insensitive).

## Piano di attivazione prudente

1. Validare con test le modifiche PR e una prova su un'istanza di staging.
2. Verificare il comportamento dell'autenticazione GitHub con ChatGPT e la compatibilita FastMCP installata.
3. Preparare le 4 variabili Render in ambiente privato **prima** di attivare questo ramo.
4. Adattare il collegamento repository Render alla copia personale soltanto dopo il collaudo, oppure distribuire lo staging su un nuovo servizio e adeguare la callback GitHub.
5. Configurare ChatGPT con autenticazione OAuth al posto di No Authentication. La precedente connessione senza auth smettera di funzionare quando il server sara protetto.
6. Verificare a) rifiuto senza token, b) rifiuto account GitHub diverso, c) accesso consentito, d) `stato_server` e i 228 strumenti.
7. Disattivare/eliminare eventuali servizi Render pubblici rimasti senza autenticazione.

**Nota**: il piano Free di Render puo sospendere/riavviare il processo; occorre verificare il comportamento di sessioni, stato OAuth e storage FastMCP dopo riavvii. Non caricare fascicoli professionali riservati prima del collaudo di sicurezza.

## Controlli prima di autorizzare il merge

- La CI GitHub deve risultare completata con successo sul ramo di questa Pull Request.
- Oltre ai test unitari, provare il collegamento OAuth da ChatGPT a un servizio di staging (non al server gia in uso).
- Non interpretare `stato_server` ottenuto con la precedente connessione **senza autenticazione** come verifica dell'accesso protetto.
- Controllare che ogni richiesta MCP non autenticata e ogni account GitHub non presente nell'allowlist venga rifiutato.
- Non trasmettere dati dei clienti fino al completamento delle prove e alla dismissione dell'endpoint non protetto.
