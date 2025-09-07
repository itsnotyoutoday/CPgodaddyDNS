#!/usr/local/CyberCP/bin/python
import logging
import socket
from typing import List, Dict, Optional, Set
from django.utils import timezone
from .gdapi import GoDaddyAPI, GoDaddyAPIException
from .models import GoDaddyConfig, GoDaddyDomainCache

logger = logging.getLogger(__name__)

class DomainClassifier:
    """Classify domains by their DNS hosting type"""
    
    def __init__(self, config: GoDaddyConfig):
        self.config = config
        self.gd_api = GoDaddyAPI(
            config.api_key, 
            config.api_secret, 
            config.use_production
        )
        self.server_ip = self._get_server_ip()
    
    def _get_server_ip(self) -> str:
        """Get this server's public IP address"""
        try:
            with open('/etc/cyberpanel/machineIP', 'r') as f:
                return f.read().strip().split('\n')[0]
        except Exception:
            # Fallback - try to detect IP
            try:
                import requests
                response = requests.get('https://api.ipify.org', timeout=10)
                return response.text.strip()
            except Exception:
                logger.warning("Could not determine server IP address")
                return "127.0.0.1"
    
    def discover_and_classify_domains(self) -> Dict[str, List[Dict]]:
        """Discover all domains in GoDaddy account and classify them"""
        try:
            # Get all domains from GoDaddy
            godaddy_domains = self.gd_api.get_owned_domains()
            
            classified = {
                'server_hosted': [],
                'external_hosted': [],
                'parked': [],
                'errors': []
            }
            
            for domain_info in godaddy_domains:
                domain_name = domain_info.get('domainName') or domain_info.get('domain')
                if not domain_name:
                    continue
                
                try:
                    classification = self._classify_single_domain(domain_name, domain_info)
                    classified[classification['type']].append(classification)
                    
                    # Update cache
                    self._update_domain_cache(domain_name, domain_info, classification)
                    
                except Exception as e:
                    logger.error(f"Failed to classify domain {domain_name}: {str(e)}")
                    classified['errors'].append({
                        'domain': domain_name,
                        'error': str(e)
                    })
            
            # Update last refresh timestamp
            self.config.last_domain_refresh = timezone.now()
            self.config.save()
            
            return classified
            
        except GoDaddyAPIException as e:
            logger.error(f"GoDaddy API error during domain discovery: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during domain discovery: {str(e)}")
            raise
    
    def _classify_single_domain(self, domain_name: str, domain_info: Dict) -> Dict:
        """Classify a single domain"""
        try:
            # Get DNS records for analysis
            dns_records = self.gd_api.get_domain_records(domain_name)
            
            # Analyze A records to determine hosting
            a_records = [r for r in dns_records if r.get('type') == 'A']
            
            classification = {
                'domain': domain_name,
                'status': domain_info.get('status', 'UNKNOWN'),
                'expires': domain_info.get('expires'),
                'auto_renew': domain_info.get('renewAuto', False),
                'records_count': len(dns_records),
                'a_records': a_records
            }
            
            if not a_records:
                # No A records - likely parked
                classification.update({
                    'type': 'parked',
                    'hosting_detail': 'No A records found',
                    'points_to_server': False,
                    'detected_ips': []
                })
            else:
                # Analyze A records
                hosting_analysis = self._analyze_a_records(domain_name, a_records)
                classification.update(hosting_analysis)
            
            return classification
            
        except Exception as e:
            logger.error(f"Error classifying domain {domain_name}: {str(e)}")
            return {
                'domain': domain_name,
                'type': 'errors',
                'error': str(e),
                'points_to_server': False,
                'detected_ips': []
            }
    
    def _analyze_a_records(self, domain_name: str, a_records: List[Dict]) -> Dict:
        """Analyze A records to determine hosting type"""
        detected_ips = []
        points_to_server = False
        external_ips = []
        
        # Look for root domain and www A records
        root_records = []
        www_records = []
        other_records = []
        
        for record in a_records:
            record_name = record.get('name', '@')
            record_data = record.get('data')
            
            if not record_data:
                continue
                
            detected_ips.append(record_data)
            
            if record_name in ['@', domain_name]:
                root_records.append(record)
            elif record_name in ['www', f'www.{domain_name}']:
                www_records.append(record)
            else:
                other_records.append(record)
            
            # Check if any A record points to our server
            if record_data == self.server_ip:
                points_to_server = True
            else:
                external_ips.append(record_data)
        
        # Determine hosting type based on analysis
        if points_to_server:
            if external_ips:
                hosting_type = 'server_hosted'
                hosting_detail = f'Mixed hosting - server IP {self.server_ip} and external IPs {external_ips}'
            else:
                hosting_type = 'server_hosted'
                hosting_detail = f'Fully hosted on server - IP {self.server_ip}'
        else:
            if detected_ips:
                hosting_type = 'external_hosted'
                hosting_detail = f'Hosted externally - IPs {detected_ips}'
            else:
                hosting_type = 'parked'
                hosting_detail = 'No valid A records found'
        
        return {
            'type': hosting_type,
            'hosting_detail': hosting_detail,
            'points_to_server': points_to_server,
            'detected_ips': detected_ips,
            'root_records_count': len(root_records),
            'www_records_count': len(www_records),
            'other_records_count': len(other_records)
        }
    
    def _update_domain_cache(self, domain_name: str, domain_info: Dict, classification: Dict):
        """Update or create domain cache entry"""
        try:
            cache_entry, created = GoDaddyDomainCache.objects.get_or_create(
                config=self.config,
                domain_name=domain_name,
                defaults={
                    'status': domain_info.get('status', 'ACTIVE'),
                    'auto_renew': domain_info.get('renewAuto', False),
                    'hosting_type': classification.get('type', 'unknown'),
                    'points_to_server': classification.get('points_to_server', False),
                    'detected_ips': classification.get('detected_ips', [])
                }
            )
            
            if not created:
                # Update existing entry
                cache_entry.status = domain_info.get('status', 'ACTIVE')
                cache_entry.auto_renew = domain_info.get('renewAuto', False)
                cache_entry.hosting_type = classification.get('type', 'unknown')
                cache_entry.points_to_server = classification.get('points_to_server', False)
                cache_entry.detected_ips = classification.get('detected_ips', [])
                cache_entry.save()
            
            # Parse expires date if available
            if 'expires' in domain_info and domain_info['expires']:
                try:
                    from datetime import datetime
                    expires_str = domain_info['expires']
                    # Handle different date formats that GoDaddy might use
                    for fmt in ['%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d']:
                        try:
                            expires_date = datetime.strptime(expires_str, fmt)
                            cache_entry.expires_at = expires_date
                            cache_entry.save()
                            break
                        except ValueError:
                            continue
                except Exception as e:
                    logger.warning(f"Could not parse expires date for {domain_name}: {str(e)}")
            
        except Exception as e:
            logger.error(f"Failed to update domain cache for {domain_name}: {str(e)}")

class DomainFilter:
    """Filter CyberPanel domains to show only GoDaddy-managed ones"""
    
    def __init__(self, config: GoDaddyConfig):
        self.config = config
    
    def get_manageable_domains(self) -> Dict[str, List[Dict]]:
        """Get domains that can be managed through this plugin"""
        # Get cached GoDaddy domains
        cached_domains = GoDaddyDomainCache.objects.filter(config=self.config)
        
        if not cached_domains.exists():
            # No cache - need to run discovery first
            return {
                'needs_discovery': True,
                'server_hosted': [],
                'external_hosted': [],
                'parked': []
            }
        
        # Group by hosting type
        result = {
            'needs_discovery': False,
            'server_hosted': [],
            'external_hosted': [],
            'parked': [],
            'last_updated': None
        }
        
        for domain_cache in cached_domains:
            domain_data = {
                'domain': domain_cache.domain_name,
                'status': domain_cache.status,
                'expires_at': domain_cache.expires_at,
                'points_to_server': domain_cache.points_to_server,
                'detected_ips': domain_cache.detected_ips,
                'last_synced': domain_cache.last_synced,
                'sync_enabled': domain_cache.sync_enabled
            }
            
            if domain_cache.hosting_type in result:
                result[domain_cache.hosting_type].append(domain_data)
        
        # Get last update time
        if cached_domains:
            result['last_updated'] = max(d.updated_at for d in cached_domains)
        
        return result
    
    def get_cyberpanel_dns_domains(self, user_id: int) -> List[Dict]:
        """Get domains that exist in CyberPanel DNS system"""
        try:
            from dns.models import Domains as DNSDomains
            
            dns_domains = DNSDomains.objects.filter(admin_id=user_id)
            godaddy_domain_names = set(
                GoDaddyDomainCache.objects.filter(config=self.config)
                .values_list('domain_name', flat=True)
            )
            
            # Return only domains that exist in both systems
            filtered_domains = []
            for dns_domain in dns_domains:
                if dns_domain.name in godaddy_domain_names:
                    try:
                        cache_entry = GoDaddyDomainCache.objects.get(
                            config=self.config,
                            domain_name=dns_domain.name
                        )
                        filtered_domains.append({
                            'domain': dns_domain.name,
                            'dns_zone_id': dns_domain.id,
                            'hosting_type': cache_entry.hosting_type,
                            'points_to_server': cache_entry.points_to_server,
                            'sync_enabled': cache_entry.sync_enabled,
                            'last_synced': cache_entry.last_synced
                        })
                    except GoDaddyDomainCache.DoesNotExist:
                        # Domain in CyberPanel but not in GoDaddy cache
                        filtered_domains.append({
                            'domain': dns_domain.name,
                            'dns_zone_id': dns_domain.id,
                            'hosting_type': 'unknown',
                            'points_to_server': False,
                            'sync_enabled': False,
                            'needs_classification': True
                        })
            
            return filtered_domains
            
        except ImportError:
            logger.error("Could not import DNS models - DNS module not available")
            return []
        except Exception as e:
            logger.error(f"Error getting CyberPanel DNS domains: {str(e)}")
            return []

def refresh_domain_cache(config: GoDaddyConfig) -> Dict:
    """Refresh the domain cache for a user"""
    try:
        classifier = DomainClassifier(config)
        results = classifier.discover_and_classify_domains()
        
        return {
            'success': True,
            'domains_found': (
                len(results['server_hosted']) + 
                len(results['external_hosted']) + 
                len(results['parked'])
            ),
            'server_hosted': len(results['server_hosted']),
            'external_hosted': len(results['external_hosted']),
            'parked': len(results['parked']),
            'errors': len(results['errors']),
            'details': results
        }
        
    except Exception as e:
        logger.error(f"Failed to refresh domain cache: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }