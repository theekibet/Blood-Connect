import os
from dotenv import load_dotenv
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

# Load environment variables
load_dotenv()

# Check if we're in development mode
DEVELOPMENT_MODE = os.getenv("DEVELOPMENT_MODE", "true").lower() == "true"

if not DEVELOPMENT_MODE:
    import openai
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set in environment.")
    client = openai.OpenAI(api_key=api_key)


@csrf_exempt
def chatbot_api(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_message = data.get("message", "").strip()
            if not user_message:
                return JsonResponse({"error": "No message provided"}, status=400)

            # FAQ check (simplified)
            FAQS = {
                "who can donate blood?": "Anyone aged 16-65, weighing at least 50kg, and in good health can donate blood in Kenya.",
                # ... more FAQs ...
            }
            if user_message.lower() in FAQS:
                reply = FAQS[user_message.lower()]
            else:
                system_prompt = (
                    "You are a helpful assistant for a blood donation website in Kenya. "
                    "Answer questions about blood donation, eligibility, appointments, and safety. "
                    "If you don't know the answer, direct the user to contact support."
                )
                if DEVELOPMENT_MODE:
                    reply = f"You said...'{user_message}'. (This is a mock reply to your query)"
                else:
                    response = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message}
                        ]
                    )
                    reply = response.choices[0].message.content

            return JsonResponse({"reply": reply})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    return JsonResponse({"error": "Invalid request method"}, status=400)
