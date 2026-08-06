#!/usr/bin/env bash
# Git scraping dell'archivio di una newsletter Substack.
#
# Substack sfida con Cloudflare tutte le richieste dagli IP datacenter (403
# cf-mitigated: challenge), quindi si passa da r.jina.ai. Reader converte in
# markdown HTML e XML, ma lascia intatto application/json: si legge quindi
# l'API /api/v1/archive, non il feed RSS.
#
# Uso: fetch_substack.sh <subdomain> [file-di-output]
# Env: JINA_API_KEY (facoltativa: senza, rate limit più basso)

set -euo pipefail

SUB="${1:?uso: fetch_substack.sh <subdomain> [output.json]}"
OUT="${2:-data/substack/${SUB}.json}"
PAGE_SIZE=50
MAX_PAGES=20

auth=()
[[ -n "${JINA_API_KEY:-}" ]] && auth=(-H "Authorization: Bearer ${JINA_API_KEY}")

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

offset=0
page=0
: > "$tmp/all.ndjson"

while (( page < MAX_PAGES )); do
  target="https://${SUB}.substack.com/api/v1/archive?sort=new&limit=${PAGE_SIZE}&offset=${offset}"

  # Senza API key si condivide il rate limit gratuito: un 429 occasionale è
  # normale e non merita una run rossa.
  for attempt in 1 2 3; do
    http=$(curl -sS --max-time 90 -o "$tmp/resp.json" -w '%{http_code}' \
      -H "Accept: application/json" -H "X-No-Cache: true" "${auth[@]}" \
      "https://r.jina.ai/${target}")
    [[ "$http" == "200" ]] && break
    [[ "$http" == "429" || "$http" -ge 500 ]] || break
    echo "HTTP $http, riprovo tra $(( attempt * 15 ))s" >&2
    sleep $(( attempt * 15 ))
  done

  if [[ "$http" != "200" ]]; then
    echo "r.jina.ai ha risposto HTTP $http (offset $offset)" >&2
    head -c 300 "$tmp/resp.json" >&2; echo >&2
    exit 1
  fi

  # Reader incapsula la risposta dell'origine in .data.content: per un endpoint
  # JSON quel campo è il JSON originale, byte per byte.
  if ! jq -e '.data.content' "$tmp/resp.json" > /dev/null; then
    echo "Risposta Reader inattesa (offset $offset)" >&2
    head -c 300 "$tmp/resp.json" >&2; echo >&2
    exit 1
  fi

  jq -r '.data.content' "$tmp/resp.json" > "$tmp/page.json"

  if ! jq -e 'type == "array"' "$tmp/page.json" > /dev/null 2>&1; then
    echo "Il contenuto non è un array JSON — probabile challenge o pagina di errore:" >&2
    head -c 300 "$tmp/page.json" >&2; echo >&2
    exit 1
  fi

  n=$(jq 'length' "$tmp/page.json")
  echo "offset ${offset}: ${n} post"
  (( n == 0 )) && break

  jq -c '.[]' "$tmp/page.json" >> "$tmp/all.ndjson"

  (( n < PAGE_SIZE )) && break
  offset=$(( offset + PAGE_SIZE ))
  page=$(( page + 1 ))
  sleep 2   # gentile con il rate limit di Reader
done

mkdir -p "$(dirname "$OUT")"

# Solo i campi stabili e leggibili: body_html e affini renderebbero il diff
# illeggibile, che è tutto il punto del git scraping.
jq -s 'map({
    id, title, subtitle, description,
    slug, url: .canonical_url,
    post_date, audience, type,
    section: .section_name,
    wordcount, reaction_count, comment_count,
    authors: [.publishedBylines[]?.name],
    tags: [.postTags[]?.name],
    cover_image
  })
  | sort_by(.post_date) | reverse' "$tmp/all.ndjson" > "$OUT"

echo "Scritti $(jq 'length' "$OUT") post in $OUT"
