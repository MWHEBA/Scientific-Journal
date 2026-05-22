from django.urls import path
from apps.dashboard.views import (
    DashboardHomeRedirectView,
    AuthorDashboardView,
    AuthorDraftsView,
    AuthorPublishedArticlesView,
    ReviewerDashboardView,
    ReviewerSubmissionsView,
    ReviewerPostReviewView,
    ReviewerArticlesView,
    ReviewerSubmissionDetailView,
    AssignReviewerView,
    SiteSettingsView,
    AdminDashboardView,
    AdminSubmissionsView,
    AdminArticlesView,
    AdminSubmissionDetailView,
    AdminPaymentsView,
    VolumeCreateView,
    VolumeManagementView,
    VolumeUpdateView,
    IssueCreateView,
    IssueUpdateView,
    IssueManagementView,
    AssignArticleToIssueView,
    UserManagementView,
    ReviewerManagementView,
    AdminImpersonateStartView,
    AdminImpersonateStopView,
)

app_name = 'dashboard'

urlpatterns = [
    path('',                                DashboardHomeRedirectView.as_view(),  name='home'),
    # المؤلف
    path('author/',                         AuthorDashboardView.as_view(),        name='author'),
    path('author/drafts/',                  AuthorDraftsView.as_view(),           name='author_drafts'),
    path('author/published/',               AuthorPublishedArticlesView.as_view(), name='author_published'),

    # المراجع
    path('reviewer/',                       ReviewerDashboardView.as_view(),      name='reviewer'),
    path('reviewer/submissions/',           ReviewerSubmissionsView.as_view(),    name='reviewer_submissions'),
    path('reviewer/post-review/',           ReviewerPostReviewView.as_view(),     name='reviewer_post_review'),
    path('reviewer/submissions/<int:pk>/',  ReviewerSubmissionDetailView.as_view(), name='reviewer_submission_detail'),
    path('reviewer/articles/',              ReviewerArticlesView.as_view(),       name='reviewer_articles'),

    # المشرف — الرئيسية
    path('admin/',                          AdminDashboardView.as_view(),         name='admin'),

    # المشرف — التقديمات
    path('admin/submissions/',              AdminSubmissionsView.as_view(),       name='admin_submissions'),
    path('admin/articles/',                 AdminArticlesView.as_view(),          name='admin_articles'),
    path('admin/submissions/<int:pk>/',     AdminSubmissionDetailView.as_view(),  name='submission_detail'),

    # المشرف — الدفعات
    path('admin/payments/',                 AdminPaymentsView.as_view(),          name='admin_payments'),

    # المشرف — تعيين مراجع
    path('admin/assign/<int:pk>/',          AssignReviewerView.as_view(),         name='assign_reviewer'),

    # المشرف — المجلدات والأعداد
    path('admin/volumes/',                  VolumeManagementView.as_view(),       name='volumes'),
    path('admin/volumes/<int:pk>/edit/',    VolumeUpdateView.as_view(),           name='volume_update'),
    path('admin/issues/',                   IssueManagementView.as_view(),        name='issues'),
    path('admin/issues/create/',            IssueCreateView.as_view(),            name='issue_create'),
    path('admin/issues/<int:pk>/edit/',     IssueUpdateView.as_view(),            name='issue_update'),
    path('admin/articles/<int:pk>/assign/', AssignArticleToIssueView.as_view(),   name='assign_article'),

    # المشرف — المراجعون
    path('admin/reviewers/',                ReviewerManagementView.as_view(),     name='reviewers'),

    # المشرف — المستخدمون
    path('admin/users/',                    UserManagementView.as_view(),         name='users'),
    path('admin/users/<int:pk>/impersonate/', AdminImpersonateStartView.as_view(), name='impersonate_start'),
    path('admin/users/impersonate/stop/',   AdminImpersonateStopView.as_view(),   name='impersonate_stop'),

    # المشرف — الإعدادات
    path('admin/settings/',                 SiteSettingsView.as_view(),           name='settings'),
]
