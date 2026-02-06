from django.contrib import admin
from .models import StaffProfile, Chunk, CrawlUrl, Faculty, Institute, Department


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "title", "faculty", "institute", "department", "updated_at")
    search_fields = ("name", "faculty__name", "institute__name", "department__name")


@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(Institute)
class InstituteAdmin(admin.ModelAdmin):
    search_fields = ("name", "faculty__name")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    search_fields = ("name", "institute__name")


@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
    list_display = ("staff", "chunk_index", "created_at")
    search_fields = ("staff__name",)


@admin.register(CrawlUrl)
class CrawlUrlAdmin(admin.ModelAdmin):
    list_display = ("url", "status", "depth", "http_status", "last_fetched_at")
    search_fields = ("url",)
