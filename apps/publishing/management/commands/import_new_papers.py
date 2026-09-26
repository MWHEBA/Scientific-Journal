import os
import json
import re
import urllib.parse
import requests
import time
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.text import slugify
from django.contrib.auth import get_user_model

from apps.submissions.models import ArticleSubmission, JournalSection, ManuscriptFile, CoAuthor
from apps.submissions.statuses import SubmissionStatus
from apps.publishing.models import PublishedArticle, Volume, Issue, PublishedArticleSlugHistory
from apps.accounts.models import AuthorProfile

User = get_user_model()

def clean_english_slug(text):
    decoded = urllib.parse.unquote(text)
    slug = slugify(decoded)
    if not slug:
        slug = re.sub(r'[^a-zA-Z0-9\-]+', '-', decoded.lower())
    return slug.strip('-')[:200] or 'article'

def normalize_author_name(name):
    if not name:
        return ""
    name = name.lower().strip()
    name = re.sub(r'\b(dr|prof|mr|mrs|ms|phd)\b\.?', '', name)
    name = re.sub(r'[^\w\s]', '', name)
    name = re.sub(r'\s+', ' ', name)
    return name.strip()

def clean_abstract_html(text):
    if not text:
        return ""
    import html
    text = html.unescape(text)
    text = re.sub(r'\[caption[^\]]*\].*?\[/caption\]', '', text, flags=re.DOTALL)
    text = re.sub(r'\[[^\]]+\]', '', text)
    text = re.sub(r'</p>|<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in text.split('\n')]
    lines = [line for line in lines if line]
    return '\n\n'.join(lines)

def parse_english_issue(issue_str, post_date=None):
    text = issue_str.lower()
    year_match = re.search(r'\b(202[0-9])\b', text)
    if not year_match and post_date:
        year = int(post_date.split('-')[0])
    else:
        year = int(year_match.group(1)) if year_match else 2021
    
    vol_match = re.search(r'\b(?:volume|vol\.?)\s*(\d+)', text)
    volume_num = int(vol_match.group(1)) if vol_match else 1
    
    issue_match = re.search(r'\b(?:issue|number|no\.?)\s*(\d+)', text)
    issue_num = int(issue_match.group(1)) if issue_match else 1
    
    quarter = 1
    if any(m in text for m in ['january', 'february', 'jan', 'feb']):
        quarter = 1
    elif any(m in text for m in ['march', 'april', 'mar', 'apr']):
        quarter = 2
    elif any(m in text for m in ['may', 'june', 'jun']):
        quarter = 3
    elif any(m in text for m in ['july', 'august', 'jul', 'aug']):
        quarter = 4
    elif any(m in text for m in ['september', 'october', 'sep', 'oct']):
        quarter = 5
    elif any(m in text for m in ['november', 'december', 'nov', 'dec']):
        quarter = 6
    else:
        quarter = max(1, min(6, issue_num))
        
    return volume_num, issue_num, year, quarter

def download_file_with_retry(url, delay=1.0, retries=3):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    attempt = 0
    backoff = 2.0
    while attempt < retries:
        try:
            if delay > 0:
                time.sleep(delay)
            response = requests.get(url, headers=headers, timeout=20)
            if response.status_code == 200:
                return response.content
            elif response.status_code in [403, 404]:
                return None
        except Exception:
            pass
        attempt += 1
        time.sleep(backoff)
        backoff *= 2
    return None

class Command(BaseCommand):
    help = 'Import the 11 discovered new papers from WordPress details JSON'

    def add_arguments(self, parser):
        parser.add_argument(
            '--json-file',
            type=str,
            help='Path to the WordPress details JSON file',
            default='new_papers_details.json'
        )

    def handle(self, *args, **options):
        json_path = options['json_file']
        
        # If the default file doesn't exist, check the absolute local path
        if not os.path.exists(json_path) and json_path == 'new_papers_details.json':
            fallback_path = r"C:\Users\UTD\.gemini\antigravity-ide\brain\eebc3dbf-ebc5-41e0-998e-25165e1ce736\scratch\new_papers_details.json"
            if os.path.exists(fallback_path):
                json_path = fallback_path
                
        if not os.path.exists(json_path):
            self.stdout.write(self.style.ERROR(f"JSON file not found: {json_path}"))
            return
            
        with open(json_path, 'r', encoding='utf-8') as f:
            papers = json.load(f)

            
        self.stdout.write(self.style.SUCCESS(f"Loaded {len(papers)} papers from JSON."))
        
        imported_count = 0
        
        for idx, p in enumerate(papers, 1):
            title = p['title']
            post_id = p['id']
            post_date = p['date']
            post_name = p['slug']
            content = p['content']
            
            self.stdout.write(f"\n[{idx}/{len(papers)}] Importing: {title[:60]}... (ID: {post_id})")
            
            # Determine Section
            section_name = p['categories'][0] if p['categories'] else "General"
            section = JournalSection.objects.filter(name=section_name).first()
            if not section:
                section_slug = clean_english_slug(section_name)
                base_slug = section_slug
                counter = 1
                while JournalSection.objects.filter(slug=section_slug).exists():
                    section_slug = f"{base_slug}-{counter}"
                    counter += 1
                section = JournalSection.objects.create(name=section_name, slug=section_slug)
                self.stdout.write(f"  Created Section: {section_name}")
                
            # Determine Issue / Volume
            issue_text = p['issues'][0] if p['issues'] else None
            if not issue_text:
                self.stdout.write(self.style.ERROR(f"  Skipping ID {post_id} - No issue taxonomy found."))
                continue
                
            vol_num, iss_num, year, quarter = parse_english_issue(issue_text, post_date)
            
            volume = Volume.objects.filter(number=vol_num).first()
            if not volume:
                volume = Volume.objects.create(number=vol_num, year=year)
                self.stdout.write(f"  Created Volume: {vol_num} ({year})")
            
            issue, _ = Issue.objects.get_or_create(
                volume=volume,
                number=iss_num,
                defaults={'quarter': quarter, 'published_at': post_date.split(' ')[0]}
            )
            
            # Determine Authors
            primary_author_name = p['authors'][0] if p['authors'] else "Unknown Author"
            co_author_names = p['authors'][1:] if p['authors'] else []
            
            norm_name = normalize_author_name(primary_author_name)
            primary_author = None
            
            # Look up in DB by normalized first_name
            for u in User.objects.filter(role=User.ROLE_AUTHOR):
                if normalize_author_name(u.first_name) == norm_name:
                    primary_author = u
                    break
                    
            if not primary_author:
                username = f"author_wp_{post_id}"
                email = f"{username}@ijcmit.com"
                username_counter = 1
                base_username = username
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}_{username_counter}"
                    username_counter += 1
                
                primary_author = User.objects.create_user(
                    username=username,
                    email=email,
                    first_name=primary_author_name[:150],
                    role=User.ROLE_AUTHOR
                )
                AuthorProfile.objects.get_or_create(user=primary_author)
                self.stdout.write(f"  Created User & AuthorProfile: {primary_author_name}")
                
            # Clean abstract
            clean_abstract = clean_abstract_html(content)
            
            # Check if exists
            post_slug = clean_english_slug(post_name or title)
            existing_article = PublishedArticle.objects.filter(slug=post_slug).first()
            if not existing_article:
                existing_article = PublishedArticle.objects.filter(title__iexact=title).first()
                
            if existing_article:
                self.stdout.write(self.style.WARNING(f"  Article already exists in DB. Skipping creation."))
                continue
                
            with transaction.atomic():
                # Create Submission
                submission = ArticleSubmission.objects.create(
                    title=title,
                    abstract=clean_abstract,
                    section=section,
                    author=primary_author,
                    status=SubmissionStatus.PUBLISHED
                )
                
                # Keywords
                if p['tags']:
                    submission.keywords.add(*p['tags'])
                    
                # Co-authors
                for order, co_name in enumerate(co_author_names):
                    CoAuthor.objects.create(
                        submission=submission,
                        full_name=co_name,
                        order=order
                    )
                    
                # Download and Attach PDFs
                pdf_urls = [pdf['url'] for pdf in p['pdfs']]
                manuscript = None
                
                for pdf_url in pdf_urls:
                    if not pdf_url.endswith('.pdf'):
                        continue
                    filename = pdf_url.split('/')[-1].split('?')[0]
                    self.stdout.write(f"  Downloading PDF: {pdf_url}")
                    pdf_content = download_file_with_retry(pdf_url)
                    if pdf_content:
                        manuscript = ManuscriptFile(
                            submission=submission,
                            version=1,
                            is_current=True
                        )
                        manuscript.file.save(filename, ContentFile(pdf_content), save=True)
                        self.stdout.write(self.style.SUCCESS(f"    Saved PDF: {filename}"))
                        break
                        
                if not manuscript:
                    self.stdout.write(self.style.WARNING("  No PDF downloaded. Creating placeholder PDF."))
                    manuscript = ManuscriptFile(
                        submission=submission,
                        version=1,
                        is_current=True
                    )
                    manuscript.file.save(f"placeholder_{post_id}.pdf", ContentFile(b"%PDF-1.4 ... placeholder"), save=True)
                    
                # Create PublishedArticle
                keywords_str = ', '.join(p['tags'])
                slug = PublishedArticle.generate_unique_slug(post_name or title)
                article = PublishedArticle.objects.create(
                    submission=submission,
                    manuscript_file=manuscript,
                    issue=issue,
                    title=title,
                    abstract=clean_abstract,
                    keywords=keywords_str[:500],
                    section=section,
                    slug=slug
                )
                
                # Force override timestamps
                ArticleSubmission.objects.filter(pk=submission.pk).update(created_at=post_date, updated_at=post_date)
                ManuscriptFile.objects.filter(pk=manuscript.pk).update(uploaded_at=post_date)
                PublishedArticle.objects.filter(pk=article.pk).update(published_at=post_date)
                
                self.stdout.write(self.style.SUCCESS(f"  Successfully imported article: {title[:40]}"))
                imported_count += 1
                
        self.stdout.write(self.style.SUCCESS(f"\nImport process completed! Successfully imported {imported_count} new articles."))
