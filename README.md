# StaffSearch

StaffSearch is a lightweight staff directory tool for the University of Liverpool. It crawls staff profile pages, extracts structured fields, and powers a search + chat experience over the content.

**How it works**
1. The crawler starts from seed URLs and follows links within `liverpool.ac.uk`.
2. Staff profiles are detected by the `/people/<slug>` pattern.
3. Content is stored in `StaffProfile`, chunked, embedded, and used for search + chat results.

**Best ways to use it**
- Use the search box and filters to find people by name, department, or keywords.
- Ask chat for short summaries and follow the returned profile links.
- Use “Add Staff Profile” to seed a specific profile URL.

## Quickstart

1. Create env file:
```bash
cp .env.example .env
```

2. Build and start:
```bash
docker compose up --build
```

3. Run migrations:
```bash
docker compose exec web python manage.py migrate
```

4. Start a crawl:
```bash
docker compose exec web python manage.py shell -c "from directory.tasks import run_weekly_crawl; run_weekly_crawl.delay()"
```

5. Open:
- `http://localhost:8000`

## Notes
- Crawling ignores `robots.txt` per explicit permission.
- Seed URL defaults to `https://liverpool.ac.uk/` (configurable in `.env`).
- Staff pages are identified by `/people/<staff-name>`.
