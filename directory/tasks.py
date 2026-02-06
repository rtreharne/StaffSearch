import re
import time
from urllib.parse import urlparse
from datetime import datetime, timezone

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.contrib.postgres.search import SearchVector

from .crawler import (
    normalize_url,
    is_allowed,
    is_staff_profile_path,
    should_skip_url,
    extract_links,
    extract_text_content,
    extract_staff_fields,
    fetch_url,
)
from .models import CrawlUrl, StaffProfile, Chunk, SeedUrl, CrawlControl, Faculty, Institute, Department
from .openai_client import OpenAIClient
from .utils import chunk_text, hash_text


KEEP_PATH_REGEX = re.compile(settings.CRAWL_KEEP_PATH_REGEX)


def enqueue_url(url, depth, priority=0):
    url = normalize_url(url)
    if not is_allowed(url, settings.CRAWL_ALLOWLIST_DOMAIN):
        return
    if should_skip_url(url):
        return
    CrawlUrl.objects.get_or_create(url=url, defaults={"depth": depth, "status": "queued", "priority": priority})


def enqueue_staff_url(url, depth, priority=0):
    url = normalize_url(url)
    if not is_allowed(url, settings.CRAWL_ALLOWLIST_DOMAIN):
        return
    CrawlUrl.objects.get_or_create(url=url, defaults={"depth": depth, "status": "queued", "priority": priority})


def enqueue_seed():
    control = CrawlControl.objects.first()
    if control and control.is_paused:
        return
    seed_urls = list(SeedUrl.objects.filter(active=True).order_by("-priority").values_list("url", "priority"))
    for seed, priority in seed_urls:
        enqueue_url(seed, 0, priority=priority)
    for seed in settings.CRAWL_SEED_URLS:
        enqueue_url(seed, 0, priority=10)
    enqueue_url(settings.CRAWL_SEED_URL, 0, priority=0)


@shared_task
def run_weekly_crawl():
    control = CrawlControl.objects.first()
    if control and control.is_paused:
        return
    CrawlUrl.objects.filter(status="staff_queued").update(status="queued")
    enqueue_seed()
    for _ in range(settings.CRAWL_CONCURRENCY):
        crawl_step.delay()


@shared_task
def crawl_step():
    control = CrawlControl.objects.first()
    if control and control.is_paused:
        return
    with transaction.atomic():
        url_obj = (
            CrawlUrl.objects.select_for_update(skip_locked=True)
            .filter(status="queued")
            .order_by("-priority", "id")
            .first()
        )
        if not url_obj:
            return
        url_obj.status = "fetched"
        url_obj.save(update_fields=["status"])

    try:
        time.sleep(settings.CRAWL_RATE_LIMIT)
        response = fetch_url(url_obj.url, etag=url_obj.etag, last_modified=url_obj.last_modified)
        url_obj.http_status = response.status_code
        url_obj.last_fetched_at = datetime.now(timezone.utc)

        if response.status_code == 304:
            url_obj.status = "skipped"
            url_obj.save(update_fields=["http_status", "last_fetched_at", "status"])
            return

        if response.status_code != 200:
            url_obj.status = "error"
            url_obj.save(update_fields=["http_status", "last_fetched_at", "status"])
            return

        html = response.text
        url_obj.etag = response.headers.get("ETag", "")
        url_obj.last_modified = response.headers.get("Last-Modified", "")

        parsed_path = urlparse(url_obj.url).path or ""
        if is_staff_profile_path(parsed_path, KEEP_PATH_REGEX):
            process_staff_page.delay(url_obj.url, html)

        links = extract_links(html, url_obj.url)
        if url_obj.depth < settings.CRAWL_MAX_DEPTH:
            for link in links:
                if is_allowed(link, settings.CRAWL_ALLOWLIST_DOMAIN):
                    link_path = urlparse(link).path or ""
                    if is_staff_profile_path(link_path, KEEP_PATH_REGEX):
                        enqueue_staff_url(link, url_obj.depth + 1, priority=url_obj.priority + 5)
                    else:
                        enqueue_url(link, url_obj.depth + 1)

        url_obj.status = "fetched"
        url_obj.save(update_fields=["http_status", "etag", "last_modified", "last_fetched_at", "status"])
    except Exception as exc:
        url_obj.status = "error"
        url_obj.error = str(exc)
        url_obj.save(update_fields=["status", "error"])
    finally:
        control = CrawlControl.objects.first()
        if control and control.is_paused:
            return
        if CrawlUrl.objects.filter(status="queued").exists():
            crawl_step.delay()


@shared_task
def process_staff_page(url, html):
    url = normalize_url(url)
    text_content = extract_text_content(html)
    content_hash = hash_text(text_content)

    fields = extract_staff_fields(html, base_url=url)

    staff, created = StaffProfile.objects.get_or_create(profile_url=url)

    # Fetch and append tabbed content pages (e.g., /research#tabbed-content)
    try:
        links = extract_links(html, url)
        tabbed_links = []
        for link in links:
            if "#tabbed-content" in link:
                tabbed_links.append(link.split("#", 1)[0])
        tabbed_links = list(dict.fromkeys(tabbed_links))

        extra_texts = []
        extra_html = []
        for link in tabbed_links:
            if not is_allowed(link, settings.CRAWL_ALLOWLIST_DOMAIN):
                continue
            time.sleep(settings.CRAWL_RATE_LIMIT)
            resp = fetch_url(link)
            if resp.status_code != 200:
                continue
            extra_html.append(resp.text)
            extra_texts.append(extract_text_content(resp.text))

        if extra_texts:
            text_content = text_content + "\n\n" + "\n\n".join(extra_texts)
            html = html + "\n\n" + "\n\n".join(extra_html)
    except Exception:
        pass

    content_hash = hash_text(text_content)
    if not created and staff.content_hash == content_hash:
        return

    faculty_name = (fields.get("faculty", "") or "").strip()
    institute_name = (fields.get("institute", "") or "").strip()
    department_name = (fields.get("department", "") or "").strip()

    faculty = None
    institute = None
    department = None

    if faculty_name:
        faculty, _ = Faculty.objects.get_or_create(name=faculty_name)
    if institute_name:
        institute, _ = Institute.objects.get_or_create(
            name=institute_name,
            defaults={"faculty": faculty},
        )
        if faculty and institute.faculty_id != faculty.id:
            institute.faculty = faculty
            institute.save(update_fields=["faculty"])
    if department_name:
        department, _ = Department.objects.get_or_create(
            name=department_name,
            defaults={"institute": institute},
        )
        if institute and department.institute_id != institute.id:
            department.institute = institute
            department.save(update_fields=["institute"])

    staff.name = fields.get("name", "")
    staff.title = fields.get("title", "")
    staff.suffix = fields.get("suffix", "")
    staff.faculty = faculty
    staff.institute = institute
    staff.department = department
    staff.faculty_text = faculty_name
    staff.institute_text = institute_name
    staff.department_text = department_name
    staff.text_content = text_content
    staff.raw_html = html
    staff.content_hash = content_hash
    staff.save()

    embed_staff_profile.delay(staff.id)


@shared_task
def embed_staff_profile(staff_id):
    staff = StaffProfile.objects.get(id=staff_id)
    chunks = chunk_text(staff.text_content, max_tokens=800, overlap=200)
    if not chunks:
        return

    client = OpenAIClient()
    embeddings = client.embed_texts(chunks)

    Chunk.objects.filter(staff=staff).delete()

    chunk_objs = []
    for idx, chunk in enumerate(chunks):
        chunk_objs.append(
            Chunk(
                staff=staff,
                chunk_index=idx,
                chunk_text=chunk,
                embedding=embeddings[idx],
            )
        )

    Chunk.objects.bulk_create(chunk_objs, batch_size=100)

    Chunk.objects.filter(staff=staff).update(tsv=SearchVector("chunk_text"))


@shared_task
def fetch_and_process_profile(url):
    time.sleep(settings.CRAWL_RATE_LIMIT)
    response = fetch_url(url)
    if response.status_code != 200:
        return
    process_staff_page.delay(url, response.text)
