# Hacker News scraper contract

SCRAPER_STUDIO_COLLECTOR_ID=c_hn_digest_factory
HACKER_NEWS_URL=https://news.ycombinator.com
HACKER_NEWS_SCRAPER_USAGE="bdata scraper run $SCRAPER_STUDIO_COLLECTOR_ID https://news.ycombinator.com --pretty"

Extract top stories: title, url, points, author, comment_count.

Job posts and Ask HN rows stay in the feed. Missing points on a hiring thread is not a failure.

When the site breaks:

1. `factory break` (demo) or watch a real scrape fail
2. `factory heal` — same Collector ID, no `--auto-approve`
3. Human `factory approve` (or `factory reject`)
4. `factory run` again with this same `c_*` id

Never point `bdata scraper run -o` at `data/latest.json`.
