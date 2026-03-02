from blood.models import DonationCenter, StockUnit, StockTransaction, BloodBagBarcode
from donor.models import Donor, BloodDonate,DonorEligibility
from phlebotomist.models import Phlebotomist, Appointment
from lab_technologist.models import LabTechnologistProfile, BloodTest
from blood_bank_technician.models import BloodBankTechProfile
from hospital.models import Hospital, HospitalUser, HospitalBloodRequest
from django.contrib.auth.models import User
from django.db.models import Count, Q, Sum, Avg, F
from django.utils import timezone
from datetime import timedelta, date, datetime
from collections import defaultdict

class BloodDonationKnowledgeBase:
    """
    Enhanced knowledge base with real-time system data and role-specific context
    Matches the actual system architecture
    """
    
    @staticmethod
    def get_system_context():
        """Get current system-wide statistics and context"""
        try:
            today = timezone.now().date()
            
            # Donor statistics
            total_donors = Donor.objects.count()
            donors_with_verified_blood = Donor.objects.filter(bloodgroup_verified=True).count()
            donors_with_pending_eligibility = DonorEligibility.objects.filter(approved=False).count() if 'DonorEligibility' in globals() else 0
            
            # Phlebotomist statistics
            total_phlebotomists = Phlebotomist.objects.count()
            approved_phlebotomists = Phlebotomist.objects.filter(is_approved=True).count()
            pending_phlebotomists = Phlebotomist.objects.filter(is_approved=False).count()
            
            # Lab technician statistics
            total_lab_techs = LabTechnologistProfile.objects.count()
            
            # Blood bank technician statistics
            total_bb_techs = BloodBankTechProfile.objects.count()
            
            # Hospital statistics
            total_hospitals = Hospital.objects.count()
            verified_hospitals = Hospital.objects.filter(verified=True).count()
            total_hospital_users = HospitalUser.objects.count()
            
            # Blood requests
            active_requests = HospitalBloodRequest.objects.filter(
                status__in=['pending', 'approved']
            ).count()
            
            pending_requests = HospitalBloodRequest.objects.filter(status='pending').count()
            approved_requests = HospitalBloodRequest.objects.filter(status='approved').count()
            dispatched_requests = HospitalBloodRequest.objects.filter(status='dispatched').count()
            
            # Blood donations
            thirty_days_ago = timezone.now() - timedelta(days=30)
            recent_donations = BloodDonate.objects.filter(
                date__gte=thirty_days_ago
            ).count()
            
            # Test results
            safe_donations = BloodDonate.objects.filter(status='tested_safe').count()
            unsafe_donations = BloodDonate.objects.filter(status='tested_unsafe').count()
            pending_tests = BloodDonate.objects.filter(status='collected').count()
            
            # Stock levels
            total_available_units = StockUnit.objects.filter(
                safety_status='safe',
                is_quarantined=False,
                unit__gt=0,
                expiry_date__gte=today
            ).aggregate(total=Sum('unit'))['total'] or 0
            
            total_stock_batches = StockUnit.objects.filter(
                safety_status='safe',
                is_quarantined=False,
                unit__gt=0,
                expiry_date__gte=today
            ).count()
            
            # Stock by blood group
            stock_info = list(StockUnit.objects.filter(
                safety_status='safe',
                is_quarantined=False,
                unit__gt=0,
                expiry_date__gte=today
            ).values('bloodgroup').annotate(
                total_units=Sum('unit'),
                batch_count=Count('id')
            ).order_by('bloodgroup'))
            
            # Critical stock alerts (below 1000ml)
            critical_stock_count = StockUnit.objects.filter(
                safety_status='safe',
                is_quarantined=False,
                unit__gt=0,
                unit__lt=1000,
                expiry_date__gte=today
            ).count()
            
            # Expiring soon (within 7 days)
            expiring_soon = StockUnit.objects.filter(
                safety_status='safe',
                is_quarantined=False,
                unit__gt=0,
                expiry_date__lte=today + timedelta(days=7),
                expiry_date__gte=today
            ).count()
            
            # Pending blood tests
            pending_blood_tests = BloodDonate.objects.filter(
                status='collected',
                lab_test__isnull=True
            ).count()
            
            # Recent activities
            recent_activities = []
            
            # Recent donations (last 5)
            recent_donations_list = BloodDonate.objects.select_related(
                'donor__user', 'donation_center'
            ).order_by('-date')[:5]
            
            for donation in recent_donations_list:
                recent_activities.append({
                    'type': 'donation',
                    'date': donation.date,
                    'description': f"{donation.donor.user.get_full_name() if donation.donor else 'Someone'} donated {donation.unit}ml {donation.bloodgroup} blood",
                    'status': donation.status
                })
            
            # Recent requests (last 5)
            recent_requests = HospitalBloodRequest.objects.select_related(
                'hospital'
            ).order_by('-created_at')[:5]
            
            for request in recent_requests:
                recent_activities.append({
                    'type': 'request',
                    'date': request.created_at,
                    'description': f"{request.hospital.name} requested {request.units_requested}ml {request.blood_group} for patient {request.patient_full_name}",
                    'status': request.status
                })
            
            # Sort by date (newest first) and limit
            recent_activities.sort(key=lambda x: x['date'], reverse=True)
            recent_activities = recent_activities[:5]
            
            context = {
                'total_donors': total_donors,
                'donors_with_verified_blood': donors_with_verified_blood,
                'donors_with_pending_eligibility': donors_with_pending_eligibility,
                'total_phlebotomists': total_phlebotomists,
                'approved_phlebotomists': approved_phlebotomists,
                'pending_phlebotomists': pending_phlebotomists,
                'total_lab_techs': total_lab_techs,
                'total_bb_techs': total_bb_techs,
                'total_hospitals': total_hospitals,
                'verified_hospitals': verified_hospitals,
                'total_hospital_users': total_hospital_users,
                'active_requests': active_requests,
                'pending_requests': pending_requests,
                'approved_requests': approved_requests,
                'dispatched_requests': dispatched_requests,
                'recent_donations': recent_donations,
                'safe_donations': safe_donations,
                'unsafe_donations': unsafe_donations,
                'pending_tests': pending_tests,
                'total_available_units': total_available_units,
                'total_stock_batches': total_stock_batches,
                'stock_info': stock_info,
                'critical_stock_count': critical_stock_count,
                'expiring_soon': expiring_soon,
                'pending_blood_tests': pending_blood_tests,
                'recent_activities': recent_activities,
                'today': today.strftime('%B %d, %Y'),
            }
            
            return context
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod
    def get_blood_group_info(bloodgroup):
        """Get specific blood group information with real-time data"""
        try:
            today = timezone.now().date()
            
            # Total available safe stock
            total_stock = StockUnit.objects.filter(
                bloodgroup=bloodgroup.upper(),
                safety_status='safe',
                is_quarantined=False,
                unit__gt=0,
                expiry_date__gte=today
            ).aggregate(total=Sum('unit'))['total'] or 0
            
            total_batches = StockUnit.objects.filter(
                bloodgroup=bloodgroup.upper(),
                safety_status='safe',
                is_quarantined=False,
                unit__gt=0,
                expiry_date__gte=today
            ).count()
            
            # Stock by center
            stock_by_center = StockUnit.objects.filter(
                bloodgroup=bloodgroup.upper(),
                safety_status='safe',
                is_quarantined=False,
                unit__gt=0,
                expiry_date__gte=today
            ).values('center__name').annotate(
                units=Sum('unit'),
                batches=Count('id')
            ).order_by('-units')
            
            centers_with_stock = [
                {'name': item['center__name'], 'units': item['units'], 'batches': item['batches']}
                for item in stock_by_center
            ]
            
            # Pending hospital requests for this blood type
            pending_requests = HospitalBloodRequest.objects.filter(
                blood_group=bloodgroup.upper(),
                status='pending'
            ).count()
            
            # Stock expiring soon (within 7 days)
            expiring_soon = StockUnit.objects.filter(
                bloodgroup=bloodgroup.upper(),
                safety_status='safe',
                is_quarantined=False,
                expiry_date__lte=today + timedelta(days=7),
                expiry_date__gte=today,
                unit__gt=0
            ).count()
            
            # Unsafe batches for this blood group
            unsafe_batches = StockUnit.objects.filter(
                bloodgroup=bloodgroup.upper(),
                safety_status='unsafe'
            ).count()
            
            # Donor statistics for this blood group
            donors_with_this_group = Donor.objects.filter(
                bloodgroup=bloodgroup.upper()
            ).count()
            
            verified_donors = Donor.objects.filter(
                bloodgroup=bloodgroup.upper(),
                bloodgroup_verified=True
            ).count()
            
            # Recent donations of this blood group (last 30 days)
            recent_donations = BloodDonate.objects.filter(
                bloodgroup=bloodgroup.upper(),
                status__in=['tested_safe', 'collected'],
                date__gte=timezone.now() - timedelta(days=30)
            ).count()
            
            return {
                'bloodgroup': bloodgroup.upper(),
                'total_units': total_stock,
                'total_batches': total_batches,
                'centers_with_stock': centers_with_stock,
                'centers_count': len(centers_with_stock),
                'pending_requests': pending_requests,
                'expiring_batches': expiring_soon,
                'unsafe_batches': unsafe_batches,
                'total_donors': donors_with_this_group,
                'verified_donors': verified_donors,
                'recent_donations': recent_donations,
            }
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod
    def get_donation_centers_info(city=None, center_id=None):
        """Get detailed information about donation centers"""
        try:
            # Base query
            centers_query = DonationCenter.objects.all()
            
            if city:
                centers_query = centers_query.filter(city__icontains=city)
            
            if center_id:
                centers_query = centers_query.filter(id=center_id)
            
            centers_data = []
            today = timezone.now().date()
            
            for center in centers_query.order_by('name')[:20]:
                # Get stock summary for this center
                safe_stock = StockUnit.objects.filter(
                    center=center,
                    safety_status='safe',
                    is_quarantined=False,
                    unit__gt=0,
                    expiry_date__gte=today
                )
                
                stock_by_group = safe_stock.values('bloodgroup').annotate(
                    units=Sum('unit'),
                    batches=Count('id')
                ).order_by('bloodgroup')
                
                total_units = safe_stock.aggregate(total=Sum('unit'))['total'] or 0
                total_batches = safe_stock.count()
                
                # Pending tests at this center
                pending_tests = BloodDonate.objects.filter(
                    donation_center=center,
                    status='collected',
                    lab_test__isnull=True
                ).count()
                
                # Phlebotomists at this center
                phlebotomists = Phlebotomist.objects.filter(
                    center=center,
                    is_approved=True,
                    is_active=True
                ).count()
                
                # Lab techs at this center
                lab_techs = LabTechnologistProfile.objects.filter(
                    center=center,
                    is_active=True
                ).count()
                
                # Blood bank techs at this center
                bb_techs = BloodBankTechProfile.objects.filter(
                    center=center,
                    is_active=True
                ).count()
                
                # Today's appointments
                today_appointments = Appointment.objects.filter(
                    center=center,
                    date__date=today
                ).count()
                
                # Upcoming appointments
                upcoming_appointments = Appointment.objects.filter(
                    center=center,
                    date__gte=timezone.now(),
                    status__in=['pending', 'approved']
                ).count()
                
                # Build stock summary string
                stock_summary = []
                for item in stock_by_group:
                    status = "✅" if item['units'] >= 1000 else "⚠️" if item['units'] >= 500 else "🚨"
                    stock_summary.append(f"{status} {item['bloodgroup']}: {item['units']}ml")
                
                centers_data.append({
                    'id': center.id,
                    'name': center.name,
                    'city': center.city,
                    'address': center.address,
                    'contact': center.contact_number,
                    'hours': center.open_hours,
                    'latitude': center.latitude,
                    'longitude': center.longitude,
                    'total_stock': total_units,
                    'stock_batches': total_batches,
                    'stock_by_group': list(stock_by_group),
                    'stock_summary': stock_summary,
                    'phlebotomists': phlebotomists,
                    'lab_techs': lab_techs,
                    'bb_techs': bb_techs,
                    'pending_tests': pending_tests,
                    'today_appointments': today_appointments,
                    'upcoming_appointments': upcoming_appointments,
                    'has_critical_stock': any(item['units'] < 500 for item in stock_by_group),
                })
            
            return {
                'total_centers': centers_query.count(),
                'centers': centers_data,
                'query_city': city,
            }
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod
    def get_eligibility_info():
        """Get comprehensive blood donation eligibility criteria"""
        return {
            'basic_requirements': {
                'age': '16-65 years (16-17 with parental consent)',
                'weight': 'Minimum 50kg (110 lbs)',
                'health': 'Generally good health on donation day',
                'interval': '56 days (8 weeks) between whole blood donations',
                'sleep': 'At least 5-6 hours of sleep night before',
                'meal': 'Have a meal within 3 hours before donation',
            },
            'temporary_deferrals': [
                'Cold, flu, or sore throat (wait until recovered)',
                'Dental work (24 hours for cleaning, 72 hours for extraction)',
                'Antibiotics (complete course + 7 days)',
                'Tattoo or piercing (6 months)',
                'Surgery or major procedure (6-12 months, depending on procedure)',
                'Pregnancy (6 weeks after delivery)',
                'Breastfeeding (6 weeks after delivery)',
                'Recent vaccination (2-4 weeks depending on vaccine type)',
                'Travel to malaria-risk area (6 months)',
                'Blood transfusion (12 months)',
            ],
            'permanent_disqualifications': [
                'HIV/AIDS (positive test)',
                'Hepatitis B or C (positive)',
                'Certain cancers (depending on type and treatment)',
                'Chronic liver disease',
                'Severe heart disease',
                'Uncontrolled diabetes with complications',
                'Bleeding disorders (hemophilia, etc.)',
                'IV drug use (non-prescribed)',
            ],
            'medication_guidelines': {
                'allowed': ['Blood pressure meds', 'Birth control', 'Thyroid meds', 'Antihistamines'],
                'waiting_period': ['Accutane (1 month)', 'Finasteride/Propecia (1 month)', 'Blood thinners (consult doctor)'],
            },
            'tips': [
                'Drink plenty of water day before and day of donation',
                'Eat iron-rich foods (spinach, red meat, beans)',
                'Avoid fatty foods right before donation',
                'Wear comfortable clothing with sleeves that can roll up',
                'Bring ID and donor card if available',
                'Relax and let staff know if you feel uncomfortable',
            ],
            'process': {
                'registration': '5-10 minutes',
                'health_check': '5-10 minutes',
                'donation': '8-10 minutes',
                'rest': '10-15 minutes',
                'total': 'About 45-60 minutes',
            }
        }
    
    @staticmethod
    def get_donor_specific_info(donor):
        """Get comprehensive donor-specific information with real-time data"""
        try:
            if not donor or not donor.id:
                return {'error': 'Invalid donor'}
            
            # Basic info
            info = {
                'id': donor.id,
                'username': donor.user.username,
                'full_name': donor.user.get_full_name() or donor.user.username,
                'email': donor.user.email,
                'first_name': donor.user.first_name,
                'last_name': donor.user.last_name,
                'profile_pic': donor.profile_pic.url if donor.profile_pic else None,
                'bloodgroup': donor.bloodgroup or 'Not set',
                'bloodgroup_verified': donor.bloodgroup_verified,
                'bloodgroup_verified_by': donor.bloodgroup_verified_by.get_full_name() if donor.bloodgroup_verified_by else None,
                'bloodgroup_verified_at': donor.bloodgroup_verified_at,
                'mobile': donor.mobile,
                'national_id': donor.national_id,
                'dob': donor.dob,
                'age': donor.age,
                'county': donor.county,
                'location_name': donor.location_name,
                'latitude': donor.latitude,
                'longitude': donor.longitude,
                'points': donor.points,
                'last_donation_date': donor.last_donation_date,
                'member_since': donor.user.date_joined,
                'profile_updated': donor.updated_at,
            }
            
            # Donation statistics
            all_donations = BloodDonate.objects.filter(donor=donor)
            
            info['total_donations'] = all_donations.count()
            info['safe_donations'] = all_donations.filter(status='tested_safe').count()
            info['unsafe_donations'] = all_donations.filter(status='tested_unsafe').count()
            info['pending_donations'] = all_donations.filter(status__in=['pending', 'approved', 'collected']).count()
            
            # Total volume donated (safe donations only)
            total_volume = all_donations.filter(status='tested_safe').aggregate(total=Sum('unit'))['total'] or 0
            info['total_volume_ml'] = total_volume
            info['lives_impacted'] = total_volume // 450  # Each unit saves ~3 lives, 450ml per unit
            
            # Next eligible donation
            next_eligible = donor.next_eligible_donation_date()
            if next_eligible:
                today = timezone.now().date()
                days_until = (next_eligible - today).days
                info['next_eligible_donation'] = next_eligible.strftime('%B %d, %Y')
                info['days_until_eligible'] = days_until
                info['can_donate_now'] = days_until <= 0
            else:
                info['next_eligible_donation'] = 'Eligible now'
                info['days_until_eligible'] = 0
                info['can_donate_now'] = True
            
            # Recent donation history
            recent_donations = BloodDonate.objects.filter(
                donor=donor
            ).select_related('donation_center', 'phlebotomist__user').order_by('-date')[:10]
            
            info['recent_donations'] = []
            for donation in recent_donations:
                # Get test result if available
                test_result = None
                if hasattr(donation, 'lab_test'):
                    test_result = donation.lab_test.result if donation.lab_test else None
                
                # Get barcode if available
                barcode = None
                if hasattr(donation, 'bloodbagbarcode'):
                    barcode = donation.bloodbagbarcode.barcode if donation.bloodbagbarcode else None
                
                info['recent_donations'].append({
                    'id': donation.id,
                    'date': donation.date.strftime('%B %d, %Y'),
                    'time': donation.date.strftime('%I:%M %p'),
                    'status': donation.status,
                    'status_display': donation.get_status_display() if hasattr(donation, 'get_status_display') else donation.status,
                    'units': donation.unit,
                    'bloodgroup': donation.bloodgroup,
                    'center': donation.donation_center.name if donation.donation_center else 'N/A',
                    'phlebotomist': donation.phlebotomist.user.get_full_name() if donation.phlebotomist else 'N/A',
                    'test_result': test_result,
                    'barcode': barcode,
                })
            
            # Upcoming appointments
            upcoming_appointments = Appointment.objects.filter(
                donor=donor,
                date__gte=timezone.now(),
                status__in=['pending', 'approved']
            ).select_related('phlebotomist__user', 'center').order_by('date')[:5]
            
            info['upcoming_appointments'] = []
            for appt in upcoming_appointments:
                # Get linked donation if any
                donation = appt.get_related_donation()
                
                info['upcoming_appointments'].append({
                    'id': appt.id,
                    'date': appt.date.strftime('%B %d, %Y'),
                    'time': appt.date.strftime('%I:%M %p'),
                    'status': appt.status,
                    'status_display': appt.get_status_display() if hasattr(appt, 'get_status_display') else appt.status,
                    'phlebotomist': appt.phlebotomist.user.get_full_name() if appt.phlebotomist else 'Not assigned',
                    'center': appt.center.name if appt.center else 'N/A',
                    'donation_id': donation.id if donation else None,
                })
            
            # Points and achievements
            info['points_breakdown'] = {
                'total': donor.points,
                'per_donation': 10,
                'donation_points': info['safe_donations'] * 10,
            }
            
            # Milestones
            milestones = [1, 5, 10, 25, 50, 100]
            current = info['safe_donations']
            next_milestone = next((m for m in milestones if m > current), None)
            
            info['milestones'] = {
                'current': current,
                'next': next_milestone,
                'progress': current / next_milestone * 100 if next_milestone else 100,
            }
            
            return info
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod
    def get_phlebotomist_specific_info(phlebotomist):
        """Get comprehensive phlebotomist-specific information"""
        try:
            if not phlebotomist or not phlebotomist.id:
                return {'error': 'Invalid phlebotomist'}
            
            today = timezone.now().date()
            now = timezone.now()
            
            info = {
                'id': phlebotomist.id,
                'username': phlebotomist.user.username,
                'full_name': phlebotomist.user.get_full_name() or phlebotomist.user.username,
                'email': phlebotomist.user.email,
                'profile_pic': phlebotomist.profile_pic.url if phlebotomist.profile_pic else None,
                'license_number': phlebotomist.license_number,
                'license_expiry': phlebotomist.license_expiry,
                'license_valid': phlebotomist.is_license_valid if hasattr(phlebotomist, 'is_license_valid') else True,
                'phone': phlebotomist.phone,
                'qualification': phlebotomist.qualification,
                'specialization': phlebotomist.specialization,
                'years_experience': phlebotomist.years_of_experience,
                'is_approved': phlebotomist.is_approved,
                'approved_at': phlebotomist.approved_at,
                'center': phlebotomist.center.name if phlebotomist.center else 'Not assigned',
                'center_id': phlebotomist.center.id if phlebotomist.center else None,
                'member_since': phlebotomist.created_at,
            }
            
            # ===== APPOINTMENT STATISTICS =====
            all_appointments = Appointment.objects.filter(phlebotomist=phlebotomist)
            
            info['total_appointments'] = all_appointments.count()
            info['today_appointments'] = all_appointments.filter(date__date=today).count()
            info['pending_appointments'] = all_appointments.filter(status='pending').count()
            info['approved_appointments'] = all_appointments.filter(status='approved').count()
            info['collected_appointments'] = all_appointments.filter(status='collected').count()
            info['completed_appointments'] = all_appointments.filter(status='completed').count()
            info['cancelled_appointments'] = all_appointments.filter(status='cancelled').count()
            
            # Today's appointments detailed
            today_appointments = all_appointments.filter(
                date__date=today
            ).select_related('donor__user', 'center').order_by('date')
            
            info['today_appointments_list'] = []
            for appt in today_appointments:
                info['today_appointments_list'].append({
                    'id': appt.id,
                    'time': appt.date.strftime('%I:%M %p'),
                    'donor': appt.donor.user.get_full_name() if appt.donor else 'Unknown',
                    'donor_bloodgroup': appt.donor.bloodgroup if appt.donor else 'N/A',
                    'status': appt.status,
                    'center': appt.center.name if appt.center else 'N/A',
                })
            
            # Upcoming appointments (next 7 days)
            next_week = today + timedelta(days=7)
            upcoming = all_appointments.filter(
                date__date__gte=today,
                date__date__lte=next_week,
                status__in=['pending', 'approved']
            ).order_by('date')[:10]
            
            info['upcoming_appointments'] = []
            for appt in upcoming:
                info['upcoming_appointments'].append({
                    'id': appt.id,
                    'date': appt.date.strftime('%A, %B %d'),
                    'time': appt.date.strftime('%I:%M %p'),
                    'donor': appt.donor.user.get_full_name() if appt.donor else 'Unknown',
                    'status': appt.status,
                })
            
            # Pending approvals
            pending = all_appointments.filter(status='pending').order_by('date')[:10]
            info['pending_approvals'] = []
            for appt in pending:
                info['pending_approvals'].append({
                    'id': appt.id,
                    'date': appt.date.strftime('%b %d, %I:%M %p'),
                    'donor': appt.donor.user.get_full_name() if appt.donor else 'Unknown',
                })
            
            # ===== CENTER STOCK INFORMATION =====
            if phlebotomist.center:
                center = phlebotomist.center
                
                # Safe stock at center
                safe_stock = StockUnit.objects.filter(
                    center=center,
                    safety_status='safe',
                    is_quarantined=False,
                    unit__gt=0,
                    expiry_date__gte=today
                )
                
                stock_summary = safe_stock.values('bloodgroup').annotate(
                    total=Sum('unit'),
                    batches=Count('id')
                ).order_by('bloodgroup')
                
                info['center_stock'] = {}
                info['critical_stock'] = []
                
                for item in stock_summary:
                    bg = item['bloodgroup']
                    units = item['total']
                    info['center_stock'][bg] = units
                    
                    if units < 500:
                        info['critical_stock'].append(f"{bg} ({units}ml)")
                    elif units < 1000:
                        info['low_stock'].append(f"{bg} ({units}ml)")
                
                # Pending tests at center
                info['pending_tests_at_center'] = BloodDonate.objects.filter(
                    donation_center=center,
                    status='collected',
                    lab_test__isnull=True
                ).count()
                
                # Expiring stock at center
                expiring = StockUnit.objects.filter(
                    center=center,
                    safety_status='safe',
                    is_quarantined=False,
                    expiry_date__lte=today + timedelta(days=7),
                    expiry_date__gte=today,
                    unit__gt=0
                )
                
                info['expiring_stock'] = expiring.count()
                info['expiring_details'] = []
                for item in expiring[:5]:
                    info['expiring_details'].append(f"{item.bloodgroup} ({item.unit}ml) expires {item.expiry_date.strftime('%b %d')}")
            
            # ===== RECENT ACTIVITIES =====
            recent_activities = []
            
            # Recent donations collected
            recent_collections = BloodDonate.objects.filter(
                phlebotomist=phlebotomist
            ).select_related('donor__user').order_by('-date')[:5]
            
            for donation in recent_collections:
                recent_activities.append({
                    'type': 'collection',
                    'time': donation.date,
                    'description': f"Collected {donation.unit}ml from {donation.donor.user.get_full_name() if donation.donor else 'Unknown'} ({donation.bloodgroup})",
                    'status': donation.status,
                })
            
            # Recent appointments processed
            recent_appointments = all_appointments.filter(
                status__in=['completed', 'collected', 'cancelled', 'rejected']
            ).order_by('-date')[:5]
            
            for appt in recent_appointments:
                recent_activities.append({
                    'type': 'appointment',
                    'time': appt.date,
                    'description': f"Appointment for {appt.donor.user.get_full_name() if appt.donor else 'Unknown'} - {appt.status}",
                    'status': appt.status,
                })
            
            # Sort by time
            recent_activities.sort(key=lambda x: x['time'], reverse=True)
            info['recent_activities'] = recent_activities[:5]
            
            return info
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod
    def get_lab_tech_specific_info(lab_tech):
        """Get comprehensive lab technologist information"""
        try:
            if not lab_tech or not lab_tech.id:
                return {'error': 'Invalid lab technologist'}
            
            today = timezone.now().date()
            
            info = {
                'id': lab_tech.id,
                'full_name': lab_tech.user.get_full_name() or lab_tech.user.username,
                'email': lab_tech.user.email,
                'employee_id': lab_tech.employee_id,
                'license_number': lab_tech.license_number,
                'qualification': lab_tech.qualification,
                'specialization': lab_tech.specialization,
                'center': lab_tech.center.name if lab_tech.center else 'Not assigned',
                'center_id': lab_tech.center.id if lab_tech.center else None,
                'years_experience': lab_tech.years_of_experience,
                'certification_valid': lab_tech.certification_valid if hasattr(lab_tech, 'certification_valid') else True,
                'certification_expiry': lab_tech.certification_expiry,
            }
            
            # ===== TESTING STATISTICS =====
            all_tests = BloodTest.objects.filter(tested_by=lab_tech)
            
            info['total_tests'] = all_tests.count()
            info['tests_today'] = all_tests.filter(test_date__date=today).count()
            info['safe_tests'] = all_tests.filter(result='safe').count()
            info['unsafe_tests'] = all_tests.filter(result='unsafe').count()
            info['pending_tests'] = all_tests.filter(result='pending').count()
            
            # Pending tests that need attention
            if lab_tech.center:
                pending_blood = BloodDonate.objects.filter(
                    donation_center=lab_tech.center,
                    status='collected',
                    lab_test__isnull=True
                ).select_related('donor__user', 'phlebotomist__user').order_by('date')
                
                info['pending_blood_samples'] = []
                for blood in pending_blood[:10]:
                    info['pending_blood_samples'].append({
                        'id': blood.id,
                        'donor': blood.donor.user.get_full_name() if blood.donor else 'Unknown',
                        'collection_date': blood.date.strftime('%b %d, %I:%M %p'),
                        'phlebotomist': blood.phlebotomist.user.get_full_name() if blood.phlebotomist else 'Unknown',
                        'unit': blood.unit,
                        'bloodgroup': blood.bloodgroup or 'Unknown',
                    })
                
                info['pending_count'] = pending_blood.count()
            
            # Recent tests performed
            recent_tests = all_tests.select_related(
                'blood_collection__donor__user'
            ).order_by('-test_date')[:10]
            
            info['recent_tests'] = []
            for test in recent_tests:
                result_emoji = '✅' if test.result == 'safe' else '⚠️' if test.result == 'unsafe' else '⏳'
                info['recent_tests'].append({
                    'id': test.id,
                    'date': test.test_date.strftime('%b %d, %I:%M %p'),
                    'donor': test.blood_collection.donor.user.get_full_name() if test.blood_collection and test.blood_collection.donor else 'Unknown',
                    'bloodgroup': test.blood_group or 'Pending',
                    'result': test.result,
                    'result_emoji': result_emoji,
                })
            
            # Blood group verification stats
            donors_verified = Donor.objects.filter(
                bloodgroup_verified_by=lab_tech.user
            ).count()
            
            info['donors_verified'] = donors_verified
            
            # Today's performance
            today_tests = all_tests.filter(test_date__date=today)
            info['today_safe'] = today_tests.filter(result='safe').count()
            info['today_unsafe'] = today_tests.filter(result='unsafe').count()
            
            return info
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod
    def get_bb_tech_specific_info(bb_tech):
        """Get comprehensive blood bank technician information"""
        try:
            if not bb_tech or not bb_tech.id:
                return {'error': 'Invalid blood bank technician'}
            
            today = timezone.now().date()
            
            info = {
                'id': bb_tech.id,
                'full_name': bb_tech.user.get_full_name() or bb_tech.user.username,
                'email': bb_tech.user.email,
                'employee_id': bb_tech.employee_id,
                'phone': bb_tech.phone,
                'center': bb_tech.center.name if bb_tech.center else 'Not assigned',
                'center_id': bb_tech.center.id if bb_tech.center else None,
            }
            
            # ===== INVENTORY STATISTICS =====
            if bb_tech.center:
                center = bb_tech.center
                
                # Safe stock
                safe_stock = StockUnit.objects.filter(
                    center=center,
                    safety_status='safe',
                    is_quarantined=False,
                    unit__gt=0,
                    expiry_date__gte=today
                )
                
                info['total_safe_units'] = safe_stock.count()
                info['total_safe_volume'] = safe_stock.aggregate(total=Sum('unit'))['total'] or 0
                
                # Stock by blood group
                stock_by_group = safe_stock.values('bloodgroup').annotate(
                    units=Sum('unit'),
                    batches=Count('id')
                ).order_by('bloodgroup')
                
                info['stock_by_group'] = list(stock_by_group)
                
                # Critical stock alerts
                info['critical_alerts'] = []
                info['low_stock'] = []
                
                for item in stock_by_group:
                    if item['units'] < 500:
                        info['critical_alerts'].append(f"{item['bloodgroup']}: {item['units']}ml")
                    elif item['units'] < 1000:
                        info['low_stock'].append(f"{item['bloodgroup']}: {item['units']}ml")
                
                # Pending verification stock
                pending_stock = StockUnit.objects.filter(
                    center=center,
                    safety_status='pending',
                    unit__gt=0,
                    expiry_date__gte=today
                )
                
                info['pending_verification_units'] = pending_stock.count()
                info['pending_verification_volume'] = pending_stock.aggregate(total=Sum('unit'))['total'] or 0
                
                # Unsafe/quarantined stock
                unsafe_stock = StockUnit.objects.filter(
                    center=center,
                    safety_status='unsafe'
                )
                
                info['unsafe_units'] = unsafe_stock.count()
                info['unsafe_volume'] = unsafe_stock.aggregate(total=Sum('unit'))['total'] or 0
                
                # Expiring soon
                expiring_soon = safe_stock.filter(
                    expiry_date__lte=today + timedelta(days=7)
                )
                
                info['expiring_soon_units'] = expiring_soon.count()
                info['expiring_soon_volume'] = expiring_soon.aggregate(total=Sum('unit'))['total'] or 0
                
                # Hospital requests
                pending_requests = HospitalBloodRequest.objects.filter(
                    assigned_centre=center,
                    status='pending'
                )
                
                info['pending_hospital_requests'] = pending_requests.count()
                info['pending_requests_detail'] = []
                
                for req in pending_requests[:5]:
                    info['pending_requests_detail'].append({
                        'id': req.id,
                        'request_number': req.request_number,
                        'hospital': req.hospital.name,
                        'blood_group': req.blood_group,
                        'units': req.units_requested,
                        'urgency': req.get_urgency_display(),
                        'patient': req.patient_full_name,
                    })
                
                # Approved requests ready for dispatch
                approved_requests = HospitalBloodRequest.objects.filter(
                    assigned_centre=center,
                    status='approved'
                )
                
                info['approved_requests'] = approved_requests.count()
                
                # Recent transactions
                recent_transactions = StockTransaction.objects.filter(
                    stockunit__center=center
                ).select_related('stockunit', 'user').order_by('-transaction_at')[:10]
                
                info['recent_transactions'] = []
                for tx in recent_transactions:
                    tx_type = '➕' if tx.transaction_type == 'addition' else '➖'
                    info['recent_transactions'].append({
                        'time': tx.transaction_at.strftime('%b %d, %I:%M %p'),
                        'type': tx.transaction_type,
                        'emoji': tx_type,
                        'bloodgroup': tx.stockunit.bloodgroup,
                        'quantity': tx.quantity_added or tx.quantity_deducted,
                        'user': tx.user.get_full_name() if tx.user else 'System',
                    })
            
            return info
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod
    def get_hospital_specific_info(hospital_user):
        """Get comprehensive hospital user information"""
        try:
            if not hospital_user or not hospital_user.id:
                return {'error': 'Invalid hospital user'}
            
            hospital = hospital_user.hospital
            
            info = {
                'id': hospital_user.id,
                'full_name': hospital_user.user.get_full_name() or hospital_user.user.username,
                'email': hospital_user.user.email,
                'role': hospital_user.get_role_display(),
                'is_primary_contact': hospital_user.is_primary_contact,
                'hospital': {
                    'id': hospital.id,
                    'name': hospital.name,
                    'registration': hospital.registration_number,
                    'county': hospital.county,
                    'contact_person': hospital.contact_person,
                    'contact_phone': hospital.contact_phone,
                    'email': hospital.email,
                    'verified': hospital.verified,
                    'serving_centre': hospital.serving_centre.name if hospital.serving_centre else None,
                    'has_blood_storage': hospital.has_blood_storage,
                }
            }
            
            # ===== BLOOD REQUESTS =====
            all_requests = HospitalBloodRequest.objects.filter(hospital=hospital)
            
            info['total_requests'] = all_requests.count()
            info['pending_requests'] = all_requests.filter(status='pending').count()
            info['approved_requests'] = all_requests.filter(status='approved').count()
            info['dispatched_requests'] = all_requests.filter(status='dispatched').count()
            info['delivered_requests'] = all_requests.filter(status='delivered').count()
            info['rejected_requests'] = all_requests.filter(status='rejected').count()
            info['cancelled_requests'] = all_requests.filter(status='cancelled').count()
            
            # Recent requests
            recent = all_requests.select_related(
                'assigned_centre'
            ).order_by('-created_at')[:10]
            
            info['recent_requests'] = []
            for req in recent:
                status_emoji = {
                    'pending': '⏳', 'approved': '✅', 'dispatched': '🚚',
                    'delivered': '📦', 'rejected': '❌', 'cancelled': '🚫'
                }.get(req.status, '📋')
                
                info['recent_requests'].append({
                    'id': req.id,
                    'request_number': req.request_number,
                    'date': req.created_at.strftime('%b %d, %Y'),
                    'patient': req.patient_full_name,
                    'blood_group': req.blood_group,
                    'units': req.units_requested,
                    'urgency': req.get_urgency_display(),
                    'status': req.status,
                    'status_emoji': status_emoji,
                    'centre': req.assigned_centre.name if req.assigned_centre else 'Not assigned',
                })
            
            # Stock at serving centre (if available)
            if hospital.serving_centre:
                today = timezone.now().date()
                centre_stock = StockUnit.objects.filter(
                    center=hospital.serving_centre,
                    safety_status='safe',
                    is_quarantined=False,
                    unit__gt=0,
                    expiry_date__gte=today
                ).values('bloodgroup').annotate(
                    units=Sum('unit')
                ).order_by('bloodgroup')
                
                info['centre_stock'] = {}
                for item in centre_stock:
                    info['centre_stock'][item['bloodgroup']] = item['units']
            
            return info
        except Exception as e:
            return {'error': str(e)}


class IntentClassifier:
    """
    Enhanced intent classifier with comprehensive intent detection
    """
    
    @staticmethod
    def classify_intent(message):
        """Determine what the user is asking about"""
        message_lower = message.lower().strip()
        
        # ===== GREETINGS =====
        greetings = ['hello', 'hi', 'hey', 'greetings', 'good morning', 'good afternoon', 
                     'good evening', 'howdy', 'what\'s up', 'sup', 'yo', 'hi there']
        if any(word in message_lower for word in greetings):
            return 'greeting', None
        
        # ===== THANK YOUS =====
        thanks = ['thank', 'thanks', 'appreciate', 'grateful', 'thx']
        if any(word in message_lower for word in thanks):
            return 'thanks', None
        
        # ===== FAREWELLS =====
        farewells = ['bye', 'goodbye', 'see you', 'later', 'talk to you later', 'cya']
        if any(word in message_lower for word in farewells):
            return 'farewell', None
        
        # ===== HELP REQUESTS =====
        help_words = ['help', 'support', 'assist', 'guide', 'tutorial', 'how to use', 'what can you do']
        if any(word in message_lower for word in help_words):
            return 'help', None
        
        # ===== SYSTEM STATISTICS =====
        if any(word in message_lower for word in ['how many', 'total', 'statistics', 'stats', 'count', 'number of']):
            if any(word in message_lower for word in ['donor', 'donors']):
                return 'system_stats', 'donors'
            elif any(word in message_lower for word in ['phlebotomist', 'phlebotomists', 'nurse', 'nurses']):
                return 'system_stats', 'phlebotomists'
            elif any(word in message_lower for word in ['lab', 'technician', 'tech', 'laboratory']):
                return 'system_stats', 'lab_techs'
            elif any(word in message_lower for word in ['blood bank', 'bb tech', 'inventory']):
                return 'system_stats', 'bb_techs'
            elif any(word in message_lower for word in ['hospital', 'hospitals']):
                return 'system_stats', 'hospitals'
            elif any(word in message_lower for word in ['center', 'centers', 'location', 'locations']):
                return 'system_stats', 'centers'
            elif any(word in message_lower for word in ['request', 'requests']):
                return 'system_stats', 'requests'
            elif any(word in message_lower for word in ['donation', 'donations']):
                return 'system_stats', 'donations'
            elif any(word in message_lower for word in ['test', 'tests', 'testing']):
                return 'system_stats', 'tests'
            elif any(word in message_lower for word in ['stock', 'inventory', 'available blood']):
                return 'system_stats', 'stock'
            return 'system_stats', 'general'
        
        # ===== BLOOD GROUP QUERIES =====
        blood_groups = ['o+', 'o-', 'a+', 'a-', 'b+', 'b-', 'ab+', 'ab-', 
                        'o positive', 'o negative', 'a positive', 'a negative', 
                        'b positive', 'b negative', 'ab positive', 'ab negative']
        
        for bg in blood_groups:
            if bg in message_lower:
                # Extract the standard format
                if 'positive' in bg:
                    std_bg = bg.replace(' positive', '+').upper()
                elif 'negative' in bg:
                    std_bg = bg.replace(' negative', '-').upper()
                else:
                    std_bg = bg.upper()
                return 'blood_group_info', std_bg
        
        # ===== DONATION CENTERS =====
        if any(word in message_lower for word in ['center', 'centers', 'location', 'where can i donate', 
                                                   'find', 'nearest', 'near me', 'closest']):
            # Check for specific cities
            cities = ['nairobi', 'mombasa', 'kisumu', 'nakuru', 'eldoret', 'thika', 
                      'malindi', 'kitui', 'machakos', 'kiambu', 'kericho', 'kisii']
            for city in cities:
                if city in message_lower:
                    return 'donation_centers', city
            return 'donation_centers', None
        
        # ===== ELIGIBILITY =====
        eligibility_phrases = ['eligible', 'eligibility', 'can i donate', 'requirements', 
                                'qualify', 'criteria', 'am i allowed', 'who can donate', 
                                'can\'t donate', 'cannot donate', 'disqualify']
        if any(phrase in message_lower for phrase in eligibility_phrases):
            return 'eligibility', None
        
        # ===== DONOR PROFILE QUERIES =====
        donor_profile = ['my profile', 'my account', 'my information', 'my details', 
                         'my blood type', 'my blood group', 'my points', 'my rewards',
                         'my donations', 'my history', 'when can i donate', 'my appointments',
                         'my upcoming', 'my next donation', 'my eligibility status']
        if any(phrase in message_lower for phrase in donor_profile):
            return 'user_profile', 'donor'
        
        # ===== PHLEBOTOMIST PROFILE QUERIES =====
        phlebotomist_profile = ['my duties', 'my tasks', 'my appointments', 'my schedule',
                                 'pending approvals', 'today\'s appointments', 'my patients',
                                 'my center stock', 'blood stock', 'critical alerts']
        if any(phrase in message_lower for phrase in phlebotomist_profile):
            return 'user_profile', 'phlebotomist'
        
        # ===== LAB TECH PROFILE QUERIES =====
        lab_profile = ['pending tests', 'samples to test', 'my tests', 'testing queue',
                       'unsafe results', 'safe results', 'blood group verification']
        if any(phrase in message_lower for phrase in lab_profile):
            return 'user_profile', 'lab_tech'
        
        # ===== BB TECH PROFILE QUERIES =====
        bb_profile = ['inventory', 'stock levels', 'hospital requests', 'dispatch',
                      'expiring blood', 'quarantine', 'unsafe blood', 'pending verification']
        if any(phrase in message_lower for phrase in bb_profile):
            return 'user_profile', 'bb_tech'
        
        # ===== HOSPITAL PROFILE QUERIES =====
        hospital_profile = ['my requests', 'hospital requests', 'request status',
                            'pending requests', 'approved requests', 'dispatched blood']
        if any(phrase in message_lower for phrase in hospital_profile):
            return 'user_profile', 'hospital'
        
        # ===== APPOINTMENT QUERIES =====
        appointment_phrases = ['appointment', 'appointments', 'schedule', 'booking', 'book',
                               'reschedule', 'cancel appointment', 'donation appointment']
        if any(phrase in message_lower for phrase in appointment_phrases):
            return 'appointments', None
        
        # ===== DONATION PROCESS =====
        process_phrases = ['how to donate', 'donation process', 'steps', 'procedure', 
                           'what happens', 'what to expect', 'first time', 'first donation']
        if any(phrase in message_lower for phrase in process_phrases):
            return 'donation_process', None
        
        # ===== BLOOD REQUEST =====
        request_phrases = ['request blood', 'need blood', 'blood request', 'order blood',
                           'request for patient', 'emergency blood']
        if any(phrase in message_lower for phrase in request_phrases):
            return 'blood_request', None
        
        # ===== TESTING PROCESS =====
        testing_phrases = ['blood testing', 'lab test', 'test results', 'how testing works',
                           'safe blood', 'unsafe blood', 'quarantine', 'disease screening']
        if any(phrase in message_lower for phrase in testing_phrases):
            return 'testing_process', None
        
        # ===== POINTS AND REWARDS =====
        points_phrases = ['points', 'rewards', 'earn', 'badges', 'achievements', 
                          'milestones', 'levels', 'recognition']
        if any(phrase in message_lower for phrase in points_phrases):
            return 'points_rewards', None
        
        # ===== CONTACT INFORMATION =====
        contact_phrases = ['contact', 'phone', 'email', 'call', 'reach', 'support',
                           'customer service', 'help desk', 'complaint']
        if any(phrase in message_lower for phrase in contact_phrases):
            return 'contact', None
        
        # ===== FAQ / KNOWLEDGE =====
        faq_phrases = ['faq', 'frequently asked', 'common questions', 'tell me about',
                       'what is', 'what are', 'explain', 'how does', 'why']
        if any(phrase in message_lower for phrase in faq_phrases):
            return 'faq', None
        
        # ===== CURRENT WEATHER / TIME (fun feature) =====
        weather_phrases = ['weather', 'temperature', 'forecast', 'raining', 'sunny']
        time_phrases = ['time', 'date', 'today', 'tomorrow', 'what day']
        
        if any(phrase in message_lower for phrase in weather_phrases):
            return 'weather', None
        if any(phrase in message_lower for phrase in time_phrases):
            return 'time', None
        
        # ===== FALLBACK =====
        return 'general_query', None


class ResponseFormatter:
    """
    Helper class to format responses with modern chatbot UI elements
    """
    
    @staticmethod
    def format_number(num):
        """Format numbers with commas"""
        return f"{num:,}"
    
    @staticmethod
    def time_ago(date_obj):
        """Get human-readable time ago"""
        if not date_obj:
            return "Unknown"
        
        now = timezone.now()
        diff = now - date_obj
        
        if diff.days > 365:
            years = diff.days // 365
            return f"{years} year{'s' if years > 1 else ''} ago"
        elif diff.days > 30:
            months = diff.days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
        elif diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "Just now"
    
    @staticmethod
    def blood_group_emoji(bloodgroup):
        """Get emoji for blood group"""
        emojis = {
            'A+': '🅰️➕', 'A-': '🅰️➖',
            'B+': '🅱️➕', 'B-': '🅱️➖',
            'AB+': '🆎➕', 'AB-': '🆎➖',
            'O+': '🅾️➕', 'O-': '🅾️➖',
        }
        return emojis.get(bloodgroup.upper(), '🩸')
    
    @staticmethod
    def status_emoji(status):
        """Get emoji for status"""
        emojis = {
            'pending': '⏳', 'approved': '✅', 'collected': '📦',
            'completed': '✔️', 'cancelled': '❌', 'rejected': '🚫',
            'safe': '✅', 'unsafe': '⚠️', 'tested_safe': '✅',
            'tested_unsafe': '⚠️', 'dispatched': '🚚', 'delivered': '📦',
        }
        return emojis.get(status.lower(), '📋')
    
    @staticmethod
    def urgency_emoji(urgency):
        """Get emoji for urgency"""
        emojis = {
            'emergency': '🚨', 'urgent': '⚠️', 'routine': '📋',
        }
        return emojis.get(urgency.lower(), '📋')
    
    @staticmethod
    def progress_bar(current, total, width=10):
        """Create a text progress bar"""
        if total == 0:
            return '⬜' * width + ' 0%'
        
        percentage = min(100, int((current / total) * 100))
        filled = int((percentage / 100) * width)
        bar = '🟩' * filled + '⬜' * (width - filled)
        return f"{bar} {percentage}%"