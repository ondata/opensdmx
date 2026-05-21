# CLI test examples

Dataset di riferimento per i test: `PRC_HICP_MANR` (Eurostat) — HICP variazione annua mensile, 4 dimensioni (freq, unit, coicop, geo), dataset compatto e veloce.

## Eurostat (provider default)

### 1. search — cerca dataset per parola chiave

```bash
opensdmx search "consumer price"
```

### 2. info — metadati e dimensioni

```bash
opensdmx info PRC_HICP_MANR
```

### 3. values — valori disponibili per una dimensione

```bash
opensdmx values PRC_HICP_MANR coicop
```

### 4. get — scarica dati con filtri (stdout CSV)

```bash
opensdmx get PRC_HICP_MANR --coicop CP00 --geo IT
```

### 5. get con --out — salva su file

```bash
opensdmx get PRC_HICP_MANR --coicop CP00 --geo IT --out /tmp/hicp_it.csv
```

Formati supportati: `.csv`, `.parquet`, `.json` (ndjson).

### 6. get con --start-period e --end-period

```bash
opensdmx get PRC_HICP_MANR --coicop CP00 --geo IT --start-period 2020 --end-period 2023
```

Formato periodo: `YYYY` (annuale), `YYYY-MM` (mensile), `YYYY-Q1` (trimestrale).

### 7. get con --last-n

```bash
opensdmx get PRC_HICP_MANR --coicop CP00 --geo IT --last-n 6
```

Restituisce le ultime 6 osservazioni. Esiste anche `--first-n`.

### 8. get bulk — scarica tutto senza filtri (wildcard)

```bash
opensdmx get DCIS_POPORESBIL1_24 --provider istat \
  --FREQ A --DATA_TYPE BEG --SEX 9 --start-period 2024 --end-period 2024 \
  --yes --out /tmp/comuni.csv
```

Quando nessun filtro è impostato su una dimensione ad alta cardinalità (es. REF_AREA con ~8.000 comuni),
`--yes` costruisce una singola chiamata REST wildcard invece di loopare su chunk.
Senza `--yes`, il CLI mostra il conteggio delle serie e si ferma in attesa di conferma.

### 9. get con valori multipli (operatore +)

```bash
opensdmx get PRC_HICP_MANR --coicop CP00 --geo IT+DE+FR --last-n 3
```

### 9. plot — grafico line chart

```bash
opensdmx plot PRC_HICP_MANR --coicop CP00 --geo IT --out /tmp/hicp_it.png
```

Default output: `chart.png` nella directory corrente.

### 10. plot con opzioni grafiche

```bash
opensdmx plot PRC_HICP_MANR --coicop CP00 --geo IT+DE+FR \
  --color geo \
  --title "HICP - variazione annua" \
  --xlabel "Data" --ylabel "%" \
  --width 12 --height 6 \
  --out /tmp/hicp_multi.png
```

### 11. --provider — cambia provider al volo

```bash
opensdmx search "consumer price" --provider eurostat
opensdmx info PRC_HICP_MANR --provider eurostat
```

Provider disponibili: `eurostat`, `istat`, `ecb`, `oecd`, `insee`, `bundesbank`, `worldbank`, `abs`.
URL custom: `--provider https://mio-server/sdmx/2.1`.

### 12. blacklist — gestione dataset non disponibili

```bash
opensdmx blacklist
```

---

## ISTAT (--provider istat)

> I comandi `search`, `info`, `values` funzionano. I comandi `get` e `plot` sono da verificare quando l'endpoint `/data` di ISTAT è disponibile.
>
> Nota: ISTAT ha un rate limit di 13s tra le chiamate. `--last-n` potrebbe non essere supportato (da verificare); usare `--start-period` / `--end-period` come alternativa.

Dataset candidato per i test: da identificare (preferibile ≤4 dimensioni, dati annuali o mensili nazionali).

### 1. search

```bash
opensdmx search "prezzi" --provider istat
```

### 2. info

```bash
opensdmx info 168_2 --provider istat
```

`168_2` = IPCA mensili e trimestrali 2001-2015, 5 dimensioni.

### 3. values

```bash
opensdmx values 168_2 MEASURE --provider istat
```

### 4. get — scarica dati con filtri

```bash
opensdmx get 168_2 --provider istat \
  --FREQ M --REF_AREA IT --DATA_TYPE 13 --MEASURE 4 --COICOP_REV_ISTAT 00 \
  --start-period 2013 --end-period 2015
```

`DATA_TYPE=13` = HICP base 2005=100 mensile; `MEASURE=4` = numero indice.

### 5–11. get con opzioni, plot, filtri

Da completare.
