const ICS_URL =
  "https://ec.europa.eu/eurostat/o/calendars/eventsIcal?theme=0&category=1";

const VALID_THEMES = [
  "economy",
  "agriculture",
  "transport",
  "environment",
  "industry",
  "population",
  "international",
  "science",
];

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const theme = url.searchParams.get("theme")?.toLowerCase() ?? null;

    if (theme && !VALID_THEMES.includes(theme)) {
      return new Response(
        `Invalid theme. Valid values: ${VALID_THEMES.join(", ")}`,
        { status: 400 }
      );
    }

    const icsText = await fetch(ICS_URL).then((r) => r.text());
    const events = parseICS(icsText);

    const today = new Date().toISOString().slice(0, 10);

    const filtered = events
      .filter((e) => e.categories.includes("Data release"))
      .filter((e) => e.date <= today)
      .filter((e) => !theme || e.theme === theme)
      .sort((a, b) => b.date.localeCompare(a.date))
      .slice(0, 10);

    const rss = buildRSS(filtered, theme);

    return new Response(rss, {
      headers: {
        "Content-Type": "application/rss+xml; charset=utf-8",
        "Cache-Control": "public, max-age=3600",
      },
    });
  },
};

function parseICS(text) {
  const events = [];
  const blocks = text.split("BEGIN:VEVENT").slice(1);

  for (const block of blocks) {
    const get = (field) => {
      const match = block.match(new RegExp(`^${field}[^:]*:(.+)$`, "m"));
      return match ? match[1].trim() : "";
    };

    const dateRaw = get("DTSTART");
    const date = dateRaw.replace(
      /^(\d{4})(\d{2})(\d{2})$/,
      "$1-$2-$3"
    );

    const categoriesRaw = get("X-CATEGORY");
    const categories = categoriesRaw
      .split("\\,")
      .map((c) => c.trim());

    events.push({
      uid: get("UID"),
      summary: get("SUMMARY"),
      date,
      theme: get("X-THEME"),
      categories,
    });
  }

  return events;
}

function buildRSS(events, theme) {
  const themeLabel = theme ? ` — ${theme}` : "";
  const items = events
    .map((e) => {
      const pubDate = new Date(e.date).toUTCString();
      return `
    <item>
      <title>${escapeXML(e.summary)}</title>
      <pubDate>${pubDate}</pubDate>
      <category>${escapeXML(e.theme)}</category>
      <guid isPermaLink="false">${escapeXML(e.uid)}</guid>
    </item>`;
    })
    .join("");

  return `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Eurostat Data Releases${escapeXML(themeLabel)}</title>
    <link>https://ec.europa.eu/eurostat/en/web/main/data/data-release-calendar</link>
    <description>Eurostat statistical data releases${escapeXML(themeLabel)}</description>
    <language>en</language>
${items}
  </channel>
</rss>`;
}

function escapeXML(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}
