#!/usr/local/CyberCP/bin/python
import requests
import json
import logging
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

class GoDaddyAPIException(Exception):
    """Custom exception for GoDaddy API errors"""
    pass

class GoDaddyAPI:
    """GoDaddy DNS API wrapper"""
    
    def __init__(self, api_key: str, api_secret: str, production: bool = False):
        self.api_key = api_key
        self.api_secret = api_secret
        
        # Use production or OTE environment
        self.base_url = 'https://api.godaddy.com/v1' if production else 'https://api.ote-godaddy.com/v1'
        
        self.headers = {
            'Authorization': f'sso-key {api_key}:{api_secret}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        # Rate limiting - GoDaddy allows 60 requests per minute
        self.rate_limit = 60
        self.request_count = 0
    
    def _make_request(self, method: str, endpoint: str, data: Dict = None, params: Dict = None) -> Dict:
        """Make HTTP request to GoDaddy API with error handling"""
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method.upper() == 'GET':
                response = requests.get(url, headers=self.headers, params=params, timeout=30)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=self.headers, json=data, params=params, timeout=30)
            elif method.upper() == 'PUT':
                response = requests.put(url, headers=self.headers, json=data, params=params, timeout=30)
            elif method.upper() == 'PATCH':
                response = requests.patch(url, headers=self.headers, json=data, params=params, timeout=30)
            elif method.upper() == 'DELETE':
                response = requests.delete(url, headers=self.headers, params=params, timeout=30)
            else:
                raise GoDaddyAPIException(f"Unsupported HTTP method: {method}")
            
            # Check for API errors
            if response.status_code == 401:
                raise GoDaddyAPIException("Authentication failed - check API key and secret")
            elif response.status_code == 403:
                raise GoDaddyAPIException("Access forbidden - check account permissions")
            elif response.status_code == 404:
                raise GoDaddyAPIException("Resource not found")
            elif response.status_code == 429:
                raise GoDaddyAPIException("Rate limit exceeded - too many requests")
            elif response.status_code >= 400:
                error_msg = f"API request failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    if 'message' in error_data:
                        error_msg += f": {error_data['message']}"
                except:
                    error_msg += f": {response.text}"
                raise GoDaddyAPIException(error_msg)
            
            # Parse JSON response
            if response.content:
                return response.json()
            return {}
            
        except requests.RequestException as e:
            logger.error(f"GoDaddy API request failed: {str(e)}")
            raise GoDaddyAPIException(f"Network error: {str(e)}")
    
    def get_owned_domains(self) -> List[Dict]:
        """Get all domains in the GoDaddy account"""
        try:
            domains = self._make_request('GET', '/domains')
            return domains if domains else []
        except Exception as e:
            logger.error(f"Failed to get owned domains: {str(e)}")
            raise GoDaddyAPIException(f"Failed to retrieve domains: {str(e)}")
    
    def get_domain_info(self, domain: str) -> Dict:
        """Get detailed information about a specific domain"""
        try:
            domain_info = self._make_request('GET', f'/domains/{domain}')
            return domain_info
        except Exception as e:
            logger.error(f"Failed to get domain info for {domain}: {str(e)}")
            raise GoDaddyAPIException(f"Failed to get domain info: {str(e)}")
    
    def get_domain_records(self, domain: str, record_type: str = None) -> List[Dict]:
        """Get DNS records for a domain"""
        try:
            endpoint = f'/domains/{domain}/records'
            if record_type:
                endpoint += f'/{record_type}'
            
            records = self._make_request('GET', endpoint)
            return records if records else []
        except Exception as e:
            logger.error(f"Failed to get records for {domain}: {str(e)}")
            raise GoDaddyAPIException(f"Failed to get DNS records: {str(e)}")
    
    def get_specific_record(self, domain: str, record_type: str, name: str) -> List[Dict]:
        """Get specific DNS record"""
        try:
            endpoint = f'/domains/{domain}/records/{record_type}/{name}'
            records = self._make_request('GET', endpoint)
            return records if records else []
        except Exception as e:
            logger.error(f"Failed to get {record_type} record {name} for {domain}: {str(e)}")
            raise GoDaddyAPIException(f"Failed to get specific record: {str(e)}")
    
    def create_dns_record(self, domain: str, record_type: str, name: str, data: str, 
                         ttl: int = 3600, priority: int = None) -> bool:
        """Add a new DNS record"""
        try:
            record_data = {
                'type': record_type,
                'name': name,
                'data': data,
                'ttl': max(ttl, 600)  # GoDaddy minimum TTL is 600
            }
            
            if priority is not None and record_type in ['MX', 'SRV']:
                record_data['priority'] = priority
            
            # Use PATCH to add records
            self._make_request('PATCH', f'/domains/{domain}/records', data=[record_data])
            return True
            
        except Exception as e:
            logger.error(f"Failed to create DNS record for {domain}: {str(e)}")
            raise GoDaddyAPIException(f"Failed to create DNS record: {str(e)}")
    
    def update_dns_record(self, domain: str, record_type: str, name: str, data: str, 
                         ttl: int = 3600, priority: int = None) -> bool:
        """Update an existing DNS record"""
        try:
            record_data = {
                'type': record_type,
                'name': name,
                'data': data,
                'ttl': max(ttl, 600)
            }
            
            if priority is not None and record_type in ['MX', 'SRV']:
                record_data['priority'] = priority
            
            # Use PUT to replace all records of this type/name
            self._make_request('PUT', f'/domains/{domain}/records/{record_type}/{name}', data=[record_data])
            return True
            
        except Exception as e:
            logger.error(f"Failed to update DNS record for {domain}: {str(e)}")
            raise GoDaddyAPIException(f"Failed to update DNS record: {str(e)}")
    
    def delete_dns_record(self, domain: str, record_type: str, name: str) -> bool:
        """Delete a DNS record"""
        try:
            # GoDaddy doesn't have a direct delete - we get all records of this type
            # and PUT back the ones we want to keep
            existing_records = self.get_specific_record(domain, record_type, name)
            
            if not existing_records:
                return True  # Already doesn't exist
            
            # Replace with empty list to delete all records of this type/name
            self._make_request('PUT', f'/domains/{domain}/records/{record_type}/{name}', data=[])
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete DNS record for {domain}: {str(e)}")
            raise GoDaddyAPIException(f"Failed to delete DNS record: {str(e)}")
    
    def replace_all_records(self, domain: str, records: List[Dict]) -> bool:
        """Replace all DNS records for a domain (be careful!)"""
        try:
            # Validate TTL values
            for record in records:
                if 'ttl' in record:
                    record['ttl'] = max(record['ttl'], 600)
            
            self._make_request('PUT', f'/domains/{domain}/records', data=records)
            return True
            
        except Exception as e:
            logger.error(f"Failed to replace records for {domain}: {str(e)}")
            raise GoDaddyAPIException(f"Failed to replace DNS records: {str(e)}")
    
    def test_connection(self) -> bool:
        """Test if API credentials are valid"""
        try:
            # Try to get domains list as a connectivity test
            self.get_owned_domains()
            return True
        except Exception as e:
            logger.error(f"API connection test failed: {str(e)}")
            return False
    
    def get_account_info(self) -> Dict:
        """Get account information (if available)"""
        try:
            # This endpoint may not be available in all GoDaddy API versions
            account_info = self._make_request('GET', '/account')
            return account_info
        except Exception as e:
            logger.warning(f"Could not retrieve account info: {str(e)}")
            return {}