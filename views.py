#!/usr/local/CyberCP/bin/python
import json
import logging
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.utils import timezone
from loginSystem.views import loadLoginPage
from plogical.acl import ACLManager
from plogical.httpProc import httpProc

from .models import GoDaddyConfig, GoDaddyDomainCache, GoDaddySyncLog, GoDaddyConflictQueue
from .gdapi import GoDaddyAPI, GoDaddyAPIException
from .domain_discovery import DomainFilter, refresh_domain_cache
from .sync_manager import SyncManager, get_sync_status
from .signals import trigger_domain_sync, trigger_domain_discovery, create_godaddy_status_file

logger = logging.getLogger(__name__)

# DNS Integration Views
def dns_home_override(request):
    """Override for the main DNS home page"""
    try:
        userID = request.session['userID']
        currentACL = ACLManager.loadedACL(userID)
        
        # Check if GoDaddy DNS is configured
        try:
            config = GoDaddyConfig.objects.get(user_id=userID, is_active=True)
            godaddy_enabled = True
        except GoDaddyConfig.DoesNotExist:
            godaddy_enabled = False
            config = None
        
        # Check PowerDNS status
        powerdns_enabled = os.path.exists('/home/cyberpanel/powerdns')
        
        # If GoDaddy is enabled, create status file
        if godaddy_enabled:
            create_godaddy_status_file()
        
        data = {
            'godaddy_dns_enabled': godaddy_enabled,
            'powerdns_enabled': powerdns_enabled,
            'config': config
        }
        
        # Use our custom template that integrates GoDaddy DNS
        template = 'dns/index.html'  # This will use our override template
        proc = httpProc(request, template, data, 'dnsHome')
        return proc.render()
        
    except KeyError:
        return redirect(loadLoginPage)

# Configuration Views
def godaddy_config(request):
    """Main configuration page"""
    try:
        userID = request.session['userID']
        currentACL = ACLManager.loadedACL(userID)
        
        # Get or create config
        try:
            config = GoDaddyConfig.objects.get(user_id=userID)
        except GoDaddyConfig.DoesNotExist:
            config = None
        
        data = {
            'config': config,
            'has_config': config is not None,
            'is_active': config.is_active if config else False,
            'sync_enabled': config.sync_enabled if config else False,
        }
        
        template = 'godaddyDNS/config.html'
        proc = httpProc(request, template, data, 'godaddyConfig')
        return proc.render()
        
    except KeyError:
        return redirect(loadLoginPage)

@csrf_exempt  
def save_config(request):
    """Save GoDaddy configuration"""
    try:
        userID = request.session['userID']
        data = json.loads(request.body)
        
        api_key = data.get('api_key', '').strip()
        api_secret = data.get('api_secret', '').strip()
        use_production = data.get('use_production', False)
        sync_enabled = data.get('sync_enabled', True)
        conflict_strategy = data.get('conflict_strategy', 'godaddy_wins')
        
        if not api_key or not api_secret:
            return JsonResponse({
                'success': False, 
                'error': 'API Key and Secret are required'
            })
        
        # Test API connection
        try:
            gd_api = GoDaddyAPI(api_key, api_secret, use_production)
            if not gd_api.test_connection():
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid API credentials or connection failed'
                })
        except GoDaddyAPIException as e:
            return JsonResponse({
                'success': False,
                'error': f'API test failed: {str(e)}'
            })
        
        # Save configuration
        config, created = GoDaddyConfig.objects.get_or_create(
            user_id=userID,
            defaults={
                'api_key': api_key,
                'api_secret': api_secret,
                'use_production': use_production,
                'sync_enabled': sync_enabled,
                'conflict_strategy': conflict_strategy,
                'is_active': True
            }
        )
        
        if not created:
            config.api_key = api_key
            config.api_secret = api_secret
            config.use_production = use_production
            config.sync_enabled = sync_enabled
            config.conflict_strategy = conflict_strategy
            config.is_active = True
            config.save()
        
        return JsonResponse({'success': True, 'message': 'Configuration saved successfully'})
        
    except Exception as e:
        logger.error(f"Error saving GoDaddy config: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

# Domain Management Views
def domain_management(request):
    """Domain discovery and management page"""
    try:
        userID = request.session['userID']
        
        try:
            config = GoDaddyConfig.objects.get(user_id=userID, is_active=True)
        except GoDaddyConfig.DoesNotExist:
            return redirect('godaddyConfig')
        
        # Get domain data
        domain_filter = DomainFilter(config)
        domains_data = domain_filter.get_manageable_domains()
        
        # Get server IP for display
        try:
            with open('/etc/cyberpanel/machineIP', 'r') as f:
                server_ip = f.read().strip().split('\n')[0]
        except Exception:
            server_ip = "Unknown"
        
        data = {
            'config': config,
            'server_ip': server_ip,
            'domains_data': domains_data,
            'needs_discovery': domains_data.get('needs_discovery', True),
            'last_updated': domains_data.get('last_updated')
        }
        
        template = 'godaddyDNS/domains.html'
        proc = httpProc(request, template, data, 'godaddyDomains')
        return proc.render()
        
    except KeyError:
        return redirect(loadLoginPage)

@csrf_exempt
def discover_domains(request):
    """Trigger domain discovery"""
    try:
        userID = request.session['userID']
        
        result = trigger_domain_discovery(userID)
        
        if result.get('success'):
            return JsonResponse({
                'success': True,
                'message': f"Discovered {result.get('domains_found', 0)} domains",
                'details': {
                    'server_hosted': result.get('server_hosted', 0),
                    'external_hosted': result.get('external_hosted', 0),
                    'parked': result.get('parked', 0)
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Domain discovery failed')
            })
        
    except Exception as e:
        logger.error(f"Domain discovery error: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
def toggle_domain_sync(request):
    """Enable/disable sync for a specific domain"""
    try:
        userID = request.session['userID']
        data = json.loads(request.body)
        
        domain_name = data.get('domain')
        sync_enabled = data.get('sync_enabled', True)
        
        config = GoDaddyConfig.objects.get(user_id=userID, is_active=True)
        domain_cache = GoDaddyDomainCache.objects.get(
            config=config,
            domain_name=domain_name
        )
        
        domain_cache.sync_enabled = sync_enabled
        domain_cache.save()
        
        return JsonResponse({
            'success': True,
            'message': f"Sync {'enabled' if sync_enabled else 'disabled'} for {domain_name}"
        })
        
    except Exception as e:
        logger.error(f"Error toggling domain sync: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

# Sync Management Views
def sync_status(request):
    """Sync status and history page"""
    try:
        userID = request.session['userID']
        
        try:
            config = GoDaddyConfig.objects.get(user_id=userID, is_active=True)
        except GoDaddyConfig.DoesNotExist:
            return redirect('godaddyConfig')
        
        sync_status_data = get_sync_status(userID)
        
        # Get pending conflicts
        pending_conflicts = GoDaddyConflictQueue.objects.filter(
            config=config,
            status='pending'
        )
        
        data = {
            'config': config,
            'sync_status': sync_status_data,
            'pending_conflicts': pending_conflicts
        }
        
        template = 'godaddyDNS/sync_status.html'
        proc = httpProc(request, template, data, 'godaddySyncStatus')
        return proc.render()
        
    except KeyError:
        return redirect(loadLoginPage)

@csrf_exempt
def manual_sync(request):
    """Trigger manual sync"""
    try:
        userID = request.session['userID']
        data = json.loads(request.body)
        
        domain_name = data.get('domain')  # Optional - sync specific domain
        
        result = trigger_domain_sync(userID, domain_name)
        
        if result.get('success', True):  # Default to True if no success key
            message = f"Sync completed successfully"
            if domain_name:
                message += f" for {domain_name}"
            
            details = {
                'domains_processed': result.get('domains_processed', 0),
                'records_updated': result.get('records_updated', 0),
                'conflicts_resolved': result.get('conflicts_resolved', 0)
            }
            
            return JsonResponse({
                'success': True,
                'message': message,
                'details': details
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Sync failed')
            })
        
    except Exception as e:
        logger.error(f"Manual sync error: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
def get_sync_logs(request):
    """Get sync logs for AJAX updates"""
    try:
        userID = request.session['userID']
        config = GoDaddyConfig.objects.get(user_id=userID, is_active=True)
        
        logs = GoDaddySyncLog.objects.filter(config=config).order_by('-started_at')[:20]
        
        log_data = []
        for log in logs:
            log_data.append({
                'id': log.id,
                'type': log.sync_type,
                'domain': log.domain_name,
                'status': log.status,
                'started_at': log.started_at.isoformat(),
                'completed_at': log.completed_at.isoformat() if log.completed_at else None,
                'duration': log.duration_seconds(),
                'domains_processed': log.domains_processed,
                'records_updated': log.records_updated,
                'errors': len(log.errors) if log.errors else 0
            })
        
        return JsonResponse({'success': True, 'logs': log_data})
        
    except Exception as e:
        logger.error(f"Error getting sync logs: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

# DNS Record Management Views (following CyberPanel patterns)
def manage_dns_records(request):
    """DNS record management interface"""
    try:
        userID = request.session['userID']
        
        try:
            config = GoDaddyConfig.objects.get(user_id=userID, is_active=True)
        except GoDaddyConfig.DoesNotExist:
            return redirect('godaddyConfig')
        
        # Get manageable domains
        domain_filter = DomainFilter(config)
        domains = domain_filter.get_cyberpanel_dns_domains(userID)
        
        data = {
            'config': config,
            'domains': domains
        }
        
        template = 'godaddyDNS/manage_records.html'
        proc = httpProc(request, template, data, 'godaddyRecords')
        return proc.render()
        
    except KeyError:
        return redirect(loadLoginPage)

@csrf_exempt
def get_domain_records(request):
    """Get DNS records for a domain"""
    try:
        userID = request.session['userID']
        data = json.loads(request.body)
        
        domain_name = data.get('domain')
        record_type = data.get('record_type', 'A')
        
        config = GoDaddyConfig.objects.get(user_id=userID, is_active=True)
        
        # Get records from GoDaddy
        gd_api = GoDaddyAPI(config.api_key, config.api_secret, config.use_production)
        
        if record_type == 'ALL':
            records = gd_api.get_domain_records(domain_name)
        else:
            records = gd_api.get_domain_records(domain_name, record_type)
        
        # Filter out NS records
        records = [r for r in records if r.get('type') != 'NS']
        
        return JsonResponse({
            'success': True,
            'records': records,
            'count': len(records)
        })
        
    except Exception as e:
        logger.error(f"Error getting domain records: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)})

# Plugin Status and Health Views
def plugin_status(request):
    """Plugin status and health check page"""
    try:
        userID = request.session['userID']
        
        # Check if user has configuration
        try:
            config = GoDaddyConfig.objects.get(user_id=userID)
            has_config = True
            
            # Test API connection
            try:
                gd_api = GoDaddyAPI(config.api_key, config.api_secret, config.use_production)
                api_status = gd_api.test_connection()
            except Exception as e:
                api_status = False
                api_error = str(e)
            else:
                api_error = None
            
        except GoDaddyConfig.DoesNotExist:
            has_config = False
            api_status = False
            api_error = "No configuration found"
            config = None
        
        # Get statistics
        stats = {}
        if config:
            stats = {
                'total_domains': GoDaddyDomainCache.objects.filter(config=config).count(),
                'server_hosted': GoDaddyDomainCache.objects.filter(
                    config=config, hosting_type='server_hosted'
                ).count(),
                'external_hosted': GoDaddyDomainCache.objects.filter(
                    config=config, hosting_type='external_hosted'
                ).count(),
                'parked': GoDaddyDomainCache.objects.filter(
                    config=config, hosting_type='parked'
                ).count(),
                'recent_syncs': GoDaddySyncLog.objects.filter(config=config).count(),
                'pending_conflicts': GoDaddyConflictQueue.objects.filter(
                    config=config, status='pending'
                ).count()
            }
        
        data = {
            'has_config': has_config,
            'config': config,
            'api_status': api_status,
            'api_error': api_error,
            'stats': stats
        }
        
        template = 'godaddyDNS/status.html'
        proc = httpProc(request, template, data, 'godaddyStatus')
        return proc.render()
        
    except KeyError:
        return redirect(loadLoginPage)