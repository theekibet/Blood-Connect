import json
import uuid
import logging
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum, F, Q, Count
from blood.models import DonationCenter, Stock, StockUnit, StockTransaction

logger = logging.getLogger(__name__)


def get_blood_stock_context(selected_center_id=None):
    """
    Returns context data for blood stock overview per donation center and blood group.
    Includes centers, blood groups, stocks filtered by selected center if provided,
    and JSON data for charts.
    
    NOTE: Now only counts SAFE, non-quarantined stock for accurate availability.
    """
    centers = DonationCenter.objects.all()
    blood_groups = [bg for bg, _ in Stock.BLOOD_GROUP_CHOICES]

    all_centers_stock_data = []
    for center in centers:
        center_stock = {bg: 0 for bg in blood_groups}
        for stock in Stock.objects.filter(center=center):
            center_stock[stock.bloodgroup] = stock.unit
        all_centers_stock_data.append({
            'center': center,
            'stock': center_stock
        })

    chart_data = [
        {
            'center': c['center'].name,
            'center_id': c['center'].id,
            'city': c['center'].city,
            'stock': c['stock'],
        } for c in all_centers_stock_data
    ]

    selected_center = None
    stocks = Stock.objects.none()
    if selected_center_id and selected_center_id != 'all':
        try:
            selected_center = DonationCenter.objects.get(id=int(selected_center_id))
            stocks = Stock.objects.filter(center=selected_center)
        except (ValueError, DonationCenter.DoesNotExist):
            selected_center = None
            stocks = Stock.objects.none()

    return {
        'centers': centers,
        'blood_groups': blood_groups,
        'chart_data_json': json.dumps(chart_data),
        'selected_center': selected_center,
        'stocks': stocks,
    }


def add_stock(center, bloodgroup, units, expiry_date, safety_status='pending', 
              unsafe_reason=None, safety_notes=None, blood_donation=None, 
              added_by_user=None, added_by_role='nurse'):
    """
    Add blood units to StockUnit batch and update aggregate Stock.
    Creates a new StockUnit batch with a unique barcode.
    
    This function is used for BLOOD DONATIONS when completing appointments.
    
    NEW: Now includes safety_status parameter for safety verification tracking.

    Args:
        center (DonationCenter): The donation center.
        bloodgroup (str): The blood group (e.g., 'A+', 'O-').
        units (int): Quantity in ml to add (must be positive).
        expiry_date (date): Expiry date for this stock unit.
        safety_status (str): Safety verification status ('pending', 'safe', 'unsafe').
                            Defaults to 'pending' for verification workflow.
        unsafe_reason (str, optional): Reason if marking as unsafe.
        safety_notes (str, optional): Additional notes about safety verification.
        blood_donation (BloodDonate, optional): Link to the original blood donation.
        added_by_user (User, optional): User adding the stock.
        added_by_role (str): Role of user adding stock ('nurse', 'lab_tech', 'system').

    Returns:
        StockUnit instance: The newly created stock batch.

    Raises:
        ValueError: If units <= 0, expiry date is invalid, safety_status invalid, 
                   or barcode generation fails.
    """
    if units <= 0 and safety_status != 'unsafe':
        raise ValueError("Units to add must be positive for safe/pending blood.")
    
    if expiry_date < timezone.now().date():
        raise ValueError("Expiry date cannot be in the past.")
    
    # Validate safety status
    valid_statuses = ['pending', 'safe', 'unsafe']
    if safety_status not in valid_statuses:
        raise ValueError(f"Invalid safety_status '{safety_status}'. Must be one of: {valid_statuses}")
    
    # Validate unsafe reason is provided when status is unsafe
    if safety_status == 'unsafe' and not unsafe_reason:
        raise ValueError("unsafe_reason is required when safety_status is 'unsafe'")

    logger.info(
        f"🩸 ADDITION REQUEST: {units}ml {bloodgroup} to {center.name} "
        f"(expires: {expiry_date}, safety: {safety_status})"
        + (f" - Reason: {unsafe_reason}" if unsafe_reason else "")
        + (f" - Notes: {safety_notes}" if safety_notes else "")
    )

    with transaction.atomic():
        try:
            # Generate unique barcode with retry mechanism
            barcode = None
            for attempt in range(10):
                candidate = f"STK-{uuid.uuid4().hex[:10].upper()}"
                if not StockUnit.objects.filter(barcode=candidate).exists():
                    barcode = candidate
                    break
            
            if not barcode:
                logger.error("❌ BARCODE GENERATION FAILED after 10 attempts")
                raise ValueError("Failed to generate unique barcode after 10 attempts.")

            # Set actual units - zero out if unsafe
            actual_units = 0 if safety_status == 'unsafe' else units

            # Create the new StockUnit batch with safety status
            stock_unit = StockUnit.objects.create(
                center=center,
                bloodgroup=bloodgroup,
                unit=actual_units,
                expiry_date=expiry_date,
                barcode=barcode,
                added_on=timezone.now(),
                blood_donation=blood_donation,
                safety_status=safety_status,
                unsafe_reason=unsafe_reason,
                safety_notes=safety_notes,
                is_quarantined=(safety_status == 'unsafe'),
                safety_verified_by=added_by_user if safety_status != 'pending' else None,
                safety_verified_at=timezone.now() if safety_status != 'pending' else None,
                safety_verified_by_role=added_by_role if safety_status != 'pending' else None,
                added_to_inventory_by=added_by_user,
                added_to_inventory_by_role=added_by_role,
                added_to_inventory_at=timezone.now()
            )

            safety_indicator = {
                'pending': '⏳',
                'safe': '✅',
                'unsafe': '⚠️'
            }.get(safety_status, '❓')

            logger.info(
                f"📈 STOCK UNIT CREATED: {barcode} - {actual_units}ml {bloodgroup} at {center.name} "
                f"{safety_indicator} {safety_status.upper()}"
                + (f" - Reason: {unsafe_reason}" if unsafe_reason else "")
            )

            # Create stock transaction record
            StockTransaction.objects.create(
                stockunit=stock_unit,
                quantity_added=actual_units,
                transaction_type='addition',
                user=added_by_user,
                notes=f"Stock added - Status: {safety_status}" + (f" - {unsafe_reason}" if unsafe_reason else "")
            )

            # The signal handler will automatically update the Stock aggregate
            # NOTE: Aggregate now only counts SAFE stock, so pending/unsafe won't affect it yet
            stock, created = Stock.objects.get_or_create(
                center=center,
                bloodgroup=bloodgroup,
                defaults={'unit': 0}
            )
            
            # Refresh the stock record to get current value after signal processing
            stock.refresh_from_db()

            if created:
                logger.info(
                    f"✅ NEW STOCK RECORD: {center.name} - {bloodgroup} "
                    f"initialized with {stock.unit}ml (safe stock only)"
                )
            else:
                logger.info(
                    f"✅ STOCK UPDATED: {center.name} - {bloodgroup} "
                    f"now has {stock.unit}ml (safe stock only)"
                )

            return stock_unit

        except Exception as e:
            logger.error(f"❌ ADDITION ERROR: {e}", exc_info=True)
            raise


def deduct_stock_fifo(center, bloodgroup, required_units, deducted_by_user=None, 
                      deducted_by_role='blood_bank_tech', blood_request=None, appointment=None):
    """
    Deduct required_units (ml) of blood from StockUnits for a given center & bloodgroup,
    using FIFO (earliest expiry first).
    
    This function is used for BLOOD REQUESTS when completing appointments.
    
    CRITICAL UPDATE: Now ONLY deducts from SAFE, non-quarantined stock.
    This ensures only verified safe blood is issued to patients.

    Args:
        center (DonationCenter): The donation center.
        bloodgroup (str): The blood group (e.g., 'A+', 'O-').
        required_units (int): Quantity in ml to deduct.
        deducted_by_user (User, optional): User performing the deduction.
        deducted_by_role (str): Role of user ('blood_bank_tech', 'nurse', 'admin').
        blood_request (BloodRequest, optional): Related blood request.
        appointment (Appointment, optional): Related appointment.

    Returns:
        (True, deductions) where deductions is a list of dicts with barcode, quantity, expiry_date
        or
        (False, error_message) if not enough safe stock available.
    """
    if required_units <= 0:
        return False, "Required units must be positive."

    logger.info(
        f"🩸 DEDUCTION REQUEST: {required_units}ml {bloodgroup} from {center.name} "
        f"(SAFE stock only)"
    )

    with transaction.atomic():
        try:
            # ===================================================================
            # CRITICAL: ONLY query SAFE, non-quarantined stock units
            # ===================================================================
            stock_qs = StockUnit.objects.filter(
                center=center,
                bloodgroup=bloodgroup,
                safety_status='safe',         # ✅ ONLY SAFE BLOOD
                is_quarantined=False,         # ✅ NOT QUARANTINED
                unit__gt=0,
                expiry_date__gte=timezone.now().date()
            ).order_by('expiry_date', 'added_on', 'id').select_for_update()

            # Check total SAFE availability before attempting deduction
            total_available = stock_qs.aggregate(total=Sum('unit'))['total'] or 0
            
            if total_available < required_units:
                # Check if there's pending/unsafe stock to provide better error message
                pending_stock = StockUnit.objects.filter(
                    center=center,
                    bloodgroup=bloodgroup,
                    safety_status='pending',
                    unit__gt=0,
                    expiry_date__gte=timezone.now().date()
                ).aggregate(total=Sum('unit'))['total'] or 0
                
                error_msg = (
                    f"Insufficient SAFE stock: Only {total_available}ml verified safe blood available, "
                    f"need {required_units}ml."
                )
                
                if pending_stock > 0:
                    error_msg += (
                        f" Note: {pending_stock}ml is awaiting safety verification. "
                        f"Please verify pending stock before issuing."
                    )
                
                logger.warning(
                    f"❌ INSUFFICIENT SAFE STOCK: Need {required_units}ml, "
                    f"available {total_available}ml safe {bloodgroup} at {center.name} "
                    f"(pending: {pending_stock}ml)"
                )
                return False, error_msg

            to_deduct = required_units
            deductions = []

            for stock in stock_qs:
                if to_deduct <= 0:
                    break
                    
                take = min(stock.unit, to_deduct)
                deduction_record = {
                    'barcode': stock.barcode,
                    'quantity': take,
                    'expiry_date': stock.expiry_date,
                    'original_unit': stock.unit,
                    'remaining_unit': stock.unit - take,
                    'safety_status': stock.safety_status,
                    'stock_unit_id': stock.id
                }
                deductions.append(deduction_record)
                
                # Update stock unit
                stock.unit -= take
                stock.save(update_fields=['unit'])
                
                # Create stock transaction record
                StockTransaction.objects.create(
                    stockunit=stock,
                    quantity_deducted=take,
                    transaction_type='deduction',
                    user=deducted_by_user,
                    blood_request=blood_request,
                    appointment=appointment,
                    notes=f"Deducted {take}ml for blood request" + (f" #{blood_request.id}" if blood_request else "")
                )
                
                logger.info(
                    f"📉 DEDUCTED: {take}ml from {stock.barcode} "
                    f"(remaining: {stock.unit}ml) - ✅ SAFE STOCK"
                )
                
                to_deduct -= take

            # Verify all required units were deducted
            if to_deduct > 0:
                logger.error(
                    f"❌ DEDUCTION FAILED: Still short by {to_deduct}ml "
                    f"after processing all safe units"
                )
                return False, f"Deduction failed: Short by {to_deduct}ml."

            logger.info(
                f"✅ DEDUCTION SUCCESS: {required_units}ml SAFE {bloodgroup} "
                f"deducted from {center.name} using {len(deductions)} batch(es)"
            )
            
            # The signal handler will automatically update the Stock aggregate
            return True, deductions

        except Exception as e:
            logger.error(f"❌ DEDUCTION ERROR: {e}", exc_info=True)
            return False, f"Deduction failed due to error: {str(e)}"


def check_stock_availability(center, bloodgroup, required_units, include_pending=False):
    """
    Check if sufficient stock is available for a blood request.
    
    NEW: Now checks SAFE stock by default. Can optionally include pending stock.
    
    Args:
        center (DonationCenter): The donation center.
        bloodgroup (str): The blood group.
        required_units (int): Required quantity in ml.
        include_pending (bool): If True, includes pending verification stock in count.
    
    Returns:
        dict: {
            'available': bool,
            'current_stock': int (safe stock),
            'pending_stock': int (awaiting verification),
            'unsafe_stock': int (quarantined),
            'shortage': int (if any),
            'expiring_soon': list of safe units expiring within 7 days,
            'can_fulfill': bool (whether request can be fulfilled with safe stock)
        }
    """
    # Safe stock (available for issuance)
    safe_stock = StockUnit.objects.filter(
        center=center,
        bloodgroup=bloodgroup,
        safety_status='safe',
        is_quarantined=False,
        unit__gt=0,
        expiry_date__gte=timezone.now().date()
    ).aggregate(total=Sum('unit'))['total'] or 0
    
    # Pending verification stock
    pending_stock = StockUnit.objects.filter(
        center=center,
        bloodgroup=bloodgroup,
        safety_status='pending',
        unit__gt=0,
        expiry_date__gte=timezone.now().date()
    ).aggregate(total=Sum('unit'))['total'] or 0
    
    # Unsafe/quarantined stock
    unsafe_stock = StockUnit.objects.filter(
        center=center,
        bloodgroup=bloodgroup,
        safety_status='unsafe',
    ).aggregate(total=Sum('unit'))['total'] or 0
    
    # Calculate total considering include_pending flag
    if include_pending:
        current_stock = safe_stock + pending_stock
    else:
        current_stock = safe_stock
    
    # Check for safe units expiring soon (within 7 days)
    expiring_soon = StockUnit.objects.filter(
        center=center,
        bloodgroup=bloodgroup,
        safety_status='safe',
        is_quarantined=False,
        unit__gt=0,
        expiry_date__gte=timezone.now().date(),
        expiry_date__lte=(timezone.now().date() + timezone.timedelta(days=7))
    ).values('barcode', 'unit', 'expiry_date', 'safety_status')
    
    # Get detailed breakdown by batch
    available_batches = StockUnit.objects.filter(
        center=center,
        bloodgroup=bloodgroup,
        safety_status='safe',
        is_quarantined=False,
        unit__gt=0,
        expiry_date__gte=timezone.now().date()
    ).values('barcode', 'unit', 'expiry_date').order_by('expiry_date')
    
    return {
        'available': safe_stock >= required_units,
        'can_fulfill': safe_stock >= required_units,
        'current_stock': current_stock,
        'safe_stock': safe_stock,
        'pending_stock': pending_stock,
        'unsafe_stock': unsafe_stock,
        'shortage': max(0, required_units - safe_stock),
        'expiring_soon': list(expiring_soon),
        'available_batches': list(available_batches),
        'total_batches': available_batches.count()
    }


def get_available_stock(center, bloodgroup=None):
    """
    Get available SAFE stock for issuance.
    
    Returns only blood units that are:
    - Verified as safe
    - Not quarantined
    - Not expired
    - Have units > 0
    
    Args:
        center (DonationCenter): The donation center.
        bloodgroup (str, optional): Specific blood group to filter by.
    
    Returns:
        QuerySet: StockUnit objects that are safe for use.
    """
    queryset = StockUnit.objects.filter(
        center=center,
        safety_status='safe',
        is_quarantined=False,
        unit__gt=0,
        expiry_date__gte=timezone.now().date()
    ).select_related('blood_donation__donor__user')
    
    if bloodgroup:
        queryset = queryset.filter(bloodgroup=bloodgroup)
    
    logger.debug(
        f"Available safe stock query for {center.name}" + 
        (f" - {bloodgroup}" if bloodgroup else " - all blood groups")
    )
    
    return queryset.order_by('expiry_date', 'added_on')


def get_pending_verification_stock(center, bloodgroup=None):
    """
    Get stock units awaiting safety verification.
    
    Args:
        center (DonationCenter): The donation center.
        bloodgroup (str, optional): Specific blood group to filter by.
    
    Returns:
        QuerySet: StockUnit objects pending verification.
    """
    queryset = StockUnit.objects.filter(
        center=center,
        safety_status='pending',
        unit__gt=0,
        expiry_date__gte=timezone.now().date()
    ).select_related('blood_donation__donor__user')
    
    if bloodgroup:
        queryset = queryset.filter(bloodgroup=bloodgroup)
    
    return queryset.order_by('-added_on')


def get_unsafe_stock(center, bloodgroup=None):
    """
    Get stock units marked as unsafe/quarantined.
    
    Args:
        center (DonationCenter): The donation center.
        bloodgroup (str, optional): Specific blood group to filter by.
    
    Returns:
        QuerySet: StockUnit objects that are unsafe.
    """
    queryset = StockUnit.objects.filter(
        center=center,
        safety_status='unsafe'
    ).select_related('blood_donation__donor__user', 'safety_verified_by')
    
    if bloodgroup:
        queryset = queryset.filter(bloodgroup=bloodgroup)
    
    return queryset.order_by('-safety_verified_at')


def get_stock_summary(center):
    """
    Get comprehensive stock summary including safety status breakdown.
    
    Args:
        center (DonationCenter): The donation center.
    
    Returns:
        dict: Stock summary with counts for safe, pending, and unsafe stock.
    """
    summary = {
        'safe': StockUnit.objects.filter(
            center=center,
            safety_status='safe',
            is_quarantined=False,
            unit__gt=0,
            expiry_date__gte=timezone.now().date()
        ).aggregate(
            total_units=Sum('unit'),
            count=Count('id')
        ),
        'pending': StockUnit.objects.filter(
            center=center,
            safety_status='pending',
            unit__gt=0,
            expiry_date__gte=timezone.now().date()
        ).aggregate(
            total_units=Sum('unit'),
            count=Count('id')
        ),
        'unsafe': StockUnit.objects.filter(
            center=center,
            safety_status='unsafe'
        ).aggregate(
            total_units=Sum('unit'),
            count=Count('id')
        ),
        'expired': StockUnit.objects.filter(
            center=center,
            unit__gt=0,
            expiry_date__lt=timezone.now().date()
        ).aggregate(
            total_units=Sum('unit'),
            count=Count('id')
        ),
    }
    
    # Add totals
    summary['total_safe_units'] = summary['safe']['total_units'] or 0
    summary['total_safe_batches'] = summary['safe']['count'] or 0
    summary['total_pending_units'] = summary['pending']['total_units'] or 0
    summary['total_pending_batches'] = summary['pending']['count'] or 0
    summary['total_unsafe_units'] = summary['unsafe']['total_units'] or 0
    summary['total_unsafe_batches'] = summary['unsafe']['count'] or 0
    summary['total_expired_units'] = summary['expired']['total_units'] or 0
    summary['total_expired_batches'] = summary['expired']['count'] or 0
    
    # Get breakdown by blood group
    summary['by_blood_group'] = {}
    for bg, _ in Stock.BLOOD_GROUP_CHOICES:
        summary['by_blood_group'][bg] = {
            'safe': StockUnit.objects.filter(
                center=center,
                bloodgroup=bg,
                safety_status='safe',
                is_quarantined=False,
                unit__gt=0,
                expiry_date__gte=timezone.now().date()
            ).aggregate(units=Sum('unit'), batches=Count('id')),
            'pending': StockUnit.objects.filter(
                center=center,
                bloodgroup=bg,
                safety_status='pending',
                unit__gt=0,
                expiry_date__gte=timezone.now().date()
            ).aggregate(units=Sum('unit'), batches=Count('id')),
        }
    
    return summary


def get_stock_summary_by_center(center=None):
    """
    Get stock summary for all blood groups at a specific center or all centers.
    
    NEW: Now includes safety status breakdown.
    
    Args:
        center (DonationCenter, optional): Specific center. If None, returns all centers.
    
    Returns:
        dict: Stock summary organized by center and blood group with safety breakdown.
    """
    if center:
        centers = [center]
    else:
        centers = DonationCenter.objects.all()
    
    summary = {}
    for center_obj in centers:
        center_stock = {}
        stocks = Stock.objects.filter(center=center_obj)
        
        for stock in stocks:
            # Get safe stock breakdown (available for issuance)
            safe_units_breakdown = StockUnit.objects.filter(
                center=center_obj,
                bloodgroup=stock.bloodgroup,
                safety_status='safe',
                is_quarantined=False,
                unit__gt=0,
                expiry_date__gte=timezone.now().date()
            ).values('barcode', 'unit', 'expiry_date', 'safety_status').order_by('expiry_date')
            
            # Get pending verification stock
            pending_units = StockUnit.objects.filter(
                center=center_obj,
                bloodgroup=stock.bloodgroup,
                safety_status='pending',
                unit__gt=0,
                expiry_date__gte=timezone.now().date()
            ).aggregate(total=Sum('unit'))['total'] or 0
            
            # Get pending batches count
            pending_batches = StockUnit.objects.filter(
                center=center_obj,
                bloodgroup=stock.bloodgroup,
                safety_status='pending',
                unit__gt=0,
                expiry_date__gte=timezone.now().date()
            ).count()
            
            # Get unsafe/quarantined stock
            unsafe_units = StockUnit.objects.filter(
                center=center_obj,
                bloodgroup=stock.bloodgroup,
                safety_status='unsafe'
            ).aggregate(total=Sum('unit'))['total'] or 0
            
            # Get expired units
            expired_units = StockUnit.objects.filter(
                center=center_obj,
                bloodgroup=stock.bloodgroup,
                unit__gt=0,
                expiry_date__lt=timezone.now().date()
            ).aggregate(total=Sum('unit'))['total'] or 0
            
            center_stock[stock.bloodgroup] = {
                'total_safe_units': stock.unit,  # Aggregate now only counts safe stock
                'available_batches': len(safe_units_breakdown),
                'pending_verification_units': pending_units,
                'pending_verification_batches': pending_batches,
                'unsafe_quarantined_units': unsafe_units,
                'expired_units': expired_units,
                'safe_batches': list(safe_units_breakdown),
                'can_issue': stock.unit > 0,  # Based on safe stock only
                'needs_verification': pending_units > 0
            }
        
        summary[center_obj.name] = center_stock
    
    return summary


def cleanup_expired_stock():
    """
    Mark expired stock units and log them for audit purposes.
    This function should be run periodically (e.g., daily via cron job).
    
    NEW: Also handles safety status of expired units.
    
    Returns:
        dict: Summary of cleanup operations.
    """
    today = timezone.now().date()
    
    with transaction.atomic():
        # Find expired stock units that still have quantity
        expired_units = StockUnit.objects.filter(
            expiry_date__lt=today,
            unit__gt=0
        ).select_for_update()
        
        cleanup_summary = {
            'expired_units_found': expired_units.count(),
            'total_expired_ml': 0,
            'centers_affected': set(),
            'blood_groups_affected': set(),
            'expired_details': [],
            'safety_status_breakdown': {
                'safe': 0,
                'pending': 0,
                'unsafe': 0
            }
        }
        
        for unit in expired_units:
            cleanup_summary['total_expired_ml'] += unit.unit
            cleanup_summary['centers_affected'].add(unit.center.name)
            cleanup_summary['blood_groups_affected'].add(unit.bloodgroup)
            cleanup_summary['safety_status_breakdown'][unit.safety_status] += unit.unit
            
            cleanup_summary['expired_details'].append({
                'barcode': unit.barcode,
                'center': unit.center.name,
                'bloodgroup': unit.bloodgroup,
                'expired_ml': unit.unit,
                'expiry_date': unit.expiry_date.isoformat(),
                'days_expired': (today - unit.expiry_date).days,
                'safety_status': unit.safety_status
            })
            
            safety_indicator = {
                'safe': '✅',
                'pending': '⏳',
                'unsafe': '⚠️'
            }.get(unit.safety_status, '❓')
            
            logger.warning(
                f"⚠️ EXPIRED STOCK: {unit.barcode} - {unit.unit}ml {unit.bloodgroup} "
                f"at {unit.center.name} (expired {unit.expiry_date}, "
                f"safety: {safety_indicator} {unit.safety_status})"
            )
            
            # Create transaction record for expiration
            StockTransaction.objects.create(
                stockunit=unit,
                quantity_deducted=unit.unit,
                transaction_type='deduction',
                notes=f"Auto-cleanup: Blood expired on {unit.expiry_date}"
            )
            
            # Mark as expired but keep the record for audit
            # If it was safe, it's now effectively unsafe due to expiration
            if unit.safety_status == 'safe':
                unit.safety_status = 'unsafe'
                unit.unsafe_reason = 'expired'
                unit.is_quarantined = True
            
            unit.unit = 0
            unit.save(update_fields=['unit', 'safety_status', 'unsafe_reason', 'is_quarantined'])
        
        # Convert sets to lists for JSON serialization
        cleanup_summary['centers_affected'] = list(cleanup_summary['centers_affected'])
        cleanup_summary['blood_groups_affected'] = list(cleanup_summary['blood_groups_affected'])
        
        if cleanup_summary['expired_units_found'] > 0:
            logger.info(
                f"🧹 CLEANUP COMPLETE: {cleanup_summary['expired_units_found']} expired units processed, "
                f"{cleanup_summary['total_expired_ml']}ml marked as expired and quarantined"
            )
        
        return cleanup_summary


def validate_stock_consistency():
    """
    Validate that Stock aggregate records match the sum of their SAFE StockUnit records.
    This function helps identify any inconsistencies in stock data.
    
    UPDATED: Now validates against SAFE stock only, as aggregates should only count safe stock.
    
    Returns:
        dict: Validation results with any inconsistencies found.
    """
    inconsistencies = []
    
    for stock in Stock.objects.all():
        # Calculate actual total from SAFE StockUnits only
        actual_total = StockUnit.objects.filter(
            center=stock.center,
            bloodgroup=stock.bloodgroup,
            safety_status='safe',         # Only safe stock
            is_quarantined=False,         # Not quarantined
            unit__gt=0,
            expiry_date__gte=timezone.now().date()
        ).aggregate(total=Sum('unit'))['total'] or 0
        
        # Check for discrepancy
        if stock.unit != actual_total:
            # Also get breakdown for detailed reporting
            pending_total = StockUnit.objects.filter(
                center=stock.center,
                bloodgroup=stock.bloodgroup,
                safety_status='pending',
                unit__gt=0,
                expiry_date__gte=timezone.now().date()
            ).aggregate(total=Sum('unit'))['total'] or 0
            
            unsafe_total = StockUnit.objects.filter(
                center=stock.center,
                bloodgroup=stock.bloodgroup,
                safety_status='unsafe'
            ).aggregate(total=Sum('unit'))['total'] or 0
            
            inconsistency = {
                'center': stock.center.name,
                'bloodgroup': stock.bloodgroup,
                'aggregate_stock': stock.unit,
                'actual_safe_stock': actual_total,
                'pending_stock': pending_total,
                'unsafe_stock': unsafe_total,
                'difference': stock.unit - actual_total
            }
            inconsistencies.append(inconsistency)
            
            logger.warning(
                f"⚠️ STOCK INCONSISTENCY: {stock.center.name} - {stock.bloodgroup} "
                f"shows {stock.unit}ml but actual safe stock is {actual_total}ml "
                f"(pending: {pending_total}ml, unsafe: {unsafe_total}ml)"
            )
    
    return {
        'consistent': len(inconsistencies) == 0,
        'inconsistencies_found': len(inconsistencies),
        'details': inconsistencies
    }


def fix_stock_inconsistencies():
    """
    Fix any stock inconsistencies by recalculating aggregate Stock records
    from their corresponding SAFE StockUnit records.
    
    UPDATED: Now calculates based on SAFE stock only.
    
    Returns:
        dict: Results of the fix operation.
    """
    fixed_records = []
    
    with transaction.atomic():
        for stock in Stock.objects.all():
            # Calculate correct total from SAFE StockUnits only
            correct_total = StockUnit.objects.filter(
                center=stock.center,
                bloodgroup=stock.bloodgroup,
                safety_status='safe',
                is_quarantined=False,
                unit__gt=0,
                expiry_date__gte=timezone.now().date()
            ).aggregate(total=Sum('unit'))['total'] or 0
            
            if stock.unit != correct_total:
                old_value = stock.unit
                stock.unit = correct_total
                stock.save(update_fields=['unit'])
                
                fixed_record = {
                    'center': stock.center.name,
                    'bloodgroup': stock.bloodgroup,
                    'old_value': old_value,
                    'new_value': correct_total,
                    'difference': correct_total - old_value
                }
                fixed_records.append(fixed_record)
                
                logger.info(
                    f"🔧 STOCK FIXED: {stock.center.name} - {stock.bloodgroup} "
                    f"corrected from {old_value}ml to {correct_total}ml (safe stock only)"
                )
    
    return {
        'records_fixed': len(fixed_records),
        'details': fixed_records
    }


def bulk_verify_safe_stock(center, bloodgroup=None, verified_by_user=None, notes=None):
    """
    Bulk verify pending stock units as safe.
    Useful for administrators or nurses to quickly verify multiple units.
    
    Args:
        center (DonationCenter): The donation center.
        bloodgroup (str, optional): Specific blood group to verify.
        verified_by_user (User, optional): User performing the verification.
        notes (str, optional): Notes to add to all verified units.
    
    Returns:
        dict: Summary of bulk verification operation.
    """
    with transaction.atomic():
        queryset = StockUnit.objects.filter(
            center=center,
            safety_status='pending',
            unit__gt=0,
            expiry_date__gte=timezone.now().date()
        ).select_for_update()
        
        if bloodgroup:
            queryset = queryset.filter(bloodgroup=bloodgroup)
        
        verified_count = 0
        total_units = 0
        verified_units = []
        
        for unit in queryset:
            old_status = unit.safety_status
            unit.mark_safe(
                verified_by_user=verified_by_user,
                notes=notes or f"Bulk verified as safe at {center.name}"
            )
            
            # Create transaction record
            StockTransaction.objects.create(
                stockunit=unit,
                quantity_added=unit.unit,
                transaction_type='addition',
                user=verified_by_user,
                notes=f"Bulk verified - Status changed from {old_status} to safe"
            )
            
            verified_count += 1
            total_units += unit.unit
            verified_units.append({
                'barcode': unit.barcode,
                'bloodgroup': unit.bloodgroup,
                'units': unit.unit
            })
            
            logger.info(
                f"✅ BULK VERIFIED: {unit.barcode} - {unit.unit}ml {unit.bloodgroup} "
                f"at {center.name}"
            )
        
        return {
            'verified_count': verified_count,
            'total_units': total_units,
            'center': center.name,
            'bloodgroup': bloodgroup or 'all',
            'verified_by': verified_by_user.get_full_name() if verified_by_user else 'System',
            'verified_units': verified_units
        }


def get_safety_verification_stats(center=None):
    """
    Get statistics about safety verification status across centers.
    
    Args:
        center (DonationCenter, optional): Specific center. If None, all centers.
    
    Returns:
        dict: Comprehensive safety verification statistics.
    """
    queryset = StockUnit.objects.all()
    if center:
        queryset = queryset.filter(center=center)
    
    stats = {
        'total_units': queryset.count(),
        'safe_units': queryset.filter(safety_status='safe').count(),
        'pending_units': queryset.filter(safety_status='pending').count(),
        'unsafe_units': queryset.filter(safety_status='unsafe').count(),
        
        'safe_ml': queryset.filter(
            safety_status='safe', 
            unit__gt=0
        ).aggregate(total=Sum('unit'))['total'] or 0,
        
        'pending_ml': queryset.filter(
            safety_status='pending',
            unit__gt=0
        ).aggregate(total=Sum('unit'))['total'] or 0,
        
        'unsafe_ml': queryset.filter(
            safety_status='unsafe'
        ).aggregate(total=Sum('unit'))['total'] or 0,
        
        'verification_rate': 0,
        'unsafe_rate': 0,
    }
    
    # Calculate rates
    if stats['total_units'] > 0:
        stats['verification_rate'] = round(
            (stats['safe_units'] / stats['total_units']) * 100, 2
        )
        stats['unsafe_rate'] = round(
            (stats['unsafe_units'] / stats['total_units']) * 100, 2
        )
    
    # Get unsafe reasons breakdown
    unsafe_reasons = queryset.filter(
        safety_status='unsafe'
    ).values('unsafe_reason').annotate(
        count=Count('id'),
        total_ml=Sum('unit')
    ).order_by('-count')
    
    stats['unsafe_reasons_breakdown'] = list(unsafe_reasons)
    
    # Recently verified (last 7 days)
    seven_days_ago = timezone.now() - timezone.timedelta(days=7)
    stats['recently_verified'] = queryset.filter(
        safety_verified_at__gte=seven_days_ago
    ).count()
    
    # Verification by role
    stats['verified_by_role'] = queryset.filter(
        safety_status='safe'
    ).values('safety_verified_by_role').annotate(
        count=Count('id'),
        total_ml=Sum('unit')
    ).order_by('-count')
    
    return stats