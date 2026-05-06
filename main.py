import os
import json
import httpx
import certifi
from fastapi import FastAPI, Request, HTTPException
from groq import Groq
from dotenv import load_dotenv
from pymongo import MongoClient

# 1. Load Secrets
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
KAPSO_API_KEY = os.getenv("KAPSO_API_KEY")
MONGO_URL = os.getenv("COSMOS_MONGO_URL")
MANAGER_PHONE = os.getenv("MANAGER_PHONE_NUMBER") 

app = FastAPI(title="WhatsApp Sales Wingman")
groq_client = Groq(api_key=GROQ_API_KEY)

# 2. Connect to MongoDB
client = MongoClient(MONGO_URL, tlsCAFile=certifi.where())
db = client["RetailWingman"]
inventory_collection = db["products"]
customers_db = db["customers"]

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
        await client.post(url, headers=headers, json=payload)

@app.post("/webhook/kapso")
async def kapso_webhook(request: Request):
    payload = await request.json()
    
    # =================================================================
    # 🔘 THE "CLOSE BUTTON" LISTENER
    # =================================================================
    conversation_block = payload.get("conversation", {})
    if conversation_block.get("status") == "ended":
        closed_phone = conversation_block.get("phone_number")
        if closed_phone:
            # Wake the AI back up!
            customers_db.update_one({"phone_number": closed_phone}, {"$set": {"state": "ai"}})
            print(f"✅ CHAT CLOSED IN DASHBOARD: AI automatically resumed for {closed_phone}.")
        return {"status": "success", "event": "conversation_ended"}


    # =================================================================
    # 📨 NORMAL MESSAGE PROCESSING
    # =================================================================
    msg_block = payload.get("message", {})
    
    # If there's no message block (and it wasn't a close event), ignore it
    if not msg_block:
        return {"status": "ignored"}
        
    direction = msg_block.get("kapso", {}).get("direction") or msg_block.get("direction")
    sender_phone = msg_block.get("phone_number") or msg_block.get("from") or payload.get("conversation", {}).get("phone_number")
    msg_type = msg_block.get("type")
    
    # Extract Text
    if msg_type == "audio":
        message_text = msg_block.get("kapso", {}).get("transcript", {}).get("text", "")
    else:
        message_text = msg_block.get("content") or msg_block.get("text", {}).get("body", "")

    if not message_text or not sender_phone:
        return {"status": "ignored"}

    # Fetch or Create Profile
    user_profile = customers_db.find_one({"phone_number": sender_phone})
    if not user_profile:
        user_profile = {"phone_number": sender_phone, "state": "ai", "history": []}
        customers_db.insert_one(user_profile)

    # Ignore all manager outbound texts (since Kapso doesn't forward them in sandbox anyway)
    if direction == "outbound":
        return {"status": "ignored"}

    print(f"\n💬 PROCESSING CUSTOMER MESSAGE: {message_text}")

    # =================================================================
    # 🚨 HANDOFF & NOTIFICATION LOGIC (Customer Inbound)
    # =================================================================
    trigger_words = ["human", "manager", "support", "real person", "agent"]
    if any(word in message_text.lower() for word in trigger_words) and user_profile.get("state") == "ai":
        customers_db.update_one({"phone_number": sender_phone}, {"$set": {"state": "human"}})
        
        handoff_msg = "I'm pausing my digital assistant. A manager will be with you shortly!"
        await send_whatsapp_text(sender_phone, handoff_msg)
        
        if MANAGER_PHONE:
            alert_msg = f"🚨 *NEW HANDOFF ALERT*\n\nCustomer *{sender_phone}* is asking for a human.\n\n*Message:* {message_text}"
            await send_whatsapp_text(MANAGER_PHONE, alert_msg)
            
        print(f"🚨 HANDOFF TRIGGERED for {sender_phone}.")
        return {"status": "success"}

    # 🛑 Stop the AI if a Human is handling it
    if user_profile.get("state") == "human":
        print(f"🛑 AI MUTED: Ignored customer message from {sender_phone}")
        return {"status": "ignored"}

    # =================================================================
    # 🤖 MAIN AI PROCESSING LOOP
    # =================================================================
    customers_db.update_one(
        {"phone_number": sender_phone},
        {"$push": {"history": {"role": "user", "content": message_text}}}
    )

    live_inventory = list(inventory_collection.find({}, {"_id": 0}))
    updated_profile = customers_db.find_one({"phone_number": sender_phone})
    chat_history = updated_profile["history"]

    system_prompt = f"""
    You are an expert retail sales advisor replying on WhatsApp.
    Analyze the customer's message, identify their problem, and recommend the best product.

    INVENTORY: {json.dumps(live_inventory)}

    RULES:
    1. Identify the core problem and pick the SINGLE best product that solves it.
    2. LANGUAGE STRICTNESS: You MUST reply in ENGLISH ONLY.
    3. FORMATTING: You MUST use WhatsApp markdown to highlight key terms. Wrap the product name and key features in asterisks to bold them.
    4. STYLE: Make it engaging and punchy. Use relevant emojis. 
    5. Always include a past customer review.
    
    Return ONLY valid JSON: {{"whatsapp_reply": "The complete formatted text message"}}
    """

    messages_payload = [{"role": "system", "content": system_prompt}] + chat_history

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages_payload,
            response_format={"type": "json_object"}
        )
        
        ai_data = json.loads(response.choices[0].message.content)
        final_message = ai_data["whatsapp_reply"]
        
        print(f"🤖 AI RECOMMENDS:\n{final_message}")

        await send_whatsapp_text(sender_phone, final_message)
        
        customers_db.update_one(
            {"phone_number": sender_phone},
            {"$push": {"history": {"role": "assistant", "content": final_message}}}
        )

        return {"status": "success"}

    except Exception as e:
        print(f"❌ AI ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))