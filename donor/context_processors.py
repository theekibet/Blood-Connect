import random
from django.contrib.contenttypes.models import ContentType
from utils.models import Notification
from donor.models import Donor, DonorEligibility, BloodDonate
from datetime import date, timedelta
from django.utils import timezone
from django.core.exceptions import FieldError

def donor_notification_count(request):
    """
    Context processor providing notification counts and donor-specific context.
    Returns:
        - donor_unread_notification_count: Number of unread notifications
        - donor_eligibility_status: Current eligibility status
        - donor_dashboard_stats: Quick stats for dashboard
        - donor_has_pending_actions: Flag for pending actions
        - donor_next_milestone: Next donation milestone
        - donor_support_options: Available support options for non-eligible donors
    """
    context = {
        'donor_unread_notification_count': 0,
        'donor_eligibility_status': None,
        'donor_has_pending_actions': False,
        'donor_next_milestone': None,
        'donor_can_donate_now': False,
        'donor_eligibility_completed': False,
        'donor_volunteer_suggestions': [],
        'donor_show_welcome_modal': False,
    }
    
    if request.user.is_authenticated:
        try:
            donor = Donor.objects.get(user=request.user)
            
            # ==========================================
            # 1. NOTIFICATION COUNT - SIMPLIFIED
            # ==========================================
            try:
                # Try direct ForeignKey to User first
                unread_count = Notification.objects.filter(
                    recipient=donor.user,
                    is_read=False
                ).count()
            except (FieldError, AttributeError):
                try:
                    # Try GenericForeignKey to Donor
                    donor_ct = ContentType.objects.get_for_model(Donor)
                    unread_count = Notification.objects.filter(
                        recipient_content_type=donor_ct,
                        recipient_object_id=donor.id,
                        is_read=False
                    ).count()
                except (FieldError, AttributeError):
                    try:
                        # Try GenericForeignKey to User
                        user_ct = ContentType.objects.get_for_model(request.user.__class__)
                        unread_count = Notification.objects.filter(
                            recipient_content_type=user_ct,
                            recipient_object_id=request.user.id,
                            is_read=False
                        ).count()
                    except (FieldError, AttributeError) as e:
                        print(f"Notification query error: {e}")
                        unread_count = 0
            
            context['donor_unread_notification_count'] = unread_count
            
            # ==========================================
            # 2. ELIGIBILITY STATUS - FIXED (removed updated_at)
            # ==========================================
            try:
                eligibility = DonorEligibility.objects.get(donor=donor)
                
                # Check which fields actually exist
                eligibility_data = {
                    'is_eligible': getattr(eligibility, 'approved', False),
                    'weight': getattr(eligibility, 'weight', None),
                    'gender': getattr(eligibility, 'gender', None),
                    'good_health': getattr(eligibility, 'good_health', None),
                    'travel_history': getattr(eligibility, 'travel_history', None),
                }
                
                # Add last_checked only if the field exists
                if hasattr(eligibility, 'updated_at'):
                    eligibility_data['last_checked'] = eligibility.updated_at
                elif hasattr(eligibility, 'updated'):
                    eligibility_data['last_checked'] = eligibility.updated
                elif hasattr(eligibility, 'modified'):
                    eligibility_data['last_checked'] = eligibility.modified
                elif hasattr(eligibility, 'created_at'):
                    eligibility_data['last_checked'] = eligibility.created_at
                else:
                    eligibility_data['last_checked'] = timezone.now()
                
                context['donor_eligibility_status'] = eligibility_data
                context['donor_eligibility_completed'] = True
                
            except DonorEligibility.DoesNotExist:
                context['donor_eligibility_completed'] = False
                # Show welcome modal for new donors who haven't completed eligibility
                if not request.session.get('has_seen_welcome_modal', False):
                    context['donor_show_welcome_modal'] = True
                    request.session['has_seen_welcome_modal'] = True
            
            # ==========================================
            # 3. DONATION STATS & NEXT ELIGIBILITY
            # ==========================================
            # Count safe donations
            safe_donations = BloodDonate.objects.filter(
                donor=donor,
                status='tested_safe'
            ).count()
            
            # Check if donor has any unsafe donations
            has_unsafe = BloodDonate.objects.filter(
                donor=donor,
                status='tested_unsafe'
            ).exists()
            
            # Calculate next eligible donation date
            if hasattr(donor, 'last_donation_date') and donor.last_donation_date:
                # Standard waiting period is 56 days (8 weeks)
                next_eligible = donor.last_donation_date + timedelta(days=56)
                today = timezone.now().date()
                days_until = (next_eligible - today).days if next_eligible > today else 0
                
                context['donor_can_donate_now'] = (
                    context['donor_eligibility_completed'] and
                    context['donor_eligibility_status'] and
                    context['donor_eligibility_status'].get('is_eligible', False) and
                    not has_unsafe and
                    days_until == 0
                )
                
                context['donor_next_eligible_date'] = next_eligible
                context['donor_days_until_eligible'] = max(0, days_until)
            else:
                # First-time donor
                context['donor_can_donate_now'] = (
                    context['donor_eligibility_completed'] and
                    context['donor_eligibility_status'] and
                    context['donor_eligibility_status'].get('is_eligible', False) and
                    not has_unsafe
                )
            
            # ==========================================
            # 4. MILESTONE TRACKING
            # ==========================================
            milestones = [1, 5, 10, 25, 50, 100]
            for milestone in milestones:
                if safe_donations < milestone:
                    context['donor_next_milestone'] = {
                        'target': milestone,
                        'current': safe_donations,
                        'remaining': milestone - safe_donations,
                        'percentage': int((safe_donations / milestone) * 100) if safe_donations > 0 else 0
                    }
                    break
            
            # ==========================================
            # 5. PENDING ACTIONS CHECK
            # ==========================================
            # Check for pending donation requests
            pending_donations = BloodDonate.objects.filter(
                donor=donor,
                status__in=['pending', 'approved']
            ).exists()
            
            # Check for incomplete eligibility
            eligibility_incomplete = not context['donor_eligibility_completed']
            
            context['donor_has_pending_actions'] = pending_donations or eligibility_incomplete
            
            # ==========================================
            # 6. VOLUNTEER SUGGESTIONS (for non-eligible donors)
            # ==========================================
            if (not context['donor_eligibility_completed'] or 
                (context['donor_eligibility_completed'] and 
                 context['donor_eligibility_status'] and 
                 not context['donor_eligibility_status'].get('is_eligible', False))):
                
                context['donor_volunteer_suggestions'] = [
                    {
                        'title': 'Blood Drive Ambassador',
                        'description': 'Organize blood drives in your community',
                        'icon': 'fa-flag',
                        'url': '/volunteer/blood-drive/',
                        'commitment': 'Flexible'
                    },
                    {
                        'title': 'Social Media Advocate',
                        'description': 'Share donation stories and urgent needs',
                        'icon': 'fa-share-alt',
                        'url': '/volunteer/advocate/',
                        'commitment': '1-2 hours/week'
                    },
                    {
                        'title': 'Transportation Volunteer',
                        'description': 'Help donors get to donation centers',
                        'icon': 'fa-truck',
                        'url': '/volunteer/transport/',
                        'commitment': 'Flexible'
                    },
                    {
                        'title': 'Administrative Support',
                        'description': 'Help with paperwork and coordination',
                        'icon': 'fa-file-signature',
                        'url': '/volunteer/admin/',
                        'commitment': '2-4 hours/week'
                    },
                    {
                        'title': 'Community Educator',
                        'description': 'Teach about blood donation importance',
                        'icon': 'fa-chalkboard-teacher',
                        'url': '/volunteer/educator/',
                        'commitment': 'Monthly events'
                    },
                ]
            
            # ==========================================
            # 7. QUICK STATS FOR DASHBOARD
            # ==========================================
            context['donor_dashboard_stats'] = {
                'total_safe_donations': safe_donations,
                'total_points': getattr(donor, 'points', 0),
                'blood_group': getattr(donor, 'bloodgroup', 'Unknown'),
                'blood_group_verified': getattr(donor, 'bloodgroup_verified', False),
                'is_hero': safe_donations >= 1,
                'hero_level': 'Gold' if safe_donations >= 10 else 'Silver' if safe_donations >= 5 else 'Bronze' if safe_donations >= 1 else 'New Donor',
            }
            
            # ==========================================
            # 8. URGENT BLOOD NEEDS (context for all donors)
            # ==========================================
            context['donor_urgent_needs'] = [
                {'blood_type': 'O-', 'message': 'Critical shortage', 'priority': 'high'},
                {'blood_type': 'A-', 'message': 'Low supply', 'priority': 'medium'},
            ]
            
        except Donor.DoesNotExist:
            # User is authenticated but not a donor
            pass
        except Exception as e:
            # Log error but don't break the page
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error in donor_notification_count context processor: {e}")
            print(f"Context processor error: {e}")  # For development debugging
    
    return context


def donor_eligibility_context(request):
    """
    Dedicated context processor for eligibility-related data.
    Useful for pages that need eligibility information without other donor data.
    """
    context = {
        'show_eligibility_reminder': False,
        'eligibility_reminder_message': None,
    }
    
    if request.user.is_authenticated:
        try:
            donor = Donor.objects.get(user=request.user)
            
            # Check if eligibility form needs to be completed
            if not DonorEligibility.objects.filter(donor=donor).exists():
                # Check if user has been active for more than 2 days without completing
                from django.utils import timezone
                days_since_joined = (timezone.now().date() - request.user.date_joined.date()).days
                
                if days_since_joined >= 2:
                    context['show_eligibility_reminder'] = True
                    context['eligibility_reminder_message'] = (
                        "You haven't completed your eligibility form yet. "
                        "Complete it to start donating blood!"
                    )
                elif days_since_joined == 0:
                    # New user - show welcome message
                    context['show_eligibility_reminder'] = True
                    context['eligibility_reminder_message'] = (
                        "Welcome! Take a moment to complete your eligibility form "
                        "so you can start saving lives."
                    )
                    
        except Donor.DoesNotExist:
            pass
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error in donor_eligibility_context: {e}")
    
    return context


def donor_support_options(request):
    """
    Context processor providing support/volunteer options for all users.
    This promotes the "everyone has a role" message.
    """
    return {
        'donor_support_options': [
            {
                'title': 'Become a Blood Drive Ambassador',
                'description': 'Organize and promote blood drives in your community',
                'icon': 'fas fa-flag',
                'url': '/support/blood-drive-ambassador/',
                'badge': 'Popular'
            },
            {
                'title': 'Join Our Volunteer Team',
                'description': 'Help with events, administration, and donor support',
                'icon': 'fas fa-hands-helping',
                'url': '/support/volunteer/',
                'badge': 'Flexible Hours'
            },
            {
                'title': 'Spread Awareness',
                'description': 'Share our mission on social media and in your community',
                'icon': 'fas fa-bullhorn',
                'url': '/support/awareness/',
                'badge': 'Make Impact'
            },
            {
                'title': 'Financial Support',
                'description': 'Help us maintain equipment and reach more donors',
                'icon': 'fas fa-hand-holding-usd',
                'url': '/support/donate/',
                'badge': 'Tax Deductible'
            },
            {
                'title': 'Corporate Partnership',
                'description': 'Bring your organization to support blood donation',
                'icon': 'fas fa-building',
                'url': '/support/corporate/',
                'badge': 'Partner'
            },
            {
                'title': 'Blood Drive Host',
                'description': 'Host a blood drive at your workplace or community center',
                'icon': 'fas fa-calendar-alt',
                'url': '/support/host-drive/',
                'badge': 'Impactful'
            },
        ]
    }