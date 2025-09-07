from django.apps import AppConfig

class GodaddydnsConfig(AppConfig):
    name = 'godaddyDNS'
    verbose_name = 'GoDaddy DNS Manager'
    
    def ready(self):
        import godaddyDNS.signals