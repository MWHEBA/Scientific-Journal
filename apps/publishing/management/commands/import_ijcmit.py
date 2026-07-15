import re
import urllib.parse
import xml.etree.ElementTree as ET
import requests
import time
import html
import json
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
    # Decode URL percent-encoded chars
    decoded = urllib.parse.unquote(text)
    # Standard slugification
    slug = slugify(decoded)
    if not slug:
        # Fallback manual cleaning
        slug = re.sub(r'[^a-zA-Z0-9\-]+', '-', decoded.lower())
    return slug.strip('-')[:200] or 'article'


def normalize_author_name(name):
    if not name:
        return ""
    name = name.lower().strip()
    # Remove titles
    name = re.sub(r'\b(dr|prof|mr|mrs|ms|phd)\b\.?', '', name)
    # Remove punctuation
    name = re.sub(r'[^\w\s]', '', name)
    # Normalize spaces
    name = re.sub(r'\s+', ' ', name)
    return name.strip()


def clean_abstract_html(text):
    if not text:
        return ""
    # 1. Unescape HTML entities
    text = html.unescape(text)
    # 2. Remove WordPress caption shortcodes
    text = re.sub(r'\[caption[^\]]*\].*?\[/caption\]', '', text, flags=re.DOTALL)
    # 3. Remove all other WordPress shortcodes [xyz ...]
    text = re.sub(r'\[[^\]]+\]', '', text)
    # 4. Replace block elements with newlines to preserve spacing
    text = re.sub(r'</p>|<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    # 5. Strip all other HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # 6. Normalize spacing (but keep newlines)
    lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in text.split('\n')]
    # Remove empty lines
    lines = [line for line in lines if line]
    return '\n\n'.join(lines)


def parse_english_issue(issue_str, post_date=None):
    text = issue_str.lower()
    
    # Extract 4-digit year (e.g. 2021, 2022...)
    year_match = re.search(r'\b(202[0-9])\b', text)
    if not year_match and post_date:
        year = int(post_date.split('-')[0])
    else:
        year = int(year_match.group(1)) if year_match else 2021
    
    # Extract volume
    vol_match = re.search(r'\b(?:volume|vol\.?)\s*(\d+)', text)
    volume_num = int(vol_match.group(1)) if vol_match else 1
    
    # Extract issue
    issue_match = re.search(r'\b(?:issue|number|no\.?)\s*(\d+)', text)
    issue_num = int(issue_match.group(1)) if issue_match else 1
    
    # Determine quarter (1-6) based on English months
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
        # Fallback to issue number clamped
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
                # Permanent errors, do not retry
                return None
        except Exception:
            pass
        attempt += 1
        time.sleep(backoff)
        backoff *= 2
    return None


class Command(BaseCommand):
    help = 'Import IJCMIT articles from a WordPress WXR XML export file with robust error recovery'

    def add_arguments(self, parser):
        parser.add_argument('xml_file', type=str, help='Path to the WXR XML file')
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear all existing articles, issues, volumes, and submissions before import',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Parse the XML and simulate actions without writing to the database or downloading PDFs',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Limit the number of imported articles (useful for testing/dev environments)',
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=1.0,
            help='Delay in seconds between HTTP downloads to prevent blocking (default: 1.0)',
        )

    def safe_write(self, msg, style_func=None):
        try:
            if style_func:
                self.stdout.write(style_func(msg))
            else:
                self.stdout.write(msg)
        except UnicodeEncodeError:
            safe_msg = msg.encode('ascii', errors='replace').decode('ascii')
            if style_func:
                self.stdout.write(style_func(safe_msg))
            else:
                self.stdout.write(safe_msg)

    def handle(self, *args, **options):
        xml_file_path = options['xml_file']
        dry_run = options['dry_run']
        limit = options['limit']

        report = {
            'total_posts_found': 0,
            'processed_count': 0,
            'success_count': 0,
            'skipped_existing_count': 0,
            'failed_downloads': [],
            'created_authors': [],
            'warnings': []
        }

        # 1. Clear database if requested
        if options['clear'] and not dry_run:
            self.safe_write("Clearing database models...", self.style.WARNING)
            with transaction.atomic():
                PublishedArticleSlugHistory.objects.all().delete()
                PublishedArticle.objects.all().delete()
                Issue.objects.all().delete()
                Volume.objects.all().delete()
                CoAuthor.objects.all().delete()
                ManuscriptFile.objects.all().delete()
                ArticleSubmission.objects.all().delete()
                JournalSection.objects.all().delete()
            self.safe_write("Database cleared successfully!", self.style.SUCCESS)

        # 2. Parse XML File
        self.safe_write(f"Parsing XML file: {xml_file_path}")
        try:
            tree = ET.parse(xml_file_path)
            root = tree.getroot()
        except Exception as e:
            self.safe_write(f"Error parsing XML file: {e}", self.style.ERROR)
            return

        namespaces = {
            'wp': 'http://wordpress.org/export/1.2/',
            'content': 'http://purl.org/rss/1.0/modules/content/',
            'dc': 'http://purl.org/dc/elements/1.1/'
        }

        # 2.1. Pre-create all defined categories (sections) in database - Skipped to avoid spam categories
        self.safe_write("Skipping pre-creation of all XML categories to avoid spam categories.", self.style.WARNING)

        items = root.findall('.//item')
        
        # Build WordPress Author Index
        wp_authors = {}
        channel = root.find('channel')
        if channel is not None:
            for author_node in channel.findall('wp:author', namespaces):
                login = author_node.find('wp:author_login', namespaces).text
                email = author_node.find('wp:author_email', namespaces).text
                display_name = author_node.find('wp:author_display_name', namespaces).text
                wp_authors[login] = {'email': email, 'display_name': display_name}

        # Build Attachment Index by parent ID
        attachments_by_parent = {}
        for item in items:
            pt = item.find('wp:post_type', namespaces)
            if pt is not None and pt.text == 'attachment':
                parent_node = item.find('wp:post_parent', namespaces)
                parent_id = parent_node.text if parent_node is not None else None
                att_url = item.find('wp:attachment_url', namespaces)
                if parent_id and att_url is not None and att_url.text:
                    attachments_by_parent.setdefault(parent_id, []).append(att_url.text)

        # 3. Process published posts
        published_posts = []
        for item in items:
            pt = item.find('wp:post_type', namespaces)
            status = item.find('wp:status', namespaces)
            if pt is not None and pt.text == 'post' and status is not None and status.text == 'publish':
                published_posts.append(item)

        report['total_posts_found'] = len(published_posts)
        self.safe_write(f"Found {len(published_posts)} published posts to import.", self.style.SUCCESS)

        if limit > 0:
            published_posts = published_posts[:limit]
            self.safe_write(f"Limiting import to first {limit} articles.", self.style.WARNING)

        success_count = 0
        skipped_count = 0

        for idx, post in enumerate(published_posts):
            title = post.find('title').text or "Untitled Article"
            post_id = post.find('wp:post_id', namespaces).text
            post_date = post.find('wp:post_date', namespaces).text
            post_name = post.find('wp:post_name', namespaces).text
            content = post.find('content:encoded', namespaces).text or ""
            creator = post.find('dc:creator', namespaces).text

            self.safe_write(f"\n[{idx+1}/{len(published_posts)}] Processing: {title[:60]}... (ID: {post_id})")

            # Extract taxonomies
            categories = []
            tags = []
            issue_text = None
            paper_authors = []

            for cat in post.findall('category'):
                domain = cat.attrib.get('domain', '')
                name = cat.text
                if domain == 'category':
                    categories.append(name)
                elif domain == 'post_tag':
                    tags.append(name)
                elif domain == 'issue':
                    issue_text = name
                elif domain == 'paper_author':
                    paper_authors.append(name)

            if not issue_text:
                self.safe_write(f"  Skipping post ID {post_id} ('{title[:40]}...') because it has no issue taxonomy (likely spam).", self.style.WARNING)
                skipped_count += 1
                report['processed_count'] += 1
                report['skipped_existing_count'] += 1
                continue

            # 3.1. Determine Section
            section_name = categories[0] if categories else "General"
            section = None
            if not dry_run:
                section = JournalSection.objects.filter(name=section_name).first()
                if not section:
                    section_slug = clean_english_slug(section_name)
                    base_slug = section_slug
                    counter = 1
                    while JournalSection.objects.filter(slug=section_slug).exists():
                        section_slug = f"{base_slug}-{counter}"
                        counter += 1
                    section = JournalSection.objects.create(
                        name=section_name,
                        slug=section_slug
                    )

            # 3.2. Resolve Issue / Volume
            issue = None
            if issue_text:
                vol_num, iss_num, year, quarter = parse_english_issue(issue_text, post_date)
                
                if not dry_run:
                    # Avoid unique constraint on Volume.number by checking existence first
                    volume = Volume.objects.filter(number=vol_num).first()
                    if not volume:
                        volume = Volume.objects.create(number=vol_num, year=year)
                    elif volume.year != year:
                        warn_msg = f"Volume {vol_num} already exists with year {volume.year}, but post ID {post_id} XML indicates year {year}. Reusing existing volume."
                        self.safe_write(f"  {warn_msg}", self.style.WARNING)
                        report['warnings'].append(warn_msg)

                    issue, _ = Issue.objects.get_or_create(
                        volume=volume,
                        number=iss_num,
                        defaults={'quarter': quarter, 'published_at': post_date.split(' ')[0]}
                    )
                else:
                    self.safe_write(f"  [Dry-run] Parsed Volume {vol_num} ({year}) and Issue {iss_num} (Quarter {quarter})")

            # 3.3. Resolve Authors
            primary_author_name = None
            co_author_names = []

            if paper_authors:
                primary_author_name = paper_authors[0]
                co_author_names = paper_authors[1:]
            else:
                creator_info = wp_authors.get(creator, {})
                primary_author_name = creator_info.get('display_name') or creator

            primary_author = None
            if not dry_run:
                if not hasattr(self, 'imported_authors'):
                    self.imported_authors = {}

                norm_name = normalize_author_name(primary_author_name)
                primary_author = self.imported_authors.get(norm_name)
                
                if not primary_author:
                    # Look up in DB by normalized first_name
                    for u in User.objects.filter(role=User.ROLE_AUTHOR):
                        if normalize_author_name(u.first_name) == norm_name:
                            primary_author = u
                            break

                if not primary_author:
                    username = f"author_wp_{post_id}"
                    email = f"{username}@ijcmit.com"
                    
                    # Username uniqueness check
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
                    self.safe_write(f"  Created User & AuthorProfile: {primary_author_name}")
                    report['created_authors'].append(primary_author_name)
                    
                self.imported_authors[norm_name] = primary_author

            # Clean abstract text
            clean_abstract = clean_abstract_html(content)

            # Check Idempotency: Does the article already exist?
            post_slug = clean_english_slug(post_name or title)
            existing_article = None
            
            if not dry_run:
                existing_article = PublishedArticle.objects.filter(slug=post_slug).first()
                if not existing_article:
                    existing_article = PublishedArticle.objects.filter(title__iexact=title).first()

            if existing_article and not dry_run:
                self.safe_write(f"  Article already exists in DB (ID: {existing_article.id}). Updating metadata...", self.style.WARNING)
                submission = existing_article.submission
                submission.title = title
                submission.abstract = clean_abstract
                submission.section = section
                submission.author = primary_author
                submission.save()

                # Sync keywords
                if tags:
                    submission.keywords.clear()
                    submission.keywords.add(*tags)

                # Sync co-authors
                submission.co_authors.all().delete()
                for order, co_name in enumerate(co_author_names):
                    CoAuthor.objects.create(
                        submission=submission,
                        full_name=co_name,
                        order=order
                    )

                skipped_count += 1
                report['skipped_existing_count'] += 1
            else:
                submission = None
                if not dry_run:
                    submission = ArticleSubmission.objects.create(
                        title=title,
                        abstract=clean_abstract,
                        section=section,
                        author=primary_author,
                        status=SubmissionStatus.PUBLISHED
                    )
                    if tags:
                        submission.keywords.add(*tags)

                    for order, co_name in enumerate(co_author_names):
                        CoAuthor.objects.create(
                            submission=submission,
                            full_name=co_name,
                            order=order
                        )

            # 3.5. Download & Attach PDFs
            pdf_urls = attachments_by_parent.get(post_id, [])
            manuscript = None

            if existing_article and not dry_run:
                # If there's an existing manuscript, check if the file exists on storage
                m_file = existing_article.manuscript_file
                if m_file and m_file.file and m_file.file.storage.exists(m_file.file.name):
                    manuscript = m_file
                    self.safe_write(f"  PDF file already exists in storage ({m_file.file.name}). Skipping download.", self.style.SUCCESS)

            if not manuscript:
                for pdf_url in pdf_urls:
                    if not pdf_url.endswith('.pdf'):
                        continue
                    
                    filename = pdf_url.split('/')[-1].split('?')[0]
                    self.safe_write(f"  Downloading PDF: {pdf_url}")
                    
                    pdf_content = None
                    if not dry_run:
                        pdf_content = download_file_with_retry(pdf_url, delay=options['delay'])
                    
                    if pdf_content and not dry_run:
                        manuscript = ManuscriptFile(
                            submission=submission,
                            version=1,
                            is_current=True
                        )
                        manuscript.file.save(filename, ContentFile(pdf_content), save=True)
                        self.safe_write(f"    Saved manuscript file: {filename}", self.style.SUCCESS)
                        break
                    else:
                        if dry_run:
                            self.safe_write(f"    [Dry-run] Would download PDF from {pdf_url}", self.style.WARNING)
                        else:
                            self.safe_write(f"    Failed to download PDF from {pdf_url}", self.style.ERROR)
                            report['failed_downloads'].append({'post_id': post_id, 'url': pdf_url})

            if not manuscript and not dry_run:
                # Create a placeholder manuscript file if download failed or no PDF is found
                self.safe_write("  No PDF attached or download failed. Creating placeholder manuscript file.", self.style.WARNING)
                manuscript = ManuscriptFile(
                    submission=submission,
                    version=1,
                    is_current=True
                )
                manuscript.file.save(f"placeholder_{post_id}.pdf", ContentFile(b"%PDF-1.4 ... placeholder"), save=True)

            # 3.6. Create/Update PublishedArticle
            if not dry_run:
                keywords_str = ', '.join(tags)
                
                if existing_article:
                    existing_article.manuscript_file = manuscript
                    existing_article.issue = issue
                    existing_article.title = title
                    existing_article.abstract = clean_abstract
                    existing_article.keywords = keywords_str[:500]
                    existing_article.section = section
                    # Recalculate slug safely
                    existing_article.slug = PublishedArticle.generate_unique_slug(post_name or title, exclude_pk=existing_article.pk)
                    existing_article.save()
                    article = existing_article
                else:
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

                # 3.7. Force override timestamps to match WordPress dates
                ArticleSubmission.objects.filter(pk=submission.pk).update(created_at=post_date, updated_at=post_date)
                ManuscriptFile.objects.filter(pk=manuscript.pk).update(uploaded_at=post_date)
                PublishedArticle.objects.filter(pk=article.pk).update(published_at=post_date)

                self.safe_write(f"  Successfully imported article: {article.title}", self.style.SUCCESS)
                success_count += 1
            else:
                self.safe_write(f"  [Dry-run] Parsed article successfully: {title}")
                success_count += 1

            report['processed_count'] += 1

        report['success_count'] = success_count

        if not dry_run:
            # Save report
            with open('import_report.json', 'w', encoding='utf-8') as rf:
                json.dump(report, rf, indent=4, ensure_ascii=False)
            self.safe_write(f"\nImport finished! Successfully imported {success_count} articles ({skipped_count} updated/skipped). Detailed report saved in import_report.json", self.style.SUCCESS)
        else:
            self.safe_write(f"\n[Dry-run] Simulation finished! Handled {success_count} posts.", self.style.SUCCESS)
