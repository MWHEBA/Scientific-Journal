from django.urls import path
from apps.submissions.views import (
    SubmissionCreateView,
    SubmissionUpdateView,
    SubmissionSubmitView,
    RevisionUploadView,
    SubmissionWithdrawView,
    SubmissionArchiveView,
    SubmissionUnarchiveView,
)

app_name = 'submissions'

urlpatterns = [
    path('new/',              SubmissionCreateView.as_view(), name='create'),
    path('<int:pk>/edit/',    SubmissionUpdateView.as_view(), name='edit'),
    path('<int:pk>/submit/',  SubmissionSubmitView.as_view(), name='submit'),
    path('<int:pk>/revise/',  RevisionUploadView.as_view(),   name='revise'),
    path('<int:pk>/withdraw/',  SubmissionWithdrawView.as_view(),   name='withdraw'),
    path('<int:pk>/archive/', SubmissionArchiveView.as_view(), name='archive'),
    path('<int:pk>/unarchive/', SubmissionUnarchiveView.as_view(), name='unarchive'),
]
