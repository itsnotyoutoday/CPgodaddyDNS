#!/usr/local/CyberCP/bin/python
"""
GoDaddy DNS Plugin Installation Script
Run this script to install the GoDaddy DNS plugin into CyberPanel
"""

import sys
import os
import django
import subprocess
import warnings

# Suppress all warnings and errors during install for clean user experience
warnings.filterwarnings('ignore')
os.environ['PYTHONWARNINGS'] = 'ignore'
os.environ['DJANGO_SETTINGS_MODULE'] = 'CyberCP.settings'

# Setup Django
sys.path.append('/usr/local/CyberCP')
django.setup()

def run_command(command, description, hide_errors=False):
    """Run a command and handle errors gracefully"""
    print(f"→ {description}...")
    try:
        # Suppress stderr for Django commands to avoid system check warnings
        if hide_errors or 'manage.py' in command:
            command += ' 2>/dev/null'
        
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            if hide_errors:
                print(f"⚠ {description} completed with warnings")
                return False
            else:
                # Show clean error without full stderr dump
                print(f"✗ {description} failed")
                return False
        else:
            print(f"✓ {description} completed")
            return True
    except Exception as e:
        print(f"✗ {description} failed: {str(e)}")
        return False

def add_to_installed_apps():
    """Add godaddyDNS to INSTALLED_APPS and middleware in settings.py"""
    settings_file = '/usr/local/CyberCP/CyberCP/settings.py'
    
    try:
        with open(settings_file, 'r') as f:
            content = f.read()
        
        modified = False
        
        # Fix any corrupted ALLOWED_HOSTS first (from previous install attempts)
        if "ALLOWED_HOSTS = ['*'    'godaddyDNS'," in content:
            content = content.replace("ALLOWED_HOSTS = ['*'    'godaddyDNS',", "ALLOWED_HOSTS = ['*']")
            modified = True
            print("   ✓ Fixed corrupted ALLOWED_HOSTS")
        
        # Check if already added to INSTALLED_APPS
        if "'godaddyDNS'" not in content and '"godaddyDNS"' not in content:
            # Find INSTALLED_APPS and add our app properly
            if 'INSTALLED_APPS' in content:
                # Find the specific location to add - after aiScanner and before #    'WebTerminal'
                if "    'aiScanner'," in content and "    #    'WebTerminal'" in content:
                    content = content.replace(
                        "    'aiScanner',\n    #    'WebTerminal'",
                        "    'aiScanner',\n    'godaddyDNS',\n    #    'WebTerminal'"
                    )
                    modified = True
                    print("✓ Added godaddyDNS to INSTALLED_APPS")
                else:
                    print("✗ Could not find safe insertion point in INSTALLED_APPS")
                    return False
            else:
                print("✗ Could not find INSTALLED_APPS in settings.py")
                return False
        else:
            print("✓ godaddyDNS already in INSTALLED_APPS")
        
        # Add middleware if not present
        if 'godaddyDNS.middleware.GoDaddyDNSMiddleware' not in content:
            if 'MIDDLEWARE' in content:
                # Find the MIDDLEWARE list and add our middleware
                middleware_pattern = r'MIDDLEWARE\s*=\s*\[(.*?)\]'
                import re
                match = re.search(middleware_pattern, content, re.DOTALL)
                if match:
                    middleware_content = match.group(0)
                    # Add our middleware before the closing bracket
                    new_middleware = middleware_content.replace(
                        ']',
                        "    'godaddyDNS.middleware.GoDaddyDNSMiddleware',\n]"
                    )
                    content = content.replace(middleware_content, new_middleware)
                    modified = True
                    print("✓ Added GoDaddy DNS middleware")
        else:
            print("✓ GoDaddy DNS middleware already configured")
        
        # Add template context processor if not present
        if 'godaddyDNS.middleware.godaddy_dns_context' not in content:
            if 'TEMPLATES' in content and 'context_processors' in content:
                # Add context processor
                context_processor = "'godaddyDNS.middleware.godaddy_dns_context',"
                if 'context_processors' in content:
                    # Find the context_processors section and add our processor
                    lines = content.split('\n')
                    for i, line in enumerate(lines):
                        if 'context_processors' in line:
                            # Look for the closing bracket of context_processors
                            for j in range(i + 1, len(lines)):
                                if ']' in lines[j] and 'context_processors' not in lines[j]:
                                    lines.insert(j, f"                {context_processor}")
                                    content = '\n'.join(lines)
                                    modified = True
                                    print("✓ Added GoDaddy DNS template context processor")
                                    break
                            break
        
        # Write back to file if modified
        if modified:
            with open(settings_file, 'w') as f:
                f.write(content)
        
        return True
            
    except Exception as e:
        print(f"✗ Error updating settings.py: {str(e)}")
        return False

def add_url_routing():
    """Add URL routing to main CyberCP urls.py and override DNS home"""
    urls_file = '/usr/local/CyberCP/CyberCP/urls.py'
    
    try:
        with open(urls_file, 'r') as f:
            content = f.read()
        
        modified = False
        
        # Add GoDaddy URL routing if not present
        if 'godaddy/' not in content:
            # Add the URL pattern
            new_pattern = "    re_path(r'^godaddy/', include('godaddyDNS.urls')),"
            
            # Find urlpatterns and add our pattern
            if 'urlpatterns' in content:
                # Add before the last closing bracket
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if ']' in line and 'urlpatterns' in content[:content.find(line)]:
                        lines.insert(i, new_pattern)
                        break
                
                content = '\n'.join(lines)
                modified = True
                print("✓ Added GoDaddy URL routing")
        else:
            print("✓ GoDaddy URL routing already configured")
        
        # Override DNS home URL to use our view
        if "re_path(r'^dns/$'" in content and 'godaddyDNS.views.dns_home_override' not in content:
            # Replace the DNS home URL with our override
            content = content.replace(
                "re_path(r'^dns/$', dns_views.loadDNSHome, name='loadDNSHome')",
                "re_path(r'^dns/$', include('godaddyDNS.views.dns_home_override'), name='loadDNSHome')"
            )
            modified = True
            print("✓ Added DNS home override")
        
        # Also add the include import if not present
        if ('include' not in content and 
            ('from django.urls import' in content or 'from django.conf.urls import' in content)):
            if 'from django.urls import' in content:
                content = content.replace(
                    'from django.urls import',
                    'from django.urls import include,'
                )
            elif 'from django.conf.urls import' in content:
                content = content.replace(
                    'from django.conf.urls import',
                    'from django.conf.urls import include,'
                )
            modified = True
        
        # Write back to file if modified
        if modified:
            with open(urls_file, 'w') as f:
                f.write(content)
        
        return True
            
    except Exception as e:
        print(f"✗ Error updating urls.py: {str(e)}")
        return False

def run_migrations():
    """Run Django migrations to create database tables"""
    print("→ Running database migrations...")
    
    python_path = '/usr/local/CyberCP/bin/python'
    
    # Create migrations with suppressed output
    print("   Creating database migration files...")
    result = subprocess.run(
        f'cd /usr/local/CyberCP && {python_path} manage.py makemigrations godaddyDNS 2>/dev/null',
        shell=True, capture_output=True, text=True
    )
    
    if result.returncode == 0:
        print("   ✓ Migration files created")
    else:
        print("   → Using existing migration files")
    
    # Run migrations with suppressed output
    print("   Applying database migrations...")
    result = subprocess.run(
        f'cd /usr/local/CyberCP && {python_path} manage.py migrate --verbosity=0 2>/dev/null',
        shell=True, capture_output=True, text=True
    )
    
    if result.returncode == 0:
        print("   ✓ Database migrations applied successfully")
        return True
    else:
        print("   ✗ Database migration failed")
        # Try to detect specific error
        if 'No installed app with label' in result.stderr:
            print("   → App not properly registered in Django settings")
        return False

def install_requirements():
    """Install Python requirements"""
    requirements = ['requests']
    
    for req in requirements:
        if not run_command(
            f'/usr/local/CyberCP/bin/pip install {req}',
            f'Installing {req}'
        ):
            return False
    
    return True

def setup_cron_job():
    """Set up cron job for automatic sync"""
    cron_entry = "*/15 * * * * root cd /usr/local/CyberCP && /usr/local/CyberCP/bin/python manage.py sync_godaddy_dns >/dev/null 2>&1"
    cron_file = '/etc/cron.d/godaddy-dns-sync'
    
    try:
        with open(cron_file, 'w') as f:
            f.write("# GoDaddy DNS Auto Sync\n")
            f.write("# Runs every 15 minutes to sync DNS records\n")
            f.write(cron_entry + "\n")
        
        # Set proper permissions
        os.chmod(cron_file, 0o644)
        
        print("✓ Cron job configured for automatic sync")
        return True
        
    except Exception as e:
        print(f"✗ Error setting up cron job: {str(e)}")
        return False

def create_log_directory():
    """Create log directory for the plugin"""
    log_dir = '/var/log/cyberpanel/godaddy'
    
    try:
        os.makedirs(log_dir, exist_ok=True)
        os.chmod(log_dir, 0o755)
        print("✓ Log directory created")
        return True
    except Exception as e:
        print(f"✗ Error creating log directory: {str(e)}")
        return False

def main():
    """Main installation function"""
    print("=" * 60)
    print("GoDaddy DNS Plugin Installation")
    print("=" * 60)
    
    steps = [
        ("Installing Python requirements", install_requirements),
        ("Adding to Django INSTALLED_APPS", add_to_installed_apps),
        ("Adding URL routing", add_url_routing), 
        ("Running database migrations", run_migrations),
        ("Creating log directory", create_log_directory),
        ("Setting up cron job", setup_cron_job),
    ]
    
    success_count = 0
    total_steps = len(steps)
    
    for description, function in steps:
        print(f"\n{description}...")
        if function():
            success_count += 1
        else:
            print(f"✗ {description} failed")
    
    print("\n" + "=" * 60)
    print(f"Installation completed: {success_count}/{total_steps} steps successful")
    print("=" * 60)
    
    if success_count == total_steps:
        print("\n✓ GoDaddy DNS plugin installed successfully!")
        print("\nNext steps:")
        print("1. Restart CyberPanel services:")
        print("   systemctl restart lscpd")
        print("2. Access the plugin at: https://your-server:8090/godaddy/config")
        print("3. Configure your GoDaddy API credentials")
        print("4. Discover your domains and enable sync")
        
        # Try to restart services
        print("\nAttempting to restart CyberPanel services...")
        result = subprocess.run('systemctl restart lscpd', shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print("✓ CyberPanel services restarted successfully")
            print("\n🎉 Installation completed successfully!")
            print("   Your GoDaddy DNS plugin is now ready to use!")
        else:
            print("⚠ Please manually restart CyberPanel services:")
            print("  systemctl restart lscpd")
        
    else:
        print("\n⚠ Installation completed with errors. Please check the output above.")
        print("You may need to manually complete the failed steps.")
    
    return success_count == total_steps

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)