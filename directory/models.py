from django.db import models
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from pgvector.django import VectorField, HnswIndex


class StaffProfile(models.Model):
    profile_url = models.URLField(unique=True)
    name = models.CharField(max_length=255, blank=True)
    title = models.CharField(max_length=64, blank=True)
    suffix = models.CharField(max_length=128, blank=True)
    faculty = models.ForeignKey("Faculty", on_delete=models.SET_NULL, null=True, blank=True)
    institute = models.ForeignKey("Institute", on_delete=models.SET_NULL, null=True, blank=True)
    department = models.ForeignKey("Department", on_delete=models.SET_NULL, null=True, blank=True)
    faculty_text = models.CharField(max_length=255, blank=True)
    institute_text = models.CharField(max_length=255, blank=True)
    department_text = models.CharField(max_length=255, blank=True)

    text_content = models.TextField(blank=True)
    raw_html = models.TextField(blank=True)

    etag = models.CharField(max_length=255, blank=True)
    last_modified = models.CharField(max_length=255, blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    last_fetched_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name or self.profile_url


class Faculty(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class Institute(models.Model):
    name = models.CharField(max_length=255, unique=True)
    faculty = models.ForeignKey(Faculty, on_delete=models.SET_NULL, null=True, blank=True, related_name="institutes")

    def __str__(self):
        return self.name


class Department(models.Model):
    name = models.CharField(max_length=255, unique=True)
    institute = models.ForeignKey(Institute, on_delete=models.SET_NULL, null=True, blank=True, related_name="departments")

    def __str__(self):
        return self.name


class Chunk(models.Model):
    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name="chunks")
    chunk_index = models.IntegerField()
    chunk_text = models.TextField()
    embedding = VectorField(dimensions=1536)
    tsv = SearchVectorField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            GinIndex(fields=["tsv"]),
            HnswIndex(fields=["embedding"], m=16, ef_construction=64, opclasses=["vector_cosine_ops"], name="chunk_embedding_hnsw"),
        ]

    def __str__(self):
        return f"{self.staff_id}:{self.chunk_index}"


class CrawlUrl(models.Model):
    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("fetched", "Fetched"),
        ("skipped", "Skipped"),
        ("error", "Error"),
    ]

    url = models.URLField(unique=True)
    depth = models.IntegerField(default=0)
    priority = models.IntegerField(default=0)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="queued")
    http_status = models.IntegerField(null=True, blank=True)
    etag = models.CharField(max_length=255, blank=True)
    last_modified = models.CharField(max_length=255, blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    last_fetched_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)

    def __str__(self):
        return self.url


class SeedUrl(models.Model):
    url = models.URLField(unique=True)
    priority = models.IntegerField(default=10)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.url


class CrawlControl(models.Model):
    is_paused = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"paused={self.is_paused}"


class SearchLog(models.Model):
    query = models.TextField(blank=True)
    filters = models.JSONField(default=dict, blank=True)
    offset = models.IntegerField(default=0)
    limit = models.IntegerField(default=0)
    results_count = models.IntegerField(default=0)
    user = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    request_meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M:%S} search"


class ChatLog(models.Model):
    question = models.TextField(blank=True)
    filters = models.JSONField(default=dict, blank=True)
    response = models.JSONField(default=dict, blank=True)
    sources = models.JSONField(default=list, blank=True)
    user = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    request_meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M:%S} chat"
