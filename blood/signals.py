from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.db.models import Sum
from django.db import transaction
from blood.models import Stock, StockUnit, StockTransaction
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=StockUnit)
@receiver(post_delete, sender=StockUnit)
def update_stock_aggregate(sender, instance, **kwargs):
    """
    Signal handler to update the aggregated Stock record whenever
    a StockUnit is saved or deleted.
    It sums all non-expired StockUnit units for a given center and bloodgroup,
    then updates or creates the Stock aggregate.
    """
    try:
        with transaction.atomic():
            # Calculate total units for this center/bloodgroup combination
            # Only count units that are positive and not expired
            total_units = StockUnit.objects.filter(
                center=instance.center,
                bloodgroup=instance.bloodgroup,
                expiry_date__gte=timezone.now().date(),
                unit__gt=0  # Only count units with positive quantities
            ).aggregate(total=Sum('unit'))['total'] or 0
            
            # Get or create the aggregate stock record
            stock, created = Stock.objects.get_or_create(
                center=instance.center,
                bloodgroup=instance.bloodgroup,
                defaults={'unit': total_units}
            )
            
            # Update only if the unit count has changed to avoid unnecessary saves
            if not created and stock.unit != total_units:
                old_units = stock.unit
                stock.unit = total_units
                stock.save(update_fields=['unit'])  # Only update the unit field
                
                logger.info(
                    f"📊 STOCK AGGREGATE UPDATED: {instance.center.name} - {instance.bloodgroup}: "
                    f"{old_units}ml → {total_units}ml"
                )
            elif created:
                logger.info(
                    f"📊 NEW STOCK AGGREGATE: {instance.center.name} - "
                    f"{instance.bloodgroup}: {total_units}ml"
                )
            
            # Log if stock reaches critical levels
            if total_units <= 1000 and total_units > 0:  # Low stock warning
                logger.warning(
                    f"⚠️ LOW STOCK ALERT: {instance.center.name} - {instance.bloodgroup}: "
                    f"Only {total_units}ml remaining!"
                )
            elif total_units == 0:  # Out of stock
                logger.warning(
                    f"🚨 OUT OF STOCK: {instance.center.name} - {instance.bloodgroup}: "
                    f"No stock available!"
                )
            
    except Exception as e:
        logger.error(
            f"❌ Error updating stock aggregate for {instance.center.name} - "
            f"{instance.bloodgroup}: {str(e)}",
            exc_info=True
        )
        # Re-raise to ensure the transaction is rolled back
        raise


@receiver(post_save, sender=StockUnit)
def log_stock_unit_changes(sender, instance, created, **kwargs):
    """
    Log when StockUnit records are created or modified.
    This helps with auditing and debugging stock issues.
    """
    try:
        if created:
            logger.info(
                f"📦 NEW STOCK UNIT: {instance.barcode} - "
                f"{instance.unit}ml {instance.bloodgroup} at {instance.center.name} "
                f"(expires: {instance.expiry_date})"
            )
            
            # Check for soon-to-expire units (within 7 days)
            days_until_expiry = (instance.expiry_date - timezone.now().date()).days
            if days_until_expiry <= 7:
                logger.warning(
                    f"⏰ EXPIRING SOON: {instance.barcode} expires in {days_until_expiry} days"
                )
        else:
            # This is an update to an existing StockUnit
            logger.info(
                f"🔄 STOCK UNIT UPDATED: {instance.barcode} - "
                f"{instance.unit}ml {instance.bloodgroup} at {instance.center.name}"
            )
            
            # Log if unit was completely depleted
            if instance.unit == 0:
                logger.info(f"📤 STOCK UNIT DEPLETED: {instance.barcode}")
            
    except Exception as e:
        logger.error(f"❌ Error logging StockUnit changes: {str(e)}")
        # Don't re-raise here as this is just logging


@receiver(pre_save, sender=StockUnit)
def validate_stock_unit_changes(sender, instance, **kwargs):
    """
    Validate StockUnit changes before saving to prevent invalid data.
    """
    try:
        # Ensure unit is not negative
        if instance.unit < 0:
            logger.error(f"❌ VALIDATION ERROR: Negative units not allowed for {instance.barcode}")
            raise ValueError(f"Stock unit cannot be negative: {instance.unit}")
        
        # Ensure expiry date is not in the distant past (more than 1 year ago)
        one_year_ago = timezone.now().date().replace(year=timezone.now().year - 1)
        if instance.expiry_date < one_year_ago:
            logger.error(f"❌ VALIDATION ERROR: Expiry date too old for {instance.barcode}: {instance.expiry_date}")
            raise ValueError(f"Expiry date cannot be more than 1 year in the past: {instance.expiry_date}")
        
        # Log if trying to add blood with very short expiry (less than 7 days)
        if instance.pk is None:  # New instance
            days_until_expiry = (instance.expiry_date - timezone.now().date()).days
            if days_until_expiry < 7:
                logger.warning(
                    f"⚠️ SHORT EXPIRY: Adding blood that expires in {days_until_expiry} days: {instance.barcode}"
                )
                
    except Exception as e:
        logger.error(f"❌ Error validating StockUnit: {str(e)}")
        raise


@receiver(post_save, sender=StockTransaction)
def log_stock_transaction(sender, instance, created, **kwargs):
    """
    Log stock transactions for audit trail.
    """
    if not created:
        return  # Only log new transactions
    
    try:
        transaction_type = instance.transaction_type.upper()
        user_name = instance.user.get_full_name() if instance.user else 'System'
        
        if instance.quantity_added:
            logger.info(
                f"💰 TRANSACTION - ADDITION: {instance.quantity_added}ml added to "
                f"{instance.stockunit.barcode} by {user_name}"
            )
        elif instance.quantity_deducted:
            logger.info(
                f"💸 TRANSACTION - DEDUCTION: {instance.quantity_deducted}ml deducted from "
                f"{instance.stockunit.barcode} by {user_name}"
            )
        
        # Log appointment context if available
        if instance.appointment:
            logger.info(
                f"🏥 Transaction linked to appointment {instance.appointment.id}"
            )
        
        # Log request context if available
        if hasattr(instance, 'blood_request') and instance.blood_request:
            logger.info(
                f"🩸 Transaction for blood request by {instance.blood_request.patient.get_full_name()}"
            )
        elif hasattr(instance, 'blood_donation') and instance.blood_donation:
            logger.info(
                f"🩸 Transaction for blood donation by {instance.blood_donation.patient.get_full_name()}"
            )
            
    except Exception as e:
        logger.error(f"❌ Error logging stock transaction: {str(e)}")


@receiver(post_save, sender=Stock)
def monitor_critical_stock_levels(sender, instance, **kwargs):
    """
    Monitor stock levels and create alerts for critical situations.
    """
    try:
        # Define thresholds
        CRITICAL_THRESHOLD = 500  # ml
        LOW_THRESHOLD = 1000  # ml
        
        if instance.unit <= CRITICAL_THRESHOLD and instance.unit > 0:
            logger.critical(
                f"🚨 CRITICAL STOCK LEVEL: {instance.center.name} - {instance.bloodgroup}: "
                f"Only {instance.unit}ml remaining! Immediate restocking required."
            )
            
            # Here you could trigger additional alerts:
            # - Send email notifications
            # - Create system notifications
            # - Trigger emergency procurement processes
            
        elif instance.unit <= LOW_THRESHOLD and instance.unit > CRITICAL_THRESHOLD:
            logger.warning(
                f"⚠️ LOW STOCK LEVEL: {instance.center.name} - {instance.bloodgroup}: "
                f"Only {instance.unit}ml remaining. Consider restocking soon."
            )
        
        elif instance.unit == 0:
            logger.critical(
                f"🚨 OUT OF STOCK: {instance.center.name} - {instance.bloodgroup}: "
                f"No stock available! Cannot fulfill requests."
            )
            
    except Exception as e:
        logger.error(f"❌ Error monitoring stock levels: {str(e)}")


# Additional signal for maintaining data integrity
@receiver(pre_save, sender=Stock)
def validate_stock_aggregate_changes(sender, instance, **kwargs):
    """
    Validate Stock aggregate changes to ensure data consistency.
    """
    try:
        # Ensure stock unit is not negative
        if instance.unit < 0:
            logger.error(f"❌ VALIDATION ERROR: Negative stock not allowed for {instance.center.name} - {instance.bloodgroup}")
            raise ValueError(f"Stock unit cannot be negative: {instance.unit}")
            
        # Log significant changes for audit
        if instance.pk:  # Existing instance
            try:
                old_instance = Stock.objects.get(pk=instance.pk)
                difference = instance.unit - old_instance.unit
                
                if abs(difference) > 1000:  # Log significant changes
                    logger.info(
                        f"📈 SIGNIFICANT STOCK CHANGE: {instance.center.name} - {instance.bloodgroup}: "
                        f"{old_instance.unit}ml → {instance.unit}ml (change: {difference:+}ml)"
                    )
            except Stock.DoesNotExist:
                pass  # This shouldn't happen, but handle gracefully
                
    except Exception as e:
        logger.error(f"❌ Error validating Stock aggregate: {str(e)}")
        raise
