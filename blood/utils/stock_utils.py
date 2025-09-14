import json
import uuid
from django.db import transaction
from django.utils import timezone
from blood.models import DonationCenter, Stock, StockUnit


def get_blood_stock_context(selected_center_id=None):
    """
    Returns context data for blood stock overview per donation center and blood group.
    Includes centers, blood groups, stocks filtered by selected center if provided,
    and JSON data for charts.
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


def deduct_stock_fifo(center, bloodgroup, required_units):
    """
    Deduct required_units (ml) of blood from StockUnits for a given center & bloodgroup,
    using FIFO (earliest expiry first).

    Returns:
        (True, deductions) where deductions is a list of dicts with barcode, quantity, expiry_date
        or
        (False, error_message) if not enough stock.
    """
    stock_qs = StockUnit.objects.filter(
        center=center,
        bloodgroup=bloodgroup,
        unit__gt=0,
        expiry_date__gte=timezone.now().date()
    ).order_by('expiry_date', 'added_on', 'id')  # FIFO ordering

    to_deduct = required_units
    deductions = []

    with transaction.atomic():
        for stock in stock_qs:
            if to_deduct <= 0:
                break
            take = min(stock.unit, to_deduct)
            deductions.append({
                'barcode': stock.barcode,
                'quantity': take,
                'expiry_date': stock.expiry_date,
            })
            stock.unit -= take
            # DO NOT delete depleted stock units - keep them with unit zero
            stock.save(update_fields=['unit'])
            to_deduct -= take

        if to_deduct > 0:
            transaction.set_rollback(True)
            return False, f"Not enough stock to fulfill request: short by {to_deduct} ml."

    return True, deductions


def add_stock(center, bloodgroup, units, expiry_date):
    """
    Add blood units to StockUnit batch and update aggregate Stock.
    Creates a new StockUnit batch with a unique barcode.

    Args:
        center (DonationCenter): The donation center.
        bloodgroup (str): The blood group (e.g., 'A+', 'O-').
        units (int): Quantity in ml to add (must be positive).
        expiry_date (date): Expiry date for this stock unit.

    Returns:
        StockUnit instance: The newly created stock batch.

    Raises:
        ValueError: If units <= 0, or barcode generation fails.
    """
    if units <= 0:
        raise ValueError("Units to add must be positive.")

    with transaction.atomic():
        # Generate unique barcode
        barcode = None
        for _ in range(10):
            candidate = f"STK-{uuid.uuid4().hex[:10].upper()}"
            if not StockUnit.objects.filter(barcode=candidate).exists():
                barcode = candidate
                break
        if not barcode:
            raise ValueError("Failed to generate unique barcode.")

        # Create the new StockUnit batch
        batch = StockUnit.objects.create(
            center=center,
            bloodgroup=bloodgroup,
            unit=units,
            expiry_date=expiry_date,
            barcode=barcode,
        )

        # Update or create aggregate stock record 
        stock, created = Stock.objects.get_or_create(
            center=center,
            bloodgroup=bloodgroup,
            defaults={'unit': 0}
        )
        stock.unit += units

        
        stock.save()

    return batch
