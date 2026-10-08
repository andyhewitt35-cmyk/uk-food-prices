#!/usr/bin/env python3
"""Build site/data.json for the UK grocery price comparison.

Sources (real prices only, each item keeps the time it was checked):
  * Tesco, Sainsbury's, Asda, Aldi - the free public daily dataset published by
    "UK Supermarket Price Scraper" (yappman, Apify), CC BY 4.0. ~212 products, 20 staples, daily ~06:30 UK time.
  * Morrisons - its public product pages (robots.txt allows /products/; /api/ is disallowed and not used),
    a fixed list in morrisons_products.txt, fetched slowly once per run.
If a source fails, the previous published data for that shop is kept (with its old date) and flagged.
"""
import json, re, sys, time, html, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

APIFY_URL = "https://api.apify.com/v2/datasets/ynAT9NPps2EdjMOJa/items?format=json&clean=1"
LIVE_URL = "https://andyhewitt35-cmyk.github.io/uk-food-prices/data.json"
MORRISONS_BASE = "https://groceries.morrisons.com/products/"
UA = "Mozilla/5.0 (compatible; HewittPriceCheck/1.0; personal price comparison; +https://andyhewitt35-cmyk.github.io/uk-food-prices/)"
NOW = datetime.now(timezone.utc)


def get(url, timeout=40, tries=2):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-GB,en;q=0.9"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa
            last = e
            time.sleep(3)
    raise last


def tidy(t):
    return re.sub(r"\s+", " ", (t or "").replace("’", "'")).strip()


def title_brand(b):
    t = " ".join(w.capitalize() if not w.isdigit() else w for w in b.lower().split())
    return re.sub(r"'S\b", "'s", t)


# ---------- size and unit price ----------
def parse_size(*texts, prefer_count=False):
    """Return (qty, base) with base in g / ml / each, or (None, None).
    Weight/volume wins over a pack count (tea: "40PK" + "125g") unless prefer_count (eggs)."""
    texts = [t.lower().replace(",", ".") for t in texts if t]

    def weight(s):
        m = re.search(r"(\d+)\s*[x×]\s*(\d+(?:\.\d+)?)\s*(kg|g|ml|l|ltr|litre)\b", s)
        if m:
            return to_base(int(m.group(1)) * float(m.group(2)), m.group(3))
        m = re.search(r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l|ltr|ltrs|litres?)\b", s)
        if m:
            return to_base(float(m.group(1)), m.group(2))
        m = re.search(r"(\d+)\s*pints?\b", s)
        if m:
            return round(int(m.group(1)) * 568.261), "ml"
        return None

    def count(s):
        m = re.search(r"(?:\bx\s*(\d+)\b|(\d+)\s*(?:pk|pack|each|bags|tea bags|s\b|'s\b)|^(\d+)\s+\w)", s)
        if m:
            n = int(m.group(1) or m.group(2) or m.group(3))
            return (n, "each") if 0 < n < 1000 else None
        return None

    order = (count, weight) if prefer_count else (weight, count)
    for fn in order:
        for t in texts:
            r = fn(t)
            if r:
                return r
    return None, None


def to_base(q, u):
    if u == "kg":
        return round(q * 1000), "g"
    if u == "g":
        return round(q), "g"
    if u in ("l", "ltr", "ltrs", "litre", "litres"):
        return round(q * 1000), "ml"
    return round(q), "ml"


def size_label(q, b):
    if not q:
        return ""
    if b == "g":
        return f"{q/1000:g}kg" if q >= 1000 else f"{q}g"
    if b == "ml":
        for pints in (1, 2, 4, 6, 8):
            if abs(q - pints * 568.261) < 6:
                return f"{pints} pint{'s' if pints > 1 else ''}"
        return f"{q/1000:g}L" if q >= 1000 else f"{q}ml"
    return f"{q} pack"


def unit_from_retailer(up):
    """Retailer unit price -> (value, unit) with unit in kg / l / each."""
    if not up or up.get("value") in (None, 0):
        return None, None
    v, m = float(up["value"]), (up.get("measure") or "").lower()
    if m in ("kg",):
        return v, "kg"
    if m in ("100g",):
        return v * 10, "kg"
    if m in ("10g",):
        return v * 100, "kg"
    if m in ("l", "litre", "ltr"):
        return v, "l"
    if m in ("100ml",):
        return v * 10, "l"
    if m in ("75cl",):
        return v / 0.75, "l"
    if m in ("each", "ea", "unit", "100sht"):
        return v, "each"
    return None, None


def unit_price(price, q, b, retailer_up):
    """Prefer our own figure from price and pack size (same maths for every shop)."""
    if price and q:
        if b == "g":
            return round(price / q * 1000, 2), "kg"
        if b == "ml":
            return round(price / q * 1000, 2), "l"
        if b == "each" and q > 1:
            return round(price / q, 3), "each"
    v, u = unit_from_retailer(retailer_up)
    if v is not None:
        return round(v, 2), u
    if price and q and b == "each":
        return round(price / q, 3), "each"
    return None, None


# ---------- staples ----------
STAPLES = [
    ("Milk", r"\bmilk\b", r"chocolate|milkshake|yogh|powder|coconut|oat |almond|soya|biscuit"),
    ("Bread", r"\bbread\b|bloomer|toastie|\bloaf\b", r"rolls|thins|pitta|sauce|crumbs"),
    ("Eggs", r"\beggs?\b", r"scotch|boiled|pickled|choc"),
    ("Butter", r"\bbutter\b", r"peanut|prawn|chicken|biscuit|spreadable"),
    ("Cheddar", r"cheddar", r"sauce|dip|slices|lasagne|macaroni|bake|plant"),
    ("Chicken breast", r"chicken breast", r"roast|ready to eat"),
    ("Bananas", r"banana", r"milk|loaf|cake"),
    ("Apples", r"\bapples?\b", r"juice|slices|sauce"),
    ("Potatoes", r"potato", r"roast|dauphinoise|wedges|chips|waffle"),
    ("Onions", r"onions?\b", r"pickled|rings|sliced|salad onions|silverskin"),
    ("Tomatoes", r"tomato", r"chopped|peeled|sauce|soup|puree|ketchup|beans|juice"),
    ("Pasta", r"pasta|fusilli|penne|spaghetti|macaroni|rigatoni|farfalle", r"sauce|bake|bolognese|cheese"),
    ("Rice", r"\brice\b", r"pudding|cakes|milk"),
    ("Baked beans", r"baked beans|beanz|\bbeans\b", r"sausage|cheese|green|kidney|butter"),
    ("Cereal", r"corn ?flakes|weetabix|wheat biscuits|cereal|bran flakes|cheerios|shreddies", r"bar"),
    ("Coffee", r"coffee|nescaf|americano", r"creamer|syrup"),
    ("Tea bags", r"tea\b|tea bags", r"herbal|green|camomile|peppermint|fruit|chai|iced|rooibos|sleep|immune"),
    ("Sugar", r"sugar\b", r"free|icing|brown|caster|demerara|sweetener|strands"),
    ("Orange juice", r"orange juice|orange fruit juice|orange.*juice", r"drink|mango|apple|cranberry"),
    ("Olive oil", r"olive oil", r"anchov|sardine|tuna|chicken|pickle|spray"),
]


def staple_of(name):
    n = name.lower()
    for label, inc, exc in STAPLES:
        if re.search(inc, n) and not re.search(exc, n):
            return label
    return ""


OWN_LABEL = {
    "tesco": ["tesco", "hearty food co", "grower's harvest", "growers harvest", "rosedene farms", "creamfields",
              "stockwell", "redmere", "nightingale", "boswell", "willow farms", "eastman", "finest", "h w nevill"],
    "sainsburys": ["sainsbury", "stamford street", "taste the difference", "by sainsbury"],
    "asda": ["asda", "just essentials", "exceptional by asda", "garden gang"],
    "aldi": ["everyday essentials", "nature's pick", "merevale", "cowbelle", "emporium", "village bakery", "cucina",
             "the pantry", "solesta", "barissimo", "harvest morn", "worldwide foods", "the juice company",
             "specially selected", "bramwells", "ashfields", "brooklea", "ashfield", "corale", "dairyfine"],
    "morrisons": ["morrisons", "the best", "savers"],
}


def is_own_label(shop, brand, name):
    t = f"{brand or ''} {name or ''}".lower()
    return any(k in t for k in OWN_LABEL.get(shop, []))


def norm_brand(b):
    b = (b or "").lower().replace("’", "'").strip()
    b = re.sub(r"[^a-z0-9' ]", "", b)
    b = {"kelloggs": "kellogg's", "nescafe": "nescafe", "yorkshire": "yorkshire tea", "taylors of harrogate": "yorkshire tea",
         "grower's harvest": "growers harvest"}.get(b, b)
    return b


# ---------- sources ----------
LOYALTY = {"tesco": "Clubcard price", "sainsburys": "Nectar price", "morrisons": "More Card price"}


def from_apify():
    rows = json.loads(get(APIFY_URL, timeout=90, tries=3))
    if not rows:
        raise RuntimeError("Apify dataset empty")
    latest = max(r["scrapedAt"] for r in rows)
    cutoff = (datetime.fromisoformat(latest.replace("Z", "+00:00")) - timedelta(hours=36)).isoformat()[:19]
    best = {}
    for r in rows:
        if r.get("scrapedAt", "")[:19] < cutoff or not r.get("price"):
            continue
        k = (r["retailer"], r.get("retailerProductId") or r.get("url"))
        if k not in best or r["scrapedAt"] > best[k]["scrapedAt"]:
            best[k] = r
    out = []
    for r in best.values():
        shop = r["retailer"]
        name = tidy(r.get("name"))
        brand = tidy(r.get("brand"))
        bl = brand.lower().replace("é", "e")
        display = name if not brand or bl in name.lower().replace("é", "e") or bl.split()[0] in name.lower() else f"{title_brand(brand)} {name}"
        q, b = parse_size(r.get("packSize"), name, prefer_count=staple_of(name) == "Eggs")
        price = float(r["price"])
        up, uu = unit_price(price, q, b, r.get("unitPrice"))
        loyalty = r.get("loyaltyPrice")
        if loyalty is not None and float(loyalty) >= price:
            loyalty = None
        promo = tidy(r.get("promotionText"))
        if loyalty is not None and promo and (re.match(r"buy 1 for", promo, re.I) or f"{float(loyalty):.2f}" in promo):
            promo = ""  # same thing as the loyalty price already shown
        out.append(dict(
            s=shop, n=display, b=brand, z=size_label(q, b) or (r.get("packSize") or ""), q=q, qb=b,
            p=round(price, 2), l=round(float(loyalty), 2) if loyalty is not None else None,
            lt=LOYALTY.get(shop, "Member price") if loyalty is not None else "",
            w=round(float(r["wasPrice"]), 2) if r.get("wasPrice") else None,
            pr=promo[:90], u=up, uu=uu, url=r.get("url"),
            t=r["scrapedAt"][:19] + "Z", st=r.get("inStock"), c=staple_of(name),
            own=is_own_label(shop, brand, name), src="apify"))
    return out, latest[:19] + "Z", len(rows)


def from_morrisons(path="morrisons_products.txt", delay=float(__import__("os").environ.get("MORRISONS_DELAY", "1.5"))):
    items, fails = [], 0
    lines = [l.strip() for l in open(path) if l.strip() and not l.startswith("#")]
    for i, slug in enumerate(lines):
        pid = slug.rsplit("/", 1)[-1]
        url = MORRISONS_BASE + slug
        try:
            page = get(url, timeout=30)
            it = parse_morrisons(page, pid, url)
            if it:
                items.append(it)
            else:
                fails += 1
                print("  morrisons: no price on", slug, file=sys.stderr)
        except Exception as e:
            fails += 1
            print("  morrisons: failed", slug, e, file=sys.stderr)
            if fails >= 6 and not items:
                raise RuntimeError("Morrisons pages not reachable") from e
        time.sleep(delay)
    return items, fails


def parse_morrisons(page, pid, url):
    ld = None
    for blk in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page, re.S):
        try:
            j = json.loads(blk)
        except Exception:
            continue
        if isinstance(j, dict) and j.get("@type") == "Product":
            ld = j
            break
    i = page.find(f'"retailerProductId":"{pid}"')
    state = {}
    if i >= 0:
        chunk = page[i:i + 6000]
        m = re.search(r'"price":\{"amount":"([\d.]+)"', chunk)
        if m:
            state["price"] = float(m.group(1))
        m = re.search(r'"unitPrice":\{"price":\{"amount":"([\d.]+)","currency":"GBP"\},"unit":"([^"]+)"', chunk)
        if m:
            state["unit"] = (float(m.group(1)), m.group(2))
        m = re.search(r'"available":(true|false)', chunk)
        if m:
            state["available"] = m.group(1) == "true"
        m = re.search(r'"name":"([^"]+)"', chunk)
        if m:
            state["name"] = m.group(1)
        m = re.search(r'"brand":"([^"]*)"', chunk)
        if m:
            state["brand"] = m.group(1)
        m = re.search(r'"packSizeDescription":"([^"]*)"', chunk)
        if m:
            state["size"] = m.group(1)
        pm = re.search(r'"promotions":\[(.*?)\],"taxCodes', chunk, re.S)
        state["promos"] = re.findall(r'"description":"([^"]+)"', pm.group(1)) if pm else []
        pp = re.search(r'"promoPrice":\{"amount":"([\d.]+)"', chunk)
        if pp:
            state["promoPrice"] = float(pp.group(1))
    price = state.get("price")
    if price is None and ld:
        try:
            price = float(ld["offers"]["price"])
        except Exception:
            price = None
    if not price:
        return None
    name = tidy(html.unescape(state.get("name") or (ld or {}).get("name") or "").replace("\\u0026", "&"))
    brand = html.unescape(state.get("brand") or (ld or {}).get("brand") or "")
    size_txt = state.get("size") or (ld or {}).get("size") or ""
    q, b = parse_size(size_txt, name, prefer_count=staple_of(name) == "Eggs")
    up = None
    if "unit" in state:
        v, uname = state["unit"]
        mm = uname.replace("fop.price.per.", "")
        up = {"value": v, "measure": {"kg": "kg", "100g": "100g", "litre": "l", "l": "l", "100ml": "100ml", "each": "each"}.get(mm, mm)}
    loyalty, promo, was = None, "", None
    promos = [html.unescape(d).replace("\\u002F", "/") for d in state.get("promos", [])]
    promos = [d for d in promos if d.strip().lower() not in ("unbeatable price",)]
    pp = state.get("promoPrice")
    if pp and pp < price:
        if any(re.search(r"more card", d, re.I) for d in promos):
            loyalty = pp            # single-item price for More Card holders only
        else:
            was, price = price, pp  # offer price everyone pays ("Now £x, Was £y")
    promo = promos[0] if promos else ""
    u, uu = unit_price(price, q, b, up if not was else None)
    avail = state.get("available")
    if avail is None and ld:
        avail = "InStock" in str((ld.get("offers") or {}).get("availability", ""))
    return dict(s="morrisons", n=name, b=brand, z=size_label(q, b) or size_txt, q=q, qb=b, p=round(price, 2),
                l=loyalty, lt="More Card price" if loyalty else "", w=was, pr=promo[:90], u=u, uu=uu,
                url=url, t=NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), st=avail, c=staple_of(name),
                own=is_own_label("morrisons", brand, name), src="morrisons")


def previous():
    try:
        return json.loads(get(LIVE_URL, timeout=30))
    except Exception:
        return None


VARIANT = {"semi", "skimmed", "whole", "salted", "unsalted", "decaf", "intense", "organic", "reduced", "wholemeal",
           "brown", "thick", "seeded", "virgin", "light", "lighter", "mild", "mature", "extra", "bits", "large", "medium",
           "small", "gold", "azera", "original", "spreadable", "lactose", "added", "sugar", "salt", "red", "white"}


def group_same_products(items):
    """Same branded product at 2+ shops: brand + size + main words."""
    stop = {"the", "in", "a", "of", "and", "with", "&", "for", "pack", "x", "fresh", "british", "breakfast", "cereal", "fresher", "longer", "rich", "sliced", "soft", "pure", "irish", "block"}

    def words(it):
        n = it["n"].lower().replace("'", "")
        n = re.sub(r"\d+(\.\d+)?\s*(x\s*\d+)?\s*(kg|g|ml|l|ltr|pints?|pk|pack|s)?\b", " ", n)
        bw = set(re.findall(r"[a-z]+", norm_brand(it["b"])))
        return {w for w in re.findall(r"[a-z]+", n) if w not in stop and w not in bw and len(w) > 2}

    for it in items:
        it["g"] = None
    branded = [it for it in items if not it["own"] and it["q"] and it["b"]]
    gid = 0
    for i, a in enumerate(branded):
        if a["g"] is not None:
            continue
        members = [a]
        wa = words(a)
        for bb in branded[i + 1:]:
            if bb["g"] is not None or bb["s"] in {m["s"] for m in members}:
                continue
            if norm_brand(a["b"]) != norm_brand(bb["b"]) or a["qb"] != bb["qb"] or a["c"] != bb["c"]:
                continue
            if abs(a["q"] - bb["q"]) > max(5, 0.02 * a["q"]):
                continue
            wb = words(bb)
            if (wa & VARIANT) != (wb & VARIANT):
                continue
            if wa and wb and len(wa & wb) / len(wa | wb) >= 0.5:
                members.append(bb)
        if len(members) > 1:
            gid += 1
            for m in members:
                m["g"] = gid
    return gid


def main():
    prev = previous()
    prev_items = (prev or {}).get("items", [])
    status = {}
    items = []
    try:
        a, latest, nrows = from_apify()
        items += a
        status["apify"] = dict(ok=True, latest=latest, items=len(a))
        print(f"Apify: {len(a)} products, latest {latest}")
    except Exception as e:
        old = [x for x in prev_items if x.get("src") == "apify"]
        items += old
        status["apify"] = dict(ok=False, error=str(e)[:200], items=len(old), latest=(prev or {}).get("sources", {}).get("apify", {}).get("latest"))
        print("Apify FAILED:", e, "- kept", len(old), "old items", file=sys.stderr)
    try:
        m, fails = from_morrisons()
        if not m:
            raise RuntimeError("no Morrisons prices parsed")
        items += m
        status["morrisons"] = dict(ok=True, latest=NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), items=len(m), failed=fails)
        print(f"Morrisons: {len(m)} products ({fails} not available)")
    except Exception as e:
        old = [x for x in prev_items if x.get("src") == "morrisons"]
        items += old
        status["morrisons"] = dict(ok=False, error=str(e)[:200], items=len(old), latest=(prev or {}).get("sources", {}).get("morrisons", {}).get("latest"))
        print("Morrisons FAILED:", e, "- kept", len(old), "old items", file=sys.stderr)
    if not items:
        sys.exit("No data at all - not publishing an empty page")
    groups = group_same_products(items)
    data = dict(built=NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), sources=status, groups=groups, items=items)
    with open("site/data.json", "w") as f:
        json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
    print(f"Wrote site/data.json: {len(items)} items, {groups} same-product groups")


if __name__ == "__main__":
    main()
