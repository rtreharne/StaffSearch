from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone
from urllib.parse import urlparse
import re
from django.conf import settings
from functools import wraps

import json

from .models import StaffProfile, CrawlUrl, Chunk, SeedUrl, CrawlControl, Faculty, Institute, Department, SearchLog, ChatLog
from .crawler import normalize_url, is_allowed, is_staff_profile_path
from .tasks import fetch_and_process_profile
from .openai_client import OpenAIClient
from .search import hybrid_search


@require_GET
def index(request):
    return render(request, "directory/index.html", {"is_embed": False, "embed_chat": True, "embed_mode": "full"})


@require_GET
def embed(request):
    mode = (request.GET.get("mode") or "full").strip().lower()
    if mode not in {"full", "search", "chat"}:
        mode = "full"
    return render(request, "directory/index.html", {"is_embed": True, "embed_chat": True, "embed_mode": mode})


def staff_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if not request.user.is_staff:
            return HttpResponseForbidden("Staff access required.")
        return view_func(request, *args, **kwargs)
    return _wrapped


@require_GET
@staff_required
def admin_dashboard(request):
    stats = {
        "staff_count": StaffProfile.objects.count(),
    }
    stats.update({
        "queued_urls": CrawlUrl.objects.filter(status="queued").count(),
        "fetched_urls": CrawlUrl.objects.filter(status="fetched").count(),
        "error_urls": CrawlUrl.objects.filter(status="error").count(),
        "total_urls": CrawlUrl.objects.count(),
        "chunk_count": Chunk.objects.count(),
    })
    queued = stats["queued_urls"]
    rate_limit = float(getattr(settings, "CRAWL_RATE_LIMIT", 1.0))
    concurrency = max(int(getattr(settings, "CRAWL_CONCURRENCY", 1)), 1)
    predicted_seconds = int((queued * rate_limit) / concurrency) if queued else 0
    stats["predicted_seconds"] = predicted_seconds
    stats["predicted_human"] = _format_duration(predicted_seconds)
    last_fetch = StaffProfile.objects.exclude(last_fetched_at=None).order_by("-last_fetched_at").values_list("last_fetched_at", flat=True).first()
    stats["last_fetch"] = last_fetch

    schedule_seconds = 60 * 60 * 24 * 7
    if last_fetch:
        stats["next_run"] = last_fetch + timezone.timedelta(seconds=schedule_seconds)
    else:
        stats["next_run"] = None

    control, _ = CrawlControl.objects.get_or_create(id=1, defaults={"is_paused": False})
    stats["is_paused"] = control.is_paused
    stats["in_progress"] = stats["queued_urls"] > 0 and not control.is_paused

    now = timezone.now()
    window_minutes = 5
    recent_fetches = CrawlUrl.objects.filter(
        last_fetched_at__gte=now - timezone.timedelta(minutes=window_minutes)
    ).count()
    stats["crawl_requests_per_min"] = round(recent_fetches / window_minutes, 2)
    stats["crawl_window_minutes"] = window_minutes
    if stats["crawl_requests_per_min"] > 0:
        minutes_left = stats["queued_urls"] / stats["crawl_requests_per_min"]
        minutes_left_int = int(round(minutes_left))
        hours, minutes = divmod(minutes_left_int, 60)
        stats["queued_eta_minutes"] = minutes_left_int
        stats["queued_eta_human"] = f"{hours}h {minutes}m" if hours else f"{minutes}m"
    else:
        stats["queued_eta_minutes"] = None
        stats["queued_eta_human"] = "—"
    recent_searches = SearchLog.objects.order_by("-created_at")[:100]
    recent_chats = ChatLog.objects.order_by("-created_at")[:20]
    search_summary = {
        "last_24h": SearchLog.objects.filter(created_at__gte=now - timezone.timedelta(days=1)).count(),
        "last_7d": SearchLog.objects.filter(created_at__gte=now - timezone.timedelta(days=7)).count(),
        "last_30d": SearchLog.objects.filter(created_at__gte=now - timezone.timedelta(days=30)).count(),
        "last_365d": SearchLog.objects.filter(created_at__gte=now - timezone.timedelta(days=365)).count(),
    }
    chat_summary = {
        "last_24h": ChatLog.objects.filter(created_at__gte=now - timezone.timedelta(days=1)).count(),
        "last_7d": ChatLog.objects.filter(created_at__gte=now - timezone.timedelta(days=7)).count(),
        "last_30d": ChatLog.objects.filter(created_at__gte=now - timezone.timedelta(days=30)).count(),
        "last_365d": ChatLog.objects.filter(created_at__gte=now - timezone.timedelta(days=365)).count(),
    }
    return render(
        request,
        "directory/admin_dashboard.html",
        {
            "stats": stats,
            "recent_searches": recent_searches,
            "recent_chats": recent_chats,
            "search_summary": search_summary,
            "chat_summary": chat_summary,
        },
    )


KEEP_PATH_REGEX = re.compile(settings.CRAWL_KEEP_PATH_REGEX)


def _format_duration(seconds):
    seconds = max(int(seconds), 0)
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {sec}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h"


@require_POST
@staff_required
def admin_run_crawl(request):
    from .tasks import run_weekly_crawl
    run_weekly_crawl.delay()
    return redirect("admin_dashboard")


@require_POST
@staff_required
def admin_seed_add(request):
    url = (request.POST.get("url") or "").strip()
    priority = int(request.POST.get("priority") or 10)
    active = request.POST.get("active") == "on"
    if url:
        SeedUrl.objects.update_or_create(url=url, defaults={"priority": priority, "active": active})
    return redirect("admin_dashboard")


@require_POST
@staff_required
def admin_seed_delete(request):
    seed_id = request.POST.get("seed_id")
    if seed_id:
        SeedUrl.objects.filter(id=seed_id).delete()
    return redirect("admin_dashboard")


@require_POST
@staff_required
def admin_seed_toggle(request):
    seed_id = request.POST.get("seed_id")
    if seed_id:
        seed = SeedUrl.objects.filter(id=seed_id).first()
        if seed:
            seed.active = not seed.active
            seed.save(update_fields=["active"])
    return redirect("admin_dashboard")


@require_POST
@staff_required
def admin_crawl_pause(request):
    control, _ = CrawlControl.objects.get_or_create(id=1, defaults={"is_paused": False})
    control.is_paused = True
    control.save(update_fields=["is_paused"])
    return redirect("admin_dashboard")


@require_POST
@staff_required
def admin_crawl_resume(request):
    control, _ = CrawlControl.objects.get_or_create(id=1, defaults={"is_paused": False})
    control.is_paused = False
    control.save(update_fields=["is_paused"])
    return redirect("admin_dashboard")


@require_POST
def admin_profile_add(request):
    url = (request.POST.get("profile_url") or "").strip()
    next_url = (request.POST.get("next") or "").strip()
    if not url:
        return redirect(next_url or "admin_dashboard")
    url = normalize_url(url)
    path = urlparse(url).path or ""
    if not is_allowed(url, settings.CRAWL_ALLOWLIST_DOMAIN):
        return redirect(next_url or "admin_dashboard")
    if not is_staff_profile_path(path, KEEP_PATH_REGEX):
        return redirect(next_url or "admin_dashboard")
    fetch_and_process_profile.delay(url)
    if next_url.startswith("/"):
        return redirect(next_url)
    return redirect("admin_dashboard")


@require_GET
def api_filters(request):
    faculty = (request.GET.get("faculty") or "").strip()
    institute = (request.GET.get("institute") or "").strip()

    faculties = list(Faculty.objects.order_by("name").values_list("name", flat=True))

    institutes_qs = Institute.objects.order_by("name")
    if faculty:
        institutes_qs = institutes_qs.filter(faculty__name__iexact=faculty)
    institutes = list(institutes_qs.values_list("name", flat=True))

    departments_qs = Department.objects.order_by("name")
    if institute:
        departments_qs = departments_qs.filter(institute__name__iexact=institute)
    elif faculty:
        departments_qs = departments_qs.filter(institute__faculty__name__iexact=faculty)
    departments = list(departments_qs.values_list("name", flat=True))

    return JsonResponse({
        "faculties": sorted(faculties),
        "institutes": sorted(institutes),
        "departments": sorted(departments),
    })


@require_GET
def api_search(request):
    query = request.GET.get("q", "").strip()
    filters = {
        "faculty": request.GET.get("faculty", "").strip(),
        "institute": request.GET.get("institute", "").strip(),
        "department": request.GET.get("department", "").strip(),
    }
    offset = max(int(request.GET.get("offset", 0) or 0), 0)
    limit = min(max(int(request.GET.get("limit", 8) or 8), 1), 50)

    chunks = hybrid_search(query, filters=filters, limit=limit, offset=offset)
    results = []
    for chunk in chunks:
        staff = chunk.staff
        results.append({
            "name": staff.name,
            "title": staff.title,
            "suffix": staff.suffix,
            "faculty": staff.faculty.name if staff.faculty else "",
            "institute": staff.institute.name if staff.institute else "",
            "department": staff.department.name if staff.department else "",
            "profile_url": staff.profile_url,
            "snippet": chunk.chunk_text[:280],
            "score": float(getattr(chunk, "score", 0.0) or 0.0),
        })

    SearchLog.objects.create(
        query=query,
        filters=filters,
        offset=offset,
        limit=limit,
        results_count=len(results),
        user=request.user if request.user.is_authenticated else None,
        ip_address=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        request_meta={
            "path": request.path,
            "query_string": request.META.get("QUERY_STRING", ""),
        },
    )

    return JsonResponse({"results": results})


@require_GET
def api_department_staff(request):
    department = (request.GET.get("department") or "").strip()
    if not department:
        return JsonResponse({"results": []})

    staff_qs = StaffProfile.objects.select_related(
        "faculty", "institute", "department"
    ).filter(
        department__name__iexact=department
    ).order_by("name", "profile_url")

    results = []
    for staff in staff_qs:
        results.append({
            "name": staff.name,
            "title": staff.title,
            "suffix": staff.suffix,
            "faculty": staff.faculty.name if staff.faculty else "",
            "institute": staff.institute.name if staff.institute else "",
            "department": staff.department.name if staff.department else "",
            "profile_url": staff.profile_url,
            "snippet": "",
            "score": 1.0,
        })

    return JsonResponse({"results": results})


@csrf_exempt
@require_POST
def api_chat(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    question = (payload.get("question") or "").strip()
    filters = payload.get("filters") or {}

    if not question:
        return JsonResponse({"error": "Question is required"}, status=400)

    chunks = hybrid_search(question, filters=filters, limit=8)
    if not chunks:
        response_payload = {"summary": "I cannot find that in the staff profiles.", "people": [], "sources": []}
        ChatLog.objects.create(
            question=question,
            filters=filters,
            response=response_payload,
            sources=[],
            user=request.user if request.user.is_authenticated else None,
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            request_meta={"path": request.path},
        )
        return JsonResponse(response_payload)

    context_blocks = []
    sources = []
    for chunk in chunks:
        staff = chunk.staff
        context_blocks.append(
            f"Name: {staff.name}\nTitle: {staff.title}\nFaculty: {staff.faculty.name if staff.faculty else ''}\n"
            f"Institute: {staff.institute.name if staff.institute else ''}\nDepartment: {staff.department.name if staff.department else ''}\n"
            f"Profile URL: {staff.profile_url}\nContent: {chunk.chunk_text}"
        )
        sources.append({
            "name": staff.name,
            "profile_url": staff.profile_url,
        })

    client = OpenAIClient()
    answer = client.chat_with_context(question, context_blocks)
    summary = (answer or {}).get("summary", "")
    people = (answer or {}).get("people", []) or []
    response_payload = {"summary": summary, "people": people, "sources": sources}
    ChatLog.objects.create(
        question=question,
        filters=filters,
        response=response_payload,
        sources=sources,
        user=request.user if request.user.is_authenticated else None,
        ip_address=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        request_meta={"path": request.path},
    )
    return JsonResponse(response_payload)
