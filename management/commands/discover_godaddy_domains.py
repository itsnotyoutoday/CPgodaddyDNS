#!/usr/local/CyberCP/bin/python
import sys
import os
import django

# Setup Django
sys.path.append('/usr/local/CyberCP')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "CyberCP.settings")
django.setup()

from django.core.management.base import BaseCommand
from godaddyDNS.models import GoDaddyConfig
from godaddyDNS.domain_discovery import refresh_domain_cache

class Command(BaseCommand):
    help = 'Discover and classify domains in GoDaddy accounts'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='Discover domains for specific user only'
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
                        self.stdout.write(f"Discovering domains for user {config.user_id}...")
                    
                    result = refresh_domain_cache(config)
                    
                    if result.get('success'):
                        total_processed += 1
                        if options['verbose']:
                            self.stdout.write(
                                f"  Found {result.get('domains_found', 0)} domains:"
                            )
                            self.stdout.write(
                                f"    Server-hosted: {result.get('server_hosted', 0)}"
                            )
                            self.stdout.write(
                                f"    External: {result.get('external_hosted', 0)}"
                            )
                            self.stdout.write(
                                f"    Parked: {result.get('parked', 0)}"
                            )
                            if result.get('errors', 0) > 0:
                                self.stdout.write(
                                    f"    Errors: {result.get('errors', 0)}"
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