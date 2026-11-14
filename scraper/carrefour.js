// Gira DENTRO la pagina del negozio su carrefour.it (come farebbe un browser normale).
// Restituisce i volantini del negozio, con offerte (se il volantino ha l'elenco prodotti) e pagine.
async (cfg) => {
  const escludi = new RegExp(cfg.escludi, "i");
  const H = { "X-Requested-With": "XMLHttpRequest" };
  const dom = t => new DOMParser().parseFromString(t, "text/html");
  const testo = e => (e ? e.textContent.replace(/\s+/g, " ").trim() : "");
  const assoluto = u => !u ? "" : u.startsWith("http") ? u : "https://www.carrefour.it" + (u.startsWith("/") ? "" : "/") + u;

  // 1) le schede dei volantini nella pagina del negozio
  const pagina = dom(await (await fetch(location.pathname)).text());
  const storePath = location.pathname.replace(/\/$/, "");
  const schede = [], visti = new Set();
  for (const a of pagina.querySelectorAll(".card a[href]")) {
    const m = a.getAttribute("href").match(/\/(\d{4,})$/);
    if (!m || visti.has(m[1])) continue;
    visti.add(m[1]);
    const titolo = testo(a.querySelector(".card__title"));
    if (!titolo || escludi.test(titolo)) continue;
    schede.push({ id: m[1], titolo, validita: testo(a.querySelector(".validity")), url: assoluto(a.getAttribute("href")) });
  }

  // 2) per ogni volantino: pagine da sfogliare + elenco prodotti (solo i volantini principali lo hanno)
  let storeId = (pagina.documentElement.innerHTML.match(/storeId=([A-Z0-9]+)/) || [])[1] || "";
  const volantini = [];
  for (const s of schede) {
    const v = { ...s, pagine: [], offerte: [] };
    try {
      const t = await (await fetch(`/on/demandware.store/Sites-carrefour-IT-Site/it_IT/Volantini-Pages?storeId=${storeId}&editionId=${s.id}`, { headers: H })).text();
      const z = [...new Set(t.match(/https?:[^"'\s\\]*_sliderzoom\.jpg/g) || [])];
      const num = u => +((u.match(/_(\d+)_sliderzoom\.jpg$/) || [])[1] || 0);
      v.pagine = z.sort((a, b) => num(a) - num(b));
    } catch (e) { v.errPagine = String(e); }
    try {
      const l = dom(await (await fetch(`${storePath}/x/${s.id}?label=all`)).text());
      const fs = l.querySelector('[data-component="flyerSearchComponent"]');
      if (fs) {
        const g = dom(await (await fetch(fs.dataset.optionAction + "&start=0&sz=2000", { headers: H })).text());
        for (const tile of g.querySelectorAll(".flyer-tile")) {
          let j = {};
          try { j = JSON.parse(tile.dataset.productJson || "{}"); } catch {}
          const b = tile.querySelector(".discounts-flyer") || tile;
          const img = tile.querySelector("img.tile-image");
          const orig = b.querySelector(".d-prices__original");
          v.offerte.push({
            pid: tile.dataset.pid || j.id || "",
            nome: (j.name || testo(tile.querySelector(".tile-description"))).trim(),
            marca: (j.brand || testo(tile.querySelector(".brand")) || "").trim(),
            immagine: assoluto(img && (img.dataset.src || img.getAttribute("src"))),
            link: assoluto((tile.querySelector("a.product-link") || {}).getAttribute?.("href")),
            meccanica: testo(b.querySelector(".item-two")),
            carta: testo(b.querySelector(".item-three")),
            prima: orig ? testo(orig.querySelector("span")) : "",
            primaNota: orig ? testo(orig.querySelector(".no-line")) : "",
            prezzo: testo(b.querySelector(".d-prices__final strong")),
            dopo: testo(b.querySelector(".d-prices__after")),
            unitario: testo(b.querySelector(".d-prices__partial")),
          });
        }
      }
    } catch (e) { v.errOfferte = String(e); }
    volantini.push(v);
  }
  return { storeId, volantini };
}
