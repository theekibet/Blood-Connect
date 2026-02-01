import os
import json
from dotenv import load_dotenv
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

try:
    from .models import ChatConversation, ChatMessage
    MODELS_AVAILABLE = True
except:
    MODELS_AVAILABLE = False

try:
    from .knowledge_base import BloodDonationKnowledgeBase, IntentClassifier
    KNOWLEDGE_BASE_AVAILABLE = True
except:
    KNOWLEDGE_BASE_AVAILABLE = False

load_dotenv()
DEVELOPMENT_MODE = os.getenv("DEVELOPMENT_MODE", "true").lower() == "true"


def get_user_role(user):
    """Determine user's role in the system"""
    if not user or not user.is_authenticated:
        return None
    
    if hasattr(user, 'donor'):
        return 'donor'
    elif hasattr(user, 'nurse'):
        return 'nurse'
    elif hasattr(user, 'patient'):
        return 'patient'
    elif user.is_staff:
        return 'admin'
    return None


def generate_personalized_greeting(user, role):
    """Generate role-specific greeting"""
    name = user.get_full_name() or user.username if user and user.is_authenticated else "there"
    
    greetings = {
        'donor': f"""👋 Hello {name}! Welcome back to your Blood Donation Dashboard.

**How can I assist you today?**

You can ask me about:
• 📅 Your next eligible donation date
• 🎖️ Your donation history and points
• 📍 Nearby donation centers
• 🩸 Blood donation eligibility
• 📋 Your upcoming appointments
• ℹ️ General donation information

Just type your question!""",
        
        'nurse': f"""👋 Hello Nurse {name}! Welcome to your Dashboard Assistant.

**How can I help you today?**

You can ask me about:
• 📊 Today's appointments and pending approvals
• 🏥 Your center's blood stock levels
• 📋 Critical stock alerts
• 📅 Your upcoming schedule
• 🩸 Blood group availability
• 📍 Other donation centers

What would you like to know?""",
        
        'patient': f"""👋 Hello {name}! Welcome to the Blood Request System.

**How can I assist you today?**

You can ask me about:
• 📋 Your blood request status
• 🩸 Blood availability for your blood group
• 📍 Nearest donation centers
• 📅 Your appointment history
• ⚕️ Blood transfusion information

Feel free to ask!""",
        
        'admin': f"""👋 Hello Administrator {name}!

**System Management Assistant**

You can ask me about:
• 📊 System-wide statistics
• 🩸 Blood stock across all centers
• 👥 User management information
• 📈 Donation trends
• 🏥 Center performance

How can I help?""",
        
        None: """👋 Hello! Welcome to the Blood Donation System.

**How can I help you today?**

You can ask me about:
• 🩸 Blood donation eligibility and requirements
• 📍 Finding donation centers near you
• ❓ Frequently asked questions
• 📞 Contact information
• ℹ️ General blood donation information

Please log in for personalized assistance!"""
    }
    
    return greetings.get(role, greetings[None])


def generate_response(intent, context_data, user_message, user=None):
    """Generate contextual response based on intent, user role, and system data"""
    if not KNOWLEDGE_BASE_AVAILABLE:
        return None
    
    intent_type, intent_detail = intent
    role = get_user_role(user)
    
    # === GREETING ===
    if intent_type == 'greeting':
        return generate_personalized_greeting(user, role)
    
    # === SYSTEM STATISTICS ===
    elif intent_type == 'system_stats':
        stats = context_data
        
        if intent_detail == 'donors':
            response = f"""📊 **Donor Statistics**

• **Total Registered Donors:** {stats.get('total_donors', 0):,}
• **Recent Donations (30 days):** {stats.get('recent_donations', 0):,}
• **Active Donors:** {stats.get('total_donors', 0):,}

"""
            if role == 'nurse':
                response += "💡 *Tip: You can view detailed donor information in your dashboard.*"
            elif role == 'donor':
                response += f"🎖️ You're one of our {stats.get('total_donors', 0):,} registered donors! Keep up the great work!"
            
            return response
        
        elif intent_detail == 'nurses':
            response = f"""📊 **Nursing Staff Statistics**

• **Total Nurses:** {stats.get('total_nurses', 0)}
• **Donation Centers:** {stats.get('total_centers', 0)}

"""
            if role == 'nurse':
                response += "👩‍⚕️ You're part of our dedicated healthcare team!"
            
            return response
        
        elif intent_detail == 'centers':
            response = f"""📊 **Donation Center Statistics**

• **Total Centers:** {stats.get('total_centers', 0)}
• **Active Centers:** {stats.get('total_centers', 0)}

"""
            if role == 'donor':
                response += "Would you like to know which centers are nearest to you?"
            elif role == 'nurse' and user and hasattr(user, 'nurse') and user.nurse.donation_center:
                response += f"\n🏥 Your assigned center: **{user.nurse.donation_center.name}**"
            
            return response
        
        elif intent_detail == 'requests':
            response = f"""📊 **Blood Request Statistics**

• **Active Blood Requests:** {stats.get('active_requests', 0)}
• **Pending Approvals:** {stats.get('active_requests', 0)}

"""
            if role == 'nurse':
                response += "💡 Check your dashboard for requests requiring your attention."
            elif role == 'donor':
                response += "🩸 Your donation could help fulfill these requests! Check if you're eligible to donate."
            
            return response
        
        elif intent_detail == 'donations':
            return f"""📊 **Donation Statistics**

• **Recent Donations (30 days):** {stats.get('recent_donations', 0):,}
• **Total Active Donors:** {stats.get('total_donors', 0):,}
• **Donation Centers:** {stats.get('total_centers', 0)}

{f"🎖️ Your total donations: **{user.donor.total_donations}**" if role == 'donor' and user and hasattr(user, 'donor') else ''}
"""
        
        else:  # general
            response = f"""📊 **System Overview**

• **Registered Donors:** {stats.get('total_donors', 0):,}
• **Active Patients:** {stats.get('total_patients', 0):,}
• **Nursing Staff:** {stats.get('total_nurses', 0)}
• **Donation Centers:** {stats.get('total_centers', 0)}
• **Active Blood Requests:** {stats.get('active_requests', 0)}
• **Recent Donations (30 days):** {stats.get('recent_donations', 0):,}

"""
            if role == 'donor':
                response += f"🎖️ **Your Contribution:** {user.donor.total_donations if hasattr(user, 'donor') else 0} donations"
            elif role == 'nurse':
                response += "👩‍⚕️ **Your Role:** Healthcare Professional"
            
            return response
    
    # === BLOOD GROUP INFORMATION ===
    elif intent_type == 'blood_group_info':
        blood_group = intent_detail
        info = BloodDonationKnowledgeBase.get_blood_group_info(blood_group)
        
        if 'error' in info:
            return f"❌ Sorry, I couldn't retrieve information for blood group {blood_group}."
        
        response = f"""🩸 **Blood Group {blood_group} Information**

• **Total Available:** {info.get('total_units', 0):,} ml
• **Pending Requests:** {info.get('pending_requests', 0)}
• **Available at:** {info.get('centers_count', 0)} centers
• **Expiring Soon:** {info.get('expiring_batches', 0)} batches

"""
        
        if info.get('centers'):
            response += f"\n**Centers with {blood_group}:**\n"
            for center in info['centers'][:3]:
                response += f"  • {center}\n"
        
        # Role-specific additions
        if role == 'donor' and user and hasattr(user, 'donor'):
            if user.donor.bloodgroup == blood_group:
                response += f"\n💡 This is **your blood type**! "
                if user.donor.days_until_next_donation() == 0:
                    response += "You're eligible to donate now! 🎉"
                else:
                    days = user.donor.days_until_next_donation()
                    response += f"You can donate again in **{days} days**."
        
        elif role == 'nurse':
            if info.get('pending_requests', 0) > 0:
                response += f"\n⚠️ **Attention:** {info.get('pending_requests')} pending requests for this blood type."
        
        return response
    
    # === DONATION CENTERS ===
    elif intent_type == 'donation_centers':
        city = intent_detail
        info = BloodDonationKnowledgeBase.get_donation_centers_info(city)
        
        if 'error' in info:
            return "❌ Sorry, I couldn't retrieve donation center information."
        
        response = f"""🏥 **Donation Centers"""
        if city:
            response += f" in {city.title()}"
        response += f"** ({info.get('total_centers', 0)} total)\n\n"
        
        for center in info.get('centers', [])[:5]:
            response += f"""📍 **{center.get('name', 'Unknown')}**
   📮 {center.get('address', '')}, {center.get('city', '')}
   📞 {center.get('contact', 'N/A')}
   📧 {center.get('email', 'N/A')}
   🩸 Stock: {center.get('total_stock', 0):,}ml ({center.get('batches', 0)} batches)

"""
        
        if role == 'donor':
            response += "\n💡 *Tip: You can schedule an appointment at any of these centers through your dashboard.*"
        elif role == 'nurse' and user and hasattr(user, 'nurse') and user.nurse.donation_center:
            response += f"\n🏥 *Your assigned center: {user.nurse.donation_center.name}*"
        
        return response
    
    # === ELIGIBILITY ===
    elif intent_type == 'eligibility':
        info = BloodDonationKnowledgeBase.get_eligibility_info()
        
        response = """✅ **Blood Donation Eligibility Criteria**

**Basic Requirements:**
"""
        response += f"• **Age:** {info.get('age_requirement', 'N/A')}\n"
        response += f"• **Weight:** {info.get('weight_requirement', 'N/A')}\n"
        response += f"• **Health:** {info.get('health_requirement', 'N/A')}\n"
        response += f"• **Frequency:** {info.get('interval', 'N/A')}\n"
        
        response += "\n**❌ You CANNOT donate if you have:**\n"
        for item in info.get('disqualifications', [])[:6]:
            response += f"  • {item}\n"
        
        if role == 'donor' and user and hasattr(user, 'donor'):
            donor = user.donor
            if donor.days_until_next_donation() == 0:
                response += "\n\n🎉 **Good news!** Based on your last donation, you're eligible to donate now!"
            else:
                days = donor.days_until_next_donation()
                next_date = donor.next_eligible_donation_date()
                response += f"\n\n📅 **Your Status:** You can donate again on **{next_date.strftime('%B %d, %Y')}** ({days} days from now)."
        elif role == 'donor':
            response += "\n\n💡 *Complete your eligibility form in your dashboard to get personalized information.*"
        
        return response
    
    # === USER PROFILE ===
    elif intent_type == 'user_profile':
        if not user or not user.is_authenticated:
            return "🔒 Please log in to view your profile information. You can access your dashboard after logging in."
        
        if role == 'donor':
            info = BloodDonationKnowledgeBase.get_donor_specific_info(user.donor)
            
            if 'error' in info:
                return "❌ Unable to retrieve your profile information. Please try again."
            
            response = f"""👤 **Your Donor Profile**

**Personal Information:**
• **Name:** {info.get('full_name', 'N/A')}
• **Blood Group:** {info.get('bloodgroup', 'Not set')} 🩸
• **Email:** {info.get('email', 'N/A')}

**Donation Statistics:**
• **Total Donations:** {info.get('total_donations', 0)} 🎖️
• **Points Earned:** {info.get('points', 0)} ⭐
• **Last Donation:** {info.get('last_donation', 'Never')}

**Eligibility Status:**
"""
            
            if info.get('can_donate_now'):
                response += "✅ **You are eligible to donate now!**\n"
            else:
                response += f"📅 **Next Eligible:** {info.get('next_eligible_donation')} ({info.get('days_until_eligible')} days)\n"
            
            # Recent donations
            if info.get('recent_donations'):
                response += "\n**Recent Donations:**\n"
                for donation in info['recent_donations'][:3]:
                    response += f"  • {donation['date']} - {donation['status']} ({donation['units']}ml) at {donation['center']}\n"
            
            # Upcoming appointments
            if info.get('upcoming_appointments'):
                response += "\n**Upcoming Appointments:**\n"
                for appt in info['upcoming_appointments']:
                    response += f"  • {appt['date']} - {appt['status']} with {appt['nurse']}\n"
            
            response += "\n💡 *Schedule your next donation through your dashboard!*"
            return response
        
        elif role == 'nurse':
            info = BloodDonationKnowledgeBase.get_nurse_specific_info(user.nurse)
            
            if 'error' in info:
                return "❌ Unable to retrieve your profile information. Please try again."
            
            response = f"""👩‍⚕️ **Your Nurse Profile**

**Personal Information:**
• **Name:** {info.get('full_name', 'N/A')}
• **Specialization:** {info.get('specialization', 'N/A')}
• **Registration:** {info.get('registration_number', 'N/A')}
• **Center:** {info.get('donation_center', 'Not assigned')}

**Today's Overview:**
• **Appointments Today:** {info.get('today_appointments', 0)}
• **Pending Approvals:** {info.get('pending_approvals', 0)}

"""
            
            # Upcoming appointments
            if info.get('upcoming_appointments'):
                response += "**Upcoming Appointments:**\n"
                for appt in info['upcoming_appointments']:
                    response += f"  • {appt['date']} - {appt['type']} for {appt['participant']} ({appt['status']})\n"
            
            # Center stock
            if info.get('center_stock'):
                response += "\n**Your Center's Blood Stock:**\n"
                for bg, units in info['center_stock'].items():
                    status = "⚠️" if units < 1000 else "✅"
                    response += f"  {status} {bg}: {units:,}ml\n"
            
            # Critical alerts
            if info.get('critical_stock'):
                response += "\n🚨 **Critical Stock Alerts:**\n"
                for item in info['critical_stock']:
                    response += f"  • {item}\n"
            
            return response
        
        elif role == 'patient':
            info = BloodDonationKnowledgeBase.get_patient_specific_info(user.patient)
            
            if 'error' in info:
                return "❌ Unable to retrieve your profile information. Please try again."
            
            response = f"""👤 **Your Patient Profile**

**Personal Information:**
• **Name:** {info.get('full_name', 'N/A')}
• **Blood Group:** {info.get('bloodgroup', 'Not set')} 🩸
• **Email:** {info.get('email', 'N/A')}

**Request Statistics:**
• **Total Requests:** {info.get('total_requests', 0)}
• **Active Requests:** {info.get('active_requests_count', 0)}

"""
            
            if info.get('recent_requests'):
                response += "**Recent Blood Requests:**\n"
                for req in info['recent_requests'][:3]:
                    status_emoji = {"pending": "⏳", "approved": "✅", "completed": "✔️", "rejected": "❌"}.get(req['status'], "📋")
                    response += f"  {status_emoji} {req['bloodgroup']} - {req['status']} ({req['units']}ml) - {req['date']}\n"
            
            return response
        
        return "Profile information not available."
    
    # === APPOINTMENTS ===
    elif intent_type == 'appointments':
        if not user or not user.is_authenticated:
            return "🔒 Please log in to view your appointments."
        
        if role == 'donor':
            from nurse.models import Appointment
            upcoming = Appointment.objects.filter(
                donor=user.donor,
                date__gte=timezone.now(),
                status__in=['pending', 'approved']
            ).order_by('date')[:5]
            
            if not upcoming:
                return """📅 **Your Appointments**

You don't have any upcoming appointments.

💡 *Schedule a donation appointment through your dashboard!*"""
            
            response = "📅 **Your Upcoming Appointments**\n\n"
            for appt in upcoming:
                status_emoji = {"pending": "⏳", "approved": "✅", "completed": "✔️"}.get(appt.status, "📋")
                response += f"{status_emoji} **{appt.date.strftime('%b %d, %Y %I:%M %p')}**\n"
                response += f"   Nurse: {appt.nurse.user.get_full_name() if appt.nurse else 'Not assigned'}\n"
                response += f"   Center: {appt.donation_center.name if appt.donation_center else 'N/A'}\n"
                response += f"   Status: {appt.status.title()}\n\n"
            
            return response
        
        elif role == 'nurse':
            from nurse.models import Appointment
            today = timezone.now().date()
            today_appts = Appointment.objects.filter(
                nurse=user.nurse,
                date__date=today
            ).order_by('date')
            
            response = f"📅 **Today's Appointments ({today_appts.count()})**\n\n"
            
            if not today_appts:
                response += "No appointments scheduled for today.\n\n"
            else:
                for appt in today_appts:
                    participant = (appt.donor.user.get_full_name() if appt.donor 
                                 else appt.patient.user.get_full_name() if appt.patient 
                                 else 'Unknown')
                    appt_type = "Donation" if appt.donor and not appt.patient else "Blood Request"
                    status_emoji = {"pending": "⏳", "approved": "✅", "completed": "✔️"}.get(appt.status, "📋")
                    
                    response += f"{status_emoji} **{appt.date.strftime('%I:%M %p')}** - {appt_type}\n"
                    response += f"   {participant} ({appt.status.title()})\n\n"
            
            # Pending approvals
            pending = Appointment.objects.filter(
                nurse=user.nurse,
                status='pending'
            ).count()
            
            if pending > 0:
                response += f"⚠️ **{pending} appointments pending your approval.**"
            
            return response
        
        return "Appointment information not available for your role."
    
    # === DONATION PROCESS ===
    elif intent_type == 'donation_process':
        response = """🩸 **Blood Donation Process**

**Step-by-Step Guide:**

1️⃣ **Register** as a donor on our platform
2️⃣ **Complete** your health questionnaire
3️⃣ **Check** your eligibility status
4️⃣ **Schedule** an appointment at your nearest center
5️⃣ **Arrive** 10-15 minutes before your appointment
6️⃣ **Complete** health screening with our nurse
7️⃣ **Donate** blood (takes about 10-15 minutes)
8️⃣ **Rest** and enjoy refreshments
9️⃣ **Receive** confirmation and earn points! 🎖️

⏱️ **Total Time:** About 45-60 minutes

**What to Bring:**
• Valid ID (National ID or Passport)
• Your appointment confirmation
• A positive attitude! 😊

**Tips for a Smooth Donation:**
• Drink plenty of water before
• Eat a healthy meal 2-3 hours before
• Get good sleep the night before
• Wear comfortable clothing

"""
        
        if role == 'donor' and user and hasattr(user, 'donor'):
            if user.donor.days_until_next_donation() == 0:
                response += "\n✅ **You're eligible to donate now!** Schedule your appointment today!"
            else:
                days = user.donor.days_until_next_donation()
                response += f"\n📅 **You can donate again in {days} days.**"
        
        return response
    
    # === BLOOD REQUEST ===
    elif intent_type == 'blood_request':
        if not user or not user.is_authenticated:
            return """🩸 **Blood Request Information**

To request blood, you need to:
1. **Log in** to your account
2. Navigate to the **Blood Request** section
3. Fill out the request form with required details
4. Submit your request for review

Our team will process your request as soon as possible.

🚨 **For Emergency Requests:**
Please call your nearest donation center directly.

🔒 *Please log in to submit a blood request.*"""
        
        if role == 'patient':
            from patient.models import BloodRequest
            active = BloodRequest.objects.filter(
                request_by_patient=user.patient,
                status__in=['pending', 'approved']
            ).first()
            
            if active:
                return f"""🩸 **Your Blood Request Status**

You have an active blood request:

• **Blood Group:** {active.bloodgroup}
• **Units:** {active.unit}ml
• **Status:** {active.status.title()}
• **Submitted:** {active.date.strftime('%b %d, %Y')}
• **Center:** {active.donation_center.name if active.donation_center else 'N/A'}

{f"• **Urgency:** {active.urgency_level}" if hasattr(active, 'urgency_level') else ''}

⏳ *Our team is working on your request. You'll be notified of any updates.*"""
            
            return """🩸 **Request Blood**

To request blood:

1. Go to your dashboard
2. Click **"Request Blood"**
3. Fill in the required information:
   • Patient details
   • Blood group needed
   • Number of units
   • Urgency level
4. Submit for approval

📋 *You can track your request status in your dashboard.*

🚨 **Emergency?** Call your nearest center directly."""
        
        elif role == 'donor':
            return """🩸 **Donor Blood Request**

As a donor, you can request blood on behalf of a patient:

1. Navigate to **"Make Request"** in your dashboard
2. Provide patient information
3. Specify blood group and units needed
4. Select a donation center
5. Submit the request

💡 *This feature allows you to help friends or family members who need blood.*"""
        
        return """🩸 **Blood Request Process**

**To request blood:**
1. Log in to your account
2. Go to the Blood Request section
3. Fill out the request form
4. Submit for review

**Required Information:**
• Patient details (name, age, contact)
• Blood group needed
• Number of units required
• Medical reason
• Urgency level

🚨 **For emergencies, contact your nearest donation center directly.**"""
    
    # === STOCK INFO (Nurse-specific) ===
    elif intent_type == 'stock_info':
        if role != 'nurse':
            # Generic stock info for non-nurses
            stock_info = context_data.get('stock_info', [])
            if not stock_info:
                return "Stock information is currently unavailable."
            
            response = "🩸 **Current Blood Stock Levels**\n\n"
            for item in stock_info:
                bg = item.get('bloodgroup', 'Unknown')
                units = item.get('total_units', 0)
                status = "⚠️" if units < 1000 else "✅"
                response += f"{status} **{bg}:** {units:,}ml\n"
            
            return response
        
        # Detailed stock info for nurses
        if not user or not hasattr(user, 'nurse'):
            return "This information is only available to nursing staff."
        
        nurse = user.nurse
        if not nurse.donation_center:
            return "⚠️ You are not assigned to a donation center."
        
        info = BloodDonationKnowledgeBase.get_nurse_specific_info(nurse)
        
        response = f"🩸 **Blood Stock at {nurse.donation_center.name}**\n\n"
        
        if info.get('center_stock'):
            for bg, units in sorted(info['center_stock'].items()):
                if units < 500:
                    status = "🚨 CRITICAL"
                elif units < 1000:
                    status = "⚠️ LOW"
                else:
                    status = "✅ GOOD"
                
                response += f"{status} **{bg}:** {units:,}ml\n"
        else:
            response += "No stock information available.\n"
        
        if info.get('critical_stock'):
            response += "\n🚨 **Critical Stock Alerts:**\n"
            for item in info['critical_stock']:
                response += f"  • {item}\n"
            response += "\n💡 *Consider requesting stock from other centers or encouraging donors.*"
        
        return response
    
    # === NURSE DUTIES ===
    elif intent_type == 'nurse_duties':
        if role != 'nurse':
            return "This information is specific to nursing staff."
        
        return """👩‍⚕️ **Your Nursing Responsibilities**

**Daily Tasks:**
• ✅ Review and approve pending appointments
• 🩸 Conduct donor health screenings
• 💉 Oversee blood donation procedures
• 📋 Update donation and request statuses
• 📊 Monitor blood stock levels
• 🔔 Respond to urgent requests

**Appointment Management:**
• Approve or reject donation appointments
• Complete blood donations and add to stock
• Process blood request appointments
• Deduct stock for fulfilled requests

**Stock Management:**
• Monitor blood inventory levels
• Alert for critical stock situations
• Request blood from other centers when needed
• Ensure proper stock rotation (FIFO)

**Patient Care:**
• Ensure donor safety and comfort
• Conduct pre-donation health checks
• Provide post-donation care instructions
• Handle adverse reactions professionally

💡 *Check your dashboard regularly for pending tasks and notifications.*"""
    
    # === POINTS AND REWARDS (Donor-specific) ===
    elif intent_type == 'points_rewards':
        if role != 'donor':
            return """🎖️ **Donor Rewards Program**

Our system rewards blood donors with points for each successful donation!

**Benefits for Donors:**
• Earn points for each donation
• Track your donation history
• Receive recognition for your contributions
• Build your donation legacy

🔒 *Log in as a donor to see your points and rewards!*"""
        
        if not user or not hasattr(user, 'donor'):
            return "Please log in to view your rewards."
        
        donor = user.donor
        points = donor.points
        total_donations = donor.total_donations
        
        # Calculate next milestone
        milestones = [10, 25, 50, 100, 200]
        next_milestone = next((m for m in milestones if m > total_donations), None)
        
        response = f"""🎖️ **Your Donor Rewards**

**Current Status:**
• **Total Points:** {points:,} ⭐
• **Total Donations:** {total_donations} 🩸
• **Points per Donation:** 10 ⭐

"""
        
        if next_milestone:
            donations_needed = next_milestone - total_donations
            response += f"""**Next Milestone:**
• **{next_milestone} Donations** ({donations_needed} more to go!)

"""
        
        response += """**How Points Work:**
• Earn 10 points for each successful donation
• Points accumulate with each donation
• Track your progress in your dashboard

**Benefits:**
• Recognition for your life-saving contributions
• Donation history tracking
• Priority scheduling (for regular donors)
• Certificate of appreciation

"""
        
        if total_donations >= 10:
            response += f"\n🌟 **Amazing!** You've made {total_donations} donations! You're a true life-saver!"
        elif total_donations >= 5:
            response += f"\n🎉 **Great job!** You've made {total_donations} donations! Keep up the excellent work!"
        elif total_donations >= 1:
            response += f"\n👏 **Thank you!** You've made {total_donations} donation(s)! Every donation saves lives!"
        else:
            response += "\n💪 **Get started!** Make your first donation and start earning points!"
        
        return response
    
    # === HELP ===
    elif intent_type == 'help':
        response = """📞 **Need Help?**

**Contact Options:**

📧 **Email Support:**
   support@blooddonation.ke

📞 **Hotline:**
   +254-XXX-XXXX (24/7)

🌐 **Resources:**
   • Visit our Help Center (in menu)
   • Check FAQs section
   • Read Health Tips
   • Browse Donor Resources

"""
        
        if role == 'donor':
            response += """**Quick Links for Donors:**
   • Donation eligibility checker
   • Schedule appointment
   • View donation history
   • Check points balance

"""
        elif role == 'nurse':
            response += """**Quick Links for Nurses:**
   • Manage appointments
   • Check blood stock
   • Process requests
   • View notifications

"""
        elif role == 'patient':
            response += """**Quick Links for Patients:**
   • Submit blood request
   • Track request status
   • View appointments
   • Find nearest center

"""
        
        response += "❓ **What specific information are you looking for?**"
        return response
    
    # === GENERAL QUERY (Fallback) ===
    return None


@csrf_exempt
@require_http_methods(["POST"])
def chatbot_api(request):
    """Main chatbot API endpoint with enhanced role-based responses"""
    try:
        data = json.loads(request.body)
        user_message = data.get("message", "").strip()
        session_id = data.get("session_id", "")
        
        if not user_message:
            return JsonResponse({"error": "No message provided"}, status=400)
        
        user = request.user if request.user.is_authenticated else None
        role = get_user_role(user)
        
        # Save user message to database
        if MODELS_AVAILABLE and session_id:
            try:
                conversation, created = ChatConversation.objects.get_or_create(
                    session_id=session_id,
                    defaults={'user': user}
                )
                ChatMessage.objects.create(
                    conversation=conversation,
                    message_type='user',
                    content=user_message
                )
            except Exception as db_error:
                print(f"Database error: {db_error}")
        
        # Classify intent and generate response
        reply = None
        intent_type = 'general_query'
        
        if KNOWLEDGE_BASE_AVAILABLE:
            intent = IntentClassifier.classify_intent(user_message)
            intent_type, intent_detail = intent
            context_data = BloodDonationKnowledgeBase.get_system_context()
            reply = generate_response(intent, context_data, user_message, user)
        
        # Fallback response
        if reply is None:
            if DEVELOPMENT_MODE:
                reply = f"""I understand you're asking: *"{user_message}"*

I'm here to help! Here's what I can assist you with:

{'**As a Donor:**' if role == 'donor' else '**As a Nurse:**' if role == 'nurse' else '**As a Patient:**' if role == 'patient' else '**General Information:**'}

"""
                if role == 'donor':
                    reply += """• Check your donation eligibility
• View your donation history and points
• Find nearby donation centers
• Schedule donation appointments
• Track your next eligible donation date"""
                elif role == 'nurse':
                    reply += """• View today's appointments
• Check blood stock levels
• Manage pending approvals
• Access critical stock alerts
• Review your schedule"""
                elif role == 'patient':
                    reply += """• Submit blood requests
• Track request status
• Find donation centers
• View appointment history"""
                else:
                    reply += """• Blood donation eligibility
• Donation center locations
• Blood type information
• Donation process
• Contact information"""
                
                reply += "\n\nPlease try rephrasing your question!"
            else:
                # Use AI if available (OpenAI integration)
                reply = "I apologize, but I'm having trouble processing your request. Please try asking about blood donation eligibility, centers, or stock information."
        
        # Save bot response
        if MODELS_AVAILABLE and session_id:
            try:
                ChatMessage.objects.create(
                    conversation=conversation,
                    message_type='bot',
                    content=reply,
                    intent=intent_type
                )
            except:
                pass
        
        return JsonResponse({
            "reply": reply,
            "intent": intent_type,
            "user_role": role,
            "session_id": session_id,
            "status": "success"
        })
        
    except json.JSONDecodeError as e:
        return JsonResponse({"error": "Invalid JSON format"}, status=400)
    except Exception as e:
        print(f"Chatbot Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": f"Server error: {str(e)}"}, status=500)