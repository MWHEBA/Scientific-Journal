from django.urls import path
from apps.pages.views import (
    HomeView,
    ArticleListView,
    ArticleDetailView,
    CurrentIssueView,
    ArchiveView,
    SearchView,
    SectionArticlesView,
    StaticPageView,
    article_views_api,
)

app_name = 'pages'

urlpatterns = [
    # الصفحة الرئيسية
    path('', HomeView.as_view(), name='home'),

    # المقالات
    path('articles/',              ArticleListView.as_view(),   name='article_list'),
    path('articles/<int:pk>/',     ArticleDetailView.as_view(), name='article_detail'),
    path('articles/<int:pk>/views/', article_views_api,          name='article_views'),

    # العدد الحالي والأرشيف
    path('current-issue/',         CurrentIssueView.as_view(),  name='current_issue'),
    path('archive/',               ArchiveView.as_view(),       name='archive'),

    # البحث والأقسام
    path('search/',                SearchView.as_view(),        name='search'),
    path('section/<slug:slug>/',   SectionArticlesView.as_view(), name='section_articles'),

    # الصفحات الثابتة
    path('about/',              StaticPageView.as_view(), kwargs={'slug': 'about'},             name='about'),
    path('aims-scope/',         StaticPageView.as_view(), kwargs={'slug': 'aims-scope'},        name='aims_scope'),
    path('editorial-board/',    StaticPageView.as_view(), kwargs={'slug': 'editorial-board'},   name='editorial_board'),
    path('review-process/',     StaticPageView.as_view(), kwargs={'slug': 'review-process'},    name='review_process'),
    path('ethics/',             StaticPageView.as_view(), kwargs={'slug': 'ethics'},            name='ethics'),
    path('author-guidelines/',  StaticPageView.as_view(), kwargs={'slug': 'author-guidelines'}, name='author_guidelines'),
    path('apc/',                StaticPageView.as_view(), kwargs={'slug': 'apc'},               name='apc'),
    path('contact/',            StaticPageView.as_view(), kwargs={'slug': 'contact'},           name='contact'),
    path('topics/',             StaticPageView.as_view(), kwargs={'slug': 'topics'},            name='topics'),
    path('blog/',               StaticPageView.as_view(), kwargs={'slug': 'blog'},              name='blog'),
    path('conferences/',        StaticPageView.as_view(), kwargs={'slug': 'conferences'},       name='conferences'),
]
