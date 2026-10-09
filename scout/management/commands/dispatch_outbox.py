from django.core.management.base import BaseCommand
from scout.worker import dispatch_one
class Command(BaseCommand):
    help='Dispatch up to 25 owner-approved jobs once. Disabled unless explicitly configured.'
    def handle(self,*args,**opts):
        count=0
        for _ in range(25):
            if dispatch_one() is None:break
            count+=1
        self.stdout.write(f'Processed {count} jobs. No automatic uncertain-delivery retries.')
