import re
import urllib.parse
import xml.etree.ElementTree as ET
import requests
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.text import slugify
from django.contrib.auth import get_user_model

from apps.submissions.models import ArticleSubmission, JournalSection, ManuscriptFile, CoAuthor
from apps.submissions.statuses import SubmissionStatus
from apps.publishing.models import PublishedArticle, Volume, Issue, PublishedArticleSlugHistory

User = get_user_model()

def clean_arabic_slug(text):
    # Decode URL percent-encoded chars
    decoded = urllib.parse.unquote(text)
    # Replace spaces and special characters with hyphens
    slug = re.sub(r'[\s\.\,\_\/\:\;\(\)\[\]\{\}\?\!\#\$\%\^\&\*\"\']+', '-', decoded)
    return slug.strip('-')[:200] or 'article'

def get_section_slug(section_name):
    mapping = {
        "إدارة": "إدارة",
        "إدارة المعرفة": "إدارة-المعرفة",
        "إدارة الموارد البشرية الإلكترونية": "إدارة-الموارد-البشرية-الإلكترونية",
        "ادارة الموارد البشرية": "ادارة-الموارد-البشرية",
        "اعتماد إنترنت الأشياء": "اعتماد-إنترنت-الأشياء",
        "اعتماد التكنولوجيا": "اعتماد-التكنولوجيا",
        "اعتماد الحوسبة السحابية": "اعتماد-الحوسبة-السحابية",
        "الإدارة الاستراتيجية": "الإدارة-الاستراتيجية",
        "التجارة الإلكترونية": "التجارة-الإلكترونية",
        "التجارة الإلكترونية السحابية": "التجارة-الإلكترونية-السحابية",
        "التجارة الإلكترونية القائمة على السحابة": "التجارة-الإلكترونية-القائمة-على-السح",
        "التجارة الاجتماعية": "التجارة-الاجتماعية",
        "التعلم الإلكتروني": "التعلم-الإلكتروني",
        "التعلم الإلكتروني القائم على السحابة": "التعلم-الإلكتروني-القائم-على-السحابة",
        "التعلم بواسطة السحابة الإلكترونية": "التعلم-بواسطة-السحابة-الإلكترونية",
        "الحكومة الإلكترونية": "الحكومة-الإلكترونية",
        "الحكومة الإلكترونية القائمة على السحابة": "الحكومة-الإلكترونية-القائمة-على-السح",
        "العلوم الاجتماعية": "العلوم-الاجتماعية",
        "العلوم الصحية": "العلوم-الصحية",
        "تسويق": "تسويق",
        "تكنولوجيا المعلومات الإدارية": "تكنولوجيا-المعلومات-الإدارية",
        "حوسبة سحابية": "حوسبة-سحابية",
        "علوم القانون": "علوم-القانون",
        "نظام إدارة المعلومات": "نظام-إدارة-المعلومات",
        "نظام التعلم اللَّاعِب": "نظام-التعلم-اللَّاعِب",
    }
    if section_name in mapping:
        return mapping[section_name]
    
    slug = slugify(section_name)
    if not slug:
        import hashlib
        name_hash = hashlib.md5(section_name.encode('utf-8')).hexdigest()[:8]
        slug = f"sec-{name_hash}"
    return slug

def parse_issue_string(issue_str):
    # Map Arabic numerals to English numerals
    arabic_to_eng = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
    text = issue_str.translate(arabic_to_eng)
    
    # Extract 4-digit year (e.g. 2021, 2022...)
    year_match = re.search(r'\b(202[0-9])\b', text)
    year = int(year_match.group(1)) if year_match else 2021
    
    # Extract volume (الاصدار / الإصدار)
    volume_match = re.search(r'(?:الاصدار|الإصدار)\s*(\d+)', text)
    volume_num = int(volume_match.group(1)) if volume_match else 1
    
    # Extract issue (عدد)
    issue_match = re.search(r'عدد\s*(\d+)', text)
    issue_num = int(issue_match.group(1)) if issue_match else 1
    
    # Determine quarter (1-6)
    quarter = issue_num
    if 'يناير' in text:
        quarter = 1
    elif 'مارس' in text:
        quarter = 2
    elif 'مايو' in text:
        quarter = 3
    elif 'يوليو' in text:
        quarter = 4
    elif 'سبتمبر' in text:
        quarter = 5
    elif 'نوفمبر' in text:
        quarter = 6
    else:
        # Clamp between 1 and 6
        quarter = max(1, min(6, quarter))
        
    return volume_num, issue_num, year, quarter

class Command(BaseCommand):
    help = 'Import articles from a WordPress WXR XML export file'

    def add_arguments(self, parser):
        parser.add_argument('xml_file', type=str, help='Path to the WXR XML file')
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear all existing articles, issues, volumes, and submissions before import',
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
        
        # 1. Clear database if requested
        if options['clear']:
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

        # 2.1. Pre-create all defined categories (sections) in database
        self.safe_write("Importing all categories defined in XML...", self.style.WARNING)
        channel = root.find('channel')
        if channel is not None:
            for idx, cat_node in enumerate(channel.findall('wp:category', namespaces), 1):
                name = cat_node.find('wp:cat_name', namespaces).text
                slug = get_section_slug(name)
                section, created = JournalSection.objects.get_or_create(
                    name=name,
                    defaults={'slug': slug, 'order': idx}
                )
                if created:
                    self.safe_write(f"  Created Section: {name} (Slug: {slug}, Order: {idx})")
                else:
                    section.order = idx
                    section.save()

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
                parent_id = item.find('wp:post_parent', namespaces).text
                att_url = item.find('wp:attachment_url', namespaces)
                if att_url is not None and att_url.text:
                    attachments_by_parent.setdefault(parent_id, []).append(att_url.text)

        # 3. Process published posts
        published_posts = []
        for item in items:
            pt = item.find('wp:post_type', namespaces)
            status = item.find('wp:status', namespaces)
            if pt is not None and pt.text == 'post' and status is not None and status.text == 'publish':
                published_posts.append(item)

        self.safe_write(f"Found {len(published_posts)} published posts to import.", self.style.SUCCESS)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
        }

        success_count = 0
        for idx, post in enumerate(published_posts):
            title = post.find('title').text
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

            # 3.1. Determine Section
            section_name = categories[0] if categories else "إدارة"
            section = JournalSection.objects.filter(name=section_name).first()
            if not section:
                section_slug = get_section_slug(section_name)
                section, _ = JournalSection.objects.get_or_create(
                    name=section_name,
                    defaults={'slug': section_slug}
                )

            # 3.2. Resolve Issue / Volume
            issue = None
            if issue_text:
                vol_num, iss_num, year, quarter = parse_issue_string(issue_text)
                volume, _ = Volume.objects.get_or_create(
                    number=vol_num,
                    defaults={'year': year}
                )
                issue, _ = Issue.objects.get_or_create(
                    volume=volume,
                    number=iss_num,
                    defaults={'quarter': quarter, 'published_at': post_date.split(' ')[0]}
                )

            # 3.3. Resolve Authors
            primary_author = None
            co_author_names = []

            if paper_authors:
                primary_author_name = paper_authors[0]
                co_author_names = paper_authors[1:]
            else:
                # Fallback to post creator
                creator_info = wp_authors.get(creator, {})
                primary_author_name = creator_info.get('display_name') or creator

            # Find or create primary author user
            # To be 100% safe with Django's ASCIIUsernameValidator and prevent duplicate users for the same author:
            # We search by first_name (display name) or created in this session.
            if not hasattr(self, 'imported_authors'):
                self.imported_authors = {}

            primary_author = self.imported_authors.get(primary_author_name)
            if not primary_author:
                primary_author = User.objects.filter(first_name=primary_author_name).first()

            if not primary_author:
                # Create a new user with a safe ASCII username
                username = f"author_wp_{post_id}"
                email = f"{username}@marciledu.com"
                
                # Check if this fallback email/username already exists (should not, but just in case)
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
                self.safe_write(f"  Created user: {primary_author}")
                
            self.imported_authors[primary_author_name] = primary_author

            # 3.4. Create ArticleSubmission
            submission = ArticleSubmission.objects.create(
                title=title,
                abstract=content,
                section=section,
                author=primary_author,
                status=SubmissionStatus.PUBLISHED
            )

            # Add tags (keywords)
            if tags:
                submission.keywords.add(*tags)

            # Add co-authors
            for order, co_name in enumerate(co_author_names):
                CoAuthor.objects.create(
                    submission=submission,
                    full_name=co_name,
                    order=order
                )

            # 3.5. Download & Attach PDFs
            pdf_urls = attachments_by_parent.get(post_id, [])
            manuscript = None

            for pdf_url in pdf_urls:
                if not pdf_url.endswith('.pdf'):
                    continue
                self.safe_write(f"  Downloading PDF: {pdf_url}")
                try:
                    res = requests.get(pdf_url, headers=headers, timeout=15)
                    if res.status_code == 200:
                        filename = pdf_url.split('/')[-1]
                        manuscript = ManuscriptFile(
                            submission=submission,
                            version=1,
                            is_current=True
                        )
                        manuscript.file.save(filename, ContentFile(res.content), save=True)
                        self.safe_write(f"    Saved manuscript file: {filename}")
                        break # Standard is one PDF per article
                except Exception as e:
                    self.safe_write(f"    Failed to download PDF {pdf_url}: {e}", self.style.ERROR)

            if not manuscript:
                # Create a placeholder manuscript file if download failed
                self.safe_write("  No PDF attached. Creating placeholder manuscript file.", self.style.WARNING)
                manuscript = ManuscriptFile(
                    submission=submission,
                    version=1,
                    is_current=True
                )
                manuscript.file.save(f"placeholder_{post_id}.pdf", ContentFile(b"%PDF-1.4 ... placeholder"), save=True)

            # 3.6. Create PublishedArticle
            keywords_str = ', '.join(tags)
            slug = clean_arabic_slug(post_name or title)
            
            # Check for slug uniqueness
            base_slug = slug
            slug_counter = 1
            while PublishedArticle.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{slug_counter}"
                slug_counter += 1

            article = PublishedArticle.objects.create(
                submission=submission,
                manuscript_file=manuscript,
                issue=issue,
                title=title,
                abstract=content,
                keywords=keywords_str[:500],
                section=section,
                slug=slug
            )

            # 3.7. Force override timestamps to match WordPress dates
            ArticleSubmission.objects.filter(pk=submission.pk).update(created_at=post_date, updated_at=post_date)
            ManuscriptFile.objects.filter(pk=manuscript.pk).update(uploaded_at=post_date)
            PublishedArticle.objects.filter(pk=article.pk).update(published_at=post_date)

            self.safe_write(f"  Successfully imported published article: {article}", self.style.SUCCESS)
            success_count += 1

        self.safe_write(f"\nImport finished! Successfully imported {success_count} articles.", self.style.SUCCESS)
