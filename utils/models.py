from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class Notification(models.Model):
    """Notification model - moved here to break circular imports"""
    title = models.CharField(max_length=200)
    message = models.TextField()
    
    recipient_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')
    recipient_object_id = models.PositiveIntegerField()
    recipient = GenericForeignKey('recipient_content_type', 'recipient_object_id')
    
    sender_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')
    sender_object_id = models.PositiveIntegerField()
    sender = GenericForeignKey('sender_content_type', 'sender_object_id')
    
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.title
