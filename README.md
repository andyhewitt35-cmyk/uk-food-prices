# UK food prices

Personal grocery price comparison: https://andyhewitt35-cmyk.github.io/uk-food-prices/

Type an item (e.g. "Heinz beans 415g", "semi-skimmed milk 4 pint") to see prices across the supermarkets, with unit prices (per kg, per litre or each), loyalty prices shown separately, product links and the time each price was checked.

## Where the prices come from
| Shop | How | How often |
|---|---|---|
| Tesco, Sainsbury's, Asda, Aldi | Free public daily dataset from [UK Supermarket Price Scraper (Apify), yappman](https://apify.com/yappman/uk-supermarket-price-scraper), CC BY 4.0. About 210 products across 20 staples, with loyalty prices | daily, about 06:30 UK |
| Morrisons | Its public product pages (`/products/…`, allowed by robots.txt; `/api/` is not used). Fixed list in `morrisons_products.txt`, fetched slowly | twice daily |
| Lidl, Waitrose, Co-op, Iceland, Ocado | **Not checked** – no online grocery prices (Lidl), automated access blocked (Waitrose, Ocado) or search disallowed by robots.txt (Co-op, Iceland). Links to each shop's own search only | – |

No bot checks, captchas or logins are bypassed and no paid proxies are used. If a source fails, the last good prices for that shop are kept with their original dates and the page says so.

## Files
- `fetch_prices.py` – builds `site/data.json` (run by GitHub Actions at 06:10 and 17:10 UTC)
- `morrisons_products.txt` – the Morrisons products checked
- `site/` – the page (static, no tracking, `noindex`)
- `test.js` – browser test: `NODE_PATH=…/node_modules node test.js <url> live`
