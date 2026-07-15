from django.contrib import admin
from .models import Volume, Issue, PublishedArticle, PublishedArticleSlugHistory

@admin.register(Volume)
class VolumeAdmin(admin.ModelAdmin):
    list_display = ('id', 'number', 'year', 'created_at')
    list_filter = ('year',)

@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ('id', 'volume', 'number', 'quarter', 'is_current', 'published_at')
    list_filter = ('is_current', 'volume')
    list_editable = ('is_current',)

@admin.register(PublishedArticle)
class PublishedArticleAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'issue', 'section', 'published_at', 'views_count')
    list_filter = ('issue', 'section')
    search_fields = ('title', 'abstract', 'keywords')
    date_hierarchy = 'published_at'

@admin.register(PublishedArticleSlugHistory)
class PublishedArticleSlugHistoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'article', 'slug', 'created_at')
    search_fields = ('slug', 'article__title')
