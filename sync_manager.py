#!/usr/local/CyberCP/bin/python
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from django.utils import timezone
from django.db import transaction

from .gdapi import GoDaddyAPI, GoDaddyAPIException
from .models import (
    GoDaddyConfig, GoDaddyDomainCache, GoDaddySyncLog, 
    GoDaddyRecordHistory, GoDaddyConflictQueue
)

logger = logging.getLogger(__name__)

class SyncManager:
    """Manages bi-directional DNS synchronization between CyberPanel and GoDaddy"""
    
    def __init__(self, user_id: int):
        self.user_id = user_id
        try:
            self.config = GoDaddyConfig.objects.get(user_id=user_id, is_active=True)
            self.gd_api = GoDaddyAPI(
                self.config.api_key,
                self.config.api_secret, 
                self.config.use_production
            )
        except GoDaddyConfig.DoesNotExist:
            raise ValueError(f"No active GoDaddy configuration found for user {user_id}")
    
    def full_sync(self, domain_name: str = None) -> Dict:
        """Perform full bidirectional sync"""
        sync_log = GoDaddySyncLog.objects.create(
            config=self.config,
            sync_type='manual' if domain_name else 'scheduled',
            domain_name=domain_name,
            status='running'
        )
        
        try:
            if domain_name:
                # Sync single domain
                results = self._sync_single_domain(domain_name, sync_log)
            else:
                # Sync all domains
                results = self._sync_all_domains(sync_log)
            
            sync_log.status = 'completed' if not results.get('errors') else 'partial'
            sync_log.domains_processed = results.get('domains_processed', 0)
            sync_log.records_created = results.get('records_created', 0)
            sync_log.records_updated = results.get('records_updated', 0)
            sync_log.records_deleted = results.get('records_deleted', 0)
            sync_log.conflicts_resolved = results.get('conflicts_resolved', 0)
            sync_log.errors = results.get('errors', [])
            sync_log.completed_at = timezone.now()
            sync_log.save()
            
            # Update last sync timestamp
            self.config.last_sync = timezone.now()
            self.config.save()
            
            return results
            
        except Exception as e:
            logger.error(f"Sync failed for user {self.user_id}: {str(e)}")
            sync_log.mark_failed(str(e))
            raise
    
    def _sync_all_domains(self, sync_log: GoDaddySyncLog) -> Dict:
        """Sync all domains for this user"""
        results = {
            'domains_processed': 0,
            'records_created': 0,
            'records_updated': 0,
            'records_deleted': 0,
            'conflicts_resolved': 0,
            'errors': []
        }
        
        # Get all domains that should be synced
        synced_domains = GoDaddyDomainCache.objects.filter(
            config=self.config,
            sync_enabled=True
        )
        
        for domain_cache in synced_domains:
            try:
                domain_results = self._sync_single_domain(domain_cache.domain_name, sync_log)
                
                # Aggregate results
                results['domains_processed'] += 1
                results['records_created'] += domain_results.get('records_created', 0)
                results['records_updated'] += domain_results.get('records_updated', 0)
                results['records_deleted'] += domain_results.get('records_deleted', 0)
                results['conflicts_resolved'] += domain_results.get('conflicts_resolved', 0)
                
                if domain_results.get('errors'):
                    results['errors'].extend(domain_results['errors'])
                    
            except Exception as e:
                error_msg = f"Domain {domain_cache.domain_name}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(error_msg)
        
        return results
    
    def _sync_single_domain(self, domain_name: str, sync_log: GoDaddySyncLog) -> Dict:
        """Sync a single domain"""
        results = {
            'records_created': 0,
            'records_updated': 0,
            'records_deleted': 0,
            'conflicts_resolved': 0,
            'errors': []
        }
        
        try:
            # Get records from both sides
            godaddy_records = self._get_godaddy_records(domain_name)
            local_records = self._get_local_records(domain_name)
            
            if godaddy_records is None:
                results['errors'].append(f"Could not retrieve GoDaddy records for {domain_name}")
                return results
            
            # Build comparison maps
            godaddy_map = self._build_record_map(godaddy_records, 'godaddy')
            local_map = self._build_record_map(local_records, 'local')
            
            # Sync records GoDaddy -> Local (GoDaddy takes precedence)
            sync_results = self._sync_records_to_local(domain_name, godaddy_map, local_map)
            results['records_created'] += sync_results['created']
            results['records_updated'] += sync_results['updated'] 
            results['records_deleted'] += sync_results['deleted']
            results['conflicts_resolved'] += sync_results['conflicts']
            
            if sync_results.get('errors'):
                results['errors'].extend(sync_results['errors'])
            
            # Update domain cache
            try:
                domain_cache = GoDaddyDomainCache.objects.get(
                    config=self.config,
                    domain_name=domain_name
                )
                domain_cache.last_synced = timezone.now()
                domain_cache.save()
            except GoDaddyDomainCache.DoesNotExist:
                pass
            
            return results
            
        except Exception as e:
            error_msg = f"Sync failed for {domain_name}: {str(e)}"
            results['errors'].append(error_msg)
            logger.error(error_msg)
            return results
    
    def _get_godaddy_records(self, domain_name: str) -> Optional[List[Dict]]:
        """Get DNS records from GoDaddy"""
        try:
            records = self.gd_api.get_domain_records(domain_name)
            # Filter out NS records (we don't sync nameservers)
            return [r for r in records if r.get('type') != 'NS']
        except GoDaddyAPIException as e:
            logger.error(f"Failed to get GoDaddy records for {domain_name}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting GoDaddy records for {domain_name}: {str(e)}")
            return None
    
    def _get_local_records(self, domain_name: str) -> List[Dict]:
        """Get DNS records from local database"""
        try:
            from dns.models import Domains as DNSDomains, Records as DNSRecords
            
            try:
                local_domain = DNSDomains.objects.get(name=domain_name)
                local_records = DNSRecords.objects.filter(domainOwner=local_domain)
                
                # Convert to standardized format
                records = []
                for record in local_records:
                    # Skip NS records and SOA records for sync
                    if record.type in ['NS', 'SOA']:
                        continue
                    
                    records.append({
                        'id': record.id,
                        'name': record.name,
                        'type': record.type,
                        'data': record.content,
                        'ttl': record.ttl,
                        'priority': record.prio
                    })
                
                return records
                
            except DNSDomains.DoesNotExist:
                # Domain doesn't exist locally
                return []
                
        except ImportError:
            logger.error("DNS models not available")
            return []
        except Exception as e:
            logger.error(f"Error getting local records for {domain_name}: {str(e)}")
            return []
    
    def _build_record_map(self, records: List[Dict], source: str) -> Dict[str, Dict]:
        """Build a map of records for comparison"""
        record_map = {}
        
        for record in records:
            # Create unique key for record identification
            name = record.get('name', '@')
            record_type = record.get('type')
            
            # Handle different naming conventions
            if source == 'godaddy':
                data = record.get('data')
                ttl = record.get('ttl', 3600)
                priority = record.get('priority')
            else:  # local
                data = record.get('data') or record.get('content')
                ttl = record.get('ttl', 3600)
                priority = record.get('priority') or record.get('prio')
            
            key = f"{name}||{record_type}"
            
            record_map[key] = {
                'name': name,
                'type': record_type,
                'data': data,
                'ttl': ttl,
                'priority': priority,
                'source': source,
                'original': record
            }
        
        return record_map
    
    def _sync_records_to_local(self, domain_name: str, godaddy_map: Dict, local_map: Dict) -> Dict:
        """Sync GoDaddy records to local database (GoDaddy takes precedence)"""
        results = {
            'created': 0,
            'updated': 0,
            'deleted': 0,
            'conflicts': 0,
            'errors': []
        }
        
        try:
            from dns.models import Domains as DNSDomains, Records as DNSRecords
            from loginSystem.models import Administrator
            
            # Ensure local domain exists
            try:
                local_domain = DNSDomains.objects.get(name=domain_name)
            except DNSDomains.DoesNotExist:
                # Create local domain
                admin = Administrator.objects.get(pk=self.user_id)
                local_domain = DNSDomains.objects.create(
                    admin=admin,
                    name=domain_name,
                    type="NATIVE"
                )
            
            # Process GoDaddy records
            for key, godaddy_record in godaddy_map.items():
                try:
                    if key in local_map:
                        # Record exists locally - check for differences
                        local_record = local_map[key]
                        if self._records_differ(godaddy_record, local_record):
                            # Update local record with GoDaddy data
                            self._update_local_record(local_domain, local_record, godaddy_record)
                            results['updated'] += 1
                            results['conflicts'] += 1
                    else:
                        # Create new local record
                        self._create_local_record(local_domain, godaddy_record)
                        results['created'] += 1
                        
                except Exception as e:
                    error_msg = f"Error syncing record {key}: {str(e)}"
                    results['errors'].append(error_msg)
                    logger.error(error_msg)
            
            # Delete local records that don't exist in GoDaddy
            for key, local_record in local_map.items():
                if key not in godaddy_map:
                    try:
                        self._delete_local_record(local_record)
                        results['deleted'] += 1
                    except Exception as e:
                        error_msg = f"Error deleting local record {key}: {str(e)}"
                        results['errors'].append(error_msg)
                        logger.error(error_msg)
            
            return results
            
        except Exception as e:
            logger.error(f"Error syncing records to local for {domain_name}: {str(e)}")
            results['errors'].append(str(e))
            return results
    
    def _records_differ(self, godaddy_record: Dict, local_record: Dict) -> bool:
        """Check if records are different"""
        # Compare essential fields
        gd_data = str(godaddy_record.get('data', '')).strip()
        local_data = str(local_record.get('data', '')).strip()
        
        if gd_data != local_data:
            return True
        
        gd_ttl = int(godaddy_record.get('ttl', 3600))
        local_ttl = int(local_record.get('ttl', 3600))
        
        if gd_ttl != local_ttl:
            return True
        
        # Check priority for MX and SRV records
        if godaddy_record.get('type') in ['MX', 'SRV']:
            gd_priority = godaddy_record.get('priority', 0)
            local_priority = local_record.get('priority', 0)
            if gd_priority != local_priority:
                return True
        
        return False
    
    def _create_local_record(self, local_domain, godaddy_record: Dict):
        """Create a new local DNS record"""
        try:
            from dns.models import Records as DNSRecords
            
            record = DNSRecords.objects.create(
                domainOwner=local_domain,
                domain_id=local_domain.id,
                name=godaddy_record['name'],
                type=godaddy_record['type'],
                content=godaddy_record['data'],
                ttl=godaddy_record['ttl'],
                prio=godaddy_record.get('priority', 0),
                disabled=0,
                auth=1
            )
            
            # Log the change
            GoDaddyRecordHistory.objects.create(
                config=self.config,
                domain_name=local_domain.name,
                record_name=godaddy_record['name'],
                record_type=godaddy_record['type'],
                change_type='created',
                change_source='sync',
                new_content=godaddy_record['data'],
                new_ttl=godaddy_record['ttl'],
                new_priority=godaddy_record.get('priority')
            )
            
        except Exception as e:
            logger.error(f"Failed to create local record: {str(e)}")
            raise
    
    def _update_local_record(self, local_domain, local_record: Dict, godaddy_record: Dict):
        """Update an existing local DNS record"""
        try:
            from dns.models import Records as DNSRecords
            
            # Get the actual Django model instance
            record_id = local_record['original'].get('id')
            if not record_id:
                raise ValueError("No record ID available for update")
            
            record = DNSRecords.objects.get(id=record_id)
            
            # Store old values for logging
            old_content = record.content
            old_ttl = record.ttl
            old_priority = record.prio
            
            # Update with GoDaddy data
            record.content = godaddy_record['data']
            record.ttl = godaddy_record['ttl']
            record.prio = godaddy_record.get('priority', 0)
            record.save()
            
            # Log the change
            GoDaddyRecordHistory.objects.create(
                config=self.config,
                domain_name=local_domain.name,
                record_name=godaddy_record['name'],
                record_type=godaddy_record['type'],
                change_type='updated',
                change_source='sync',
                old_content=old_content,
                new_content=godaddy_record['data'],
                old_ttl=old_ttl,
                new_ttl=godaddy_record['ttl'],
                old_priority=old_priority,
                new_priority=godaddy_record.get('priority')
            )
            
        except Exception as e:
            logger.error(f"Failed to update local record: {str(e)}")
            raise
    
    def _delete_local_record(self, local_record: Dict):
        """Delete a local DNS record"""
        try:
            from dns.models import Records as DNSRecords
            
            record_id = local_record['original'].get('id')
            if not record_id:
                raise ValueError("No record ID available for deletion")
            
            record = DNSRecords.objects.get(id=record_id)
            
            # Log the change before deletion
            GoDaddyRecordHistory.objects.create(
                config=self.config,
                domain_name=record.domainOwner.name,
                record_name=record.name,
                record_type=record.type,
                change_type='deleted',
                change_source='sync',
                old_content=record.content,
                old_ttl=record.ttl,
                old_priority=record.prio
            )
            
            record.delete()
            
        except Exception as e:
            logger.error(f"Failed to delete local record: {str(e)}")
            raise
    
    def push_to_godaddy(self, domain_name: str, record_data: Dict) -> bool:
        """Push a single record change to GoDaddy (for real-time sync)"""
        try:
            # Check if this domain is managed by GoDaddy
            try:
                domain_cache = GoDaddyDomainCache.objects.get(
                    config=self.config,
                    domain_name=domain_name
                )
                if not domain_cache.sync_enabled:
                    return False
            except GoDaddyDomainCache.DoesNotExist:
                # Domain not in cache - skip sync
                return False
            
            # Push to GoDaddy based on operation type
            if record_data.get('operation') == 'create':
                return self.gd_api.create_dns_record(
                    domain_name,
                    record_data['type'],
                    record_data['name'],
                    record_data['data'],
                    record_data.get('ttl', 3600),
                    record_data.get('priority')
                )
            elif record_data.get('operation') == 'update':
                return self.gd_api.update_dns_record(
                    domain_name,
                    record_data['type'],
                    record_data['name'],
                    record_data['data'],
                    record_data.get('ttl', 3600),
                    record_data.get('priority')
                )
            elif record_data.get('operation') == 'delete':
                return self.gd_api.delete_dns_record(
                    domain_name,
                    record_data['type'],
                    record_data['name']
                )
            
            return False
            
        except GoDaddyAPIException as e:
            logger.error(f"Failed to push record to GoDaddy: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error pushing to GoDaddy: {str(e)}")
            return False

def get_sync_status(user_id: int) -> Dict:
    """Get sync status for a user"""
    try:
        config = GoDaddyConfig.objects.get(user_id=user_id, is_active=True)
        
        # Get recent sync logs
        recent_syncs = GoDaddySyncLog.objects.filter(config=config).order_by('-started_at')[:10]
        
        # Get pending conflicts
        pending_conflicts = GoDaddyConflictQueue.objects.filter(
            config=config, 
            status='pending'
        ).count()
        
        return {
            'last_sync': config.last_sync,
            'last_domain_refresh': config.last_domain_refresh,
            'sync_enabled': config.sync_enabled,
            'recent_syncs': [
                {
                    'id': sync.id,
                    'type': sync.sync_type,
                    'domain': sync.domain_name,
                    'status': sync.status,
                    'started_at': sync.started_at,
                    'duration': sync.duration_seconds(),
                    'domains_processed': sync.domains_processed,
                    'records_updated': sync.records_updated
                }
                for sync in recent_syncs
            ],
            'pending_conflicts': pending_conflicts
        }
        
    except GoDaddyConfig.DoesNotExist:
        return {'error': 'No GoDaddy configuration found'}
    except Exception as e:
        logger.error(f"Error getting sync status: {str(e)}")
        return {'error': str(e)}