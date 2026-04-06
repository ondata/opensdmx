# eurostat-rss

Cloudflare Worker that converts the Eurostat data release calendar (ICS) into an RSS feed, filtered to **Data releases only**.

## Live feed

```
https://eurostat-rss.andy-pr.workers.dev/
```

Filter by theme:

```
https://eurostat-rss.andy-pr.workers.dev/?theme=economy
https://eurostat-rss.andy-pr.workers.dev/?theme=agriculture
https://eurostat-rss.andy-pr.workers.dev/?theme=transport
https://eurostat-rss.andy-pr.workers.dev/?theme=environment
https://eurostat-rss.andy-pr.workers.dev/?theme=industry
https://eurostat-rss.andy-pr.workers.dev/?theme=population
https://eurostat-rss.andy-pr.workers.dev/?theme=international
https://eurostat-rss.andy-pr.workers.dev/?theme=science
```

## Behaviour

- Fetches the Eurostat ICS calendar at runtime: `https://ec.europa.eu/eurostat/o/calendars/eventsIcal?theme=0&category=1`
- Filters events to `X-CATEGORY: Data release` only
- Excludes future releases (only events with release date ≤ today)
- Returns the **10 most recent** releases, sorted by date descending
- Optional `?theme=` parameter narrows results to a single theme (returns 400 if invalid)

## Deploy

```bash
cd scripts/eurostat-rss
wrangler deploy
```
