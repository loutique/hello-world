from django.contrib import admin
from django.urls import path
from registrations.views import register, health, campaign_preview_image
urlpatterns = [path("r/<slug:slug>/preview/<slug:version>/", campaign_preview_image, name="campaign_preview_image"), path("health/", health, name="health"), path("admin/", admin.site.urls), path("r/<slug:slug>/", register, name="register")]
