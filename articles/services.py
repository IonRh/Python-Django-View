import logging
from concurrent.futures import ThreadPoolExecutor
from django.core.cache import cache
from django_redis import get_redis_connection
from django.db import transaction, OperationalError, models
from redis.exceptions import RedisError
from .models import ReadStats

executor = ThreadPoolExecutor(max_workers=5)

class CacheMonitor:
    def __init__(self):
        self.redis = get_redis_connection("default")
        self.hits_key = "article:cache_hits"
        self.misses_key = "article:cache_misses"

    def record_hit(self):
        self.redis.incr(self.hits_key)

    def record_miss(self):
        self.redis.incr(self.misses_key)

    def get_hit_rate(self):
        hits = int(self.redis.get(self.hits_key) or 0)
        misses = int(self.redis.get(self.misses_key) or 0)
        total = hits + misses
        return round(hits / total * 100, 2) if total > 0 else 0.0

class ReadStatsService:
    def __init__(self):
        self.redis = get_redis_connection("default")
        self.cache_timeout = 3600

    def get_total_reads(self, article_id):
        cache_key = f"article:total_reads:{article_id}"
        monitor = CacheMonitor()
        try:
            total_reads = cache.get(cache_key)
            if total_reads is None:
                monitor.record_miss()
                try:
                    total_reads = ReadStats.objects.filter(article_id=article_id).aggregate(
                        total=models.Sum('read_count')
                    )['total'] or 0
                    cache.set(cache_key, total_reads, self.cache_timeout)
                except OperationalError as e:
                    print(f"SQLite error: {e}")
                    total_reads = 0
            else:
                monitor.record_hit()
            return total_reads
        except RedisError as e:
            print(f"Redis error: {e}")
            try:
                total_reads = ReadStats.objects.filter(article_id=article_id).aggregate(
                    total=models.Sum('read_count')
                )['total'] or 0
                return total_reads
            except OperationalError as e:
                print(f"Fallback SQLite error: {e}")
                return 0

    def get_user_reads(self, article_id, user_id):
        cache_key = f"article:user_reads:{article_id}:{user_id}"
        monitor = CacheMonitor()
        try:
            read_count = cache.get(cache_key)
            if read_count is None:
                monitor.record_miss()
                try:
                    read_stats = ReadStats.objects.get(article_id=article_id, user_id=user_id)
                    read_count = read_stats.read_count
                except ReadStats.DoesNotExist:
                    read_count = 0
                except OperationalError as e:
                    print(f"SQLite error: {e}")
                    read_count = 0
                cache.set(cache_key, read_count, self.cache_timeout)
            else:
                monitor.record_hit()
            return read_count
        except RedisError as e:
            print(f"Redis error: {e}")
            try:
                read_stats = ReadStats.objects.get(article_id=article_id, user_id=user_id)
                return read_stats.read_count
            except (ReadStats.DoesNotExist, OperationalError):
                return 0

    def get_unique_users(self, article_id):
        cache_key = f"article:unique_users:{article_id}"
        monitor = CacheMonitor()
        try:
            unique_users = self.redis.scard(cache_key)
            if unique_users == 0:
                monitor.record_miss()
                try:
                    unique_users = ReadStats.objects.filter(article_id=article_id).values('user_id').distinct().count()
                    if unique_users > 0:
                        user_ids = ReadStats.objects.filter(article_id=article_id).values_list('user_id', flat=True)
                        self.redis.sadd(cache_key, *user_ids)
                        self.redis.expire(cache_key, self.cache_timeout)
                except OperationalError as e:
                    print(f"SQLite error: {e}")
                    unique_users = 0
            else:
                monitor.record_hit()
            return unique_users
        except RedisError as e:
            print(f"Redis error: {e}")
            try:
                return ReadStats.objects.filter(article_id=article_id).values('user_id').distinct().count()
            except OperationalError:
                return 0

    def _update_read_stats_db(self, article_id, user_id):
        try:
            print(f"更新数据库统计: article_id={article_id}, user_id={user_id}")
            with transaction.atomic():
                read_stats, created = ReadStats.objects.get_or_create(
                    article_id=article_id,
                    user_id=user_id,
                    defaults={'read_count': 1}
                )
                if not created:
                    old_count = read_stats.read_count
                    read_stats.read_count += 1
                    read_stats.save()
                    print(f"更新成功: 从 {old_count} 增加到 {read_stats.read_count}")
                else:
                    print(f"创建新记录: read_count=1")
                
                # 清除相关缓存
                cache_keys = [
                    f"article:total_reads:{article_id}",
                    f"article:user_reads:{article_id}:{user_id}"
                ]
                cache.delete_many(cache_keys)
                print(f"清除缓存: {cache_keys}")
                
        except Exception as e:
            print(f"数据库更新错误: {e}")

    def increment_read(self, article_id, user_id):
        print(f"increment_read 调用: article_id={article_id}, user_id={user_id}")
        
        cache_key_total = f"article:total_reads:{article_id}"
        cache_key_user = f"article:user_reads:{article_id}:{user_id}"
        cache_key_users = f"article:unique_users:{article_id}"
        
        # 更新Redis缓存
        try:
            with self.redis.pipeline() as pipe:
                pipe.incr(cache_key_total)
                pipe.incr(cache_key_user)
                pipe.sadd(cache_key_users, user_id)
                pipe.expire(cache_key_total, self.cache_timeout)
                pipe.expire(cache_key_user, self.cache_timeout)
                pipe.expire(cache_key_users, self.cache_timeout)
                pipe.execute()
            print("Redis 缓存更新成功")
        except RedisError as e:
            print(f"Redis 写入错误: {e}")
        
        # 同步更新数据库
        try:
            self._update_read_stats_db(article_id, user_id)
        except Exception as e:
            print(f"同步数据库更新失败，使用异步方式: {e}")
            # 如果同步失败，使用异步方式
            executor.submit(self._update_read_stats_db, article_id, user_id)