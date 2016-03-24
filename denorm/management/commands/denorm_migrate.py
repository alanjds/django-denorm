from django.core.management.base import BaseCommand
from denorm import denorms


class Command(BaseCommand):
    help = """Migrate: to run on every release
        Calculates the difference between triggers in the db
        and triggers needed by the current version of your code
        and applies the set of changes needed and recomputes appropriately
    """

    def handle(self, **kwargs):
        denorms.smart_db_refresh()
