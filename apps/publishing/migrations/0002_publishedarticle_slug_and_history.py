from django.db import migrations, models
from django.utils.text import slugify


def backfill_slugs(apps, schema_editor):
    PublishedArticle = apps.get_model('publishing', 'PublishedArticle')
    reserved = {
        'about', 'aims-scope', 'editorial-board', 'review-process', 'ethics',
        'author-guidelines', 'apc', 'contact', 'topics', 'blog', 'conferences',
        'archive', 'search', 'section', 'current-issue', 'articles',
        'accounts', 'dashboard', 'payments', 'notifications', 'admin',
        'login', 'logout', 'register', 'password', 'favicon.ico', 'robots.txt', 'sitemap.xml',
    }
    used = set(
        PublishedArticle.objects.exclude(slug__isnull=True).exclude(slug='').values_list('slug', flat=True)
    )
    for article in PublishedArticle.objects.order_by('id'):
        if article.slug:
            continue
        base = slugify((article.title or '').strip())[:200] or 'article'
        if base in reserved:
            base = f'article-{base}'
        candidate = base
        i = 2
        while candidate in used:
            suffix = f'-{i}'
            candidate = f'{base[:max(1, 220-len(suffix))]}{suffix}'
            i += 1
        article.slug = candidate
        article.save(update_fields=['slug'])
        used.add(candidate)


class Migration(migrations.Migration):

    dependencies = [
        ('publishing', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='publishedarticle',
            name='slug',
            field=models.SlugField(blank=True, db_index=True, max_length=220, null=True),
        ),
        migrations.RunPython(backfill_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='publishedarticle',
            name='slug',
            field=models.SlugField(blank=True, db_index=True, max_length=220, unique=True),
        ),
        migrations.CreateModel(
            name='PublishedArticleSlugHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(db_index=True, max_length=220, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('article', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='slug_history', to='publishing.publishedarticle')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
