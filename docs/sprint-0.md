# Sprint 0 e backlog del ciclo 1

## Fatto nello sprint 0

- [x] Struttura del repository, configurazione, modello dati
- [x] Ingestione di PDF, CSV/TSV/Parquet, HDF5 e NeXus
- [x] Estrazione di grandezze fisiche con unità e conversione SI
- [x] Grafo della ricerca e collegamenti candidati per dimensione fisica
- [x] Provenienza a catena di hash con verifica di integrità
- [x] Scheda ipotesi e controllo di falsificabilità
- [x] Guadagno di informazione atteso, priorità per costo, numero di misure necessarie
- [x] Calibrazione (Brier, affidabilità)
- [x] Motore delle anomalie con correzione look-elsewhere e Isolation Forest
- [x] Gateway dei modelli con policy per classificazione
- [x] API FastAPI, 41 test automatici, demo end-to-end

## Fatto nel ciclo 1

- [x] Migrazioni del database con Alembic, schema iniziale e pgvector
- [x] Verifica su PostgreSQL 16 con pgvector: tutti i test passano su entrambi i database
- [x] Correzione della catena di provenienza con scritture concorrenti
- [x] Integrazione continua: test su SQLite (Python 3.11–3.13) e PostgreSQL, controllo di deriva delle migrazioni

## Ciclo 1 (settimane 1–6): fondamenta che servono comunque

| Priorità | Attività | Responsabile |
| --- | --- | --- |
| 1 | Autenticazione OIDC, ruoli e isolamento tra progetti | Ingegneria e sicurezza |
| 1 | SBOM CycloneDX e scansione delle dipendenze nella CI | Sicurezza |
| 2 | Ingestione di ROOT (uproot), FITS (astropy), notebook Jupyter, sorgenti LaTeX | Ingegneria |
| 2 | Parsing avanzato dei PDF con formule (GROBID) | Ingegneria |
| 2 | Connettori di letteratura: OpenAlex, arXiv, Semantic Scholar, INSPIRE-HEP, NASA ADS | Ingegneria |
| 2 | Recupero ibrido (testo, vettori, grafo) con citazioni a livello di frase | ML |
| 3 | Generatore di ipotesi via LLM in ciclo con il controllo di falsificabilità e l'avvocato del diavolo | ML e scienziati PhD |
| 3 | Sandbox isolata per l'esecuzione di codice di analisi | Ingegneria e sicurezza |
| 3 | Banchi di prova interni: anomalie iniettate, scoperte storiche, errori statistici seminati | Scienziati PhD |

## In attesa della discovery (decisione in settimana 6)

- Ordine dei moduli MVP e loro interfaccia web
- Campi obbligatori definitivi della scheda ipotesi
- Formati e connettori di laboratorio prioritari
- Prezzi e piani
