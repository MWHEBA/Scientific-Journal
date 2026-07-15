from django.contrib import admin
from .models import Review

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('id', 'submission', 'reviewer', 'decision', 'is_submitted', 'submitted_at')
    list_filter = ('decision', 'is_submitted', 'revision_round')
    search_fields = ('comments', 'reviewer__username', 'submission__title')
    date_hierarchy = 'created_at'
