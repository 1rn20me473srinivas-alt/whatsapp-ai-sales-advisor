import os
import json
import httpx
from fastapi import FastAPI, Request, HTTPException
from groq import Groq
from dotenv import load_dotenv

# 1. Load Secrets
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
KAPSO_API_KEY = os.getenv("KAPSO_API_KEY")

# 2. Initialize App
app = FastAPI(title="WhatsApp Sales Wingman")
groq_client = Groq(api_key=GROQ_API_KEY)

# 3. Load 6-Product Database
with open("data/inventory.json", "r") as file:
    INVENTORY_DB = json.load(file)

# 4. The Function to send messages OUT to WhatsApp via Kapso
async def send_whatsapp_message(phone_number: str, text: str):
    url = "https://app.kapso.ai/api/v1/whatsapp_messages"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": KAPSO_API_KEY
    }
    payload = {
        "message": {
            "phone_number": phone_number,
            "content": text,
            "message_type": "text"
        }
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code in [200, 201]:
            print(f"✅ MESSAGE SENT SUCCESSFULLY TO {phone_number}")
        else:
            print(f"❌ KAPSO ERROR: {response.text}")

# 5. The Webhook to receive messages IN from WhatsApp
@app.post("/webhook/kapso")
async def kapso_webhook(request: Request):
    # Capture the raw webhook payload from Kapso
    payload = await request.json()
    
    # Extract the message block securely
    msg_block = payload.get("message", {})
    
    # Ignore the AI's own outgoing messages (so it doesn't talk to itself)
    direction = msg_block.get("kapso", {}).get("direction") or msg_block.get("direction")
    if direction == "outbound":
        return {"status": "ignored", "reason": "outbound message"}

    # Extract the actual text and phone number
    message_text = msg_block.get("content") or msg_block.get("text", {}).get("body", "")
    sender_phone = msg_block.get("phone_number") or msg_block.get("from") or payload.get("conversation", {}).get("phone_number")

    # If it's a blank message or just a status update (like a read receipt), ignore it
    if not message_text or not sender_phone:
        return {"status": "ignored"}

    print(f"\n💬 CUSTOMER SAID: {message_text}")

    # The AI Brain Rules
    system_prompt = f"""
    You are an expert retail sales advisor replying on WhatsApp.
    Analyze the customer's message, identify their exact problem, and recommend the best product.

    INVENTORY:
    {json.dumps(INVENTORY_DB)}

    RULES:
    1. Identify the core problem.
    2. Pick the SINGLE best product that solves it.
    3. Output the response formatted beautifully for WhatsApp (use * for bolding, use emojis).
    4. Keep it short and punchy. Include a past customer review if one exists.
    
    Return ONLY valid JSON in this exact format:
    {{
        "whatsapp_reply": "The complete text message to send"
    }}
    """

    try:
        # Ask Groq what to say
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"CUSTOMER MESSAGE: {message_text}"}
            ],
            response_format={"type": "json_object"}
        )
        
        # Parse the AI response
        ai_data = json.loads(response.choices[0].message.content)
        final_message = ai_data["whatsapp_reply"]
        
        print(f"🤖 AI RECOMMENDS:\n{final_message}")

        # Send it back to WhatsApp!
        await send_whatsapp_message(sender_phone, final_message)
        
        return {"status": "success"}

    except Exception as e:
        print(f"❌ AI ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))