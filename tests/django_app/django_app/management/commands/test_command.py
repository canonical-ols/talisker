from django.core.management.base import BaseCommand, CommandError
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'test command'

    def handle(self, *args, **options):
        logger.info('test', extra={'foo': 'bar'})
