import os
import requests
from dotenv import load_dotenv

# Load your Kapso API key from the .env file
load_dotenv()
KAPSO_API_KEY = os.getenv("KAPSO_API_KEY")

# ⚠️ Your number with the '+' is correct!
CUSTOMER_PHONE = "+918660855203"  

def send_promo_blast():
    url = "https://app.kapso.ai/api/v1/whatsapp_messages" 
    
    headers = {
        "X-API-Key": KAPSO_API_KEY,
        "Content-Type": "application/json"
    }
    
    # The Cult Gym style Hook
    promo_text = (
        "Hey Champ! 🏋️‍♂️\n\n"
        "Not everyone sticks to their resolutions... but you did. 💪\n"
        "Crush your summer goals in fresh fits. Enjoy an additional 15% off in-store! 🛍️\n\n"
        "Reply *YES* to see what's in stock, or tell me what you're looking for!"
    )
    
    # We are back to a standard "text" payload
    payload = {
        "message": {
            "phone_number": CUSTOMER_PHONE,
            "content": promo_text,
            "message_type": "text"
        }
    }
    
    print("🚀 Firing promo blast...")
    response = requests.post(url, headers=headers, json=payload)
    
    if response.status_code in [200, 201]:
        print("✅ PROMO BLAST SENT SUCCESSFULLY! Check your phone.")
    else:
        print(f"❌ Error {response.status_code}: {response.text}")

if __name__ == "__main__":
    send_promo_blast()