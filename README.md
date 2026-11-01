# Research Booster

Copilota scettico per la ricerca scientifica: collega documenti, dataset ed esperimenti di un gruppo in un
grafo della ricerca, propone ipotesi falsificabili, sceglie l'esperimento più informativo e segnala anomalie
nei dati con una significatività onesta.

**Stato:** Sprint 0, le fondamenta. Lo sviluppo procede in parallelo alla discovery con i ricercatori.
Le parti che dipendono dai risultati delle interviste (interfaccia, priorità dei moduli, prezzi) non sono ancora qui.

## Cosa c'è già

| Modulo | Cartella | Cosa fa |
| --- | --- | --- |
| Ingestione | `src/rb/ingest` | PDF (testo, DOI, arXiv, grandezze con unità), CSV/TSV/Parquet, HDF5 e NeXus (struttura, attributo `units`, statistiche) |
| Grandezze fisiche | `src/rb/ingest/quantities.py` | Estrae valore, incertezza, simbolo e unità dal testo; validazione e conversione SI con pint |
| Grafo della ricerca | `src/rb/graph.py` | Nodi e archi su PostgreSQL; collegamenti candidati tra grandezze di letteratura e variabili dei dataset con la stessa dimensione fisica |
| Database | `src/rb/db.py`, `src/rb/migrations` | Migrazioni Alembic, JSONB su PostgreSQL, estensione pgvector se disponibile |
| Provenienza | `src/rb/provenance.py` | Hash dei file, istantanea dell'ambiente, registro append-only a catena di hash con verifica di integrità; scritture serializzate per progetto su PostgreSQL |
| Scheda ipotesi | `src/rb/hypotheses/card.py` | Formato standard: previsione quantitativa, condizione di falsificazione, rivali, evidenze con fonte |
| Controllo di falsificabilità | `src/rb/hypotheses/falsifiability.py` | Blocca schede senza previsione numerica o criterio misurabile; segnala linguaggio vago, clausole di fuga, evidenze unilaterali |
| Valore informativo | `src/rb/hypotheses/ranking.py` | Guadagno di informazione atteso (bit) per esperimento, priorità = bit / costo, numero di misure necessarie |
| Calibrazione | `src/rb/hypotheses/calibration.py` | Punteggio di Brier, log loss, diagramma di affidabilità |
| Anomalie | `src/rb/discovery/anomalies.py` | Scansione dei residui con fit robusto, significatività locale e globale (correzione look-elsewhere), livelli di evidenza, controlli sistematici; Isolation Forest per dati multivariati; controllo di deriva |
| Gateway modelli | `src/rb/llm/gateway.py` | Fornitori intercambiabili (Anthropic, modelli locali compatibili OpenAI, offline); i dati `controlled` non raggiungono mai un modello esterno |
| API | `src/rb/api/main.py` | FastAPI: progetti, caricamento, grafo, ipotesi, esiti, calibrazione, ranking, anomalie, verifica provenienza |

## Avvio rapido

```bash
python -m pip install -e ".[dev]"
python -m pytest            # test su SQLite
python examples/demo.py     # dimostrazione end-to-end su dati sintetici
uvicorn --factory rb.api.main:create_app --reload   # API su http://localhost:8000/docs
```

Con PostgreSQL (consigliato fuori dallo sviluppo locale):

```bash
cp .env.example .env
docker compose up --build
```

## Database e migrazioni

Lo schema è gestito solo da migrazioni Alembic (`src/rb/migrations`). All'avvio l'API porta il database
all'ultima versione; con più repliche impostare `RB_AUTO_MIGRATE=false` ed eseguire le migrazioni come passo
separato del rilascio.

```bash
export RB_DATABASE_URL=postgresql+psycopg://rb:password@localhost:5432/rb
alembic upgrade head                              # porta lo schema all'ultima versione
alembic revision --autogenerate -m "descrizione"  # nuova migrazione dopo una modifica ai modelli
alembic check                                     # verifica che modelli e migrazioni coincidano
alembic upgrade head --sql > schema.sql           # script SQL da far rivedere a un amministratore
```

Per eseguire i test su PostgreSQL (ogni test ricrea lo schema `public` del database indicato, da usare solo
su un database dedicato ai test):

```bash
RB_TEST_DATABASE_URL=postgresql+psycopg://rb:rb@localhost:5432/rb_test python -m pytest
```

L'integrazione continua (`.github/workflows/ci.yml`) esegue i test su SQLite con Python 3.11–3.13 e su
PostgreSQL 16 con pgvector, più il controllo di deriva tra modelli e migrazioni.

## Configurazione

| Variabile | Default | Significato |
| --- | --- | --- |
| `RB_DATABASE_URL` | `sqlite:///./research_booster.db` | Database; in produzione `postgresql+psycopg://...` |
| `RB_STORAGE_DIR` | `./storage` | Dove si salvano i file caricati |
| `RB_AUTO_MIGRATE` | `true` | Esegue le migrazioni all'avvio dell'API |
| `RB_LLM_PROVIDERS` | `offline` | Elenco in ordine di preferenza: `anthropic`, `local`, `offline` |
| `RB_ANTHROPIC_MODEL` | `claude-sonnet-5-5` | Modello per il fornitore Anthropic |
| `RB_ANTHROPIC_MAX_CLASSIFICATION` | `internal` | Livello massimo di dato inviabile al modello esterno |
| `ANTHROPIC_API_KEY` | | Chiave API |
| `RB_LOCAL_LLM_URL`, `RB_LOCAL_LLM_MODEL` | | Modello self-hosted per dati `controlled` |

Il fornitore `offline` non chiama alcun servizio e serve solo per sviluppo e test: in produzione va disattivato.

## Principi di prodotto nel codice

- **Evidenza o silenzio:** un'evidenza senza fonte è un errore bloccante nel controllo di falsificabilità.
- **Falsificabilità prima della plausibilità:** le schede che non superano il controllo non vanno mostrate come proposte.
- **Riproducibilità nativa:** ogni ingestione e ogni ipotesi lasciano un record di provenienza verificabile.
- **I dati restano del ricercatore:** il gateway rifiuta la chiamata piuttosto che inviare dati non ammessi.
- **Mai dire "scoperta":** il motore restituisce anomalie candidate con livello di evidenza globale e controlli da fare.

## Documenti

- `docs/decisions.md`: decisioni architetturali.
- `docs/sprint-0.md`: cosa è stato fatto e backlog del primo ciclo.
