# Decisioni architetturali

Ogni decisione rilevante ha una voce breve: contesto, decisione, conseguenze. Si aggiorna, non si riscrive.

## ADR-001 · Python e FastAPI per il backend

- **Contesto:** gli utenti e le librerie scientifiche (NumPy, SciPy, h5py, astropy, uproot, PyTorch) vivono in Python.
- **Decisione:** backend e worker in Python 3.11+, API con FastAPI, modelli dati con Pydantic.
- **Conseguenze:** stesso linguaggio per API, analisi e agenti; il frontend sarà in TypeScript a parte.

## ADR-002 · PostgreSQL prima di tutto, SQLite per sviluppo e test

- **Contesto:** l'installazione on-premise deve avere pochi componenti.
- **Decisione:** grafo su tabelle relazionali (`nodes`, `edges`) e, dal ciclo 1, vettori con pgvector nello stesso PostgreSQL. SQLite solo in locale e nei test.
- **Conseguenze:** niente database a grafo dedicato finché le prestazioni reggono; da rivalutare oltre ~10 milioni di archi per progetto.

## ADR-003 · Gateway dei modelli con policy per classificazione del dato

- **Contesto:** principio "i dati restano del ricercatore"; clienti con dati soggetti a export control.
- **Decisione:** quattro livelli (`public`, `internal`, `confidential`, `controlled`); ogni rotta dichiara il livello massimo ammesso; in assenza di una rotta valida la chiamata fallisce.
- **Conseguenze:** nessun degrado silenzioso; per dati `controlled` serve un modello locale.

## ADR-004 · Provenienza con registro a catena di hash

- **Contesto:** riproducibilità e integrità dei risultati, utile anche per priorità scientifica e brevetti.
- **Decisione:** ogni attività (ingestione, ipotesi, esito) aggiunge un record con hash del precedente, input, output, parametri e ambiente.
- **Conseguenze:** manomissioni rilevabili con `verify_chain`; la marca temporale esterna (idea "timestamp delle ipotesi") si potrà ancorare all'ultimo hash.

## ADR-005 · Controllo di falsificabilità bloccante

- **Contesto:** la generazione di ipotesi sta diventando una commodity; il nostro valore è il controllo critico.
- **Decisione:** errori (nessuna previsione numerica, criterio non misurabile, evidenza senza fonte, unità non valide) impediscono di presentare la scheda come proposta.
- **Conseguenze:** il futuro generatore basato su LLM lavorerà in ciclo: genera, controlla, corregge.

## ADR-006 · Significatività globale conservativa

- **Contesto:** il motore delle anomalie prova migliaia di finestre: senza correzione produrrebbe falsi allarmi.
- **Decisione:** correzione di Šidák sul numero totale di finestre; livelli: indizio da 2σ, evidenza candidata da 3σ, anomalia forte da 5σ globali.
- **Conseguenze:** stima prudente (finestre sovrapposte sono correlate); in futuro si può affinare con pseudo-esperimenti.

## ADR-008 · Schema gestito solo da migrazioni Alembic

- **Contesto:** clienti on-premise aggiorneranno versioni diverse in momenti diversi; lo schema deve evolvere senza perdere dati.
- **Decisione:** nessun `create_all`; ogni modifica ai modelli passa da una migrazione versionata nel pacchetto (`rb:migrations`). La CI verifica che modelli e migrazioni coincidano (`alembic check`) e che le migrazioni siano reversibili. L'API migra all'avvio, disattivabile con `RB_AUTO_MIGRATE=false`.
- **Conseguenze:** gli amministratori possono ottenere lo script SQL offline; su SQLite le modifiche future useranno la modalità batch.

## ADR-009 · Catena di provenienza serializzata per progetto su PostgreSQL

- **Contesto:** due richieste concorrenti leggevano lo stesso ultimo hash e biforcavano la catena (riprodotto in un test).
- **Decisione:** `pg_advisory_xact_lock` per progetto prima di leggere l'ultimo hash; il lock si rilascia al commit.
- **Conseguenze:** le scritture di provenienza dello stesso progetto sono sequenziali; progetti diversi restano in parallelo.

## ADR-007 · Sviluppo in parallelo alla discovery

- **Contesto:** il fondatore ha scelto di non attendere la fine delle 12 settimane di discovery.
- **Decisione:** nelle prime 6 settimane si costruiscono solo componenti utili qualunque sia l'esito (ingestione, grafo, provenienza, sicurezza, motori di calcolo). Interfaccia, priorità dei moduli e prezzi si fissano dopo la settimana 6.
- **Conseguenze:** meno rischio di lavoro buttato; ogni venerdì la sintesi delle interviste entra nella revisione di prodotto.
