from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_AUTHOR   = 'author'
    ROLE_REVIEWER = 'reviewer'
    ROLE_ADMIN    = 'admin'
    ROLE_CHOICES  = [
        (ROLE_AUTHOR,   'مؤلف'),
        (ROLE_REVIEWER, 'مراجع'),
        (ROLE_ADMIN,    'مشرف'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_AUTHOR)

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.role})"


class AuthorProfile(models.Model):
    user        = models.OneToOneField(User, on_delete=models.CASCADE,
                                       related_name='author_profile')
    institution = models.CharField(max_length=255, blank=True)
    bio         = models.TextField(blank=True)
    orcid       = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return f"AuthorProfile: {self.user.username}"


class ReviewerProfile(models.Model):
    user         = models.OneToOneField(User, on_delete=models.CASCADE,
                                        related_name='reviewer_profile')
    specialties  = models.ManyToManyField('submissions.JournalSection', blank=True)
    institution  = models.CharField(max_length=255, blank=True)
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return f"ReviewerProfile: {self.user.username}"
