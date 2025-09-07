#!/usr/local/CyberCP/bin/python
"""
GoDaddy DNS Middleware
Intercepts DNS-related requests and injects GoDaddy functionality
"""
import os
import logging
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.template import loader
from .models import GoDaddyConfig
from .signals import is_godaddy_dns_enabled, create_godaddy_status_file

logger = logging.getLogger(__name__)

class GoDaddyDNSMiddleware:
    """Middleware to override DNS functionality when GoDaddy plugin is active"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Pre-process request
        self.process_request(request)
        
        # Get response
        response = self.get_response(request)
        
        # Post-process response
        return self.process_response(request, response)
    
    def process_request(self, request):
        """Process incoming requests for DNS-related URLs"""
        
        # Only process for authenticated users
        if not hasattr(request, 'session') or 'userID' not in request.session:
            return None
        
        user_id = request.session['userID']
        
        # Check if this is a DNS-related request
        if self.is_dns_request(request):
            # If GoDaddy DNS is enabled for this user, create status file
            if is_godaddy_dns_enabled(user_id):
                create_godaddy_status_file()
                # Also create powerdns file to satisfy CyberPanel checks
                self.create_powerdns_status_file()
        
        return None
    
    def process_response(self, request, response):
        """Process responses to inject GoDaddy DNS functionality"""
        
        # Only process HTML responses for authenticated users
        if (not hasattr(request, 'session') or 
            'userID' not in request.session or
            not hasattr(response, 'content') or
            'text/html' not in response.get('Content-Type', '')):
            return response
        
        user_id = request.session['userID']
        
        # If GoDaddy DNS is enabled, modify DNS-related pages
        if (is_godaddy_dns_enabled(user_id) and 
            self.is_dns_request(request)):
            return self.inject_godaddy_dns_interface(request, response)
        
        return response
    
    def is_dns_request(self, request):
        """Check if this is a DNS-related request"""
        dns_paths = [
            '/dns/',
            '/dns/createNameServer',
            '/dns/createDNSZone',
            '/dns/addDeleteDNSRecords'
        ]
        
        return any(request.path.startswith(path) for path in dns_paths)
    
    def create_powerdns_status_file(self):
        """Create PowerDNS status file to satisfy CyberPanel checks"""
        powerdns_status_path = '/home/cyberpanel/powerdns'
        try:
            if not os.path.exists(powerdns_status_path):
                with open(powerdns_status_path, 'w') as f:
                    f.write('GoDaddy DNS Plugin Override\n')
                logger.debug("Created PowerDNS status file override")
        except Exception as e:
            logger.error(f"Failed to create PowerDNS status file: {str(e)}")
    
    def inject_godaddy_dns_interface(self, request, response):
        """Inject GoDaddy DNS interface into existing DNS pages"""
        try:
            content = response.content.decode('utf-8')
            
            # Look for DNS-related content to modify
            if 'PowerDNS is disabled' in content or 'powerdns' in content.lower():
                # Replace PowerDNS references with GoDaddy DNS
                content = content.replace(
                    'PowerDNS is disabled', 
                    'DNS managed by GoDaddy'
                )
                content = content.replace(
                    'PowerDNS', 
                    'GoDaddy DNS'
                )
                
                # Add GoDaddy DNS management links
                godaddy_nav = '''
                <div class="alert alert-info">
                    <h5><i class="fa fa-cloud"></i> GoDaddy DNS Active</h5>
                    <p>DNS records are managed through GoDaddy. Use the links below:</p>
                    <div class="btn-group" role="group">
                        <a href="/godaddy/domains" class="btn btn-primary btn-sm">
                            <i class="fa fa-globe"></i> Manage Domains
                        </a>
                        <a href="/godaddy/sync-status" class="btn btn-info btn-sm">
                            <i class="fa fa-sync"></i> Sync Status
                        </a>
                        <a href="/godaddy/config" class="btn btn-secondary btn-sm">
                            <i class="fa fa-cog"></i> Settings
                        </a>
                    </div>
                </div>
                '''
                
                # Inject the GoDaddy interface
                if '<div class="card-body">' in content:
                    content = content.replace(
                        '<div class="card-body">',
                        f'<div class="card-body">{godaddy_nav}',
                        1  # Only replace the first occurrence
                    )
            
            # Update response content
            response.content = content.encode('utf-8')
            response['Content-Length'] = len(response.content)
            
        except Exception as e:
            logger.error(f"Error injecting GoDaddy DNS interface: {str(e)}")
        
        return response

# Alternative approach: Template context processor
def godaddy_dns_context(request):
    """Add GoDaddy DNS context to all templates"""
    context = {}
    
    if hasattr(request, 'session') and 'userID' in request.session:
        user_id = request.session['userID']
        context.update({
            'godaddy_dns_enabled': is_godaddy_dns_enabled(user_id),
            'godaddy_dns_config_url': '/godaddy/config',
            'godaddy_dns_domains_url': '/godaddy/domains',
            'godaddy_dns_sync_url': '/godaddy/sync-status'
        })
    
    return context