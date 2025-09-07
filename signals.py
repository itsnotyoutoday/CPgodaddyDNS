#!/usr/local/CyberCP/bin/python
import logging
import json
from django.dispatch import receiver
from django.http import HttpRequest

# Import CyberPanel DNS signals
try:
    from dns.signals import (
        postAddDNSRecord, postDeleteDNSRecord, 
        postZoneCreation, postSubmitZoneDeletion
    )
    DNS_SIGNALS_AVAILABLE = True
except ImportError:
    logging.warning("DNS signals not available - GoDaddy sync will be disabled")
    DNS_SIGNALS_AVAILABLE = False

from .models import GoDaddyConfig, GoDaddyDomainCache
from .sync_manager import SyncManager

logger = logging.getLogger(__name__)

# DNS Status Override Functions
def is_godaddy_dns_enabled(user_id):
    """Check if GoDaddy DNS is enabled for this user"""
    try:
        config = GoDaddyConfig.objects.get(user_id=user_id, is_active=True)
        return True
    except GoDaddyConfig.DoesNotExist:
        return False

def create_godaddy_status_file():
    """Create a status file that mimics PowerDNS being enabled"""
    import os
    godaddy_status_path = '/home/cyberpanel/godaddydns'
    try:
        # Create the file if it doesn't exist
        if not os.path.exists(godaddy_status_path):
            with open(godaddy_status_path, 'w') as f:
                f.write('GoDaddy DNS Plugin Active\n')
        return True
    except Exception as e:
        logger.error(f"Failed to create GoDaddy status file: {str(e)}")
        return False

def remove_godaddy_status_file():
    """Remove the GoDaddy status file"""
    import os
    godaddy_status_path = '/home/cyberpanel/godaddydns'
    try:
        if os.path.exists(godaddy_status_path):
            os.remove(godaddy_status_path)
        return True
    except Exception as e:
        logger.error(f"Failed to remove GoDaddy status file: {str(e)}")
        return False

def extract_record_data_from_request(request: HttpRequest) -> dict:
    """Extract DNS record data from CyberPanel request"""
    try:
        if hasattr(request, 'body') and request.body:
            data = json.loads(request.body.decode('utf-8'))
        else:
            data = request.POST.dict()
        
        # Extract common fields
        record_data = {
            'domain': data.get('selectedZone') or data.get('zoneDomain'),
            'name': data.get('recordName'),
            'type': data.get('recordType'),
            'ttl': int(data.get('ttl', 3600)),
        }
        
        # Extract content based on record type
        record_type = record_data.get('type', '').upper()
        if record_type == 'A':
            record_data['data'] = data.get('recordContentA')
        elif record_type == 'AAAA':
            record_data['data'] = data.get('recordContentAAAA')
        elif record_type == 'CNAME':
            record_data['data'] = data.get('recordContentCNAME')
        elif record_type == 'MX':
            record_data['data'] = data.get('recordContentMX')
            record_data['priority'] = int(data.get('priority', 10))
        elif record_type == 'TXT':
            record_data['data'] = data.get('recordContentTXT')
        elif record_type == 'SRV':
            record_data['data'] = data.get('recordContentSRV')
            record_data['priority'] = int(data.get('priority', 10))
        elif record_type == 'SPF':
            record_data['data'] = data.get('recordContentSPF')
        elif record_type == 'CAA':
            record_data['data'] = data.get('recordContentCAA')
        else:
            # Generic fallback
            record_data['data'] = (
                data.get('content') or 
                data.get('recordContent') or
                data.get('value')
            )
        
        return record_data
        
    except Exception as e:
        logger.error(f"Failed to extract record data from request: {str(e)}")
        return {}

def get_user_godaddy_config(user_id: int):
    """Get active GoDaddy config for user"""
    try:
        return GoDaddyConfig.objects.get(user_id=user_id, is_active=True)
    except GoDaddyConfig.DoesNotExist:
        return None

def is_godaddy_managed_domain(config: GoDaddyConfig, domain_name: str) -> bool:
    """Check if domain is managed by GoDaddy"""
    try:
        domain_cache = GoDaddyDomainCache.objects.get(
            config=config,
            domain_name=domain_name
        )
        return domain_cache.sync_enabled
    except GoDaddyDomainCache.DoesNotExist:
        return False

def sync_record_to_godaddy(user_id: int, domain_name: str, record_data: dict, operation: str):
    """Sync a single record change to GoDaddy"""
    try:
        config = get_user_godaddy_config(user_id)
        if not config or not config.sync_enabled:
            return
        
        if not is_godaddy_managed_domain(config, domain_name):
            logger.debug(f"Domain {domain_name} not managed by GoDaddy for user {user_id}")
            return
        
        # Prepare record data for sync
        sync_data = {
            'operation': operation,
            'name': record_data.get('name', '@'),
            'type': record_data.get('type'),
            'data': record_data.get('data'),
            'ttl': record_data.get('ttl', 3600),
            'priority': record_data.get('priority')
        }
        
        # Skip if essential data is missing
        if not sync_data['type'] or not sync_data['data']:
            logger.warning(f"Incomplete record data for GoDaddy sync: {sync_data}")
            return
        
        # Perform sync
        sync_manager = SyncManager(user_id)
        success = sync_manager.push_to_godaddy(domain_name, sync_data)
        
        if success:
            logger.info(f"Successfully synced {operation} for {domain_name} {sync_data['name']} {sync_data['type']}")
        else:
            logger.warning(f"Failed to sync {operation} for {domain_name} {sync_data['name']} {sync_data['type']}")
            
    except Exception as e:
        logger.error(f"Error syncing record to GoDaddy: {str(e)}")

# Signal handlers (only register if DNS signals are available)
if DNS_SIGNALS_AVAILABLE:
    
    @receiver(postAddDNSRecord)
    def handle_dns_record_added(sender, **kwargs):
        """Handle DNS record creation"""
        try:
            request = kwargs.get('request')
            if not request or not hasattr(request, 'session'):
                return
            
            user_id = request.session.get('userID')
            if not user_id:
                return
            
            # Extract record data
            record_data = extract_record_data_from_request(request)
            domain_name = record_data.get('domain')
            
            if not domain_name:
                logger.warning("No domain name found in DNS record creation")
                return
            
            logger.debug(f"DNS record added signal received: {domain_name} {record_data}")
            
            # Sync to GoDaddy
            sync_record_to_godaddy(user_id, domain_name, record_data, 'create')
            
        except Exception as e:
            logger.error(f"Error in postAddDNSRecord handler: {str(e)}")
    
    @receiver(postDeleteDNSRecord)
    def handle_dns_record_deleted(sender, **kwargs):
        """Handle DNS record deletion"""
        try:
            request = kwargs.get('request')
            if not request or not hasattr(request, 'session'):
                return
            
            user_id = request.session.get('userID')
            if not user_id:
                return
            
            # For deletion, we might need to extract data differently
            # since the record might already be deleted from local DB
            record_data = extract_record_data_from_request(request)
            domain_name = record_data.get('domain')
            
            # Try to get domain from other request parameters
            if not domain_name:
                try:
                    data = json.loads(request.body.decode('utf-8'))
                    # Look for domain in deletion request
                    if 'id' in data:
                        # We have record ID - need to look up domain
                        from dns.models import Records as DNSRecords
                        try:
                            record = DNSRecords.objects.get(id=data['id'])
                            domain_name = record.domainOwner.name
                            record_data.update({
                                'name': record.name,
                                'type': record.type,
                                'data': record.content
                            })
                        except DNSRecords.DoesNotExist:
                            pass
                except Exception:
                    pass
            
            if not domain_name:
                logger.warning("No domain name found in DNS record deletion")
                return
            
            logger.debug(f"DNS record deleted signal received: {domain_name} {record_data}")
            
            # Sync deletion to GoDaddy
            sync_record_to_godaddy(user_id, domain_name, record_data, 'delete')
            
        except Exception as e:
            logger.error(f"Error in postDeleteDNSRecord handler: {str(e)}")
    
    @receiver(postZoneCreation)
    def handle_dns_zone_created(sender, **kwargs):
        """Handle DNS zone creation"""
        try:
            request = kwargs.get('request')
            if not request or not hasattr(request, 'session'):
                return
            
            user_id = request.session.get('userID')
            if not user_id:
                return
            
            # Extract zone data
            try:
                data = json.loads(request.body.decode('utf-8'))
                domain_name = data.get('zoneDomain')
            except Exception:
                domain_name = request.POST.get('zoneDomain')
            
            if not domain_name:
                return
            
            logger.debug(f"DNS zone created signal received: {domain_name}")
            
            # Check if this domain is in GoDaddy account
            config = get_user_godaddy_config(user_id)
            if config:
                try:
                    # Trigger domain classification to update cache
                    from .domain_discovery import refresh_domain_cache
                    refresh_domain_cache(config)
                except Exception as e:
                    logger.error(f"Failed to refresh domain cache after zone creation: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error in postZoneCreation handler: {str(e)}")
    
    @receiver(postSubmitZoneDeletion)
    def handle_dns_zone_deleted(sender, **kwargs):
        """Handle DNS zone deletion"""
        try:
            request = kwargs.get('request')
            if not request or not hasattr(request, 'session'):
                return
            
            user_id = request.session.get('userID')
            if not user_id:
                return
            
            # Extract zone data
            try:
                data = json.loads(request.body.decode('utf-8'))
                domain_name = data.get('zoneDomain')
            except Exception:
                domain_name = request.POST.get('zoneDomain')
            
            if not domain_name:
                return
            
            logger.debug(f"DNS zone deleted signal received: {domain_name}")
            
            # Update domain cache to disable sync for this domain
            config = get_user_godaddy_config(user_id)
            if config:
                try:
                    domain_cache = GoDaddyDomainCache.objects.get(
                        config=config,
                        domain_name=domain_name
                    )
                    domain_cache.sync_enabled = False
                    domain_cache.save()
                except GoDaddyDomainCache.DoesNotExist:
                    pass
                except Exception as e:
                    logger.error(f"Failed to update domain cache after zone deletion: {str(e)}")
            
        except Exception as e:
            logger.error(f"Error in postSubmitZoneDeletion handler: {str(e)}")

# Manual sync triggers (can be called directly)
def trigger_domain_sync(user_id: int, domain_name: str = None):
    """Manually trigger sync for a user/domain"""
    try:
        sync_manager = SyncManager(user_id)
        return sync_manager.full_sync(domain_name)
    except Exception as e:
        logger.error(f"Manual sync failed: {str(e)}")
        return {'success': False, 'error': str(e)}

def trigger_domain_discovery(user_id: int):
    """Manually trigger domain discovery for a user"""
    try:
        config = get_user_godaddy_config(user_id)
        if not config:
            return {'success': False, 'error': 'No GoDaddy configuration found'}
        
        from .domain_discovery import refresh_domain_cache
        return refresh_domain_cache(config)
    except Exception as e:
        logger.error(f"Domain discovery failed: {str(e)}")
        return {'success': False, 'error': str(e)}