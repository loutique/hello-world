from django.contrib import admin
from django.urls import path
from registrations.views import register, health
urlpatterns = [path("health/", health, name="health"), path("admin/", admin.site.urls), path("r/<slug:slug>/", register, name="register")]
