from django.views.generic import TemplateView, ListView, DetailView
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.http import JsonResponse

from apps.publishing.models import PublishedArticle, PublishedArticleSlugHistory, Issue, Volume
from apps.submissions.models import JournalSection


class HomeView(TemplateView):
    template_name = 'pages/home.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['latest_articles'] = PublishedArticle.objects.select_related(
            'section', 'submission__author'
        ).order_by('-published_at')[:6]
        ctx['current_issue'] = Issue.objects.filter(
            is_current=True
        ).select_related('volume').prefetch_related('articles').first()
        from apps.pages.models import SiteSettings
        ctx['settings'] = SiteSettings.get()
        return ctx


class ArticleListView(ListView):
    model = PublishedArticle
    template_name = 'pages/article_list.html'
    context_object_name = 'articles'
    paginate_by = 12

    def get_queryset(self):
        return PublishedArticle.objects.select_related(
            'section', 'submission__author', 'issue__volume'
        ).order_by('-published_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['sections'] = JournalSection.objects.all()
        return ctx


class ArticleDetailView(DetailView):
    model = PublishedArticle
    template_name = 'pages/article_detail.html'

    def dispatch(self, request, *args, **kwargs):
        slug = kwargs.get('slug')
        if slug and not PublishedArticle.objects.filter(slug=slug).exists():
            old = PublishedArticleSlugHistory.objects.select_related('article').filter(slug=slug).first()
            if old:
                return redirect('pages:article_detail', slug=old.article.slug, permanent=True)
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        obj = get_object_or_404(
            PublishedArticle.objects.select_related(
                'section', 'submission__author', 'issue__volume'
            ).prefetch_related('submission__co_authors'),
            slug=self.kwargs['slug'],
        )
        PublishedArticle.objects.filter(pk=obj.pk).update(views_count=obj.views_count + 1)
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['co_authors'] = self.object.submission.co_authors.all()
        ctx['related_articles'] = PublishedArticle.objects.filter(
            section=self.object.section
        ).exclude(pk=self.object.pk).select_related(
            'section', 'submission__author'
        ).order_by('-published_at')[:3]
        return ctx


class CurrentIssueView(TemplateView):
    template_name = 'pages/current_issue.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['current_issue'] = Issue.objects.filter(
            is_current=True
        ).select_related('volume').prefetch_related(
            'articles__section', 'articles__submission__author'
        ).first()
        return ctx


class ArchiveView(TemplateView):
    template_name = 'pages/archive.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['volumes'] = Volume.objects.prefetch_related('issues__articles').order_by('-number')
        return ctx


class SearchView(ListView):
    model = PublishedArticle
    template_name = 'pages/search.html'
    context_object_name = 'articles'
    paginate_by = 10

    def get_queryset(self):
        query = self.request.GET.get('q', '').strip()
        if not query:
            return PublishedArticle.objects.none()
        return PublishedArticle.objects.filter(
            Q(title__icontains=query) |
            Q(abstract__icontains=query) |
            Q(keywords__icontains=query)
        ).select_related('section', 'submission__author').order_by('-published_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['query'] = self.request.GET.get('q', '')
        return ctx


class SectionArticlesView(ListView):
    model = PublishedArticle
    template_name = 'pages/article_list.html'
    context_object_name = 'articles'
    paginate_by = 12

    def get_queryset(self):
        self.section = get_object_or_404(JournalSection, slug=self.kwargs['slug'])
        return PublishedArticle.objects.filter(
            section=self.section
        ).select_related('submission__author').order_by('-published_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['section'] = self.section
        ctx['sections'] = JournalSection.objects.all()
        return ctx


class StaticPageView(TemplateView):
    PAGES = {
        'about': ('pages/static/about.html', 'عن المجلة'),
        'aims-scope': ('pages/static/aims_scope.html', 'الأهداف والنطاق'),
        'editorial-board': ('pages/static/editorial_board.html', 'هيئة التحرير'),
        'review-process': ('pages/static/review_process.html', 'عملية المراجعة'),
        'ethics': ('pages/static/ethics.html', 'أخلاقيات النشر'),
        'author-guidelines': ('pages/static/author_guidelines.html', 'إرشادات المؤلفين'),
        'apc': ('pages/static/apc.html', 'رسوم النشر'),
        'contact': ('pages/static/contact.html', 'اتصل بنا'),
        'topics': ('pages/static/topics.html', 'مواضيع المجلة'),
        'blog': ('pages/static/blog.html', 'المدونة'),
        'conferences': ('pages/static/conferences.html', 'المؤتمرات العلمية'),
    }

    def get_template_names(self):
        slug = self.kwargs.get('slug', 'about')
        template, _ = self.PAGES.get(slug, ('pages/static/about.html', ''))
        return [template]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        slug = self.kwargs.get('slug', 'about')
        _, title = self.PAGES.get(slug, ('', 'الصفحة'))
        ctx['page_title'] = title
        from apps.pages.models import SiteSettings
        ctx['settings'] = SiteSettings.get()
        if slug == 'aims-scope':
            ctx['sections'] = JournalSection.objects.all()
        if slug == 'editorial-board':
            from apps.pages.models import EditorialBoardMember
            ctx['board_members'] = EditorialBoardMember.objects.filter(is_active=True)
        if slug == 'contact':
            from apps.pages.forms import ContactForm
            ctx['form'] = ContactForm()
        return ctx

    def post(self, request, *args, **kwargs):
        slug = self.kwargs.get('slug', 'about')
        if slug != 'contact':
            return self.get(request, *args, **kwargs)

        from apps.pages.forms import ContactForm
        from django.core.mail import send_mail
        from django.conf import settings as django_settings

        form = ContactForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data['name']
            email = form.cleaned_data['email']
            subject = form.cleaned_data['subject']
            message = form.cleaned_data['message']
            full_message = f"\nرسالة جديدة من نموذج الاتصال\n\nالاسم: {name}\nالبريد الإلكتروني: {email}\nالموضوع: {subject}\n\nالرسالة:\n{message}\n"
            try:
                from apps.pages.models import SiteSettings
                site_settings = SiteSettings.get()
                recipient_email = site_settings.contact_email or django_settings.DEFAULT_FROM_EMAIL
                send_mail(
                    subject=f'[اتصل بنا] {subject}',
                    message=full_message,
                    from_email=django_settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[recipient_email],
                    fail_silently=False,
                )
                return JsonResponse({'success': True, 'message': 'تم إرسال رسالتك بنجاح'})
            except Exception:
                return JsonResponse({'success': False, 'message': 'حدث خطأ أثناء إرسال الرسالة'}, status=500)
        return JsonResponse({'success': False, 'errors': form.errors}, status=400)


def article_views_api(request, slug):
    article = get_object_or_404(PublishedArticle, slug=slug)
    return JsonResponse({'views': article.views_count})
