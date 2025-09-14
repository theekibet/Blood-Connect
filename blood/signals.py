from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.db.models import Sum

from blood.models import Stock, StockUnit


@receiver(post_save, sender=StockUnit)
@receiver(post_delete, sender=StockUnit)
def update_stock_aggregate(sender, instance, **kwargs):
    """
    Signal handler to update the aggregated Stock record whenever
    a StockUnit is saved or deleted.

    It sums all non-expired StockUnit units for a given center and bloodgroup,
    then updates or creates the Stock aggregate.
    """
    total_units = StockUnit.objects.filter(
        center=instance.center,
        bloodgroup=instance.bloodgroup,
        expiry_date__gte=timezone.now().date()
    ).aggregate(total=Sum('unit'))['total'] or 0

    stock, created = Stock.objects.get_or_create(
        center=instance.center,
        bloodgroup=instance.bloodgroup,
        defaults={'unit': total_units}
    )

    # Update only if the unit count has changed to avoid unnecessary saves
    if not created and stock.unit != total_units:
        stock.unit = total_units
        stock.save()
