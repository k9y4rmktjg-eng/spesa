# Spesa di Famiglia — guida all'installazione

App per iPhone con le offerte di **Lidl, Conad (Via Provinciale Est 10) e Coop (Piazza Ilaria Alpi 15)** di Nonantola e una **lista della spesa condivisa** in famiglia. Tutto gratis, funziona senza Claude.

- **GitHub Pages** ospita l'app (gratis)
- **GitHub Actions** scarica le offerte ogni lunedì e giovedì alle 6:10 (gratis)
- **Firebase** (Google, piano gratuito Spark) tiene la lista condivisa

Tempo totale: circa 30 minuti, dal Mac.

---

## 1. Crea l'account GitHub (5 min)
1. Vai su **https://github.com/signup**
2. Inserisci email, una password e un **nome utente** (es. `alecaruso`): comparirà nell'indirizzo dell'app, `https://NOMEUTENTE.github.io/spesa/`
3. Inserisci il codice che arriva via email. Se chiede un piano, scegli **Free**.

## 2. Crea il repository (2 min)
1. In alto a destra **+** → **New repository**
2. Repository name: `spesa`
3. Seleziona **Public** (necessario per l'hosting gratuito; la lista di famiglia resta privata)
4. Non spuntare nient'altro → **Create repository**

## 3. Carica i file (5 min)
1. Sul Mac fai doppio clic sullo ZIP: si crea la cartella `spesa-famiglia`.
2. Apri la cartella nel Finder e premi **⌘ ⇧ .** (Cmd+Maiusc+punto) per vedere anche la cartella nascosta `.github`.
3. Nella pagina del repository clicca il link **uploading an existing file**.
4. Seleziona **tutto il contenuto** della cartella (⌘A, compresa `.github`) e trascinalo nella pagina. *Non* trascinare la cartella `spesa-famiglia` stessa.
5. In basso **Commit changes**.
6. Controlla che nell'elenco ci sia la cartella `.github`. Se manca: **Add file → Create new file**, come nome scrivi `.github/workflows/aggiorna-offerte.yml`, incolla il contenuto del file omonimo (aprilo con TextEdit) e fai **Commit changes**.

## 4. Attiva il sito (2 min)
1. **Settings** (in alto nel repository) → **Pages** (menu a sinistra)
2. Source: **Deploy from a branch** · Branch: **main** · cartella **/ (root)** → **Save**
3. Dopo 1–2 minuti in cima alla pagina compare l'indirizzo: `https://NOMEUTENTE.github.io/spesa/`

## 5. Permetti l'aggiornamento automatico (1 min)
1. **Settings → Actions → General**
2. In fondo, *Workflow permissions*: **Read and write permissions** → **Save**

## 6. Primo scaricamento delle offerte (5 min)
1. Scheda **Actions** del repository. Se compare un pulsante verde *I understand my workflows…*, cliccalo.
2. A sinistra **Aggiorna offerte** → a destra **Run workflow** → **Run workflow**.
3. Dopo 3–6 minuti compare la spunta verde ✅. Da qui in poi parte da solo ogni lunedì e giovedì.
4. Se compare una ❌, clicca l'esecuzione e poi **aggiorna** per leggere il dettaglio (o manda uno screenshot a chi ti aiuta).

## 7. Crea il database della lista (10 min)
1. Vai su **https://console.firebase.google.com** e accedi con il tuo account Google.
2. **Crea un progetto** → nome `spesa-famiglia` → disattiva *Google Analytics* → **Crea progetto**.
3. Menu a sinistra **Build → Firestore Database** → **Crea database**
   - Località: **eur3 (Europe)** oppure **europe-west8 (Milano)**
   - Modalità: **production** → **Crea**
4. Scheda **Regole**: cancella tutto, incolla il contenuto del file `firestore.rules` → **Pubblica**.
5. Ingranaggio ⚙️ in alto a sinistra → **Impostazioni progetto** → in basso *Le tue app* → icona **`</>`** (Web) → nickname `spesa` → **Registra app** (non serve Hosting).
6. Compare un blocco `firebaseConfig = { apiKey: "...", ... }`: lascia la pagina aperta.
7. Su GitHub apri il file **config.js** → icona matita ✏️ → copia i sei valori (apiKey, authDomain, projectId, storageBucket, messagingSenderId, appId) tra le virgolette → **Commit changes**.

> La `apiKey` di Firebase per app web è fatta per essere pubblica: la protezione la danno le regole del punto 4 e il codice famiglia.

## 8. Installa sugli iPhone (2 min per telefono)
1. Apri `https://NOMEUTENTE.github.io/spesa/` con **Safari** (puoi mandare il link su WhatsApp ai familiari).
2. **Condividi** (quadrato con freccia) → **Aggiungi alla schermata Home** → **Aggiungi**.
3. Apri l'app dall'icona → scheda **Famiglia** → scrivi il tuo nome e il **codice famiglia** (almeno 8 caratteri, es. `caruso-spesa-2026`) → **Salva e collega**.
4. Usate **lo stesso codice** su tutti i telefoni: in alto a destra comparirà il pallino verde **Famiglia**.

---

## Uso quotidiano
- **Offerte**: filtra per negozio e categoria, cerca, tocca un prodotto per vederlo grande, **+** per metterlo in lista.
- **Lista**: raggruppata per negozio con i totali; tocca un prodotto per spuntarlo, usa − e + per le quantità; puoi aggiungere cose a mano scegliendo il negozio.
- **Invia la lista**: la manda come testo su WhatsApp/Messaggi.
- Funziona anche senza rete al supermercato: le modifiche partono quando torna internet.

## Se qualcosa non va
- **Avviso "offerte non aggiornate"** per una catena: il suo sito è cambiato. L'app mostra le offerte precedenti e il link al volantino ufficiale; le altre catene funzionano. Va aggiornata la parte di quella catena in `scraper/scrape.py`.
- **Conad** pubblica il volantino solo in PDF: i prodotti vengono letti dal PDF, quindi nomi e foto possono essere meno precisi di Lidl e Coop.
- GitHub ti scrive via email se un aggiornamento fallisce.
- **Lidl**: le offerte sono quelle nazionali del sito, valide anche a Nonantola.

## Aggiungere un negozio in futuro
I negozi sono in `scraper/negozi.json`; ogni catena ha bisogno di una piccola funzione di lettura in `scraper/scrape.py`.

## Struttura
```
index.html        app (pagina unica)
config.js         configurazione Firebase  ← da compilare
sw.js, manifest   funzionamento offline e icona sulla Home
icons/            icone
data/offerte.json offerte (scritto in automatico)
data/img/conad/   foto ritagliate dal volantino Conad (automatico)
scraper/          programma che scarica le offerte
.github/workflows aggiornamento automatico settimanale
firestore.rules   regole di sicurezza del database
```
