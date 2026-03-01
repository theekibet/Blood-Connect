from blood.models import Stock, DonationCenter, StockUnit
from donor.models import Donor, BloodDonate
# # from patient.models import Patient, BloodRequest
from phlebotomist.models import Phlebotomist, Appointment
from django.contrib.auth.models import User
from django.db.models import Count, Q, Sum
from django.utils import timezone
from datetime import timedelta, date


class BloodDonationKnowledgeBase:
    """
    Enhanced knowledge base with role-specific context
    """
    
    @staticmethod
    def get_system_context():
        """Get current system statistics and context"""
        try:
            total_donors = Donor.objects.count()
            total_patients = 0
            total_phlebotomists = Phlebotomist.objects.count()
            total_centers = DonationCenter.objects.count()
            
            # Active requests
            active_requests = BloodRequest.objects.filter(
                status__in=['pending', 'approved']
            ).count()
            
            # Recent donations (last 30 days)
            thirty_days_ago = timezone.now() - timedelta(days=30)
            recent_donations = BloodDonate.objects.filter(
                date__gte=thirty_days_ago,
                status='approved'
            ).count()
            
            # Stock levels by blood group
            stock_info = StockUnit.objects.values('bloodgroup').annotate(
                total_units=Sum('unit')
            ).order_by('bloodgroup')
            
            # Critical stock alerts (below 1000ml)
            critical_stock = Stock.objects.filter(unit__lt=1000).count()
            
            context = {
                'total_donors': total_donors,
                'total_patients': 0,
                'total_phlebotomists': total_phlebotomists,
                'total_centers': total_centers,
                'active_requests': active_requests,
                'recent_donations': recent_donations,
                'stock_info': list(stock_info),
                'critical_stock_count': critical_stock,
            }
            
            return context
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod
    def get_blood_group_info(bloodgroup):
        """Get specific blood group information"""
        try:
            # Total available stock across all centers
            total_stock = StockUnit.objects.filter(
                bloodgroup=bloodgroup,
                unit__gt=0,
                expiry_date__gte=timezone.now().date()
            ).aggregate(total=Sum('unit'))['total'] or 0
            
            # Centers with this blood type
            centers_with_stock = DonationCenter.objects.filter(
                stockunit__bloodgroup=bloodgroup,
                stockunit__unit__gt=0
            ).distinct()
            
            # Pending requests for this blood type
            pending_requests = BloodRequest.objects.filter(
                bloodgroup=bloodgroup,
                status='pending'
            ).count()
            
            # Stock expiring soon (within 7 days)
            expiring_soon = StockUnit.objects.filter(
                bloodgroup=bloodgroup,
                expiry_date__lte=timezone.now().date() + timedelta(days=7),
                expiry_date__gte=timezone.now().date(),
                unit__gt=0
            ).count()
            
            return {
                'bloodgroup': bloodgroup,
                'total_units': total_stock,
                'centers_count': centers_with_stock.count(),
                'pending_requests': pending_requests,
                'expiring_batches': expiring_soon,
                'centers': [center.name for center in centers_with_stock[:5]]
            }
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod
    def get_donation_centers_info(city=None):
        """Get information about donation centers"""
        try:
            if city:
                centers = DonationCenter.objects.filter(city__icontains=city)
            else:
                centers = DonationCenter.objects.all()
            
            centers_data = []
            for center in centers[:10]:
                # Get stock summary for this center
                stock_summary = StockUnit.objects.filter(
                    center=center,
                    unit__gt=0
                ).aggregate(
                    total_batches=Count('id'),
                    total_units=Sum('unit')
                )
                
                centers_data.append({
                    'name': center.name,
                    'city': center.city,
                    'address': center.address,
                    'contact': center.contact_number,
                    'email': center.email,
                    'total_stock': stock_summary['total_units'] or 0,
                    'batches': stock_summary['total_batches'] or 0,
                })
            
            return {
                'total_centers': centers.count(),
                'centers': centers_data
            }
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod
    def get_eligibility_info():
        """Get blood donation eligibility criteria"""
        return {
            'age_requirement': 'Must be between 18 and 65 years old.',
            'weight_requirement': 'Must weigh at least 50kg',
            'health_requirement': 'Must be in good general health',
            'interval': 'Must wait at least 56 days between donations',
            'disqualifications': [
                'Recent tattoos or piercings (within 6 months)',
                'Currently taking antibiotics',
                'Recent surgery or illness',
                'Pregnancy or breastfeeding',
                'History of certain diseases (HIV, Hepatitis, etc.)',
                'Recent travel to malaria-endemic areas',
            ]
        }
    
    @staticmethod
    def get_donor_specific_info(donor):
        """Get comprehensive donor-specific information"""
        try:
            info = {
                'username': donor.user.username,
                'full_name': donor.user.get_full_name(),
                'email': donor.user.email,
                'bloodgroup': donor.bloodgroup,
                'total_donations': donor.total_donations,
                'points': donor.points,
                'last_donation': str(donor.last_donation_date) if donor.last_donation_date else 'Never',
            }
            
            # Next eligible donation
            next_eligible = donor.next_eligible_donation_date()
            if next_eligible:
                days_until = donor.days_until_next_donation()
                info['next_eligible_donation'] = str(next_eligible)
                info['days_until_eligible'] = days_until
                info['can_donate_now'] = days_until == 0
            else:
                info['next_eligible_donation'] = 'Eligible now'
                info['days_until_eligible'] = 0
                info['can_donate_now'] = True
            
            # Recent donation history
            recent_donations = BloodDonate.objects.filter(
                donor=donor
            ).order_by('-date')[:5]
            
            info['recent_donations'] = [
                {
                    'date': str(donation.date),
                    'status': donation.status,
                    'units': donation.unit or 0,
                    'center': donation.donation_center.name if donation.donation_center else 'N/A'
                }
                for donation in recent_donations
            ]
            
            # Upcoming appointments
            upcoming_appointments = Appointment.objects.filter(
                donor=donor,
                date__gte=timezone.now(),
                status__in=['pending', 'approved']
            ).order_by('date')[:3]
            
            info['upcoming_appointments'] = [
                {
                    'date': appt.date.strftime('%b %d, %Y %I:%M %p'),
                    'status': appt.status,
                    'phlebotomist': appt.phlebotomist.user.get_full_name() if appt.phlebotomist else 'Not assigned',
                    'center': appt.donation_center.name if appt.donation_center else 'N/A'
                }
                for appt in upcoming_appointments
            ]
            
            return info
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod
    def get_phlebotomist_specific_info(phlebotomist):
        """Get comprehensive phlebotomist-specific information"""
        try:
            info = {
                'username': phlebotomist.user.username,
                'full_name': phlebotomist.user.get_full_name(),
                'email': phlebotomist.user.email,
                'specialization': phlebotomist.specialization,
                'registration_number': phlebotomist.registration_number,
                'donation_center': phlebotomist.donation_center.name if phlebotomist.donation_center else 'Not assigned',
            }
            
            # Today's appointments
            today = timezone.now().date()
            today_appointments = Appointment.objects.filter(
                phlebotomist=phlebotomist,
                date__date=today
            ).count()
            
            info['today_appointments'] = today_appointments
            
            # Pending approvals
            pending_approvals = Appointment.objects.filter(
                phlebotomist=phlebotomist,
                status='pending'
            ).count()
            
            info['pending_approvals'] = pending_approvals
            
            # Upcoming appointments
            upcoming = Appointment.objects.filter(
                phlebotomist=phlebotomist,
                date__gte=timezone.now(),
                status__in=['pending', 'approved']
            ).order_by('date')[:5]
            
            info['upcoming_appointments'] = [
                {
                    'date': appt.date.strftime('%b %d, %Y %I:%M %p'),
                    'type': 'Donation' if appt.donor and not appt.patient else 'Blood Request',
                    'participant': (appt.donor.user.get_full_name() if appt.donor 
                                  else appt.patient.user.get_full_name() if appt.patient 
                                  else 'Unknown'),
                    'status': appt.status,
                }
                for appt in upcoming
            ]
            
            # Center stock summary (if phlebotomist has a center)
            if phlebotomist.donation_center:
                stock_summary = StockUnit.objects.filter(
                    center=phlebotomist.donation_center,
                    unit__gt=0
                ).values('bloodgroup').annotate(
                    total=Sum('unit')
                ).order_by('bloodgroup')
                
                info['center_stock'] = {
                    item['bloodgroup']: item['total'] 
                    for item in stock_summary
                }
                
                # Critical stock alerts
                critical_stock = Stock.objects.filter(
                    center=phlebotomist.donation_center,
                    unit__lt=1000
                )
                
                info['critical_stock'] = [
                    f"{stock.bloodgroup} ({stock.unit}ml)" 
                    for stock in critical_stock
                ]
            
            return info
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod

class IntentClassifier:
    """
    Enhanced intent classifier with role-specific intents
    """
    
    @staticmethod
    def classify_intent(message):
        """Determine what the user is asking about"""
        message_lower = message.lower()
        
        # Greetings
        if any(word in message_lower for word in ['hello', 'hi', 'hey', 'greetings', 'good morning', 'good afternoon', 'good evening']):
            return 'greeting', None
        
        # Help requests
        if any(word in message_lower for word in ['help', 'support', 'contact', 'assistance']):
            return 'help', None
        
        # System statistics
        if any(word in message_lower for word in ['how many', 'total', 'statistics', 'stats', 'count', 'number of']):
            if any(word in message_lower for word in ['donor', 'donors']):
                return 'system_stats', 'donors'
            elif any(word in message_lower for word in ['patient', 'patients']):
                return 'system_stats', 'patients'
            elif any(word in message_lower for word in ['phlebotomist', 'phlebotomists', 'staff']):
                return 'system_stats', 'phlebotomists'
            elif any(word in message_lower for word in ['center', 'centers', 'location', 'locations']):
                return 'system_stats', 'centers'
            elif any(word in message_lower for word in ['request', 'requests']):
                return 'system_stats', 'requests'
            elif any(word in message_lower for word in ['donation', 'donations']):
                return 'system_stats', 'donations'
            return 'system_stats', 'general'
        
        # Blood group queries
        blood_groups = ['o+', 'o-', 'a+', 'a-', 'b+', 'b-', 'ab+', 'ab-']
        for bg in blood_groups:
            if bg in message_lower:
                return 'blood_group_info', bg.upper()
        
        # Donation centers
        if any(word in message_lower for word in ['center', 'centers', 'location', 'where can i', 'nearest', 'find']):
            cities = ['nairobi', 'mombasa', 'kisumu', 'nakuru', 'eldoret', 'thika', 'malindi']
            for city in cities:
                if city in message_lower:
                    return 'donation_centers', city
            return 'donation_centers', None
        
        # Eligibility
        if any(word in message_lower for word in ['eligible', 'eligibility', 'can i donate', 'requirements', 'qualify', 'criteria']):
            return 'eligibility', None
        
        # Profile queries
        if any(word in message_lower for word in ['my profile', 'my account', 'my donations', 'my points', 'when can i donate', 'my appointments', 'my requests', 'my history']):
            return 'user_profile', None
        
        # Appointment queries
        if any(word in message_lower for word in ['appointment', 'appointments', 'schedule', 'booking', 'book']):
            return 'appointments', None
        
        # Donation process
        if any(word in message_lower for word in ['how to donate', 'donation process', 'steps', 'procedure', 'what happens']):
            return 'donation_process', None
        
        # Blood request
        if any(word in message_lower for word in ['request blood', 'need blood', 'blood request', 'urgent', 'emergency']):
            return 'blood_request', None
        
        # Stock queries (phlebotomist-specific)
        if any(word in message_lower for word in ['stock', 'inventory', 'available blood', 'blood supply']):
            return 'stock_info', None
        
        # Phlebotomist duties
        if any(word in message_lower for word in ['my duties', 'my responsibilities', 'what should i do', 'my tasks']):
            return 'phlebotomist_duties', None
        
        # Points and rewards (donor-specific)
        if any(word in message_lower for word in ['points', 'rewards', 'earn', 'badges', 'achievements']):
            return 'points_rewards', None
        
        return 'general_query', None
