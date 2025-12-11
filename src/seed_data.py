import sqlite3
import random
import os
from datetime import datetime, timedelta
from faker import Faker

# Configuration
DB_FOLDER = "data"
DB_NAME = "payments.db"
DB_PATH = os.path.join(DB_FOLDER, DB_NAME)
ROW_COUNT = 2000  # Generate enough rows to make queries interesting

fake = Faker()

def ensure_directory():
    """Ensure the data directory exists."""
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)

def get_db_connection():
    return sqlite3.connect(DB_PATH)

def create_table(conn):
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id TEXT PRIMARY KEY,
        amount_cents INTEGER,
        currency TEXT,
        status TEXT,
        payment_method TEXT,
        country_code TEXT,
        customer_email TEXT,
        description TEXT,
        created_at DATETIME
    );
    """)
    conn.commit()

def generate_fake_data():
    data = []
    
    # Weights to make data realistic
    currencies = ["USD", "EUR", "GBP"]
    currency_weights = [0.6, 0.3, 0.1]
    
    statuses = ["succeeded", "failed", "pending", "refunded"]
    status_weights = [0.85, 0.10, 0.03, 0.02]
    
    payment_methods = ["card", "paypal", "sofort", "ideal", "apple_pay"]
    method_weights = [0.7, 0.1, 0.1, 0.05, 0.05]
    
    countries = ["US", "DE", "FR", "GB", "BR", "JP"]
    country_weights = [0.5, 0.2, 0.1, 0.1, 0.05, 0.05]

    print(f"🌱 Seeding {ROW_COUNT} transactions...")

    for _ in range(ROW_COUNT):
        # Generate a Stripe-like Transaction ID
        tx_id = f"tx_{fake.uuid4().replace('-', '')[:16]}"
        
        # Weighted choices
        currency = random.choices(currencies, weights=currency_weights, k=1)[0]
        status = random.choices(statuses, weights=status_weights, k=1)[0]
        method = random.choices(payment_methods, weights=method_weights, k=1)[0]
        country = random.choices(countries, weights=country_weights, k=1)[0]
        
        # Logic: If country is DE, bump chance of 'sofort' (realistic German payment method)
        if country == 'DE' and random.random() > 0.5:
            method = 'sofort'

        # Amount in cents (e.g., 5000 = 50.00)
        amount = random.randint(500, 50000) 
        
        email = fake.email()
        description = f"Payment for {fake.bs()}"
        
        # Date generation: Distribution between now and 60 days ago
        # ensuring we have data for "Last Month" and "Yesterday"
        days_ago = random.randint(0, 60)
        created_at = datetime.now() - timedelta(days=days_ago)
        
        data.append((
            tx_id, 
            amount, 
            currency, 
            status, 
            method, 
            country, 
            email, 
            description, 
            created_at.strftime("%Y-%m-%d %H:%M:%S")
        ))

    return data

def seed():
    ensure_directory()
    conn = get_db_connection()
    create_table(conn)
    
    # Check if data already exists to avoid duplication on restart
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM transactions")
    count = cursor.fetchone()[0]
    
    if count > 0:
        print(f"✅ Database already contains {count} records. Skipping seed.")
        conn.close()
        return

    # Insert Data
    data = generate_fake_data()
    cursor.executemany("""
        INSERT INTO transactions 
        (id, amount_cents, currency, status, payment_method, country_code, customer_email, description, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, data)
    
    conn.commit()
    conn.close()
    print(f"🚀 Successfully seeded {len(data)} transactions to {DB_PATH}")

if __name__ == "__main__":
    seed()