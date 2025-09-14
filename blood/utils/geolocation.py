from math import radians, sin, cos, sqrt, atan2
from blood.models import DonationCenter
from blood.utils.blood_compatibility import get_compatible_blood_types  
from donor.models import Donor
from django.db.models import Q
from datetime import date, timedelta
from patient.models import Patient 
from blood.utils.blood_compatibility import get_compatible_recipient_blood_types

def haversine(lat1, lon1, lat2, lon2):
    """
    Calculate distance in kilometers between two lat/lon points using the Haversine formula.
    """
    R = 6371.0  # Earth’s radius in km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    distance = R * c
    return distance


def find_nearby_centers(lat, lng, max_distance_km=50):
    """
    Return a sorted list of (DonationCenter, distance_km) tuples within max_distance_km.
    """
    centers = DonationCenter.objects.filter(latitude__isnull=False, longitude__isnull=False)

    nearby_centers = []
    for center in centers:
        distance = haversine(lat, lng, center.latitude, center.longitude)
        if distance <= max_distance_km:
            nearby_centers.append((center, round(distance, 2)))

    nearby_centers.sort(key=lambda x: x[1])  # closest first
    return nearby_centers


def find_nearby_eligible_donors(lat, lng, patient_bloodgroup, max_distance_km=50):
    """
    Find donors who:
    - have compatible blood group with the patient,
    - are within max_distance_km radius,
    - are medically eligible (DonorEligibility.approved=True),
    - and have not donated in the last 56 days (or never donated).

    Returns a sorted list of tuples: (Donor instance, distance in km).
    """
    compatible_types = get_compatible_blood_types(patient_bloodgroup)
    eligibility_cutoff_date = date.today() - timedelta(days=56)

    # Query donors matching location, blood group, and medical approval
    donors_qs = Donor.objects.filter(
        latitude__isnull=False,
        longitude__isnull=False,
        bloodgroup__in=compatible_types,
        donoreligibility__approved=True,
    ).filter(
        Q(last_donation_date__lte=eligibility_cutoff_date) | Q(last_donation_date__isnull=True)
    )

    nearby_donors = []
    for donor in donors_qs:
        distance = haversine(lat, lng, donor.latitude, donor.longitude)
        if distance <= max_distance_km:
            nearby_donors.append((donor, round(distance, 2)))

    nearby_donors.sort(key=lambda x: x[1])  # Sort closest first
    return nearby_donors


def find_nearby_compatible_patients(lat, lng, donor_bloodgroup, max_distance_km=50):
    """
    Finds patients who:
    - have compatible blood group as recipients for the donor blood type,
    - are within max_distance_km radius,
    - optionally, have active blood requests or other filters as needed.

    Returns a sorted list of tuples: (Patient instance, distance in km).
    """
    compatible_recipient_types = get_compatible_recipient_blood_types(donor_bloodgroup)

    patients_qs = Patient.objects.filter(
        latitude__isnull=False,
        longitude__isnull=False,
        bloodgroup__in=compatible_recipient_types,
        
    )

    nearby_patients = []
    for patient in patients_qs:
        distance = haversine(lat, lng, patient.latitude, patient.longitude)
        if distance <= max_distance_km:
            nearby_patients.append((patient, round(distance, 2)))

    nearby_patients.sort(key=lambda x: x[1])
    return nearby_patients
