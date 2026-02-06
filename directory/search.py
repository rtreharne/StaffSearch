from django.db.models import F, FloatField
from django.db.models.functions import Cast
from django.contrib.postgres.search import SearchQuery, SearchRank
from pgvector.django import CosineDistance

from .models import Chunk
from .openai_client import OpenAIClient


def hybrid_search(query_text, filters=None, limit=20, offset=0):
    if not query_text:
        return []

    client = OpenAIClient()
    query_embedding = client.embed_texts([query_text])[0]

    filters = filters or {}
    qs = Chunk.objects.select_related("staff", "staff__faculty", "staff__institute", "staff__department")

    if filters.get("faculty"):
        qs = qs.filter(staff__faculty__name__iexact=filters["faculty"])
    if filters.get("institute"):
        qs = qs.filter(staff__institute__name__iexact=filters["institute"])
    if filters.get("department"):
        qs = qs.filter(staff__department__name__iexact=filters["department"])

    search_query = SearchQuery(query_text)
    qs = qs.annotate(
        rank=SearchRank(F("tsv"), search_query),
        distance=CosineDistance("embedding", query_embedding),
    )

    qs = qs.annotate(
        vector_score=1.0 / (1.0 + Cast(F("distance"), FloatField())),
        text_score=F("rank") / (1.0 + F("rank")),
    )

    qs = qs.annotate(score=0.6 * F("vector_score") + 0.4 * F("text_score"))

    candidates = list(qs.order_by("-score")[:200])
    seen = set()
    results = []
    for chunk in candidates:
        staff_id = chunk.staff_id
        if staff_id in seen:
            continue
        seen.add(staff_id)
        results.append(chunk)
        if len(results) >= (offset + limit):
            break

    if offset:
        return results[offset:offset + limit]
    return results[:limit]
