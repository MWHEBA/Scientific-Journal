from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.messages import get_messages
from apps.accounts.models import User

class AuthMessagesTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Create a test user
        self.user = User.objects.create_user(
            username='testuser',
            password='testpassword123',
            email='test@example.com',
            first_name='Test',
            last_name='User',
            role='author'
        )

    @override_settings(DEBUG=True)
    def test_login_failure_arabic(self):
        # Set session language to Arabic
        session = self.client.session
        session['site_language'] = 'ar'
        session.save()

        response = self.client.post(reverse('accounts:login'), {
            'username': 'testuser',
            'password': 'wrongpassword'
        })
        
        # Should render login page again (status 200)
        self.assertEqual(response.status_code, 200)
        
        # Check messages
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(len(messages) > 0)
        self.assertEqual(str(messages[0]), 'اسم المستخدم أو كلمة المرور غير صحيحة. يرجى المحاولة مرة أخرى.')
        self.assertContains(response, 'اسم المستخدم أو كلمة المرور غير صحيحة')

    @override_settings(DEBUG=True)
    def test_login_failure_english(self):
        # Set session language to English
        session = self.client.session
        session['site_language'] = 'en'
        session.save()

        response = self.client.post(reverse('accounts:login'), {
            'username': 'testuser',
            'password': 'wrongpassword'
        })
        
        self.assertEqual(response.status_code, 200)
        
        # Check messages
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(len(messages) > 0)
        self.assertEqual(str(messages[0]), 'Incorrect username or password. Please try again.')
        self.assertContains(response, 'Incorrect username or password')

    @override_settings(DEBUG=True)
    def test_login_success_arabic(self):
        session = self.client.session
        session['site_language'] = 'ar'
        session.save()

        response = self.client.post(reverse('accounts:login'), {
            'username': 'testuser',
            'password': 'testpassword123'
        })
        
        # Successful login redirects to dashboard (status 302)
        self.assertEqual(response.status_code, 302)
        
        # Follow redirect to dashboard
        response = self.client.get(response.url)
        
        # Check success message on dashboard
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(len(messages) > 0)
        self.assertEqual(str(messages[0]), 'تم تسجيل الدخول بنجاح. مرحباً بك مجدداً!')
        self.assertContains(response, 'تم تسجيل الدخول بنجاح')

    @override_settings(DEBUG=True)
    def test_login_success_english(self):
        session = self.client.session
        session['site_language'] = 'en'
        session.save()

        response = self.client.post(reverse('accounts:login'), {
            'username': 'testuser',
            'password': 'testpassword123'
        })
        
        self.assertEqual(response.status_code, 302)
        
        response = self.client.get(response.url)
        
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(len(messages) > 0)
        self.assertEqual(str(messages[0]), 'Logged in successfully. Welcome back!')
        self.assertContains(response, 'Logged in successfully')

    @override_settings(DEBUG=True)
    def test_registration_success_arabic(self):
        session = self.client.session
        session['site_language'] = 'ar'
        session.save()

        response = self.client.post(reverse('accounts:register'), {
            'username': 'newauthor',
            'first_name': 'New',
            'last_name': 'Author',
            'email': 'new@example.com',
            'password1': 'newpassword123',
            'password2': 'newpassword123'
        })
        
        # Success redirects to login page (status 302)
        self.assertEqual(response.status_code, 302)
        
        # Follow redirect to login page
        response = self.client.get(response.url)
        
        # Check success message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(len(messages) > 0)
        self.assertEqual(str(messages[0]), 'تم إنشاء حسابك بنجاح! يمكنك الآن تسجيل الدخول.')
        self.assertContains(response, 'تم إنشاء حسابك بنجاح')

    @override_settings(DEBUG=True)
    def test_registration_success_english(self):
        session = self.client.session
        session['site_language'] = 'en'
        session.save()

        response = self.client.post(reverse('accounts:register'), {
            'username': 'newauthor2',
            'first_name': 'New2',
            'last_name': 'Author2',
            'email': 'new2@example.com',
            'password1': 'newpassword123',
            'password2': 'newpassword123'
        })
        
        self.assertEqual(response.status_code, 302)
        
        response = self.client.get(response.url)
        
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(len(messages) > 0)
        self.assertEqual(str(messages[0]), 'Your account has been created successfully! You can now log in.')
        self.assertContains(response, 'Your account has been created successfully')


class AdminUserEditTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Create an admin user
        self.admin = User.objects.create_superuser(
            username='adminuser',
            password='adminpassword123',
            email='admin@example.com',
            first_name='Admin',
            last_name='User',
            role='admin'
        )
        # Create a regular author user to edit
        self.author = User.objects.create_user(
            username='authoruser',
            password='authorpassword123',
            email='author@example.com',
            first_name='Author',
            last_name='User',
            role='author'
        )

    def test_unauthorized_user_cannot_edit(self):
        # Log in as a regular author
        self.client.login(username='authoruser', password='authorpassword123')
        
        response = self.client.post(reverse('dashboard:user_edit', kwargs={'pk': self.author.pk}), {
            'username': 'newusername',
            'first_name': 'NewName',
            'last_name': 'NewLast',
            'email': 'newauthor@example.com',
            'role': 'author'
        })
        # Should redirect to login or show 403/Forbidden depending on AdminRequiredMixin
        self.assertEqual(response.status_code, 403)

    def test_admin_can_edit_user_details(self):
        # Log in as admin
        self.client.login(username='adminuser', password='adminpassword123')
        
        response = self.client.post(reverse('dashboard:user_edit', kwargs={'pk': self.author.pk}), {
            'username': 'editedauthor',
            'first_name': 'Edited',
            'last_name': 'AuthorName',
            'email': 'editedauthor@example.com',
            'role': 'author'
        })
        
        self.assertEqual(response.status_code, 302)
        
        # Verify changes in DB
        self.author.refresh_from_db()
        self.assertEqual(self.author.username, 'editedauthor')
        self.assertEqual(self.author.first_name, 'Edited')
        self.assertEqual(self.author.last_name, 'AuthorName')
        self.assertEqual(self.author.email, 'editedauthor@example.com')

    def test_admin_can_change_password(self):
        self.client.login(username='adminuser', password='adminpassword123')
        
        response = self.client.post(reverse('dashboard:user_edit', kwargs={'pk': self.author.pk}), {
            'username': 'authoruser',
            'first_name': 'Author',
            'last_name': 'User',
            'email': 'author@example.com',
            'role': 'author',
            'password': 'newpassword456'
        })
        
        self.assertEqual(response.status_code, 302)
        
        # Verify new password is set and user can authenticate with it
        from django.contrib.auth import authenticate
        user = authenticate(username='authoruser', password='newpassword456')
        self.assertIsNotNone(user)

    def test_admin_can_change_role_and_creates_profile(self):
        self.client.login(username='adminuser', password='adminpassword123')
        
        # Change author's role to reviewer
        response = self.client.post(reverse('dashboard:user_edit', kwargs={'pk': self.author.pk}), {
            'username': 'authoruser',
            'first_name': 'Author',
            'last_name': 'User',
            'email': 'author@example.com',
            'role': 'reviewer'
        })
        
        self.assertEqual(response.status_code, 302)
        self.author.refresh_from_db()
        self.assertEqual(self.author.role, 'reviewer')
        
        # Verify ReviewerProfile is created
        from apps.accounts.models import ReviewerProfile
        self.assertTrue(ReviewerProfile.objects.filter(user=self.author).exists())

