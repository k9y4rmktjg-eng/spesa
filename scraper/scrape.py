#!/usr/bin/env python3
"""
Scarica le offerte settimanali di Lidl, Conad e Coop (zona Nonantola)
e scrive data/offerte.json per l'app "Spesa di Famiglia".

Gira da solo su GitHub Actions ogni settimana. Se una catena fallisce,
le sue offerte precedenti restano e l'app mostra un avviso.
"""
import hashlib, io, json, re, shutil, sys, time, traceback, unicodedata
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "offerte.json"
IMG_DIR = DATA / "img"
CFG = json.loads((ROOT / "scraper" / "negozi.json").read_text(encoding="utf-8"))

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
MIN_OFFERTE = 3  # sotto questa soglia una catena è considerata "non aggiornata"


# ---------------------------------------------------------------- utilità
def log(*a):
    print(*a, flush=True)


def prezzo(v):
    """'1,39 €' / 1.39 / '~1,50 €~' -> 1.39 (float) oppure None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 2) if 0 < v < 5000 else None
    m = re.search(r"(\d{1,4})[.,](\d{2})", str(v))
    return round(float(f"{m.group(1)}.{m.group(2)}"), 2) if m else None


SIGLE = {"dop", "igp", "doc", "docg", "igt", "uht", "bio", "xl", "xxl"}
PICCOLE = {"di", "e", "con", "al", "alla", "allo", "alle", "ai", "del", "della",
           "dei", "delle", "in", "per", "da", "a", "o", "la", "il", "lo", "le", "gli"}


def bel_nome(s):
    """'LO SPAGHETTO N.104 VOIELLO' -> 'Lo Spaghetto N.104 Voiello'."""
    s = re.sub(r"\s+", " ", (s or "")).strip(" -–")
    if not s:
        return s
    lettere = [c for c in s if c.isalpha()]
    if lettere and sum(c.isupper() for c in lettere) / len(lettere) > 0.7:
        parole = s.lower().split(" ")
        s = " ".join(p if (i and p in PICCOLE) else
                     (p.upper() if p in SIGLE else p[:1].upper() + p[1:])
                     for i, p in enumerate(parole))
    return s


def uid(*parti):
    return hashlib.sha1("|".join(str(p) for p in parti).encode()).hexdigest()[:12]


def iso(d):
    if not d:
        return None
    if isinstance(d, (int, float)):
        return datetime.fromtimestamp(d / 1000, tz=ZoneInfo("Europe/Rome")).date().isoformat()
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", str(d))
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(d))
    return m.group(1) if m else None


def rifiuta_cookie(page):
    for testo in ["Rifiuta tutto", "Rifiuta tutti", "Rifiuta", "Continua senza accettare",
                  "Solo necessari", "Accetta solo i necessari"]:
        try:
            b = page.get_by_role("button", name=re.compile(testo, re.I)).first
            if b.is_visible(timeout=800):
                b.click(timeout=1500)
                page.wait_for_timeout(500)
                return
        except Exception:
            pass


def scorri(page, volte=8):
    for _ in range(volte):
        page.mouse.wheel(0, 2500)
        page.wait_for_timeout(350)



# ---------------------------------------------------------------- CATEGORIE comuni ai negozi
CATEGORIE = [  # (categoria, parole chiave) — l'ordine conta: vince la prima che trova
    ("Surgelati", r"surgelat|roncadin|patasnella|pizzoli|bella napoli|gelat[oi]|ghiacciol|bastoncin|sofficin|findus|pizza.*(congel|surgel)|patatine.*(forno|fritt)|minestrone|frozen"),
    ("Infanzia", r"omogeneizz|pannolin|mellin|plasmon|neonat|bimb|baby|latte (in polvere|di crescita|1|2|3)\b|pouch"),
    ("Animali", r"\bcane\b|\bcani\b|gatt[oi]|crocchett|lettiera|per animali|pet\b|felix|purina|whiskas|friskies|sheba|gourmet"),
    ("Cura della persona", r"shampoo|balsamo|bagnoschiuma|doccia|sapone|deodorant|dentifric|integrator|spazzolin|collutor|rasoi|schiuma da barba|gillette|crema (viso|mani|corpo)|assorbent|salvaslip|cotton|struccant|igiene intima|lacca|tinta|cosmet|fazzolett"),
    ("Casa e pulizia", r"detersiv|ammorbid|candeggin|sgrassat|pavimenti|lavastoviglie|piatti|bucato|anticalcare|igienizz|carta igienica|carta da cucina|rotoloni|regina\b|asciugatutto|scottex|tovagliol|rotoli|sacchi|pellicola|alluminio|spugn|dixan|dash|finish|coccolino|perlana|mastro lindo|detergent|svelto|lysoform|chanteclair|swiffer|insetticid|deodorante per ambient|pastiglie|capsule (lavatrice|lavastov)"),
    ("Bevande", r"\bacqua\b|baileys|irish cream|bibit|cola\b|pepsi|aranciata|chinotto|gassos|succo|nettare|spremut|\bt[eè] (fredd|limone|pesca)|estath|birra|vino|prosecco|spumante|pignoletto|\bdoc\b|docg|\bigt\b|rosé|rosato|lambrusco|champagne|liquor|amaro|grappa|whisky|vodka|gin\b|rum\b|aperitiv|spritz|energy|sciroppo|bevanda (di|al|vegetale)|integratore salin|gatorade|powerade"),
    ("Caffè, tè e colazione", r"caff[eè]|nescaf|twinings|\btea\b|espresso|lavazza|illy\b|kimbo|segafredo|borbone|capsul|cialde|orzo|cappuccin|\bt[eè]\b|tisan|camomill|infuso|cereali|muesli|fiocchi d|cornflakes|biscott|biscuits|fette biscott|merendin|cornett|brioche|croissant|crostatin|plumcake|marmellat|confettur|nutella|nocciolato|crema novi|skippy|crema spalmabile|miele|cacao|nesquik|pan di stelle|macine|abbracci|gocciole|oro saiwa"),
    ("Frutta e verdura", r"\bmel[ae]\b|\bpere\b|\bpera\b|banan|arance|\barancia\b|mandarin|clementin|limon|kiwi|\buva\b|frutt[ao] fresc|ananas|fragol|pesche|albicocc|cachi|melagran|avocado|insalat|lattug|rucola|spinac|zucchin|melanzan|peperon|pomodor(i|ino) (fresch|ciliegin|datterin|grappolo)|ciliegin|datterin|carot|patat[ae]\b|cipoll|aglio|finocch|sedano|cavol|broccol|verza|radicchi|funghi|champignon|zucca|carciof|legumi fresch|verdur|ortofrutt|marroni|prugne|frutta secca|noci|mandorle|nocciole|pistacch|castagn|datteri"),
    ("Carne e pesce", r"pollo|tacchino|manzo|bovino|vitell|suino|maiale|lonza|braciol|salsicc|hamburger|polpett|macinat|bistecc|fettin|cotolett|arrost|spezzatin|petto di|cosce|sovracosc|ali di|agnell|coniglio|wurstel|würstel|pesce|salmone|tonno fresc|merluzz|nasell|orata|branzin|spigol|gamber|cozze|vongol|calamar|seppi|polp[oi]|filetti di|baccal|sgombr|alici|acciugh|sardin|surimi|pepite|nuggets|cordon"),
    ("Salumi e formaggi", r"prosciutt|salam|mortadell|speck|bresaol|coppa\b|pancett|guancial|culatell|cotechino|zampone|spalla cotta|affettat|formagg|parmigian|grana|pecorin|gorgonzol|mozzarell|burrata|stracchin|squacquer|crescenza|ricotta|mascarpone|provol|scamorz|fontina|asiago|montasio|emmental|edamer|taleggio|caciott|fior di latte|feta|brie|camembert|philadelphia|frittata|gastronomia|rovagnati|snello|grattugiat|biraghi|galbani|galbanino|leerdammer|robiola|certosa|cacciatore|spianata|salumi|sottilett|fett[ei]n[ae] di formaggio|stracciatella di"),
    ("Latte, yogurt e uova", r"\blatte\b|yogurt|yoghurt|parmalat|alpro|planted|kefir|skyr|actimel|activia|budin|panna|burro|uova|margarin|dessert|danone|muller|müller|zymil|hipro|bevanda.*(soia|avena|mandorl|riso)"),
    ("Pane e forno", r"\bpane\b|panin|piadin|tortill|focacc|grissin|cracker|crackers|taralli|fette (tostat|integral)|pan bauletto|pancarr|bauletto|wasa|gallette|schiacciat|pinsa|pizza (fresca|margherita|bella)|basi pizza|pasta (sfoglia|brisè|frolla)"),
    ("Dolci e snack", r"cioccolat|tavolett|praline|caramell|chewing|gomme|patatine|chips|pop ?corn|snack|wafer|tort[ae]|panetton|pandoro|colomba|torron|dolci|pasticc|tiramis|crostat|muffin|ciambell|salatini|arachidi|kinder|ferrero|snickers|nestl[eé]|twix|mars\b|lindt|milka|loacker|haribo|pringles|san carlo|amica chips"),
    ("Pasta, riso e dispensa", r"pasta|pastin|spaghett|penne|fusill|rigaton|farfall|tagliatell|lasagn|tortellin|ravioli|gnocch|riso\b|risott|farin|zucchero|sale\b|olio|oliva|aceto|passata|polpa|pelati|sugo|ragù|pesto|tonno|legumi|fagiol|ceci|lenticch|piselli|mais|conserv|sottol|sottacet|olive|maionese|ketchup|senape|dado|brodo|spezie|lievito|minestr|zuppa|crema di|purè|cous ?cous|quinoa|orzo perlato|farro|barilla|de cecco|voiello|rummo|garofalo|divella|mutti|cirio|rio mare|nostromo|calv[eè]|knorr|star\b"),
    ("Non alimentari", r"abbigliam|maglia|calz|pantalon|giacca|scarpe|pigiama|intimo|lenzuol|asciugaman|tappet|cuscin|piumon|pentol|padell|tegam|bicchier|piatti in|posate|lampad|batteri[ae]|attrezz|trapano|avvitator|cacciavite|giardin|fiori|piant|vaso|giocattol|gioco|bicicl|auto\b|garage|elettrodomestic|stufa|termozeta|borsa calda|midea|air fryer|friggitrice|frullator|aspirapolvere|ferro da stiro|tv\b|cuffie|smartphone|tablet|cartoleria|quaderni|zaino|valigi|decoraz|natal|candel"),
]
_CAT_RE = [(c, re.compile(r, re.I)) for c, r in CATEGORIE]
HINT = {  # categorie dei siti -> categorie comuni (quando il nome non basta)
    "cura della persona": "Cura della persona", "igiene della casa": "Casa e pulizia", "bevande": "Bevande",
    "per i nostri piccoli amici": "Animali", "prodotti infanzia": "Infanzia", "casa": "Non alimentari",
    "abbigliamento e accessori": "Non alimentari", "tempo libero": "Non alimentari",
    "multimedia / tecnologia": "Non alimentari", "surgelati": "Surgelati", "ortofrutta": "Frutta e verdura",
    "macelleria": "Carne e pesce", "pescheria": "Carne e pesce", "gastronomia": "Salumi e formaggi",
    "salumeria": "Salumi e formaggi", "latticini": "Latte, yogurt e uova", "panetteria": "Pane e forno",
    "forno": "Pane e forno", "drogheria": "Pasta, riso e dispensa", "dispensa": "Pasta, riso e dispensa",
    "freschi": "Altri freschi", "freschissimi": "Altri freschi", "non food": "Non alimentari",
}
FORTI = {"Cura della persona", "Casa e pulizia", "Animali", "Infanzia", "Non alimentari"}


def categoria(nome, dettaglio="", suggerimento=""):
    """Assegna una categoria comune a tutti i negozi, dal nome del prodotto e dall'indicazione del sito."""
    h = HINT.get((suggerimento or "").strip().lower())
    if h in FORTI:
        return h
    for testo in (nome, f"{nome} {dettaglio}"):  # prima il solo nome, poi anche la descrizione
        for c, rx in _CAT_RE:
            if rx.search(testo):
                if c == "Non alimentari" and suggerimento and h not in (None, "Non alimentari"):
                    continue
                return c
    if suggerimento:  # es. categoria Lidl "Formaggi, latticini e uova"
        for c, rx in _CAT_RE:
            if rx.search(suggerimento):
                return c
    return h or "Altro"


# ---------------------------------------------------------------- LIDL
def lidl(ctx, n):
    page = ctx.new_page()
    page.goto(n["home"], wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    rifiuta_cookie(page)
    links = page.eval_on_selector_all(
        "a[href*='/c/store/']", "els => [...new Set(els.map(a => a.href.split('?')[0].split('#')[0]))]")
    links = links[: n.get("max_pagine", 25)]
    log(f"  Lidl: {len(links)} pagine offerte")
    offerte, visti = [], set()
    for url in links:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1500)
            scorri(page, 6)
            raw = page.eval_on_selector_all(
                "[data-grid-data]", "els => els.map(e => e.getAttribute('data-grid-data'))")
        except Exception as e:
            log("   pagina saltata", url, e)
            continue
        campagna = url.rstrip("/").split("/")[-2]
        campagna = re.sub(r"-kw-\d+-\d+$", "", campagna).replace("-", " ").capitalize()
        for r in raw:
            try:
                d = json.loads(r)
            except Exception:
                continue
            nome = d.get("fullTitle") or d.get("title")
            rp = d.get("regionsPrices") or {}
            cp = (next(iter(rp.values()), {}) or {}).get("currentPrice") or {}
            p = prezzo(cp.get("price")) or prezzo((d.get("price") or {}).get("price"))
            if not nome or not p:
                continue
            key = (nome.lower(), p)
            if key in visti:
                continue
            visti.add(key)
            disc = cp.get("discount") or {}
            img = d.get("image")
            if not img:
                il = d.get("imageList_V1") or d.get("imageList") or []
                img = il[0].get("image") if il and isinstance(il[0], dict) else None
            link = d.get("canonicalUrl") or d.get("canonicalPath") or ""
            if link.startswith("/"):
                link = "https://www.lidl.it" + link
            offerte.append({
                "id": "lidl-" + uid(nome, p, cp.get("endDate")),
                "negozio": "lidl",
                "nome": bel_nome(d.get("title") or nome),
                "marca": bel_nome(((d.get("brand") or {}).get("name")) or ""),
                "dettaglio": ((cp.get("packaging") or {}).get("text")) or "",
                "unitario": ((cp.get("basePrice") or {}).get("text")) or "",
                "prezzo": p,
                "prezzo_prima": prezzo(cp.get("oldPrice") or disc.get("deletedPrice")),
                "sconto": disc.get("discountText") or "",
                "categoria": categoria(d.get("title") or nome, (cp.get("packaging") or {}).get("text") or "",
                                       ((d.get("keyfacts") or {}).get("wonCategoryPrimary") or "").split("/")[-2:][0]
                                       if d.get("category") == "Food" else "non food"),
                "nota": campagna + (" · Lidl Plus" if "plus" in campagna.lower() else ""),
                "immagine": img,
                "link": link,
                "dal": iso(cp.get("startDate") or d.get("storeStartDate")),
                "al": iso(cp.get("endDate") or d.get("storeEndDate")),
            })
    page.close()
    return offerte


# ---------------------------------------------------------------- COOP
def coop(ctx, n):
    code = n["codice_negozio"]
    base = "https://svdgt.coopalleanza3-0.it/apim"
    page = ctx.new_page()
    page.goto(n["pagina_negozio"], wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2000)
    rifiuta_cookie(page)

    def get(url):
        r = ctx.request.get(url, headers={"Referer": n["pagina_negozio"],
                                          "Accept": "application/json"}, timeout=60000)
        if not r.ok:
            raise RuntimeError(f"HTTP {r.status} su {url}")
        return r.json()

    leaflets = get(f"{base}/leaflets/{code}").get("leaflets", [])
    log(f"  Coop: {len(leaflets)} volantini")
    offerte, visti = [], set()
    for lf in leaflets:
        lid, titolo = lf["id"], lf.get("titolo") or ""
        try:
            cats = {c["code"]: c["descrizione"] for c in
                    get(f"{base}/{lid}/{code}/categories").get("categories", [])}
        except Exception:
            cats = {}
        promos = get(f"{base}/{lid}/{code}/promos?").get("promos", [])
        log(f"   {titolo}: {len(promos)} prodotti")
        for pr in promos:
            testi = []
            for k in ("DXTop", "DXBottom", "CXTop", "CXBottom", "SXTop", "SXBottom"):
                testi += [t for t in ((pr.get(k) or {}).get("txt") or []) if t]
            vecchio = next((prezzo(t) for t in testi if t.strip().startswith("~")), None)
            p = next((prezzo(t) for t in testi
                      if "~" not in t and " al " not in t and "/" not in t and prezzo(t)), None)
            unit = next((t for t in testi if " al " in t or "/kg" in t or "/l" in t), "")
            sconto = next((t for t in testi if re.search(r"-\s?\d+\s?%|\dx\d|sconto", t, re.I)), "")
            nome = pr.get("desc_promo")
            if not nome or not p:
                continue
            key = (nome.lower(), p, lid)
            if key in visti:
                continue
            visti.add(key)
            offerte.append({
                "id": "coop-" + uid(pr.get("id"), lid),
                "negozio": "coop",
                "nome": bel_nome(nome),
                "marca": bel_nome(pr.get("brand") or ""),
                "dettaglio": " · ".join(x for x in [pr.get("desc_promo2"), pr.get("desc_multi")] if x),
                "unitario": unit,
                "prezzo": p,
                "prezzo_prima": vecchio,
                "sconto": sconto.strip(),
                "categoria": categoria(nome, pr.get("desc_promo2") or "", cats.get(pr.get("categoryCode"), "")),
                "nota": titolo + (" · " + pr["desc_promo3"] if pr.get("desc_promo3") else ""),
                "immagine": pr.get("img"),
                "link": lf.get("url"),
                "dal": iso(lf.get("valido_da")),
                "al": iso(lf.get("valido_a")),
            })
    page.close()
    return offerte


# ---------------------------------------------------------------- CONAD (PDF)
RE_PREZZO = re.compile(r"^(?:€\s*)?(\d{1,3})\s?[,.]\s?(\d{2})\s*€?$")


RE_BADGE = re.compile(r"^(SOTTO ?COSTO|SOTTO|COSTO|SOLO|OFFERTA|NOVIT[AÀ]|SCONTO.*|GRATIS|CONVIENE|PREZZO.*|PREZZI.*|"
                      r"BASSI E FISSI|N°.*|.*PEZZI DISPONIBILI.*|A PARTIRE DA|IN PI[UÙ]|OGNI|"
                      r"SCOPRI.*|DAL .*|FINO AL .*|SOLO PER .*|CARTA .*|€|SOLO TITOLARI.*|TITOLARI.*|ALL.ETTO|AL KG|IL TUO VOLANTINO|VIENI SU.*|SEGUICI.*|WHATSAPP.*|SCARICA.*|APP .*)$")
RE_BADGE_IN = re.compile(r"\s*\b(SOTTO ?COSTO|NOVIT[AÀ]|SOLO TITOLARI( CARTA)?)\b\s*", re.I)


def _badge(t):
    return bool(RE_BADGE.match(t.strip().upper()))


def _maiuscolo(t):
    l = [c for c in t if c.isalpha()]
    return len(l) >= 3 and sum(c.isupper() for c in l) / len(l) > 0.8


def conad_pdf(pdf_bytes, flyer, img_out):
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    offerte, visti = [], set()
    for pno, page in enumerate(doc):
        W, H = page.rect.width, page.rect.height
        righe = []
        for b in page.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                t = unicodedata.normalize("NFKC", "".join(s["text"] for s in ln["spans"])).strip()
                t = re.sub(r"(ff|fi|fl) (?=[a-zà-ù])", r"\1", t)
                if not t:
                    continue
                size = max(s["size"] for s in ln["spans"])
                righe.append({"t": t, "size": size, "bbox": fitz.Rect(ln["bbox"]), "blk": id(b)})
        # prezzi principali = numeri tipo 1,39 con font grande
        cand = [r for r in righe if RE_PREZZO.match(r["t"].replace(" ", ""))]
        if not cand:
            continue
        soglia = max(r["size"] for r in cand) * 0.45
        prezzi = [r for r in cand if r["size"] >= soglia]
        nomi = [r for r in righe if _maiuscolo(r["t"]) and not _badge(r["t"])
                and not re.search(r"\d+[,.]\d{2}", r["t"])
                and r["size"] < max(p["size"] for p in prezzi) and len(r["t"]) <= 60]
        immagini = [fitz.Rect(i["bbox"]) & page.rect for i in page.get_image_info()
                    if (fitz.Rect(i["bbox"]) & page.rect).get_area() > 0.004 * W * H
                    and (fitz.Rect(i["bbox"]) & page.rect).get_area() < 0.5 * W * H]
        # riquadri dei prodotti: rettangoli colorati disegnati nel PDF (uno per prodotto)
        riquadri = []
        for dr in page.get_drawings():
            R = dr.get("rect")
            if R is not None and dr.get("fill") is not None and 0.08 * W < R.width < 0.7 * W \
                    and 0.08 * H < R.height < 0.75 * H:
                riquadri.append(fitz.Rect(R))
        centri = [fitz.Point((q["bbox"].x0 + q["bbox"].x1) / 2, (q["bbox"].y0 + q["bbox"].y1) / 2) for q in prezzi]
        pezzi = [fitz.Rect(i["bbox"]) & page.rect for i in page.get_image_info()]
        pezzi = [I for I in pezzi if 0.0008 * W * H < I.get_area() < 0.3 * W * H
                 and sum(I.contains(c) for c in centri) == 0]

        def costo(I, q):
            Q = q["bbox"]
            if min(I.y1, Q.y1 + 0.05 * H) - max(I.y0, Q.y0 - 0.3 * H) <= 0:
                return 1e9  # nessuna sovrapposizione verticale con la zona del prodotto
            if I.x1 <= Q.x1 + 2:  # foto a sinistra del prezzo (o sopra): caso normale
                return max(0.0, Q.x0 - I.x1 - 0.12 * W) + abs((I.y0 + I.y1) / 2 - (Q.y0 + Q.y1) / 2) * 0.2
            return (I.x0 - Q.x1) + 0.15 * W
        proprietario = []
        for I in pezzi:
            q = min(prezzi, key=lambda q: costo(I, q))
            if costo(I, q) < 0.2 * W:
                proprietario.append((I, q))
        for pr in prezzi:
            P = pr["bbox"]
            pc = fitz.Point((P.x0 + P.x1) / 2, (P.y0 + P.y1) / 2)
            dentro = [R for R in riquadri if R.contains(pc)]
            tile = min(dentro, key=lambda R: R.get_area()) if dentro else None
            # nome: righe maiuscole sopra al prezzo e vicine
            vicine = []
            for r in nomi:
                R = r["bbox"]
                if R.y0 > P.y1 + 4:  # sotto al prezzo: no
                    continue
                if tile is not None and not tile.contains(fitz.Point((R.x0 + R.x1) / 2, (R.y0 + R.y1) / 2)):
                    continue  # testo di un altro riquadro
                dy = P.y0 - R.y1
                dx = abs((R.x0 + R.x1) / 2 - pc.x)
                if dy > 0.30 * H or dx > 0.30 * W:
                    continue
                vicine.append((dy + dx * 1.3, r))
            if not vicine:
                continue
            vicine.sort(key=lambda x: x[0])
            primo = vicine[0][1]
            gruppo = sorted([r for _, r in vicine
                             if abs(r["bbox"].x0 - primo["bbox"].x0) < 40
                             and abs(r["bbox"].y0 - primo["bbox"].y0) < 60],
                            key=lambda r: r["bbox"].y0)
            nome = " ".join(r["t"] for r in gruppo)
            nome = RE_BADGE_IN.sub(" ", nome)
            mrep = re.match(r"^REPARTO (\S+)\s+", nome, flags=re.I)
            reparto = mrep.group(1) if mrep else ""
            nome = re.sub(r"^REPARTO \S+\s+", "", nome, flags=re.I)
            if re.search(r"VOLANTINO|PAGIN", nome, re.I) or re.fullmatch(r"(?i)all.etto|al kg|solo|titolari", nome):
                continue
            nome = re.sub(r"\s+", " ", nome).strip(" ,.-")
            if len(nome) < 4:
                continue
            p = prezzo(pr["t"])
            key = (nome.lower(), p)
            if key in visti:
                continue
            visti.add(key)
            # dettaglio (es. "500 g") e prezzo al kg: righe minuscole subito sotto al nome
            ultimo = gruppo[-1]["bbox"]
            sotto = [r["t"] for r in sorted(righe, key=lambda r: r["bbox"].y0)
                     if -3 <= r["bbox"].y0 - ultimo.y1 < 45
                     and abs(r["bbox"].x1 - ultimo.x1) < 60 and not _maiuscolo(r["t"]) and not _badge(r["t"])
                     and re.search(r"[a-zà-ù]{2}", r["t"]) and not RE_PREZZO.match(r["t"].replace(" ", ""))]
            dett = " ".join(sotto[:3])[:90]
            # vicino al prezzo: prezzo barrato (sopra), sconto % e prezzo al kg/l (sotto)
            intorno = [r for r in righe if r is not pr and abs((r["bbox"].x0 + r["bbox"].x1) / 2 - pc.x) < 0.18 * W
                       and -0.09 * H < r["bbox"].y0 - P.y0 < 0.09 * H]
            vecchio = None
            for r in sorted(intorno, key=lambda r: abs(r["bbox"].y1 - P.y0)):
                if r["bbox"].y1 <= P.y0 + 6 and r["size"] < pr["size"] * 0.7 and re.search(r"\d+[,.]\d{2}", r["t"]) \
                        and "%" not in r["t"] and " al " not in r["t"]:
                    v = prezzo(r["t"])
                    if v and v > prezzo(pr["t"]):
                        vecchio = v
                        break
            sc = next((r["t"] for r in intorno if re.search(r"-\s?\d+([,.]\d+)?\s?%", r["t"])), "")
            m = re.search(r"-\s?(\d+)(?:[,.](\d+))?\s?%", sc)
            sconto = f"-{round(float(m.group(1) + '.' + (m.group(2) or '0')))}%" if m else ""
            if m:  # lo sconto % stampato è il dato più affidabile per ricavare il prezzo pieno
                pct = float(m.group(1) + "." + (m.group(2) or "0"))
                if 0 < pct < 90:
                    calcolato = round(prezzo(pr["t"]) / (1 - pct / 100), 2)
                    if not vecchio or abs(vecchio - calcolato) > 0.05:
                        vecchio = calcolato
            elif vecchio and vecchio > prezzo(pr["t"]) * 3:
                vecchio = None
            unit = next((r["t"] for r in intorno if re.search(r"\bal (kg|l|lt|litro|pz)\b|/kg|/l\b", r["t"], re.I)), "")
            # foto: il riquadro del prodotto; se manca (o contiene solo il prezzo) i pezzi di foto
            # "di proprietà" di questo prezzo, cioè subito a sinistra/sopra del suo testo
            T = gruppo[0]["bbox"] | P
            miei = [I for I, q in proprietario if q is pr]
            clip = None
            if tile is not None:
                coperto = sum((I & tile).get_area() for I in pezzi) / max(tile.get_area(), 1)
                clip = tile if coperto >= 0.12 else None
                T = tile if clip is None else T
            if clip is None and miei:
                unione = T
                for I in sorted(miei, key=lambda I: -I.get_area()):
                    if (unione | I).width < 0.5 * W and (unione | I).height < 0.6 * H:
                        unione = unione | I
                clip = (unione & page.rect) if unione != T else None
            if clip is None:
                clip = tile or (fitz.Rect(min(gruppo[0]["bbox"].x0, P.x0) - 20, gruppo[0]["bbox"].y0 - 0.12 * H,
                                          max(P.x1, gruppo[0]["bbox"].x1) + 20, P.y1 + 10) & page.rect)
            img_url = None
            try:
                zoom = min(3.0, 420 / max(clip.width, 1))
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)
                nomefile = uid(flyer.get("flyerCode"), nome, p) + ".jpg"
                pix.save(str(img_out / nomefile), jpg_quality=78)
                img_url = f"data/img/conad/{nomefile}"
            except Exception as e:
                log("    foto non salvata:", e)
            offerte.append({
                "id": "conad-" + uid(flyer.get("flyerCode"), nome, p),
                "negozio": "conad",
                "nome": bel_nome(nome),
                "marca": "",
                "dettaglio": dett,
                "unitario": unit,
                "prezzo": p,
                "prezzo_prima": vecchio,
                "sconto": sconto,
                "categoria": categoria(nome, dett, reparto),
                "nota": bel_nome(flyer.get("title") or "") + f" · pag. {pno + 1}",
                "immagine": img_url,
                "link": flyer.get("pdfUrl"),
                "dal": iso(flyer.get("validFrom")),
                "al": iso(flyer.get("validTo")),
            })
    return offerte


def conad(ctx, n):
    page = ctx.new_page()
    page.goto(n["pagina_negozio"], wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    rifiuta_cookie(page)
    scorri(page, 6)
    flyers = []
    for raw in page.eval_on_selector_all("[data-flyer]", "els => els.map(e => e.getAttribute('data-flyer'))"):
        try:
            flyers.append(json.loads(raw))
        except Exception:
            pass
    # altri volantini del negozio presenti come link
    links = page.eval_on_selector_all("a[href*='/volantini/']", "els => [...new Set(els.map(a => a.href))]")
    for url in links[:8]:
        if any(f.get("slug", "") in url for f in flyers):
            continue
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1500)
            for raw in page.eval_on_selector_all("[data-flyer]", "els => els.map(e => e.getAttribute('data-flyer'))"):
                try:
                    flyers.append(json.loads(raw))
                except Exception:
                    pass
        except Exception:
            pass
    page.close()
    escl = [e.upper() for e in n.get("escludi_titoli", [])]
    unici = {}
    for f in flyers:
        tit = (f.get("title") or f.get("feTitle") or "").upper()
        if not f.get("pdfUrl") or any(e in tit for e in escl):
            continue
        unici[f.get("flyerCode") or f["pdfUrl"]] = f
    log(f"  Conad: {len(unici)} volantini da leggere")
    img_out = IMG_DIR / "conad_new"
    shutil.rmtree(img_out, ignore_errors=True)
    img_out.mkdir(parents=True)
    offerte = []
    for f in unici.values():
        r = ctx.request.get(f["pdfUrl"], timeout=120000, headers={"Referer": n["pagina_negozio"]})
        if not r.ok:
            log("   PDF non scaricato", r.status, f["pdfUrl"])
            continue
        o = conad_pdf(r.body(), f, img_out)
        log(f"   {f.get('title')}: {len(o)} prodotti")
        offerte += o
    if len(offerte) >= MIN_OFFERTE:
        shutil.rmtree(IMG_DIR / "conad", ignore_errors=True)
        img_out.rename(IMG_DIR / "conad")
    else:
        shutil.rmtree(img_out, ignore_errors=True)
    return offerte


def lidl_volantini(ctx, n):
    """Link diretti ai volantini settimanali Lidl (si aprono senza scegliere il punto vendita)."""
    page = ctx.new_page()
    try:
        page.goto(n["volantino"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        ids = page.eval_on_selector_all(
            "[id^='flyer-']",
            "els => els.filter(e => /settimanal/i.test(e.textContent)).map(e => e.id.slice(6))")
        volantini = []
        for fid in dict.fromkeys(ids):
            if not re.fullmatch(r"[0-9a-f-]{36}", fid):
                continue
            r = page.request.get(f"https://endpoints.leaflets.schwarz/v4/flyer?flyer_identifier={fid}&region_id=0",
                                 timeout=30000)
            if not r.ok:
                continue
            f = (r.json() or {}).get("flyer") or {}
            if f.get("flyerUrlAbsolute"):
                volantini.append({"url": f["flyerUrlAbsolute"], "nome": f.get("name") or "",
                                  "dal": f.get("offerStartDate") or f.get("startDate") or "",
                                  "al": f.get("offerEndDate") or f.get("endDate") or "", "n": 0})
        log(f"  Lidl: {len(volantini)} volantini settimanali")
        return volantini
    finally:
        page.close()


# ---------------------------------------------------------------- main
FUNZIONI = {"lidl": lidl, "coop": coop, "conad": conad}
VOLANTINI = {"lidl": lidl_volantini}   # link diretti ai volantini, dove il sito li nasconde


def main():
    precedente = {}
    if OUT.exists():
        try:
            precedente = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            pass
    vecchie = precedente.get("offerte", [])
    stati_vecchi = {s["id"]: s for s in precedente.get("negozi", [])}
    ora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    solo = set(sys.argv[1:])

    risultato, stati = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
        for n in CFG["negozi"]:
            if solo and n["id"] not in solo:
                risultato += [o for o in vecchie if o["negozio"] == n["id"]]
                stati.append(stati_vecchi.get(n["id"], {"id": n["id"]}))
                continue
            log(f"== {n['nome']}")
            ctx = browser.new_context(
                user_agent=UA, locale="it-IT", timezone_id="Europe/Rome",
                geolocation={"latitude": 44.6776, "longitude": 11.0410},
                permissions=["geolocation"], viewport={"width": 1366, "height": 900})
            t0 = time.time()
            stato = {"id": n["id"], "nome": n["nome"], "colore": n.get("colore"),
                     "volantino": n.get("volantino"), "negozio": n.get("negozio", "")}
            try:
                off = FUNZIONI[n["tipo"]](ctx, n)
                if len(off) < MIN_OFFERTE:
                    raise RuntimeError(f"trovate solo {len(off)} offerte: il sito potrebbe essere cambiato")
                risultato += off
                stato.update(ok=True, n=len(off), aggiornato=ora, messaggio="")
                log(f"  OK {len(off)} offerte in {time.time() - t0:.0f}s")
            except Exception as e:
                traceback.print_exc()
                tenute = [o for o in vecchie if o["negozio"] == n["id"]]
                risultato += tenute
                prima = stati_vecchi.get(n["id"], {})
                stato.update(ok=False, n=len(tenute), aggiornato=prima.get("aggiornato"),
                             messaggio=str(e)[:200])
                log(f"  ERRORE: {e} (tengo {len(tenute)} offerte precedenti)")
            if n["tipo"] in VOLANTINI:  # facoltativo: se fallisce restano i link di prima
                try:
                    stato["volantini"] = VOLANTINI[n["tipo"]](ctx, n)
                except Exception as e:
                    log(f"  volantini non trovati: {e}")
                    if stati_vecchi.get(n["id"], {}).get("volantini"):
                        stato["volantini"] = stati_vecchi[n["id"]]["volantini"]
            stati.append(stato)
            ctx.close()
        browser.close()

    DATA.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"zona": CFG["zona"], "aggiornato": ora, "negozi": stati,
                               "offerte": risultato}, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Scritte {len(risultato)} offerte in {OUT}")
    # esce con errore solo se TUTTE le catene sono fallite (così GitHub ti avvisa)
    if not any(s.get("ok") for s in stati if not solo or s.get("id") in solo):
        sys.exit(1)


if __name__ == "__main__":
    main()
