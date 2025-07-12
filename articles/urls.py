from django.urls import path
from .views import article_stats_api, article_stats_page

urlpatterns = [
    path('articles/<int:article_id>/stats/', article_stats_api, name='article-stats'),
    path('articles/<int:article_id>/stats-page/', article_stats_page, name='article-stats-page'),
]