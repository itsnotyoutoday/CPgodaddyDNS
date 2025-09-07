from django.urls import re_path
from . import views

urlpatterns = [
    # DNS Integration Override
    re_path(r'^dns-home$', views.dns_home_override, name='godaddyDNSHome'),
    
    # Main configuration
    re_path(r'^config$', views.godaddy_config, name='godaddyConfig'),
    re_path(r'^save-config$', views.save_config, name='godaddySaveConfig'),
    
    # Domain management
    re_path(r'^domains$', views.domain_management, name='godaddyDomains'),
    re_path(r'^discover-domains$', views.discover_domains, name='godaddyDiscoverDomains'),
    re_path(r'^toggle-domain-sync$', views.toggle_domain_sync, name='godaddyToggleDomainSync'),
    
    # Sync management
    re_path(r'^sync-status$', views.sync_status, name='godaddySyncStatus'),
    re_path(r'^manual-sync$', views.manual_sync, name='godaddyManualSync'),
    re_path(r'^get-sync-logs$', views.get_sync_logs, name='godaddyGetSyncLogs'),
    
    # DNS record management
    re_path(r'^manage-records$', views.manage_dns_records, name='godaddyManageRecords'),
    re_path(r'^get-domain-records$', views.get_domain_records, name='godaddyGetDomainRecords'),
    
    # Plugin status
    re_path(r'^status$', views.plugin_status, name='godaddyStatus'),
]