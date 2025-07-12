from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
import time
from .services import ReadStatsService, CacheMonitor


@require_http_methods(["GET"])
def article_stats_api(request, article_id):
    start_time = time.time()
    
    service = ReadStatsService()
    monitor = CacheMonitor()
    user_id = request.user.id if request.user.is_authenticated else 0
    service.increment_read(article_id, user_id)

    data = {
        'total_reads': service.get_total_reads(article_id),
        'user_reads': service.get_user_reads(article_id, user_id),
        'unique_users': service.get_unique_users(article_id),
        'cache_hit_rate': monitor.get_hit_rate(),
        'response_time_ms': round((time.time() - start_time) * 1000, 2),
    }
    return JsonResponse(data)


def article_stats_page(request, article_id):
    start_time = time.time()
    
    service = ReadStatsService()
    monitor = CacheMonitor()
    user_id = request.user.id if request.user.is_authenticated else 0
    # service.increment_read(article_id, user_id)

    context = {
        'article_id': article_id,
        'total_reads': service.get_total_reads(article_id),
        'user_reads': service.get_user_reads(article_id, user_id),
        'unique_users': service.get_unique_users(article_id),
        'cache_hit_rate': monitor.get_hit_rate(),
        'response_time_ms': round((time.time() - start_time) * 1000, 2),
    }
    return render(request, 'articles/stats.html', context)
