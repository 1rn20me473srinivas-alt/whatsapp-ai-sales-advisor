import os
import json
from pymongo import MongoClient
from dotenv import load_dotenv

print("🔄 Initializing cloud migration...")

# 1. Load the secret URL from .env
load_dotenv()
MONGO_URL = os.getenv("COSMOS_MONGO_URL")

# 2. Connect to MongoDB Atlas
print("📡 Connecting to MongoDB Atlas...")
client = MongoClient(MONGO_URL)

# Create a Database named "RetailWingman" and a Collection named "products"
db = client["RetailWingman"]
collection = db["products"]

# 3. Load your local JSON file
print("📂 Reading local inventory.json...")
with open("data/inventory.json", "r") as file:
    inventory_data = json.load(file)

# 4. Upload the data to the cloud!
print("🚀 Uploading products to the cloud...")

# Clear out any old data just in case you run this twice
collection.delete_many({}) 

if isinstance(inventory_data, list):
    collection.insert_many(inventory_data)
    print(f"✅ SUCCESS: {len(inventory_data)} products uploaded to MongoDB!")
else:
    # If your JSON is a dictionary instead of a list, we insert it slightly differently
    collection.insert_one(inventory_data)
    print("✅ SUCCESS: Product catalog uploaded to MongoDB!")