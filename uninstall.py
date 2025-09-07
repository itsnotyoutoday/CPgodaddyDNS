#!/usr/local/CyberCP/bin/python
"""
GoDaddy DNS Plugin Uninstall Script
Run this script to completely remove the GoDaddy DNS plugin from CyberPanel
"""

import sys
import os
import django
import subprocess

# Setup Django
sys.path.append('/usr/local/CyberCP')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "CyberCP.settings")
django.setup()

def run_command(command, description):
    """Run a command and handle errors"""
    print(f"→ {description}...")
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"✗ Error: {result.stderr}")
            return False
        else:
            print(f"✓ {description} completed")
            return True
    except Exception as e:
        print(f"✗ Error: {str(e)}")
        return False

def backup_settings():
    """Create backup of settings.py before modification"""
    settings_file = '/usr/local/CyberCP/CyberCP/settings.py'
    backup_file = f'{settings_file}.backup_before_godaddy_uninstall'
    
    try:
        # Create backup
        with open(settings_file, 'r') as src, open(backup_file, 'w') as dst:
            dst.write(src.read())
        print("✓ Created settings.py backup")
        return True
    except Exception as e:
        print(f"✗ Failed to backup settings.py: {str(e)}")
        return False

def remove_from_installed_apps():
    """Remove godaddyDNS from INSTALLED_APPS and middleware"""
    settings_file = '/usr/local/CyberCP/CyberCP/settings.py'
    
    try:
        with open(settings_file, 'r') as f:
            content = f.read()
        
        original_content = content
        
        # Remove from INSTALLED_APPS
        content = content.replace("    'godaddyDNS',\n", "")
        content = content.replace("'godaddyDNS',\n", "")
        content = content.replace('"godaddyDNS",\n', "")
        
        # Remove middleware
        content = content.replace("    'godaddyDNS.middleware.GoDaddyDNSMiddleware',\n", "")
        
        # Remove context processor
        content = content.replace("                'godaddyDNS.middleware.godaddy_dns_context',\n", "")
        
        # Write back if changed
        if content != original_content:
            with open(settings_file, 'w') as f:
                f.write(content)
            print("✓ Removed godaddyDNS from Django settings")
        else:
            print("✓ godaddyDNS not found in Django settings")
        
        return True
            
    except Exception as e:
        print(f"✗ Error updating settings.py: {str(e)}")
        return False

def remove_url_routing():
    """Remove URL routing from main CyberCP urls.py"""
    urls_file = '/usr/local/CyberCP/CyberCP/urls.py'
    
    try:
        with open(urls_file, 'r') as f:
            content = f.read()
        
        original_content = content
        
        # Remove GoDaddy URL patterns
        content = content.replace("    re_path(r'^godaddy/', include('godaddyDNS.urls')),\n", "")
        content = content.replace("re_path(r'^godaddy/', include('godaddyDNS.urls')),\n", "")
        
        # Remove DNS override if present
        if 'godaddyDNS.views.dns_home_override' in content:
            # Restore original DNS home URL
            content = content.replace(
                "re_path(r'^dns/$', include('godaddyDNS.views.dns_home_override'), name='loadDNSHome')",
                "re_path(r'^dns/$', dns_views.loadDNSHome, name='loadDNSHome')"
            )
        
        # Write back if changed
        if content != original_content:
            with open(urls_file, 'w') as f:
                f.write(content)
            print("✓ Removed GoDaddy URL routing")
        else:
            print("✓ GoDaddy URL routing not found")
        
        return True
            
    except Exception as e:
        print(f"✗ Error updating urls.py: {str(e)}")
        return False

def remove_database_tables():
    """Remove database tables created by the plugin"""
    print("→ Removing database tables...")
    
    python_path = '/usr/local/CyberCP/bin/python'
    
    # Get list of tables to remove
    tables = [
        'godaddy_config',
        'godaddy_domain_cache', 
        'godaddy_sync_log',
        'godaddy_record_history',
        'godaddy_conflict_queue'
    ]
    
    try:
        # Try to run a migration to remove tables
        if run_command(
            f'cd /usr/local/CyberCP && {python_path} manage.py migrate godaddyDNS zero',
            'Removing database tables via migration'
        ):
            return True
        
        # If migration fails, try to remove tables directly
        print("→ Migration failed, attempting direct table removal...")
        
        # Import Django ORM
        from django.db import connection
        cursor = connection.cursor()
        
        for table in tables:
            try:
                cursor.execute(f"DROP TABLE IF EXISTS {table}")
                print(f"✓ Removed table {table}")
            except Exception as e:
                print(f"⚠ Could not remove table {table}: {str(e)}")
        
        print("✓ Database cleanup completed")
        return True
        
    except Exception as e:
        print(f"✗ Database cleanup failed: {str(e)}")
        return False

def remove_cron_job():
    """Remove cron job"""
    cron_file = '/etc/cron.d/godaddy-dns-sync'
    
    try:
        if os.path.exists(cron_file):
            os.remove(cron_file)
            print("✓ Removed cron job")
        else:
            print("✓ Cron job not found")
        return True
    except Exception as e:
        print(f"✗ Error removing cron job: {str(e)}")
        return False

def remove_status_files():
    """Remove status files created by the plugin"""
    files_to_remove = [
        '/home/cyberpanel/godaddydns',
        '/home/cyberpanel/powerdns'  # Only remove if created by us
    ]
    
    for file_path in files_to_remove:
        try:
            if os.path.exists(file_path):
                # Check if it's our file
                with open(file_path, 'r') as f:
                    content = f.read()
                
                if 'GoDaddy' in content:
                    os.remove(file_path)
                    print(f"✓ Removed {file_path}")
                else:
                    print(f"⚠ Skipped {file_path} (not created by GoDaddy plugin)")
            else:
                print(f"✓ {file_path} not found")
        except Exception as e:
            print(f"⚠ Could not remove {file_path}: {str(e)}")
    
    return True

def remove_log_directories():
    """Remove log directories"""
    log_dir = '/var/log/cyberpanel/godaddy'
    
    try:
        if os.path.exists(log_dir):
            import shutil
            shutil.rmtree(log_dir)
            print("✓ Removed log directory")
        else:
            print("✓ Log directory not found")
        return True
    except Exception as e:
        print(f"⚠ Could not remove log directory: {str(e)}")
        return True  # Non-critical

def remove_plugin_files():
    """Remove plugin files (optional - user choice)"""
    print("→ Plugin files will remain in /usr/local/CyberCP/godaddyDNS/")
    print("  You can manually delete this directory if desired")
    return True

def main():
    """Main uninstall function"""
    print("=" * 60)
    print("GoDaddy DNS Plugin Uninstall")
    print("=" * 60)
    
    # Confirmation
    response = input("Are you sure you want to uninstall the GoDaddy DNS plugin? (y/N): ")
    if response.lower() not in ['y', 'yes']:
        print("Uninstall cancelled.")
        return False
    
    # Backup first
    print("\nCreating backup...")
    if not backup_settings():
        response = input("Backup failed. Continue anyway? (y/N): ")
        if response.lower() not in ['y', 'yes']:
            return False
    
    steps = [
        ("Removing from Django settings", remove_from_installed_apps),
        ("Removing URL routing", remove_url_routing),
        ("Removing database tables", remove_database_tables),
        ("Removing cron job", remove_cron_job),
        ("Removing status files", remove_status_files),
        ("Removing log directories", remove_log_directories),
        ("Cleaning up plugin files", remove_plugin_files),
    ]
    
    success_count = 0
    total_steps = len(steps)
    
    print("\nUninstalling...")
    for description, function in steps:
        print(f"\n{description}...")
        if function():
            success_count += 1
        else:
            print(f"✗ {description} failed")
    
    print("\n" + "=" * 60)
    print(f"Uninstall completed: {success_count}/{total_steps} steps successful")
    print("=" * 60)
    
    if success_count == total_steps:
        print("\n✓ GoDaddy DNS plugin uninstalled successfully!")
        print("\nNext steps:")
        print("1. Restart CyberPanel services:")
        print("   systemctl restart lscpd")
        print("2. The DNS menu will show default PowerDNS options")
        print("3. Plugin files remain in /usr/local/CyberCP/godaddyDNS/ (delete manually if desired)")
        print("4. Settings backup saved as: /usr/local/CyberCP/CyberCP/settings.py.backup_before_godaddy_uninstall")
        
        # Try to restart services
        print("\nAttempting to restart CyberPanel services...")
        if run_command('systemctl restart lscpd', 'Restarting lscpd'):
            print("✓ CyberPanel services restarted")
        else:
            print("⚠ Please manually restart CyberPanel services:")
            print("  systemctl restart lscpd")
        
    else:
        print("\n⚠ Uninstall completed with errors. Please check the output above.")
        print("You may need to manually complete the failed steps.")
        print("Backup available at: /usr/local/CyberCP/CyberCP/settings.py.backup_before_godaddy_uninstall")
    
    return success_count == total_steps

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)