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

app = FastAPI(title="WhatsApp Sales Wingman (Text Only MVP)")
groq_client = Groq(api_key=GROQ_API_KEY)

# Load the inventory database
with open("data/inventory.json", "r") as file:
    INVENTORY_DB = json.load(file)

# 2. Outbound Messaging Function (Standard Text)
async def send_whatsapp_text(phone_number: str, text: str):
    url = "https://app.kapso.ai/api/v1/whatsapp_messages"
    headers = {"Content-Type": "application/json", "X-API-Key": KAPSO_API_KEY}
    
    payload = {
        "message": {
            "phone_number": phone_number,
            "message_type": "text",
            "content": text
        }
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code in [200, 201]:
            print(f"✅ TEXT SENT SUCCESSFULLY TO {phone_number}")
        else:
            print(f"\n❌ KAPSO REJECTED THE MESSAGE: {response.text}\n")

# 3. The Webhook
@app.post("/webhook/kapso")
async def kapso_webhook(request: Request):
    payload = await request.json()
    msg_block = payload.get("message", {})
    
    # Ignore our own outbound messages to prevent infinite loops (and allow human takeover)
    direction = msg_block.get("kapso", {}).get("direction") or msg_block.get("direction")
    if direction == "outbound":
        return {"status": "ignored"}

    sender_phone = msg_block.get("phone_number") or msg_block.get("from") or payload.get("conversation", {}).get("phone_number")
    msg_type = msg_block.get("type")
    
    # 🎤 Extract Text: Handle BOTH Voice Notes and Text Messages
    if msg_type == "audio":
        message_text = msg_block.get("kapso", {}).get("transcript", {}).get("text", "")
        print(f"\n🎧 VOICE NOTE RECEIVED. Transcript: '{message_text}'")
    else:
        message_text = msg_block.get("content") or msg_block.get("text", {}).get("body", "")

    if not message_text or not sender_phone:
        return {"status": "ignored"}

    print(f"\n💬 PROCESSING MESSAGE: {message_text}")

    # Updated AI Brain instructions: English only, emojis, and WhatsApp Markdown
    system_prompt = f"""
    You are an expert retail sales advisor replying on WhatsApp.
    Analyze the customer's message, identify their problem, and recommend the best product.

    INVENTORY: {json.dumps(INVENTORY_DB)}

    RULES:
    1. Identify the core problem and pick the SINGLE best product that solves it.
    2. LANGUAGE STRICTNESS: You MUST reply in ENGLISH ONLY, regardless of the language the customer uses to ask the question.
    3. FORMATTING: You MUST use WhatsApp markdown to highlight key terms. Wrap the product name and key features in asterisks to bold them (e.g., *Model X Pro Laptop* or *Dual-fan vapor cooling*).
    4. STYLE: Make it engaging and punchy. Use relevant emojis (🚨, 🔥, 💻, 🎧) to create a structured, visually appealing layout. 
    5. Always include a past customer review.
    
    Return ONLY valid JSON: {{"whatsapp_reply": "The complete formatted text message"}}
    """

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"CUSTOMER MESSAGE: {message_text}"}
            ],
            response_format={"type": "json_object"}
        )
        
        ai_data = json.loads(response.choices[0].message.content)
        final_message = ai_data["whatsapp_reply"]
        
        print(f"🤖 AI RECOMMENDS:\n{final_message}")

        # Send the standard text reply
        await send_whatsapp_text(sender_phone, final_message)
        return {"status": "success"}

    except Exception as e:
        print(f"❌ AI ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))