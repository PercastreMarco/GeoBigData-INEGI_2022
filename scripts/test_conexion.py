import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

client = MongoClient(os.environ["MONGODB_URI"])
db = client[os.environ["MONGODB_DB"]]

client.admin.command("ping")
print("✅ Conexión exitosa a MongoDB Atlas")
print("Bases de datos visibles:", client.list_database_names())