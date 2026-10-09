import time
from django.core.management import call_command
from django.core.management.base import BaseCommand
class Command(BaseCommand):
    help='Single-replica scheduler: authorized feed polling every five minutes, approved outbox every 30 seconds.'
    def handle(self,*args,**options):
        last_poll=0
        while True:
            now=time.monotonic()
            if now-last_poll>=300:call_command('poll_feeds');last_poll=now
            call_command('dispatch_outbox')
            time.sleep(30)
