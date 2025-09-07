#!/usr/local/CyberCP/bin/python
import sys
import os
import django
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

# Setup Django
sys.path.append('/usr/local/CyberCP')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "CyberCP.settings")
django.setup()

from godaddyDNS.models import GoDaddyConfig, GoDaddySyncLog
from godaddyDNS.sync_manager import SyncManager
from godaddyDNS.domain_discovery import refresh_domain_cache

class Command(BaseCommand):
    help = 'Sync DNS records between CyberPanel and GoDaddy'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='Sync specific user only'
        )
        parser.add_argument(
            '--domain',
            type=str,
            help='Sync specific domain only'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force sync even if recently synced'
        )
        parser.add_argument(
            '--refresh-domains',
            action='store_true',
            help='Refresh domain discovery cache'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without making changes'
        )
        parser.add_argument(
            '--max-age',
            type=int,
            default=15,
            help='Skip sync if last sync was within this many minutes (default: 15)'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Verbose output'
        )
    
    def handle(self, *args, **options):
        start_time = timezone.now()
        
        if options['verbose']:
            self.stdout.write("Starting GoDaddy DNS sync...")
        
        try:
            # Get configurations to sync
            configs = self._get_configs_to_sync(options)
            
            if not configs:
                if options['verbose']:
                    self.stdout.write("No active GoDaddy configurations found")
                return
            
            total_synced = 0
            total_errors = 0
            
            for config in configs:
                try:
                    result = self._sync_config(config, options)
                    total_synced += result.get('domains_processed', 0)
                    
                    if result.get('errors'):
                        total_errors += len(result['errors'])
                        for error in result['errors']:
                            self.stderr.write(self.style.ERROR(f"User {config.user_id}: {error}"))
                    
                    if options['verbose']:
                        self._print_sync_result(config, result)
                        
                except Exception as e:
                    total_errors += 1
                    error_msg = f"Sync failed for user {config.user_id}: {str(e)}"
                    self.stderr.write(self.style.ERROR(error_msg))
            
            # Summary
            duration = (timezone.now() - start_time).total_seconds()
            
            if options['verbose']:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Sync completed in {duration:.1f}s. "
                        f"Processed {total_synced} domains with {total_errors} errors."
                    )
                )
            
            # Exit with error code if there were errors
            if total_errors > 0:
                sys.exit(1)
                
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Sync command failed: {str(e)}"))
            sys.exit(1)
    
    def _get_configs_to_sync(self, options):
        """Get GoDaddy configurations that should be synced"""
        queryset = GoDaddyConfig.objects.filter(is_active=True, sync_enabled=True)
        
        if options['user_id']:
            queryset = queryset.filter(user_id=options['user_id'])
        
        configs = list(queryset)
        
        if not options['force']:
            # Filter out recently synced configs
            max_age_minutes = options['max_age']
            cutoff_time = timezone.now() - timedelta(minutes=max_age_minutes)
            
            configs = [
                config for config in configs
                if not config.last_sync or config.last_sync < cutoff_time
            ]
        
        return configs
    
    def _sync_config(self, config: GoDaddyConfig, options):
        """Sync a single user configuration"""
        try:
            # Refresh domain cache if requested
            if options['refresh_domains']:
                if options['verbose']:
                    self.stdout.write(f"Refreshing domain cache for user {config.user_id}...")
                
                cache_result = refresh_domain_cache(config)
                if not cache_result.get('success'):
                    self.stderr.write(
                        self.style.WARNING(
                            f"Domain cache refresh failed for user {config.user_id}: "
                            f"{cache_result.get('error', 'Unknown error')}"
                        )
                    )
            
            # Perform sync
            if options['dry_run']:
                return self._dry_run_sync(config, options)
            else:
                return self._perform_sync(config, options)
                
        except Exception as e:
            raise CommandError(f"Sync failed for user {config.user_id}: {str(e)}")
    
    def _perform_sync(self, config: GoDaddyConfig, options):
        """Perform actual sync"""
        sync_manager = SyncManager(config.user_id)
        
        domain_name = options.get('domain')
        return sync_manager.full_sync(domain_name)
    
    def _dry_run_sync(self, config: GoDaddyConfig, options):
        """Simulate sync without making changes"""
        # This would require modifications to sync_manager to support dry-run mode
        # For now, just return a placeholder
        return {
            'domains_processed': 0,
            'records_created': 0,
            'records_updated': 0,
            'records_deleted': 0,
            'conflicts_resolved': 0,
            'errors': [],
            'dry_run': True
        }
    
    def _print_sync_result(self, config: GoDaddyConfig, result):
        """Print sync result in verbose mode"""
        if result.get('dry_run'):
            self.stdout.write(f"[DRY RUN] User {config.user_id}:")
        else:
            self.stdout.write(f"User {config.user_id}:")
        
        self.stdout.write(f"  Domains processed: {result.get('domains_processed', 0)}")
        self.stdout.write(f"  Records created: {result.get('records_created', 0)}")
        self.stdout.write(f"  Records updated: {result.get('records_updated', 0)}")
        self.stdout.write(f"  Records deleted: {result.get('records_deleted', 0)}")
        self.stdout.write(f"  Conflicts resolved: {result.get('conflicts_resolved', 0)}")
        
        if result.get('errors'):
            self.stdout.write(f"  Errors: {len(result['errors'])}")


class DomainDiscoveryCommand(BaseCommand):
    """Separate command for domain discovery"""
    help = 'Refresh GoDaddy domain discovery cache'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='Refresh specific user only'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Verbose output'
        )
    
    def handle(self, *args, **options):
        try:
            queryset = GoDaddyConfig.objects.filter(is_active=True)
            
            if options['user_id']:
                queryset = queryset.filter(user_id=options['user_id'])
            
            total_processed = 0
            total_errors = 0
            
            for config in queryset:
                try:
                    if options['verbose']:
                        self.stdout.write(f"Refreshing domains for user {config.user_id}...")
                    
                    result = refresh_domain_cache(config)
                    
                    if result.get('success'):
                        total_processed += 1
                        if options['verbose']:
                            self.stdout.write(
                                f"  Found {result.get('domains_found', 0)} domains "
                                f"({result.get('server_hosted', 0)} server-hosted, "
                                f"{result.get('external_hosted', 0)} external, "
                                f"{result.get('parked', 0)} parked)"
                            )
                    else:
                        total_errors += 1
                        self.stderr.write(
                            self.style.ERROR(
                                f"User {config.user_id}: {result.get('error', 'Unknown error')}"
                            )
                        )
                        
                except Exception as e:
                    total_errors += 1
                    self.stderr.write(
                        self.style.ERROR(f"User {config.user_id}: {str(e)}")
                    )
            
            if options['verbose']:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Domain discovery completed. "
                        f"Processed {total_processed} users with {total_errors} errors."
                    )
                )
            
            if total_errors > 0:
                sys.exit(1)
                
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Domain discovery failed: {str(e)}"))
            sys.exit(1)