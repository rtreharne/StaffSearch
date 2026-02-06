from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("embed/", views.embed, name="embed"),
    path("admin-dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("admin-dashboard/run-crawl/", views.admin_run_crawl, name="admin_run_crawl"),
    path("admin-dashboard/seeds/add/", views.admin_seed_add, name="admin_seed_add"),
    path("admin-dashboard/seeds/delete/", views.admin_seed_delete, name="admin_seed_delete"),
    path("admin-dashboard/seeds/toggle/", views.admin_seed_toggle, name="admin_seed_toggle"),
    path("admin-dashboard/crawl/pause/", views.admin_crawl_pause, name="admin_crawl_pause"),
    path("admin-dashboard/crawl/resume/", views.admin_crawl_resume, name="admin_crawl_resume"),
    path("admin-dashboard/profile/add/", views.admin_profile_add, name="admin_profile_add"),
    path("api/filters/", views.api_filters, name="api_filters"),
    path("api/search/", views.api_search, name="api_search"),
    path("api/department/", views.api_department_staff, name="api_department_staff"),
    path("api/chat/", views.api_chat, name="api_chat"),
]
