# Spesa di Famiglia — passaggio di consegne

Documento tecnico per riprendere il lavoro sull'app da zero, anche in una chat nuova.
**Da incollare (o allegare) all'inizio di ogni nuova chat**, insieme al file da modificare.
La guida all'installazione da zero resta in `LEGGIMI.md`.

Aggiornato al 14/11/2026.

---

## 1. Cos'è e dove sta

| Cosa | Dove |
|---|---|
| App (web app installata su iPhone/iPad/iMac) | https://k9y4rmktjg-eng.github.io/spesa/ |
| Codice | https://github.com/k9y4rmktjg-eng/spesa (ramo `main`) |
| Hosting | GitHub Pages (gratis) |
| Aggiornamento offerte | GitHub Actions, lunedì e giovedì alle 6:10 (ora italiana circa) |
| Lista condivisa e preferiti | Firebase Firestore, progetto `spesa-famiglia-8fcf6` (piano gratuito) |
| Copia locale sul Mac | `Download/spesa-famiglia` |

**Negozi:** Lidl (offerte nazionali), Conad Via Provinciale Est 10 Nonantola, Coop Piazza Ilaria Alpi 15 Nonantola, Carrefour Iper Casalecchio di Reno (Shopville Gran Reno).

**Come si caricano le modifiche:** a mano dal sito GitHub → cartella giusta → *Add file → Upload files* → *Commit changes*. Dopo 1–2 minuti (pallino verde) l'app si aggiorna da sola.

---

## 2. File principali

| File | Cosa fa |
|---|---|
| `index.html` | **Tutta l'app** in un solo file: grafica (CSS), schermate, logica (JavaScript `<script type="module">`). |
| `config.js` | Chiavi Firebase, nome app, zona. **Non serve toccarlo.** |
| `sw.js` | Service worker: cache per uso offline. Costante `V` = versione (ora `spesa-v14`): **aumentarla** quando si cambia `sw.js`. L'app (index) è sempre presa fresca dalla rete, le foto e le pagine dei volantini dalla cache. |
| `manifest.webmanifest`, `icons/` | Nome e icone quando si installa sulla schermata Home. |
| `firestore.rules` | Regole di sicurezza del database (copiate in Firebase). |
| `scraper/scrape.py` | Programma Python che scarica le offerte di tutti i negozi. |
| `scraper/carrefour.js` | Pezzo di codice eseguito *dentro* il sito Carrefour (per superare il controllo anti-robot). |
| `scraper/negozi.json` | Elenco negozi con indirizzi dei volantini. |
| `scraper/requirements.txt` | Librerie Python (playwright, pymupdf, pillow…). |
| `.github/workflows/aggiorna-offerte.yml` | Il "timer" che lancia lo scraper e salva i risultati. Si può lanciare a mano: *Actions → Aggiorna offerte → Run workflow*. |
| `data/offerte.json` | **Generato** dallo scraper: tutte le offerte + stato dei negozi. Non modificare a mano. |
| `data/storico.json` | **Generato**: storico prezzi per prodotto (vedi §6). |
| `data/vol/` | **Generato**: pagine JPEG dei volantini da sfogliare nell'app. |
| `data/img/` | **Generato**: immagini (es. Conad estratte dal PDF). |

---

## 3. Come funziona lo scraper (`scraper/scrape.py`)

- Per ogni negozio di `negozi.json` chiama la funzione in `FUNZIONI` (`lidl`, `coop`, `conad`, `carrefour`) usando un browser automatico (Playwright/Chromium).
- **Ogni negozio è isolato:** se uno fallisce (o trova meno di `MIN_OFFERTE = 3` offerte) tiene le offerte precedenti e l'app mostra un avviso "offerte non aggiornate" solo per quel negozio. Il workflow fallisce (email da GitHub) solo se falliscono *tutti*.
- `VOLANTINI` (`lidl_volantini`, `coop_volantini`, `carrefour_volantini`) scaricano le pagine dei volantini in `data/vol/` (900 px, JPEG qualità 66). Quelli già scaricati vengono saltati, quelli scaduti cancellati (`pulisci_volantini`).
- Fonti per negozio:
  - **Lidl:** pagine del sito lidl.it (offerte nazionali).
  - **Coop:** API del sito Coop Alleanza 3.0, negozio codice `9650`.
  - **Conad:** il volantino esiste solo in PDF → testo e immagini letti dal PDF (`conad_pdf`). Nomi a volte generici (es. "Ferrero").
  - **Carrefour:** pagina del punto vendita (storeId `I020`); volantino principale + speciali, esclusi "catalogo", "payback", "punti" (`escludi_titoli`). Ritenta fino a 4 volte se il sito blocca.
- **Categorie:** funzione `categoria()`. Liste `PRIMA` (regole forti) e `CATEGORIE` (parole chiave); vince la prima che corrisponde, prima sul nome e poi su nome + descrizione. Si usano `\b` (inizio/fine parola) per evitare errori tipo "Bovino" → "vino".
- **L'app raggruppa le 17 categorie in 11 reparti** (costante `MACRO` in `index.html`): Frutta e verdura, Carne e pesce, Freschi, Dispensa, Colazione e dolci, Bevande, Surgelati, Casa e altro, Persona e bimbi, Animali, Altro.

**Formato di un'offerta** in `offerte.json`:
```json
{"id":"lidl-7a9c…","negozio":"lidl","nome":"Speck affumicato","marca":"Dal Salumiere",
 "dettaglio":"100 g confezione","unitario":"1 kg = 13.90 €","prezzo":1.39,"prezzo_prima":1.75,
 "sconto":"-20%","categoria":"Salumi e formaggi","nota":"Super offerte…","immagine":"https://…",
 "link":"https://…","dal":"2026-11-06","al":"2026-11-18"}
```

---

## 4. L'app (`index.html`) — punti di riferimento

- **Schermate:** Offerte, Lista, Famiglia (barra in basso).
- **Funzioni principali** (cercarle per nome nel file):
  - `caricaOfferte` carica `data/offerte.json` e prepara i dati (sconto %, testo di ricerca, macro-categoria);
  - `disegnaOfferte` / `disegnaChipNegozi` mostrano la griglia delle offerte e i filtri;
  - `disegnaTop` disegna la striscia "Le migliori di oggi";
  - `apriDettaglio` apre la scheda del prodotto;
  - `aggiungiOfferta` mette un'offerta in lista;
  - `disegnaLista` mostra la lista, raggruppata per negozio e poi per reparto (`REPARTI`, `repartoDi`);
  - `apriSfogliatore` apre lo sfogliatore dei volantini, con il pannello "🛒 Offerte" e il + per aggiungere.
- **Negozi nell'app:** oggetto `NEG` (nome, nome breve, colore, sigla). Per un negozio nuovo va aggiunto anche qui.
- **Layout largo** (iPad/iMac ≥ 1100 px): classe `body.desk`.
- **Tema:** variabili CSS in `:root` (chiaro) e `prefers-color-scheme: dark` (scuro); blocco "STILE MODERNO" in fondo allo `<style>`. Verde principale `#16A34A` (scuro `#30D158`), sconti rossi `#FF3B30`.
- **Firebase:** oggetto `store` (add/upd/del) per la lista, `prefStore` per i preferiti. Senza codice famiglia funziona solo in locale ("Solo qui").

---

## 5. Problemi tipici e soluzioni

| Sintomo | Causa probabile | Cosa fare |
|---|---|---|
| Avviso "offerte non aggiornate" per un negozio | Il sito di quel negozio è cambiato | Aprire l'ultimo run in *Actions*, leggere l'errore di quel negozio, aggiornare la sua funzione in `scrape.py`. Gli altri negozi funzionano. |
| Run fallito con errore su `git push` | Due modifiche contemporanee (es. caricato un file mentre girava) | Rilanciare *Run workflow*. Non usare "Re-run jobs". |
| Dopo un caricamento l'app mostra ancora la versione vecchia | Cache del telefono | Chiudere completamente l'app e riaprirla. Se si è cambiato `sw.js`, aumentare `V`. |
| Prodotto in categoria sbagliata | Parola chiave ambigua | Aggiungere una regola in `PRIMA` o correggere `CATEGORIE` in `scrape.py`; vale dal run successivo. |
| Carrefour fallisce ogni tanto | Controllo anti-robot | Si riprova da solo al run dopo; se persiste, rivedere `_carrefour_dati` / `carrefour.js`. |
| Lista non condivisa | Codice famiglia diverso o non salvato | Scheda Famiglia: stesso codice su tutti i telefoni, pallino verde in alto. |

**Regola d'oro:** prima di sostituire `index.html` o `scrape.py` su GitHub, tenere una copia del file vecchio (o recuperarla da GitHub: file → *History*).

---

## 6. Storico prezzi (in raccolta dal 14/11/2026)

- `aggiorna_storico()` in `scrape.py`, chiamata a fine run. Se fallisce non blocca nulla.
- `data/storico.json`: `{ "negozio|nome marca formato": { "n": "Nome", "p": [["2026-11-06", 1.39, 1.75], …] } }` → data inizio offerta, prezzo, prezzo pieno (se c'è). Tiene 400 giorni.
- **Da fare (verso metà dicembre 2026):** mostrarlo nell'app, ad esempio "prezzo più basso degli ultimi mesi" o "settimana scorsa costava meno". Il file va caricato solo quando serve (es. all'apertura del dettaglio), non all'avvio.

---

## 7. Idee in sospeso

- **"Dove conviene questa settimana":** in base alla lista, quale negozio ha più prodotti in offerta e quanto si risparmia (la famiglia fa la spesa in un solo negozio per volta).
- Storico prezzi visibile (§6).
- Scartate: avviso preferiti, confronto prodotto per prodotto tra negozi, spese abituali, widget/Apple Watch (non possibili con una web app).

---

## 8. Come chiedere una modifica in una chat nuova

1. Incolla questo documento.
2. Allega il file da cambiare (di solito `index.html` o `scraper/scrape.py`), preso da GitHub o dalla copia locale.
3. Spiega cosa vuoi e chiedi il file completo modificato.
4. Caricalo su GitHub, aspetta il pallino verde, chiudi e riapri l'app.
