# GoDaddy DNS Plugin for CyberPanel

**A seamless DNS management solution that completely replaces PowerDNS with GoDaddy's authoritative DNS service.**

This plugin integrates directly into CyberPanel's existing DNS interface, providing a complete DNS management solution through GoDaddy's API without requiring PowerDNS installation or configuration.

## 🎯 Key Benefits

- **🔄 Seamless Integration**: Replaces PowerDNS completely - no more "PowerDNS disabled" messages
- **🌐 Native GoDaddy DNS**: Uses GoDaddy's authoritative nameservers for all DNS operations
- **⚡ Real-time Sync**: DNS changes in CyberPanel instantly sync to GoDaddy
- **🎨 Unified Interface**: Works within CyberPanel's existing DNS menu structure
- **🔒 Domain Filtering**: Only manages domains actually owned in your GoDaddy account
- **📊 Smart Classification**: Automatically detects server-hosted vs. external domains

## ✨ Core Features

### DNS Management
- **Bi-directional Sync**: CyberPanel ↔ GoDaddy DNS synchronization
- **Real-time Updates**: Instant propagation of DNS changes to GoDaddy
- **Conflict Resolution**: GoDaddy takes precedence on conflicts (as it should)
- **All Record Types**: A, AAAA, CNAME, MX, TXT, SRV, CAA support

### Domain Intelligence  
- **Smart Discovery**: Scan and classify domains from your GoDaddy account
- **Server Detection**: Automatically identifies domains pointing to your server
- **Hosting Classification**:
  - 🟢 **Server-Hosted**: A records point to your server IP
  - 🟡 **External**: Hosted elsewhere but DNS manageable
  - ⚪ **Parked**: No active hosting, ready for setup

### Monitoring & Control
- **Sync History**: Complete audit trail of all DNS operations
- **Status Dashboard**: Real-time sync monitoring and statistics  
- **Manual Triggers**: On-demand sync for specific domains or all domains
- **Automated Sync**: Cron-based periodic synchronization (every 15 minutes)

## 📋 Requirements

- **CyberPanel**: Any version with DNS module (PowerDNS NOT required)
- **GoDaddy Account**: Active account with domains to manage
- **GoDaddy API Credentials**: API key and secret from [developer.godaddy.com](https://developer.godaddy.com/keys)
- **System**: Python 3.6+, requests library (auto-installed)

## 🚀 Quick Installation

### Option 1: One-Click Setup (Recommended)
```bash
cd /usr/local/CyberCP/godaddyDNS
chmod +x setup.sh
./setup.sh
```

### Option 2: Manual Installation
```bash
cd /usr/local/CyberCP/godaddyDNS
python install.py
systemctl restart lscpd
```

## 🎮 Getting Started

### Step 1: Access Configuration
1. Log into CyberPanel
2. Navigate to **DNS** menu (no more PowerDNS warnings!)
3. You'll see the GoDaddy DNS setup interface

### Step 2: Configure API Credentials
1. Visit [GoDaddy Developer Portal](https://developer.godaddy.com/keys)
2. Create API key and secret
3. Enter credentials in CyberPanel
4. Test connection

### Step 3: Discover Your Domains
1. Click "Discover Domains" to scan your GoDaddy account
2. Review domain classifications:
   - 🟢 **Server-Hosted** (pointing to your server)
   - 🟡 **External** (hosted elsewhere)
   - ⚪ **Parked** (ready for setup)
3. Enable auto-sync for desired domains

### Step 4: You're Done!
- All DNS changes in CyberPanel now sync to GoDaddy automatically
- Use the regular DNS interface as normal
- Monitor sync status and history in the dashboard

## ⚙️ How It Works

### Seamless DNS Integration
This plugin completely replaces the need for PowerDNS by:

1. **Template Override**: Replaces CyberPanel's default DNS interface with GoDaddy-powered version
2. **Middleware Integration**: Intercepts DNS requests and routes them through GoDaddy API
3. **Signal Hooks**: Captures all DNS operations in CyberPanel and syncs to GoDaddy in real-time
4. **Status Management**: Creates necessary files to satisfy CyberPanel's internal DNS checks

### Smart Domain Management
```
Your GoDaddy Account
├── example.com (A → Your Server IP) → 🟢 Server-Hosted → Auto-sync enabled
├── external.com (A → 203.0.113.5) → 🟡 External → DNS manageable  
└── parked.com (No A records) → ⚪ Parked → Ready for setup
```

### Sync Flow
```
CyberPanel DNS Change → Django Signal → GoDaddy API → Live DNS Update
         ↑                                              ↓
    User Interface ← Status Update ← Sync Confirmation ←
```

## 🎛️ Configuration Options

### API Settings
- **Environment**: Production vs OTE (testing)
- **Credentials**: Secure storage of API key/secret
- **Connection Testing**: Validate credentials before saving

### Sync Preferences  
- **Auto-sync**: Enable/disable per domain
- **Conflict Resolution**: 
  - GoDaddy takes precedence (recommended)
  - Manual review queue
  - Timestamp-based resolution
- **Sync Frequency**: Configurable cron schedule (default: 15 minutes)

### Domain Controls
- **Selective Sync**: Choose which domains to manage
- **Classification Override**: Manually adjust domain hosting type
- **Sync History**: Complete audit trail per domain

## 🎯 User Experience

### The DNS Menu Transformation

**❌ Before (PowerDNS Disabled):**
```
DNS Menu → "PowerDNS is disabled" → Dead end
```

**✅ After (GoDaddy Plugin Active):**
```
DNS Menu → GoDaddy DNS Dashboard → Full DNS Management
├── Domain Discovery & Classification
├── Real-time Sync Status  
├── DNS Record Management
└── Configuration & Settings
```

### Daily Workflow

1. **Normal DNS Operations**: Use CyberPanel's DNS interface exactly as before
2. **Instant Sync**: Changes automatically propagate to GoDaddy (within seconds)
3. **Monitor Status**: Check sync health and domain classifications
4. **Bulk Operations**: Discover new domains, trigger manual syncs as needed

### Interface Integration

| Feature | Location | Description |
|---------|----------|-------------|
| **Main Dashboard** | `/dns/` | Replaces PowerDNS interface completely |
| **Domain Management** | Integrated in DNS menu | Domain discovery and classification |
| **Sync Status** | Integrated in DNS menu | Real-time sync monitoring |
| **Configuration** | Integrated in DNS menu | API settings and preferences |

## 💻 Command Line Tools

### Manual Sync Operations
```bash
# Full sync for all users
python manage.py sync_godaddy_dns --verbose

# Sync specific user
python manage.py sync_godaddy_dns --user-id 1

# Sync specific domain
python manage.py sync_godaddy_dns --domain example.com

# Dry run (see what would change)
python manage.py sync_godaddy_dns --dry-run --verbose
```

### Domain Discovery
```bash
# Discover domains for all users  
python manage.py discover_godaddy_domains --verbose

# Discover for specific user
python manage.py discover_godaddy_domains --user-id 1
```

### Cron Management
```bash
# View current cron job
cat /etc/cron.d/godaddy-dns-sync

# Test cron job manually
cd /usr/local/CyberCP && python manage.py sync_godaddy_dns
```

## API Endpoints

The plugin provides the following internal API endpoints:

- `GET /godaddy/config` - Configuration page
- `POST /godaddy/save-config` - Save configuration
- `GET /godaddy/domains` - Domain management page
- `POST /godaddy/discover-domains` - Trigger domain discovery
- `POST /godaddy/manual-sync` - Trigger manual sync
- `GET /godaddy/sync-status` - Sync status page

## Command Line Tools

### Manual Sync
```bash
cd /usr/local/CyberCP
python manage.py sync_godaddy_dns [options]

Options:
  --user-id ID     Sync specific user only
  --domain NAME    Sync specific domain only
  --force          Force sync even if recently synced
  --dry-run        Show what would be synced
  --verbose        Detailed output
```

### Domain Discovery
```bash
cd /usr/local/CyberCP
python manage.py discover_godaddy_domains [options]

Options:
  --user-id ID     Discover domains for specific user
  --verbose        Detailed output
```

## Cron Job

The plugin automatically installs a cron job for periodic sync:

```bash
# /etc/cron.d/godaddy-dns-sync
*/15 * * * * root cd /usr/local/CyberCP && /usr/local/CyberCP/bin/python manage.py sync_godaddy_dns >/dev/null 2>&1
```

You can modify the frequency by editing this file.

## Database Schema

The plugin creates the following database tables:

- `godaddy_config` - User API configurations
- `godaddy_domain_cache` - Cached domain information
- `godaddy_sync_log` - Sync operation history
- `godaddy_record_history` - DNS record change history
- `godaddy_conflict_queue` - Unresolved conflicts

## Troubleshooting

### Common Issues

1. **API Connection Failed**
   - Verify API key and secret are correct
   - Check if using correct environment (Production vs OTE)
   - Ensure your GoDaddy account has required permissions

2. **Domain Not Found**
   - Domain must be in your GoDaddy account
   - Run domain discovery to refresh cache
   - Check domain status in GoDaddy control panel

3. **Sync Failures**
   - Check sync logs for specific error messages
   - Verify DNS records are valid
   - Ensure TTL values are ≥ 600 (GoDaddy minimum)

4. **Missing Domains**
   - Only domains in your GoDaddy account will appear
   - Domains must have active DNS management
   - Run manual domain discovery

### Debug Mode

Enable verbose logging by editing the sync cron job:

```bash
# Remove >/dev/null 2>&1 from cron job to see output
*/15 * * * * root cd /usr/local/CyberCP && /usr/local/CyberCP/bin/python manage.py sync_godaddy_dns --verbose
```

### Log Files

Check these locations for logs:
- `/var/log/cyberpanel/godaddy/` (if created)
- `/home/cyberpanel/stderr.log` (Django errors)
- CyberPanel main logs

## Security Considerations

- API credentials are stored in the database
- Use HTTPS for all web interfaces
- Limit API key permissions in GoDaddy if possible
- Regularly rotate API credentials
- Monitor sync logs for suspicious activity

## Support

For issues and questions:
1. Check the troubleshooting section above
2. Review sync logs for error messages  
3. Test with OTE environment first
4. Verify GoDaddy account permissions

## 🛠️ Installation Troubleshooting

### Common Installation Issues

**❌ "python: not found" Error**
```bash
# The installer now uses the correct CyberPanel Python path
# If you see this error, ensure you're using the latest version
```

**❌ Migration Errors**
```bash
# Manually run migrations if auto-migration fails:
cd /usr/local/CyberCP
/usr/local/CyberCP/bin/python manage.py makemigrations godaddyDNS
/usr/local/CyberCP/bin/python manage.py migrate
```

**❌ Permission Errors**  
```bash
# Fix permissions after installation:
chown -R cyberpanel:cyberpanel /usr/local/CyberCP/godaddyDNS
```

### Installation Verification

1. **Check Plugin Loading**:
   ```bash
   cd /usr/local/CyberCP
   /usr/local/CyberCP/bin/python manage.py shell -c "import godaddyDNS; print('Plugin loaded successfully')"
   ```

2. **Verify Database Tables**:
   ```bash
   /usr/local/CyberCP/bin/python manage.py dbshell -c "SHOW TABLES LIKE 'godaddy%';"
   ```

3. **Test DNS Interface**: Navigate to `/dns/` in CyberPanel - you should see GoDaddy options

## 🗑️ Uninstallation

### Complete Removal
```bash
cd /usr/local/CyberCP/godaddyDNS
./uninstall.sh
```

### Manual Cleanup (if needed)
```bash
# Remove plugin files
rm -rf /usr/local/CyberCP/godaddyDNS

# Remove cron job
rm -f /etc/cron.d/godaddy-dns-sync

# Remove status files
rm -f /home/cyberpanel/godaddydns
```

## 🔐 Security Considerations

- **API Credentials**: Stored encrypted in Django database
- **HTTPS Only**: All GoDaddy API calls use HTTPS
- **Rate Limiting**: Respects GoDaddy's 60 requests/minute limit
- **Domain Validation**: Only manages domains in your GoDaddy account
- **Audit Trail**: Complete logging of all DNS operations

## 📞 Support & Issues

### Getting Help
1. **Check Logs**: `/var/log/cyberpanel/godaddy/` and `/home/cyberpanel/stderr.log`
2. **Test with OTE**: Use GoDaddy's testing environment first
3. **Command Line**: Use `--verbose` flags for detailed output
4. **Manual Sync**: Test individual operations to isolate issues

### Known Limitations
- **GoDaddy Account Required**: Only works with domains in your GoDaddy account
- **TTL Minimum**: GoDaddy requires minimum TTL of 600 seconds
- **Rate Limits**: 60 API requests per minute
- **Domain Restrictions**: Some TLDs may have API limitations

## 🚀 Version History

- **v1.0.0** - Initial Release
  - Complete PowerDNS replacement
  - Seamless CyberPanel integration
  - Real-time bi-directional sync
  - Smart domain classification
  - Web-based management interface
  - Automated cron synchronization
  - Comprehensive logging and monitoring

## 📜 License

This plugin is provided as-is for use with CyberPanel. 

**Important**: This plugin completely replaces PowerDNS functionality. Test thoroughly in a development environment before production use. Always maintain backups of your DNS configurations.

---

**Made with ❤️ for the CyberPanel community**

For optimal experience, ensure your GoDaddy account has active domains and appropriate API permissions before installation.