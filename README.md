# StaffSearch

Dockerized Django app to crawl Liverpool staff pages, embed content, and provide hybrid search + RAG chat.

## Quickstart

1. Copy env:

```bash
cp .env.example .env
```

2. Build and start:

```bash
docker compose up --build
```

3. Run migrations (in another terminal):

```bash
docker compose exec web python manage.py migrate
```

4. Kick off a crawl:

```bash
docker compose exec web python manage.py shell -c "from directory.tasks import run_weekly_crawl; run_weekly_crawl.delay()"
```

5. Open:

- `http://localhost:8000`

## Notes

- Crawling ignores `robots.txt` per explicit permission.
- Seed URL: `https://liverpool.ac.uk/` (configurable in `.env`).
- Staff pages are identified by `/people/<staff-name>`.
