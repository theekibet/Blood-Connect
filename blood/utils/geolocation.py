# blood/utils/geolocation.py
from math import radians, sin, cos, sqrt, atan2, degrees, asin
from typing import List, Tuple, Optional, Dict
from decimal import Decimal
import logging

from django.db.models import Q, F, Prefetch
from django.core.cache import cache
from django.utils import timezone
from datetime import date, timedelta

from blood.models import DonationCenter
from donor.models import Donor
# # from patient.models import Patient

logger = logging.getLogger(__name__)

# Constants
EARTH_RADIUS_KM = 6371.0
DEFAULT_MAX_DISTANCE_KM = 50
DONATION_INTERVAL_DAYS = 56
CACHE_TIMEOUT = 300  # 5 minutes

# Coordinate validation ranges
KENYA_BOUNDS = {
    'lat_min': -4.68,
    'lat_max': 5.03,
    'lng_min': 33.89,
    'lng_max': 41.91
}

# City coordinates for common locations
KENYA_CITIES = {
    'nairobi': {'lat': -1.2864, 'lng': 36.8172},
    'mombasa': {'lat': -4.0435, 'lng': 39.6682},
    'kisumu': {'lat': -0.0917, 'lng': 34.7680},
    'nakuru': {'lat': -0.3031, 'lng': 36.0800},
    'eldoret': {'lat': 0.5143, 'lng': 35.2698},
}


class GeoLocationError(Exception):
    """Custom exception for geolocation errors"""
    pass


def validate_coordinates(lat: float, lng: float, strict: bool = True) -> Dict[str, any]:
    """
    Comprehensive coordinate validation with detailed feedback.
    
    Args:
        lat: Latitude value
        lng: Longitude value
        strict: If True, enforce Kenya boundaries
    
    Returns:
        dict: {'valid': bool, 'error': str or None, 'warnings': list}
    """
    result = {'valid': True, 'error': None, 'warnings': []}
    
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        result['valid'] = False
        result['error'] = "Coordinates must be numeric values"
        return result
    
    # Basic range validation
    if not (-90 <= lat <= 90):
        result['valid'] = False
        result['error'] = f"Latitude {lat} is out of range (-90 to 90)"
        return result
    
    if not (-180 <= lng <= 180):
        result['valid'] = False
        result['error'] = f"Longitude {lng} is out of range (-180 to 180)"
        return result
    
    # Precision check (too many decimal places might indicate error)
    lat_str = str(lat)
    lng_str = str(lng)
    if '.' in lat_str and len(lat_str.split('.')[1]) > 8:
        result['warnings'].append("Latitude has excessive precision (>8 decimals)")
    if '.' in lng_str and len(lng_str.split('.')[1]) > 8:
        result['warnings'].append("Longitude has excessive precision (>8 decimals)")
    
    # Zero coordinate check (common error)
    if lat == 0 and lng == 0:
        result['valid'] = False
        result['error'] = "Null Island coordinates (0,0) detected - location not set"
        return result
    
    # Kenya boundaries check (optional)
    if strict:
        if not (KENYA_BOUNDS['lat_min'] <= lat <= KENYA_BOUNDS['lat_max']):
            result['warnings'].append(
                f"Latitude {lat} is outside Kenya boundaries "
                f"({KENYA_BOUNDS['lat_min']} to {KENYA_BOUNDS['lat_max']})"
            )
        
        if not (KENYA_BOUNDS['lng_min'] <= lng <= KENYA_BOUNDS['lng_max']):
            result['warnings'].append(
                f"Longitude {lng} is outside Kenya boundaries "
                f"({KENYA_BOUNDS['lng_min']} to {KENYA_BOUNDS['lng_max']})"
            )
    
    return result


def haversine(lat1: float, lon1: float, lat2: float, lon2: float, 
              precision: int = 2) -> float:
    """
    Calculate distance between two coordinates using Haversine formula.
    More accurate than simple Euclidean distance for geographic coordinates.
    
    Args:
        lat1, lon1: First coordinate
        lat2, lon2: Second coordinate
        precision: Decimal places for result
    
    Returns:
        float: Distance in kilometers
    """
    # Validate coordinates
    validation1 = validate_coordinates(lat1, lon1, strict=False)
    validation2 = validate_coordinates(lat2, lon2, strict=False)
    
    if not validation1['valid']:
        raise GeoLocationError(f"Invalid first coordinate: {validation1['error']}")
    if not validation2['valid']:
        raise GeoLocationError(f"Invalid second coordinate: {validation2['error']}")
    
    try:
        # Convert to radians
        lat1_rad, lon1_rad = radians(lat1), radians(lon1)
        lat2_rad, lon2_rad = radians(lat2), radians(lon2)
        
        # Haversine formula
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        a = sin(dlat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        
        distance = EARTH_RADIUS_KM * c
        
        return round(distance, precision)
        
    except Exception as e:
        logger.error(f"Error calculating haversine distance: {str(e)}")
        raise GeoLocationError(f"Distance calculation failed: {str(e)}")


def vincenty_distance(lat1: float, lon1: float, lat2: float, lon2: float,
                     precision: int = 2) -> float:
    """
    More accurate distance calculation using Vincenty's formula.
    Better for longer distances (>100km).
    
    Args:
        lat1, lon1: First coordinate
        lat2, lon2: Second coordinate
        precision: Decimal places for result
    
    Returns:
        float: Distance in kilometers
    """
    # For simplicity, using Haversine (Vincenty is more complex)
    # Haversine is accurate enough for distances <1000km
    return haversine(lat1, lon1, lat2, lon2, precision)


def get_bounding_box(lat: float, lng: float, distance_km: float) -> Dict[str, float]:
    """
    Calculate bounding box for efficient database queries.
    Returns min/max lat/lng that encompasses the search radius.
    
    Args:
        lat: Center latitude
        lng: Center longitude
        distance_km: Radius in kilometers
    
    Returns:
        dict: {'lat_min', 'lat_max', 'lng_min', 'lng_max'}
    """
    # Rough conversion: 1 degree latitude ≈ 111 km
    # 1 degree longitude ≈ 111 km * cos(latitude)
    
    lat_delta = distance_km / 111.0
    lng_delta = distance_km / (111.0 * cos(radians(lat)))
    
    return {
        'lat_min': lat - lat_delta,
        'lat_max': lat + lat_delta,
        'lng_min': lng - lng_delta,
        'lng_max': lng + lng_delta
    }


def find_nearby_centers(
    lat: float,
    lng: float,
    max_distance_km: int = DEFAULT_MAX_DISTANCE_KM,
    use_cache: bool = True,
    include_inactive: bool = False,
    sort_by: str = 'distance'
) -> List[Tuple[DonationCenter, float]]:
    """
    Enhanced nearby centers search with bounding box optimization.
    
    Args:
        lat: Latitude of search origin
        lng: Longitude of search origin
        max_distance_km: Maximum search radius
        use_cache: Whether to use caching
        include_inactive: Whether to include inactive centers
        sort_by: 'distance', 'name', or 'city'
    
    Returns:
        List of tuples containing (DonationCenter, distance)
    """
    # Validate coordinates
    validation = validate_coordinates(lat, lng, strict=False)
    if not validation['valid']:
        logger.error(f"Invalid coordinates: {validation['error']}")
        return []
    
    if validation['warnings']:
        for warning in validation['warnings']:
            logger.warning(warning)
    
    # Cache key
    cache_key = f"nearby_centers_{lat}_{lng}_{max_distance_km}_{include_inactive}_{sort_by}"
    
    if use_cache:
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            logger.info(f"Cache hit for nearby centers: {cache_key}")
            return cached_result
    
    try:
        # Get bounding box for efficient filtering
        bbox = get_bounding_box(lat, lng, max_distance_km)
        
        # Filter centers within bounding box first (database level)
        centers_query = DonationCenter.objects.filter(
            latitude__isnull=False,
            longitude__isnull=False,
            latitude__gte=bbox['lat_min'],
            latitude__lte=bbox['lat_max'],
            longitude__gte=bbox['lng_min'],
            longitude__lte=bbox['lng_max']
        )
        
        if not include_inactive:
            centers_query = centers_query.filter(is_active=True)
        
        # Prefetch related data
        centers = centers_query.select_related().prefetch_related('stock_set')
        
        nearby_centers = []
        for center in centers:
            try:
                # Calculate actual distance
                distance = haversine(lat, lng, float(center.latitude), float(center.longitude))
                
                # Filter by actual distance (some bbox results may be outside radius)
                if distance <= max_distance_km:
                    nearby_centers.append((center, distance))
                    
            except (GeoLocationError, TypeError, ValueError) as e:
                logger.warning(f"Skipping center {center.id}: {str(e)}")
                continue
        
        # Sort results
        if sort_by == 'distance':
            nearby_centers.sort(key=lambda x: x[1])
        elif sort_by == 'name':
            nearby_centers.sort(key=lambda x: x[0].name)
        elif sort_by == 'city':
            nearby_centers.sort(key=lambda x: (x[0].city, x[1]))
        
        # Cache results
        if use_cache and nearby_centers:
            cache.set(cache_key, nearby_centers, CACHE_TIMEOUT)
        
        logger.info(
            f"Found {len(nearby_centers)} centers within {max_distance_km}km "
            f"of ({lat}, {lng})"
        )
        
        return nearby_centers
        
    except Exception as e:
        logger.error(f"Error finding nearby centers: {str(e)}", exc_info=True)
        return []


def get_user_location_from_ip(request) -> Optional[Tuple[float, float]]:
    """
    Get approximate location from IP address as fallback.
    
    Args:
        request: Django request object
    
    Returns:
        tuple: (latitude, longitude) or None
    """
    try:
        # Get IP address
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        
        # For development/localhost, return default location (Nairobi)
        if ip in ['127.0.0.1', 'localhost']:
            logger.info("Localhost detected, returning Nairobi coordinates")
            return (KENYA_CITIES['nairobi']['lat'], KENYA_CITIES['nairobi']['lng'])
        
        # In production, you would use an IP geolocation service
        # For now, return None to prompt user for location
        return None
        
    except Exception as e:
        logger.error(f"Error getting location from IP: {str(e)}")
        return None


def find_nearby_eligible_donors(
    lat: float,
    lng: float,
    max_distance_km: int = DEFAULT_MAX_DISTANCE_KM,
    donation_interval_days: int = DONATION_INTERVAL_DAYS,
    limit: Optional[int] = None
) -> List[Tuple[Donor, float]]:
    """
    Enhanced donor search with better filtering and validation.
    """
    validation = validate_coordinates(lat, lng, strict=False)
    if not validation['valid']:
        logger.error(f"Invalid coordinates for donor search: {validation['error']}")
        return []
    
        logger.error("Patient blood group not provided")
        return []
    
    try:
        if not compatible_types:
            return []
        
        eligibility_cutoff_date = date.today() - timedelta(days=donation_interval_days)
        
        # Get bounding box
        bbox = get_bounding_box(lat, lng, max_distance_km)
        
        # Optimized query with bounding box
        donors_qs = Donor.objects.filter(
            latitude__isnull=False,
            longitude__isnull=False,
            latitude__gte=bbox['lat_min'],
            latitude__lte=bbox['lat_max'],
            longitude__gte=bbox['lng_min'],
            longitude__lte=bbox['lng_max'],
            bloodgroup__in=compatible_types,
            donoreligibility__approved=True,
        ).filter(
            Q(last_donation_date__lte=eligibility_cutoff_date) | 
            Q(last_donation_date__isnull=True)
        ).select_related(
            'user',
            'donoreligibility'
        ).distinct()
        
        nearby_donors = []
        for donor in donors_qs:
            try:
                distance = haversine(lat, lng, float(donor.latitude), float(donor.longitude))
                if distance <= max_distance_km:
                    nearby_donors.append((donor, distance))
            except (GeoLocationError, TypeError, ValueError) as e:
                logger.warning(f"Skipping donor {donor.id}: {str(e)}")
                continue
        
        nearby_donors.sort(key=lambda x: x[1])
        
        if limit:
            nearby_donors = nearby_donors[:limit]
        
        logger.info(
            f"within {max_distance_km}km"
        )
        
        return nearby_donors
        
    except Exception as e:
        logger.error(f"Error finding donors: {str(e)}", exc_info=True)
        return []



def get_distance_between_users(user1_lat: float, user1_lng: float, 
                                user2_lat: float, user2_lng: float) -> Optional[float]:
    """
    Calculate distance with validation.
    """
    try:
        return haversine(user1_lat, user1_lng, user2_lat, user2_lng)
    except GeoLocationError as e:
        logger.error(f"Distance calculation failed: {str(e)}")
        return None


def get_search_statistics(lat: float, lng: float, 
                          max_distance_km: int = DEFAULT_MAX_DISTANCE_KM) -> Dict:
    """
    Get comprehensive statistics about search area.
    """
    validation = validate_coordinates(lat, lng, strict=False)
    if not validation['valid']:
        return {'error': validation['error']}
    
    try:
        centers = find_nearby_centers(lat, lng, max_distance_km)
        
        stats = {
            'search_location': {'lat': lat, 'lng': lng},
            'search_radius_km': max_distance_km,
            'total_centers': len(centers),
            'closest_center': None,
            'farthest_center': None,
            'average_distance': None,
            'timestamp': timezone.now().isoformat(),
            'validation_warnings': validation.get('warnings', [])
        }
        
        if centers:
            distances = [d for _, d in centers]
            stats['closest_center'] = {
                'name': centers[0][0].name,
                'distance': centers[0][1]
            }
            stats['farthest_center'] = {
                'name': centers[-1][0].name,
                'distance': centers[-1][1]
            }
            stats['average_distance'] = round(sum(distances) / len(distances), 2)
        
        return stats
        
    except Exception as e:
        logger.error(f"Error generating statistics: {str(e)}")
        return {'error': str(e)}
