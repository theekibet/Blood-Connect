import os
import json
from datetime import datetime
from dotenv import load_dotenv
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404

try:
    from .models import ChatConversation, ChatMessage
    MODELS_AVAILABLE = True
except:
    MODELS_AVAILABLE = False

try:
    from .knowledge_base import BloodDonationKnowledgeBase, IntentClassifier, ResponseFormatter
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
    elif hasattr(user, 'phlebotomist'):
        return 'phlebotomist'
    elif hasattr(user, 'lab_tech_profile'):
        return 'lab_tech'
    elif hasattr(user, 'blood_bank_tech_profile'):
        return 'bb_tech'
    elif hasattr(user, 'hospitaluser'):
        return 'hospital'
    elif user.is_staff:
        return 'admin'
    
    return None


def generate_personalized_greeting(user, role):
    """Generate role-specific greeting with modern, friendly tone"""
    name = user.get_full_name().split()[0] if user and user.is_authenticated and user.get_full_name() else (user.username if user and user.is_authenticated else "there")
    
    greetings = {
        'donor': f"""👋 **Hey {name}!** Great to see you again!

🌟 **Your Donation Dashboard Assistant**

I'm here to help you with everything about your donation journey:

**📋 Quick Actions:**
• Check your **next eligible donation date**
• View your **donation history & points**
• Find **nearby donation centers**
• Schedule or manage **appointments**

**💡 Just ask me:**
> "When can I donate next?"
> "How many points do I have?"
> "Show my upcoming appointments"
> "Find donation centers near me"

What would you like to know today?""",
        
        'phlebotomist': f"""👋 **Hey {name}!** Ready to save lives today?

🩺 **Your Phlebotomist Dashboard Assistant**

I'll help you stay on top of your daily tasks:

**📊 Today's Snapshot:**
• Check your **appointment schedule**
• View **pending approvals**
• Monitor **center blood stock**
• Track **critical alerts**

**⚡ Quick Commands:**
> "Show my appointments for today"
> "What's pending my approval?"
> "How's our blood stock?"
> "Any critical alerts?"

How can I assist you today?""",
        
        'lab_tech': f"""🧪 **Hey {name}!** Welcome to the Lab!

🔬 **Your Lab Dashboard Assistant**

I'll help you manage your testing workflow:

**📋 Testing Overview:**
• Check **pending samples**
• View **recent test results**
• Track **blood group verifications**
• Monitor **test statistics**

**⚡ Quick Commands:**
> "How many samples pending?"
> "Show my recent tests"
> "Any unsafe results today?"
> "Blood group verification stats"

What would you like to check?""",
        
        'bb_tech': f"""🏥 **Hey {name}!** Blood Bank Operations!

📦 **Your Inventory Dashboard Assistant**

I'll help you manage the blood inventory:

**📊 Inventory Overview:**
• Check **current stock levels**
• View **pending hospital requests**
• Monitor **expiring blood**
• Track **recent transactions**

**⚡ Quick Commands:**
> "Show current stock levels"
> "Any critical shortages?"
> "Pending hospital requests?"
> "Blood expiring soon?"

How can I help with inventory?""",
        
        'hospital': f"""🏨 **Hey {name}!** Hospital Operations!

🩸 **Your Hospital Dashboard Assistant**

I'll help you manage blood requests:

**📋 Request Overview:**
• Check **request status**
• View **recent requests**
• Monitor **dispatched blood**
• Track **deliveries**

**⚡ Quick Commands:**
> "Status of my recent requests"
> "Any pending approvals?"
> "Show dispatched blood"
> "Check serving centre stock"

What would you like to know?""",
        
        'admin': f"""👨‍💼 **Welcome back, {name}!**

📊 **System Administration Assistant**

I'll help you monitor the entire system:

**📈 System Overview:**
• Total donors, staff, and hospitals
• Blood stock across all centers
• Pending approvals and requests
• System-wide statistics

**⚡ Quick Commands:**
> "Show system statistics"
> "How many pending approvals?"
> "Blood stock overview"
> "Recent activities"

How can I assist with system management?""",
        
        None: """👋 **Hello there!** Welcome to BloodConnect!

🩸 **Your Blood Donation Assistant**

I'm here to help you with all things blood donation:

**✨ I can help you with:**
• **Eligibility** - Who can donate blood?
• **Centers** - Find donation centers near you
• **Blood Types** - Information about different blood groups
• **Process** - How blood donation works
• **FAQs** - Common questions answered

**💬 Try asking:**
> "Am I eligible to donate blood?"
> "Find donation centers in Nairobi"
> "Tell me about O+ blood type"
> "How does the donation process work?"

🔒 **For personalized assistance, please log in!**

What would you like to know?"""
    }
    
    return greetings.get(role, greetings[None])


def generate_response(intent, context_data, user_message, user=None):
    """Generate contextual response based on intent, user role, and system data"""
    if not KNOWLEDGE_BASE_AVAILABLE:
        return None
    
    intent_type, intent_detail = intent
    role = get_user_role(user)
    formatter = ResponseFormatter()
    
    # ===== GREETING =====
    if intent_type == 'greeting':
        return generate_personalized_greeting(user, role)
    
    # ===== THANKS =====
    elif intent_type == 'thanks':
        responses = [
            "You're very welcome! 😊 Is there anything else I can help with?",
            "My pleasure! 🩸 Let me know if you need anything else!",
            "Happy to help! 💙 Any other questions?",
            "Anytime! 🙌 What else would you like to know?"
        ]
        import random
        return random.choice(responses)
    
    # ===== FAREWELL =====
    elif intent_type == 'farewell':
        if role == 'donor':
            return "👋 Take care! Remember, your next donation could save lives. See you soon!"
        elif role == 'phlebotomist':
            return "👋 Have a great shift saving lives! Come back if you need anything."
        else:
            return "👋 Goodbye! Feel free to come back anytime with more questions!"
    
    # ===== HELP =====
    elif intent_type == 'help':
        help_text = """📚 **Here's What I Can Help You With**

**For Everyone:**
• 🩸 Blood donation eligibility
• 🏥 Find donation centers
• 🔬 Blood type information
• 📋 Donation process
• ❓ Frequently asked questions

"""
        if role == 'donor':
            help_text += """
**For Donors:**
• 📅 Check your appointments
• 🎖️ View your donation history & points
• 📍 Find nearby centers
• ⏰ Next eligible donation date
• 📊 Your profile information
"""
        elif role == 'phlebotomist':
            help_text += """
**For Phlebotomists:**
• 📋 Today's appointments
• ✅ Pending approvals
• 🩸 Center blood stock
• ⚠️ Critical alerts
• 📅 Upcoming schedule
"""
        elif role == 'lab_tech':
            help_text += """
**For Lab Technologists:**
• 🧪 Pending blood samples
• 📊 Test results & statistics
• ✅ Blood group verifications
• 📈 Testing history
"""
        elif role == 'bb_tech':
            help_text += """
**For Blood Bank Technicians:**
• 📦 Current inventory levels
• 🏥 Hospital blood requests
• ⏳ Expiring blood alerts
• 📊 Stock transactions
"""
        elif role == 'hospital':
            help_text += """
**For Hospital Staff:**
• 📋 Blood request status
• 🚚 Dispatched blood tracking
• 🏨 Serving centre stock
• 📊 Request history
"""
        
        help_text += """
**💬 Just ask me in plain English!**

Example: "When can I donate next?" or "Show me pending approvals"

What would you like to know?"""
        return help_text
    
    # ===== SYSTEM STATISTICS =====
    elif intent_type == 'system_stats':
        stats = context_data
        
        if 'error' in stats:
            return "😕 Sorry, I'm having trouble retrieving system statistics right now. Please try again later."
        
        if intent_detail == 'donors':
            return f"""📊 **Donor Statistics**

🩸 **Total Donors:** {formatter.format_number(stats.get('total_donors', 0))}
✅ **Verified Blood Groups:** {formatter.format_number(stats.get('donors_with_verified_blood', 0))}
⏳ **Pending Eligibility:** {formatter.format_number(stats.get('donors_with_pending_eligibility', 0))}
🎖️ **Safe Donations:** {formatter.format_number(stats.get('safe_donations', 0))}
⚠️ **Unsafe Donations:** {formatter.format_number(stats.get('unsafe_donations', 0))}

{f"🌟 You're one of {formatter.format_number(stats.get('total_donors', 0))} amazing donors!" if role == 'donor' else ""}"""
        
        elif intent_detail == 'phlebotomists':
            return f"""📊 **Phlebotomy Staff Statistics**

👩‍⚕️ **Total Phlebotomists:** {formatter.format_number(stats.get('total_phlebotomists', 0))}
✅ **Approved:** {formatter.format_number(stats.get('approved_phlebotomists', 0))}
⏳ **Pending Approval:** {formatter.format_number(stats.get('pending_phlebotomists', 0))}
🏥 **Donation Centers:** {formatter.format_number(stats.get('total_centers', 0))}

{f"👋 You're part of our dedicated team of {formatter.format_number(stats.get('approved_phlebotomists', 0))} approved phlebotomists!" if role == 'phlebotomist' else ""}"""
        
        elif intent_detail == 'lab_techs':
            return f"""📊 **Laboratory Statistics**

🧪 **Lab Technologists:** {formatter.format_number(stats.get('total_lab_techs', 0))}
⏳ **Pending Blood Tests:** {formatter.format_number(stats.get('pending_blood_tests', 0))}
✅ **Safe Results:** {formatter.format_number(stats.get('safe_donations', 0))}
⚠️ **Unsafe Results:** {formatter.format_number(stats.get('unsafe_donations', 0))}"""
        
        elif intent_detail == 'hospitals':
            return f"""📊 **Hospital Statistics**

🏥 **Total Hospitals:** {formatter.format_number(stats.get('total_hospitals', 0))}
✅ **Verified Hospitals:** {formatter.format_number(stats.get('verified_hospitals', 0))}
👤 **Hospital Users:** {formatter.format_number(stats.get('total_hospital_users', 0))}
📋 **Active Requests:** {formatter.format_number(stats.get('active_requests', 0))}"""
        
        elif intent_detail == 'requests':
            return f"""📊 **Blood Request Statistics**

📋 **Active Requests:** {formatter.format_number(stats.get('active_requests', 0))}
⏳ **Pending:** {formatter.format_number(stats.get('pending_requests', 0))}
✅ **Approved:** {formatter.format_number(stats.get('approved_requests', 0))}
🚚 **Dispatched:** {formatter.format_number(stats.get('dispatched_requests', 0))}"""
        
        elif intent_detail == 'donations':
            return f"""📊 **Donation Statistics**

🩸 **Recent Donations (30 days):** {formatter.format_number(stats.get('recent_donations', 0))}
✅ **Tested Safe:** {formatter.format_number(stats.get('safe_donations', 0))}
⚠️ **Tested Unsafe:** {formatter.format_number(stats.get('unsafe_donations', 0))}
⏳ **Pending Tests:** {formatter.format_number(stats.get('pending_tests', 0))}"""
        
        elif intent_detail == 'tests':
            return f"""📊 **Testing Statistics**

🧪 **Pending Blood Tests:** {formatter.format_number(stats.get('pending_blood_tests', 0))}
✅ **Safe Donations:** {formatter.format_number(stats.get('safe_donations', 0))}
⚠️ **Unsafe Donations:** {formatter.format_number(stats.get('unsafe_donations', 0))}"""
        
        elif intent_detail == 'stock':
            stock_info = stats.get('stock_info', [])
            response = f"""📦 **Current Blood Stock Levels**

📊 **Total Available:** {formatter.format_number(stats.get('total_available_units', 0))} ml
📦 **Total Batches:** {formatter.format_number(stats.get('total_stock_batches', 0))}

"""
            for item in stock_info:
                bg = item['bloodgroup']
                units = item['total_units']
                status = "🚨" if units < 500 else "⚠️" if units < 1000 else "✅"
                response += f"{status} **{bg}:** {formatter.format_number(units)}ml ({item['batch_count']} batches)\n"
            
            if stats.get('critical_stock_count', 0) > 0:
                response += f"\n🚨 **Critical Alerts:** {stats['critical_stock_count']} blood types below 1000ml"
            
            if stats.get('expiring_soon', 0) > 0:
                response += f"\n⏳ **Expiring Soon:** {stats['expiring_soon']} batches within 7 days"
            
            return response
        
        else:  # general
            response = f"""📊 **System Overview - {stats.get('today', '')}**

👥 **Users:**
• Donors: {formatter.format_number(stats.get('total_donors', 0))}
• Phlebotomists: {formatter.format_number(stats.get('total_phlebotomists', 0))}
• Lab Techs: {formatter.format_number(stats.get('total_lab_techs', 0))}
• Blood Bank Techs: {formatter.format_number(stats.get('total_bb_techs', 0))}

🏥 **Hospitals:**
• Registered: {formatter.format_number(stats.get('total_hospitals', 0))}
• Verified: {formatter.format_number(stats.get('verified_hospitals', 0))}
• Active Requests: {formatter.format_number(stats.get('active_requests', 0))}

🩸 **Blood:**
• Available: {formatter.format_number(stats.get('total_available_units', 0))}ml
• Safe Donations: {formatter.format_number(stats.get('safe_donations', 0))}
• Pending Tests: {formatter.format_number(stats.get('pending_blood_tests', 0))}

"""
            if stats.get('recent_activities'):
                response += "\n**📌 Recent Activity:**\n"
                for activity in stats['recent_activities'][:3]:
                    time_ago = formatter.time_ago(activity['date'])
                    response += f"• {activity['description']} ({time_ago})\n"
            
            return response
    
    # ===== BLOOD GROUP INFORMATION =====
    elif intent_type == 'blood_group_info':
        blood_group = intent_detail
        info = BloodDonationKnowledgeBase.get_blood_group_info(blood_group)
        
        if 'error' in info:
            return f"😕 Sorry, I couldn't find information for blood group {blood_group}."
        
        emoji = formatter.blood_group_emoji(blood_group)
        
        response = f"""{emoji} **Blood Group {blood_group} Information**

📊 **Current Status:**
• **Available Stock:** {formatter.format_number(info.get('total_units', 0))}ml
• **Total Batches:** {info.get('total_batches', 0)}
• **Available at:** {info.get('centers_count', 0)} centers

🩸 **Donor Stats:**
• **Total Donors:** {formatter.format_number(info.get('total_donors', 0))}
• **Verified Donors:** {formatter.format_number(info.get('verified_donors', 0))}
• **Recent Donations (30d):** {info.get('recent_donations', 0)}

"""
        if info.get('centers_with_stock'):
            response += "**📍 Centers with Stock:**\n"
            for center in info['centers_with_stock'][:3]:
                response += f"• {center['name']}: {formatter.format_number(center['units'])}ml ({center['batches']} batches)\n"
        
        if info.get('pending_requests', 0) > 0:
            response += f"\n⚠️ **Pending Requests:** {info['pending_requests']} hospitals need this blood type"
        
        if info.get('expiring_batches', 0) > 0:
            response += f"\n⏳ **Expiring Soon:** {info['expiring_batches']} batches within 7 days"
        
        # Role-specific personalization
        if role == 'donor' and user and hasattr(user, 'donor'):
            if user.donor.bloodgroup == blood_group:
                if user.donor.bloodgroup_verified:
                    response += f"\n\n✅ **This is YOUR blood type!** It's been verified by our lab."
                else:
                    response += f"\n\n📝 **This is your blood type.** It will be verified on your first donation."
                
                if info.get('total_units', 0) < 500:
                    response += f"\n🌟 **Urgent need!** Your blood type is critically low. Please consider donating!"
        
        return response
    
    # ===== DONATION CENTERS =====
    elif intent_type == 'donation_centers':
        city = intent_detail
        info = BloodDonationKnowledgeBase.get_donation_centers_info(city)
        
        if 'error' in info:
            return "😕 Sorry, I couldn't retrieve donation center information."
        
        if not info.get('centers'):
            if city:
                return f"🏥 No donation centers found in {city.title()}. Try searching in another city or view all centers."
            else:
                return "🏥 No donation centers found in the system."
        
        response = f"""🏥 **Donation Centers"""
        if city:
            response += f" in {city.title()}"
        response += f"** ({info['total_centers']} total)\n\n"
        
        for center in info['centers'][:5]:
            response += f"""📍 **{center['name']}**
📮 {center['address']}
📞 {center['contact']}
🕒 {center['hours']}
🩸 **Stock:** {formatter.format_number(center['total_stock'])}ml ({center['stock_batches']} batches)
"""
            if center.get('stock_summary'):
                response += "   " + " | ".join(center['stock_summary'][:3]) + "\n"
            
            if center.get('has_critical_stock'):
                response += "   ⚠️ **Critical stock alert at this center**\n"
            
            response += "\n"
        
        if len(info['centers']) > 5:
            response += f"... and {len(info['centers']) - 5} more centers\n"
        
        # Role-specific additions
        if role == 'donor' and user and hasattr(user, 'donor'):
            response += "\n💡 **Tip:** You can schedule appointments at any of these centers through your dashboard!"
        elif role == 'phlebotomist' and user and hasattr(user, 'phlebotomist') and user.phlebotomist.center:
            response += f"\n🏥 **Your assigned center:** {user.phlebotomist.center.name}"
        
        return response
    
    # ===== ELIGIBILITY =====
    elif intent_type == 'eligibility':
        info = BloodDonationKnowledgeBase.get_eligibility_info()
        
        response = """✅ **Blood Donation Eligibility Guide**

**📋 Basic Requirements:**
"""
        response += f"• **Age:** {info['basic_requirements']['age']}\n"
        response += f"• **Weight:** {info['basic_requirements']['weight']}\n"
        response += f"• **Health:** {info['basic_requirements']['health']}\n"
        response += f"• **Interval:** {info['basic_requirements']['interval']}\n\n"
        
        response += """**⏳ Temporary Deferrals (Wait periods):**\n"""
        for item in info['temporary_deferrals'][:5]:
            response += f"• {item}\n"
        
        response += "\n**🚫 Permanent Disqualifications:**\n"
        for item in info['permanent_disqualifications'][:4]:
            response += f"• {item}\n"
        
        response += f"""
**💡 Tips for a Successful Donation:**
• {info['tips'][0]}
• {info['tips'][1]}
• {info['tips'][2]}

**⏱️ Time Needed:** {info['process']['total']}
"""
        
        # Personalized for donor
        if role == 'donor' and user and hasattr(user, 'donor'):
            donor = user.donor
            
            response += f"\n**👤 Your Status:**\n"
            response += f"• **Blood Group:** {donor.bloodgroup or 'Not set'} {'✅ Verified' if donor.bloodgroup_verified else '⏳ Pending verification'}\n"
            
            if donor.dob:
                response += f"• **Age:** {donor.age} years {'✅' if donor.age >= 16 else '❌ Under 16'}\n"
            
            if donor.days_until_next_donation() == 0:
                response += f"• **Eligibility:** ✅ **You can donate now!**\n"
                response += "• **Action:** Schedule your appointment today!"
            else:
                days = donor.days_until_next_donation()
                next_date = donor.next_eligible_donation_date()
                response += f"• **Next Eligible:** {next_date.strftime('%B %d, %Y')} ({days} days)\n"
        
        return response
    
    # ===== USER PROFILE =====
    elif intent_type == 'user_profile':
        if not user or not user.is_authenticated:
            return "🔒 **Please log in** to view your profile information. Your dashboard will show your personalized stats!"
        
        profile_type = intent_detail
        
        if profile_type == 'donor' and role == 'donor':
            info = BloodDonationKnowledgeBase.get_donor_specific_info(user.donor)
            
            if 'error' in info:
                return "😕 Sorry, I couldn't retrieve your profile information."
            
            response = f"""👤 **Your Donor Profile**

**{info['full_name']}** {'✅ Verified' if info['bloodgroup_verified'] else ''}

📋 **Personal:**
• **Blood Group:** {info['bloodgroup']} {formatter.blood_group_emoji(info['bloodgroup'])}
• **Member Since:** {info['member_since'].strftime('%B %Y')}
• **Location:** {info['county'] or 'Not set'}

🎖️ **Donation Stats:**
• **Total Donations:** {info['safe_donations']} safe donations
• **Total Volume:** {formatter.format_number(info['total_volume_ml'])}ml
• **Lives Impacted:** ~{formatter.format_number(info['lives_impacted'])} lives
• **Points Earned:** {formatter.format_number(info['points'])} ⭐

"""
            if info['can_donate_now']:
                response += "✅ **You're eligible to donate now!** Schedule your appointment today!\n\n"
            else:
                response += f"📅 **Next Eligible:** {info['next_eligible_donation']} ({info['days_until_eligible']} days)\n\n"
            
            # Milestone progress
            if info['milestones']['next']:
                progress = info['milestones']['progress']
                bar = formatter.progress_bar(info['milestones']['current'], info['milestones']['next'])
                response += f"**🏆 Next Milestone:** {info['milestones']['current']}/{info['milestones']['next']} donations\n"
                response += f"{bar}\n\n"
            
            # Recent donations
            if info['recent_donations']:
                response += "**📅 Recent Donations:**\n"
                for donation in info['recent_donations'][:3]:
                    emoji = formatter.status_emoji(donation['status'])
                    response += f"• {emoji} {donation['date']}: {donation['units']}ml {donation['bloodgroup']} at {donation['center']}\n"
            
            # Upcoming appointments
            if info['upcoming_appointments']:
                response += "\n**📋 Upcoming Appointments:**\n"
                for appt in info['upcoming_appointments']:
                    response += f"• {appt['date']} at {appt['time']} with {appt['phlebotomist']}\n"
            
            return response
        
        elif profile_type == 'phlebotomist' and role == 'phlebotomist':
            info = BloodDonationKnowledgeBase.get_phlebotomist_specific_info(user.phlebotomist)
            
            if 'error' in info:
                return "😕 Sorry, I couldn't retrieve your profile information."
            
            response = f"""👩‍⚕️ **Your Phlebotomist Profile**

**{info['full_name']}**
📋 {info['specialization'] or 'General Phlebotomist'}
🏥 **Center:** {info['center']}
✅ **Status:** {'Approved' if info['is_approved'] else 'Pending Approval'}

📊 **Today's Overview:**
• **Appointments Today:** {info['today_appointments']}
• **Pending Approvals:** {info['pending_appointments']}
• **Completed Today:** {info['completed_appointments']}

"""
            # Today's appointments
            if info['today_appointments_list']:
                response += "**⏰ Today's Schedule:**\n"
                for appt in info['today_appointments_list']:
                    emoji = formatter.status_emoji(appt['status'])
                    response += f"• {emoji} {appt['time']} - {appt['donor']} ({appt['donor_bloodgroup']})\n"
            
            # Center stock
            if info.get('center_stock'):
                response += "\n**🩸 Your Center's Stock:**\n"
                for bg, units in info['center_stock'].items():
                    status = "🚨" if units < 500 else "⚠️" if units < 1000 else "✅"
                    response += f"{status} {bg}: {formatter.format_number(units)}ml\n"
            
            # Critical alerts
            if info.get('critical_stock'):
                response += "\n⚠️ **Critical Alerts:**\n"
                for alert in info['critical_stock'][:3]:
                    response += f"• {alert}\n"
            
            return response
        
        elif profile_type == 'lab_tech' and role == 'lab_tech':
            info = BloodDonationKnowledgeBase.get_lab_tech_specific_info(user.lab_tech_profile)
            
            if 'error' in info:
                return "😕 Sorry, I couldn't retrieve your profile information."
            
            response = f"""🧪 **Your Lab Technologist Profile**

**{info['full_name']}**
🔬 {info['specialization'] or 'General Lab Tech'}
🏥 **Center:** {info['center']}

📊 **Testing Statistics:**
• **Total Tests:** {info['total_tests']}
• **Tests Today:** {info['tests_today']}
• **Safe Results:** {info['safe_tests']} ✅
• **Unsafe Results:** {info['unsafe_tests']} ⚠️
• **Donors Verified:** {info['donors_verified']}

"""
            if info.get('pending_count', 0) > 0:
                response += f"⏳ **Pending Samples:** {info['pending_count']} awaiting testing\n\n"
                
                if info.get('pending_blood_samples'):
                    response += "**Recent Pending Samples:**\n"
                    for sample in info['pending_blood_samples'][:3]:
                        response += f"• {sample['donor']} - {sample['bloodgroup']} ({sample['collection_date']})\n"
            
            return response
        
        elif profile_type == 'bb_tech' and role == 'bb_tech':
            info = BloodDonationKnowledgeBase.get_bb_tech_specific_info(user.blood_bank_tech_profile)
            
            if 'error' in info:
                return "😕 Sorry, I couldn't retrieve your profile information."
            
            response = f"""📦 **Your Blood Bank Technician Profile**

**{info['full_name']}**
🏥 **Center:** {info['center']}

📊 **Inventory Overview:**
• **Safe Stock:** {info.get('total_safe_units', 0)} batches ({formatter.format_number(info.get('total_safe_volume', 0))}ml)
• **Pending Verification:** {info.get('pending_verification_units', 0)} batches
• **Unsafe/Quarantined:** {info.get('unsafe_units', 0)} batches
• **Expiring Soon:** {info.get('expiring_soon_units', 0)} batches

"""
            if info.get('critical_alerts'):
                response += "🚨 **Critical Stock Alerts:**\n"
                for alert in info['critical_alerts'][:3]:
                    response += f"• {alert}\n"
            
            if info.get('pending_hospital_requests', 0) > 0:
                response += f"\n📋 **Pending Hospital Requests:** {info['pending_hospital_requests']}\n"
                if info.get('pending_requests_detail'):
                    for req in info['pending_requests_detail'][:2]:
                        emoji = formatter.urgency_emoji(req['urgency'])
                        response += f"• {emoji} {req['hospital']}: {req['units']}ml {req['blood_group']} for {req['patient']}\n"
            
            return response
        
        elif profile_type == 'hospital' and role == 'hospital':
            info = BloodDonationKnowledgeBase.get_hospital_specific_info(user.hospitaluser)
            
            if 'error' in info:
                return "😕 Sorry, I couldn't retrieve your profile information."
            
            response = f"""🏨 **Your Hospital Profile**

**{info['full_name']}**
👤 **Role:** {info['role']}
🏥 **Hospital:** {info['hospital']['name']}
✅ **Verified:** {'Yes' if info['hospital']['verified'] else 'No - Pending Verification'}

📊 **Request Statistics:**
• **Total Requests:** {info['total_requests']}
• **Pending:** {info['pending_requests']} ⏳
• **Approved:** {info['approved_requests']} ✅
• **Dispatched:** {info['dispatched_requests']} 🚚
• **Delivered:** {info['delivered_requests']} 📦

"""
            if info.get('recent_requests'):
                response += "**📋 Recent Requests:**\n"
                for req in info['recent_requests'][:3]:
                    emoji = req['status_emoji']
                    response += f"• {emoji} {req['request_number']}: {req['units']}ml {req['blood_group']} ({req['status']})\n"
            
            if info.get('centre_stock'):
                response += "\n**🩸 Serving Centre Stock:**\n"
                for bg, units in list(info['centre_stock'].items())[:5]:
                    response += f"• {bg}: {formatter.format_number(units)}ml\n"
            
            return response
        
        return "Profile information not available for your role."
    
    # ===== APPOINTMENTS =====
    elif intent_type == 'appointments':
        if not user or not user.is_authenticated:
            return "🔒 **Please log in** to view your appointments. You can schedule donations through your dashboard!"
        
        if role == 'donor':
            info = BloodDonationKnowledgeBase.get_donor_specific_info(user.donor)
            
            if info.get('upcoming_appointments'):
                response = "📅 **Your Upcoming Appointments**\n\n"
                for appt in info['upcoming_appointments']:
                    emoji = formatter.status_emoji(appt['status'])
                    response += f"{emoji} **{appt['date']} at {appt['time']}**\n"
                    response += f"   • Location: {appt['center']}\n"
                    response += f"   • Phlebotomist: {appt['phlebotomist']}\n"
                    response += f"   • Status: {appt['status'].title()}\n\n"
                
                response += "💡 **Need to reschedule?** You can manage appointments in your dashboard."
                return response
            else:
                if info['can_donate_now']:
                    return "📅 You don't have any upcoming appointments. **You're eligible to donate now!** Schedule one through your dashboard today! 🩸"
                else:
                    return f"📅 You don't have any upcoming appointments. Your next eligible donation date is {info['next_eligible_donation']}."
        
        elif role == 'phlebotomist':
            info = BloodDonationKnowledgeBase.get_phlebotomist_specific_info(user.phlebotomist)
            
            response = f"""📅 **Appointment Overview**

**Today ({info['today_appointments']} appointments):**
"""
            if info['today_appointments_list']:
                for appt in info['today_appointments_list']:
                    emoji = formatter.status_emoji(appt['status'])
                    response += f"• {emoji} {appt['time']} - {appt['donor']} ({appt['donor_bloodgroup']}) - {appt['status']}\n"
            else:
                response += "• No appointments scheduled for today\n"
            
            response += f"\n**Pending Approvals:** {info['pending_appointments']}\n"
            
            if info.get('upcoming_appointments'):
                response += "\n**Upcoming (Next 7 days):**\n"
                for appt in info['upcoming_appointments'][:3]:
                    response += f"• {appt['date']} at {appt['time']} - {appt['donor']}\n"
            
            return response
        
        return "Appointment information not available for your role."
    
    # ===== DONATION PROCESS =====
    elif intent_type == 'donation_process':
        info = BloodDonationKnowledgeBase.get_eligibility_info()
        
        response = """🩸 **Blood Donation Process: Your Step-by-Step Guide**

**Step 1️⃣: Before You Donate**
• Check eligibility (I can help with that!)
• Drink plenty of water
• Eat a healthy meal (iron-rich foods)
• Get good sleep (5-6 hours minimum)

**Step 2️⃣: Registration** ({})
• Complete donor form
• Show valid ID
• Provide medical history

**Step 3️⃣: Health Screening** ({})
• Quick health check
• Blood pressure, pulse, temperature
• Hemoglobin test (finger prick)
• Confidential interview

**Step 4️⃣: The Donation** ({})
• Comfortable reclining chair
• Clean, sterile equipment
• Actually takes 8-10 minutes
• About 450ml of blood collected

**Step 5️⃣: Refresh & Rest** ({})
• Rest for 10-15 minutes
• Enjoy snacks and drinks
• Receive donor card/points
• Schedule next donation

**⏱️ Total Time:** {} (donation itself is quick!)

""".format(
    info['process']['registration'],
    info['process']['health_check'],
    info['process']['donation'],
    info['process']['rest'],
    info['process']['total']
)
        
        response += """**💡 Pro Tips:**
• Wear comfortable clothing with sleeves that roll up
• Bring a friend for your first time
• Let staff know if you feel nervous
• Stay hydrated after donating

**After Donation:**
• Keep bandage on for several hours
• Avoid strenuous exercise for 24 hours
• Drink extra fluids for 2 days
• Eat iron-rich foods

"""
        
        if role == 'donor' and user and hasattr(user, 'donor'):
            if user.donor.days_until_next_donation() == 0:
                response += "✅ **You're eligible to donate now!** Ready to schedule your appointment?"
        
        return response
    
    # ===== BLOOD REQUEST =====
    elif intent_type == 'blood_request':
        if not user or not user.is_authenticated:
            return """🩸 **Blood Request Information**

To request blood for a patient:

1️⃣ **Hospital staff must log in** with their hospital credentials
2️⃣ Navigate to **Blood Requests** section
3️⃣ Click **"New Request"**
4️⃣ Fill in:
   • Patient details (name, age, ID)
   • Blood group needed
   • Units required
   • Urgency level
   • Doctor's information
5️⃣ Submit for approval

🚨 **For Emergency Requests:**
Call your nearest donation center immediately!

🔒 *Please log in with your hospital account to submit requests.*"""
        
        elif role in ['phlebotomist', 'bb_tech', 'hospital']:
            if role == 'hospital':
                info = BloodDonationKnowledgeBase.get_hospital_specific_info(user.hospitaluser)
                
                response = f"""🏥 **Blood Request Portal**

📋 **To create a new request:**
1. Go to **"Blood Requests"** in your dashboard
2. Click **"New Request"**
3. Fill in patient information:
   • Full name, age, gender
   • Blood group and units needed
   • Urgency level
   • Doctor's name and license
4. Submit for processing

**Your Recent Activity:**
• **Pending:** {info['pending_requests']} requests
• **Approved:** {info['approved_requests']} requests
• **Dispatched:** {info['dispatched_requests']} requests

"""
                if info.get('recent_requests'):
                    response += "**Recent Requests:**\n"
                    for req in info['recent_requests'][:3]:
                        emoji = req['status_emoji']
                        response += f"• {emoji} {req['request_number']}: {req['units']}ml {req['blood_group']} - {req['status']}\n"
                
                return response
            
            elif role == 'bb_tech':
                info = BloodDonationKnowledgeBase.get_bb_tech_specific_info(user.blood_bank_tech_profile)
                
                response = f"""📦 **Blood Request Management**

📋 **Pending Hospital Requests:** {info.get('pending_hospital_requests', 0)}

"""
                if info.get('pending_requests_detail'):
                    response += "**Requests Needing Attention:**\n"
                    for req in info['pending_requests_detail']:
                        emoji = formatter.urgency_emoji(req['urgency'])
                        response += f"• {emoji} {req['hospital']}: {req['units']}ml {req['blood_group']} for {req['patient']} ({req['urgency']})\n"
                    
                    response += "\n**To process:** Go to 'Hospital Requests' in your dashboard"
                
                return response
            
            elif role == 'phlebotomist':
                return """🩸 **Blood Requests for Phlebotomists**

As a phlebotomist, you can view but not approve blood requests - that's handled by Blood Bank Technicians.

**What you can do:**
• View request status
• Check available stock
• Prepare for collection when approved

**To see requests:** Navigate to **"Blood Requests"** in your dashboard."""
        
        return "Blood request information not available for your role."
    
    # ===== TESTING PROCESS =====
    elif intent_type == 'testing_process':
        response = """🧪 **Blood Testing Process**

**How donated blood is tested:**

**Step 1: Collection** 📦
• Phlebotomist collects blood sample
• Sample labeled with unique barcode
• Sent to lab for testing

**Step 2: Blood Typing** 🩸
• Determine ABO group (A, B, AB, O)
• Determine Rh factor (+ or -)
• **First-time donors:** Blood group permanently verified

**Step 3: Disease Screening** 🔬
• HIV (1 & 2)
• Hepatitis B & C
• Syphilis
• Malaria
• Other region-specific tests

**Step 4: Results** 📊
• **Safe:** Blood added to inventory ✅
• **Unsafe:** Blood quarantined and discarded ⚠️

**Step 5: Notification** 📱
• Donor notified of results
• Safe blood available for patients
• Unsafe donors contacted confidentially

**⏱️ Timeline:** Results typically available in 24-48 hours

**💡 Important:** All testing is confidential and follows strict safety protocols."""
        
        if role == 'lab_tech':
            response += "\n\n🔬 **As a Lab Tech:** You play a crucial role in this process! Check your dashboard for pending samples."
        
        return response
    
    # ===== POINTS AND REWARDS =====
    elif intent_type == 'points_rewards':
        if role != 'donor':
            return """🎖️ **Donor Rewards Program**

Our donors earn points for every successful donation!

**How it works:**
• **10 points** for each safe donation
• Points accumulate with each donation
• Track your progress in your dashboard
• Special recognition at milestones

**Milestones:**
• 1 donation: First-time donor 🎉
• 5 donations: Bronze donor 🥉
• 10 donations: Silver donor 🥈
• 25 donations: Gold donor 🥇
• 50+ donations: Platinum donor 💎

🔒 **Log in as a donor to see your points!**"""
        
        if not user or not hasattr(user, 'donor'):
            return "Please log in to view your rewards."
        
        donor = user.donor
        info = BloodDonationKnowledgeBase.get_donor_specific_info(donor)
        
        total = info['safe_donations']
        points = info['points']
        
        # Determine badge
        if total >= 50:
            badge = "💎 **Platinum Donor**"
        elif total >= 25:
            badge = "🥇 **Gold Donor**"
        elif total >= 10:
            badge = "🥈 **Silver Donor**"
        elif total >= 5:
            badge = "🥉 **Bronze Donor**"
        elif total >= 1:
            badge = "🎉 **First-Time Donor**"
        else:
            badge = "🌟 **Ready to Start**"
        
        response = f"""🎖️ **Your Donor Rewards**

**{badge}**

📊 **Your Stats:**
• **Total Donations:** {total} safe donations
• **Points Earned:** {points} ⭐
• **Lives Impacted:** ~{info['lives_impacted']} lives

**Points Breakdown:**
• Each safe donation = 10 points
• Total from donations: {total * 10} points
• **Current balance:** {points} points

"""
        # Milestone progress
        if info['milestones']['next']:
            progress = info['milestones']['progress']
            bar = formatter.progress_bar(info['milestones']['current'], info['milestones']['next'])
            response += f"**🏆 Next Milestone:** {info['milestones']['current']}/{info['milestones']['next']} donations\n"
            response += f"{bar}\n\n"
        
        response += """**Benefits:**
• Recognition for your life-saving contributions
• Priority scheduling for regular donors
• Certificate of appreciation at milestones
• Satisfaction of saving lives! 💙

"""
        
        if total == 0:
            response += "🌟 **Ready to start your journey?** Schedule your first donation today!"
        elif total >= 10:
            response += f"🎊 **Amazing!** You're a true hero with {total} donations!"
        
        return response
    
    # ===== CONTACT =====
    elif intent_type == 'contact':
        return """📞 **Contact Information**

**Need help? Reach out to us!**

📧 **Email Support:**
support@bloodconnect.ke
(Response within 24 hours)

📞 **Phone Support:**
+254 700 123 456
Mon-Fri: 8:00 AM - 8:00 PM
Sat-Sun: 9:00 AM - 5:00 PM

📍 **Head Office:**
BloodConnect Kenya
Nairobi, Kenya

🚨 **Emergency Blood Requests:**
Call your nearest donation center directly

💬 **Live Chat:**
Available on our website during business hours

**For urgent matters, please call instead of email.**"""
    
    # ===== FAQ =====
    elif intent_type == 'faq':
        return """❓ **Frequently Asked Questions**

**Q: Who can donate blood?**
A: Generally, healthy individuals aged 16-65 weighing at least 50kg. See eligibility for details.

**Q: How often can I donate?**
A: Every 56 days (8 weeks) for whole blood donation.

**Q: Is donating blood safe?**
A: Yes! Sterile equipment is used once and discarded. You cannot get diseases from donating.

**Q: How long does it take?**
A: About 45-60 minutes total, with donation itself taking 8-10 minutes.

**Q: Will it hurt?**
A: You may feel a quick pinch, but most donors feel fine. Our phlebotomists are experts!

**Q: What should I eat before donating?**
A: Iron-rich foods like spinach, red meat, beans. Avoid fatty foods.

**Q: Can I donate if I have a cold?**
A: No, wait until you're fully recovered and off medication.

**Q: How will I know my blood type?**
A: You'll be notified after your first donation when lab testing is complete.

**Q: What happens to my blood?**
A: It's tested, processed, and used for patients in need - surgeries, emergencies, chronic conditions.

**Q: Can I get tested for diseases?**
A: Donation includes disease screening, but don't donate just for testing - use health facilities.

**Need more details? Ask me about:**
• Eligibility criteria
• Donation process
• Blood types
• Specific concerns"""
    
    # ===== WEATHER (fun feature) =====
    elif intent_type == 'weather':
        import datetime
        now = datetime.datetime.now()
        
        # You could integrate a real weather API here
        # For now, provide a fun response
        responses = [
            "☀️ It's a beautiful day to save lives! Perfect for donating blood.",
            "🌧️ Rainy days are great for staying in, but hospitals still need blood! Consider donating if it's safe to travel.",
            "⛅ Whatever the weather, someone needs blood today. You can make a difference!",
            f"Today's forecast: {now.strftime('%A, %B %d')} - Perfect weather for being a hero! 🦸"
        ]
        import random
        return random.choice(responses)
    
    # ===== TIME =====
    elif intent_type == 'time':
        now = timezone.now()
        return f"🕒 It's **{now.strftime('%I:%M %p')}** on **{now.strftime('%A, %B %d, %Y')}**.\n\nHow can I help you today?"
    
    # ===== GENERAL QUERY (Fallback) =====
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
        
        # Get authenticated user if any
        user = request.user if request.user.is_authenticated else None
        role = get_user_role(user)
        
        # Save user message to database if models available
        conversation = None
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
        
        # Classify intent
        intent_type = 'general_query'
        intent_detail = None
        reply = None
        
        if KNOWLEDGE_BASE_AVAILABLE:
            intent = IntentClassifier.classify_intent(user_message)
            intent_type, intent_detail = intent
            
            # Get system context
            context_data = BloodDonationKnowledgeBase.get_system_context()
            
            # Generate response
            reply = generate_response(intent, context_data, user_message, user)
        
        # Fallback response if no reply generated
        if reply is None:
            if DEVELOPMENT_MODE:
                reply = f"""🤔 **I'm not sure I understood that.**

I'm still learning, but I can help you with:

**General Information:**
• Blood donation eligibility
• Donation center locations
• Blood type information
• Donation process
• FAQs

"""
                if role:
                    reply += f"\n**As a {role.replace('_', ' ').title()}:**\n"
                    reply += "• Check your dashboard for personalized info\n"
                    reply += "• Try asking about your appointments or tasks\n"
                
                reply += "\n💡 **Try rephrasing your question or ask about something specific!**"
            else:
                # More helpful fallback
                reply = """🤔 **I'm here to help!**

You can ask me about:
• 🩸 Blood donation eligibility ("Can I donate?")
• 🏥 Donation centers ("Find centers in Nairobi")
• 🩸 Blood types ("Tell me about O+ blood")
• 📋 Donation process ("How does donation work?")
• ❓ FAQs ("Common questions")

**For personalized info, please log in and ask about:**
• Your appointments
• Donation history
• Points and rewards
• Pending tasks

What would you like to know?"""
        
        # Save bot response
        if MODELS_AVAILABLE and conversation:
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
            "intent_detail": intent_detail,
            "user_role": role,
            "is_authenticated": user is not None,
            "session_id": session_id,
            "status": "success",
            "timestamp": timezone.now().isoformat()
        })
        
    except json.JSONDecodeError as e:
        return JsonResponse({"error": "Invalid JSON format"}, status=400)
    except Exception as e:
        print(f"Chatbot Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            "error": f"Server error: {str(e)}",
            "reply": "😕 Sorry, I'm having technical difficulties. Please try again in a moment."
        }, status=500)


@login_required
@require_http_methods(["GET"])
def chatbot_history(request):
    """Get chat history for authenticated user"""
    if not MODELS_AVAILABLE:
        return JsonResponse({"error": "Chat history not available"}, status=404)
    
    try:
        # Get user's conversations
        conversations = ChatConversation.objects.filter(
            user=request.user
        ).order_by('-updated_at')[:5]
        
        history = []
        for conv in conversations:
            messages = ChatMessage.objects.filter(
                conversation=conv
            ).order_by('created_at')[:10]
            
            history.append({
                'id': conv.id,
                'started_at': conv.created_at.isoformat(),
                'last_message': conv.updated_at.isoformat(),
                'message_count': conv.messages.count(),
                'preview': conv.messages.filter(message_type='user').last().content[:100] if conv.messages.filter(message_type='user').exists() else None
            })
        
        return JsonResponse({
            'conversations': history
        })
        
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)