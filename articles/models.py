from django.db import models

class Article(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()

    def __str__(self):
        return self.title

class ReadStats(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE)
    user_id = models.IntegerField()
    read_count = models.IntegerField(default=0)
    last_read_time = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('article', 'user_id')