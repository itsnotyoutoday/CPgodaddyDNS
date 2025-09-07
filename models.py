from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from loginSystem.models import Administrator
import json

class GoDaddyConfig(models.Model):
    """GoDaddy API configuration per user"""
    user = models.OneToOneField(Administrator, on_delete=models.CASCADE, related_name='godaddy_config')
    api_key = models.CharField(max_length=255, help_text="GoDaddy API Key")
    api_secret = models.CharField(max_length=255, help_text="GoDaddy API Secret") 
    is_active = models.BooleanField(default=False, help_text="Enable GoDaddy DNS sync")
    use_production = models.BooleanField(default=False, help_text="Use production API (vs OTE testing)")
    
    # Sync settings
    sync_enabled = models.BooleanField(default=True, help_text="Enable automatic sync")
    conflict_strategy = models.CharField(
        max_length=20,
        choices=[
            ('godaddy_wins', 'GoDaddy Takes Precedence'),
            ('manual', 'Queue for Manual Review'),
            ('timestamp', 'Use Modification Timestamps')
        ],
        default='godaddy_wins'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    last_domain_refresh = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        app_label = 'godaddyDNS'
        db_table = 'godaddy_config'
        verbose_name = 'GoDaddy Configuration'
        verbose_name_plural = 'GoDaddy Configurations'
    
    def __str__(self):
        return f"GoDaddy Config for {self.user.userName}"
    
    def save(self, *args, **kwargs):
        # Validate API credentials format
        if self.api_key and len(self.api_key) < 10:
            raise ValidationError("API Key appears to be too short")
        if self.api_secret and len(self.api_secret) < 10:
            raise ValidationError("API Secret appears to be too short")
        super().save(*args, **kwargs)

class GoDaddyDomainCache(models.Model):
    """Cache of domains available in user's GoDaddy account"""
    config = models.ForeignKey(GoDaddyConfig, on_delete=models.CASCADE, related_name='cached_domains')
    domain_name = models.CharField(max_length=255, db_index=True)
    
    # Domain info from GoDaddy API
    status = models.CharField(max_length=50, default='ACTIVE')
    expires_at = models.DateTimeField(null=True, blank=True)
    auto_renew = models.BooleanField(default=False)
    
    # DNS hosting classification
    hosting_type = models.CharField(
        max_length=20,
        choices=[
            ('server_hosted', 'Hosted on Server'),
            ('external_hosted', 'Hosted Elsewhere'), 
            ('parked', 'Parked/No Hosting'),
            ('unknown', 'Unable to Determine')
        ],
        default='unknown'
    )
    
    # Server IP analysis
    points_to_server = models.BooleanField(default=False)
    detected_ips = models.JSONField(default=list, help_text="List of A record IPs detected")
    
    # Sync tracking
    last_synced = models.DateTimeField(null=True, blank=True)
    sync_enabled = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'godaddyDNS'
        db_table = 'godaddy_domain_cache'
        unique_together = ('config', 'domain_name')
        indexes = [
            models.Index(fields=['domain_name']),
            models.Index(fields=['hosting_type']),
            models.Index(fields=['points_to_server']),
        ]
    
    def __str__(self):
        return f"{self.domain_name} ({self.hosting_type})"

class GoDaddySyncLog(models.Model):
    """Log of sync operations"""
    config = models.ForeignKey(GoDaddyConfig, on_delete=models.CASCADE, related_name='sync_logs')
    
    sync_type = models.CharField(
        max_length=20,
        choices=[
            ('scheduled', 'Scheduled Sync'),
            ('manual', 'Manual Sync'),
            ('triggered', 'Triggered by Change'),
            ('initial', 'Initial Import')
        ]
    )
    
    # Target domain (null for full sync)
    domain_name = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    
    # Sync results
    status = models.CharField(
        max_length=20,
        choices=[
            ('running', 'In Progress'),
            ('completed', 'Completed Successfully'),
            ('failed', 'Failed'),
            ('partial', 'Completed with Errors')
        ],
        default='running'
    )
    
    # Statistics
    domains_processed = models.IntegerField(default=0)
    records_created = models.IntegerField(default=0)
    records_updated = models.IntegerField(default=0)
    records_deleted = models.IntegerField(default=0)
    conflicts_resolved = models.IntegerField(default=0)
    
    # Error tracking
    errors = models.JSONField(default=list)
    error_message = models.TextField(blank=True)
    
    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        app_label = 'godaddyDNS'
        db_table = 'godaddy_sync_log'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['sync_type']),
            models.Index(fields=['started_at']),
        ]
    
    def __str__(self):
        domain_str = f" ({self.domain_name})" if self.domain_name else ""
        return f"{self.sync_type.title()} sync{domain_str} - {self.status}"
    
    def duration_seconds(self):
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    def mark_completed(self):
        """Mark sync as completed"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save()
    
    def mark_failed(self, error_message):
        """Mark sync as failed with error message"""
        self.status = 'failed'
        self.error_message = error_message
        self.completed_at = timezone.now()
        self.save()

class GoDaddyRecordHistory(models.Model):
    """History of DNS record changes for conflict resolution"""
    config = models.ForeignKey(GoDaddyConfig, on_delete=models.CASCADE, related_name='record_history')
    domain_name = models.CharField(max_length=255, db_index=True)
    
    # Record identification
    record_name = models.CharField(max_length=255)
    record_type = models.CharField(max_length=10)
    
    # Change tracking
    change_type = models.CharField(
        max_length=20,
        choices=[
            ('created', 'Record Created'),
            ('updated', 'Record Updated'),
            ('deleted', 'Record Deleted'),
            ('conflict', 'Conflict Detected')
        ]
    )
    
    change_source = models.CharField(
        max_length=20,
        choices=[
            ('local', 'CyberPanel'),
            ('godaddy', 'GoDaddy'),
            ('sync', 'Sync Process')
        ]
    )
    
    # Record content
    old_content = models.TextField(blank=True)
    new_content = models.TextField(blank=True)
    old_ttl = models.IntegerField(null=True, blank=True)
    new_ttl = models.IntegerField(null=True, blank=True)
    old_priority = models.IntegerField(null=True, blank=True) 
    new_priority = models.IntegerField(null=True, blank=True)
    
    # Resolution tracking
    conflict_resolved = models.BooleanField(default=False)
    resolution_method = models.CharField(max_length=50, blank=True)
    
    changed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        app_label = 'godaddyDNS'
        db_table = 'godaddy_record_history'
        ordering = ['-changed_at']
        indexes = [
            models.Index(fields=['domain_name', 'record_name', 'record_type']),
            models.Index(fields=['change_type']),
            models.Index(fields=['changed_at']),
        ]
    
    def __str__(self):
        return f"{self.domain_name} {self.record_name} {self.record_type} - {self.change_type}"

class GoDaddyConflictQueue(models.Model):
    """Queue of conflicts requiring manual resolution"""
    config = models.ForeignKey(GoDaddyConfig, on_delete=models.CASCADE, related_name='conflict_queue')
    domain_name = models.CharField(max_length=255, db_index=True)
    
    # Record details
    record_name = models.CharField(max_length=255)
    record_type = models.CharField(max_length=10)
    
    # Conflict data
    local_data = models.JSONField(help_text="Local record data")
    godaddy_data = models.JSONField(help_text="GoDaddy record data")
    
    # Resolution
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Awaiting Resolution'),
            ('resolved_local', 'Resolved - Keep Local'),
            ('resolved_godaddy', 'Resolved - Keep GoDaddy'),
            ('resolved_custom', 'Resolved - Custom Value'),
            ('ignored', 'Ignored/Skipped')
        ],
        default='pending'
    )
    
    resolution_data = models.JSONField(null=True, blank=True)
    resolved_by = models.ForeignKey(Administrator, null=True, blank=True, on_delete=models.SET_NULL)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        app_label = 'godaddyDNS'
        db_table = 'godaddy_conflict_queue'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['domain_name']),
        ]
    
    def __str__(self):
        return f"Conflict: {self.domain_name} {self.record_name} {self.record_type}"