# debug_login.py — Run this file directly with: python debug_login.py
# This will tell you EXACTLY why login is failing

import mysql.connector
import bcrypt

# ── YOUR DB CREDENTIALS ──────────────────────────
DB_HOST     = "localhost"
DB_USER     = "root"
DB_PASSWORD = "my@123appsql892819"   # your MySQL root password
DB_NAME     = "travel_app"
# ─────────────────────────────────────────────────

EMAIL    = input("Enter your email to test: ").strip()
PASSWORD = input("Enter your password to test: ").strip()

print("\n🔍 Connecting to database...")
try:
    conn = mysql.connector.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
    )
    print("✅ DB connected successfully")
except Exception as e:
    print(f"❌ DB connection failed: {e}")
    exit()

cur = conn.cursor(dictionary=True)

# 1. Exact match
cur.execute("SELECT * FROM users WHERE email = %s", (EMAIL,))
user_exact = cur.fetchone()

# 2. Case-insensitive match
cur.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(%s)", (EMAIL,))
user_lower = cur.fetchone()

print(f"\n📧 Exact email match found:      {'✅ YES' if user_exact else '❌ NO'}")
print(f"📧 Case-insensitive match found: {'✅ YES' if user_lower else '❌ NO'}")

user = user_lower or user_exact

if not user:
    print("\n❌ PROBLEM: Email not found in database at all!")
    print("   → Check you are typing the correct email.")
    print("   → Emails in DB:")
    cur.execute("SELECT email FROM users")
    for row in cur.fetchall():
        print(f"      • {row['email']}")
    conn.close()
    exit()

print(f"\n👤 User found: {user['full_name']}")
stored_hash = user["password_hash"]
print(f"🔐 Stored hash (raw):    '{stored_hash}'")
print(f"🔐 Stored hash (stripped): '{stored_hash.strip()}'")
print(f"📏 Hash length: {len(stored_hash)} chars  (should be 60)")
print(f"🔤 Hash starts with: {stored_hash[:4]}  (should be '$2b$')")

# Check for whitespace contamination
if stored_hash != stored_hash.strip():
    print("⚠️  WARNING: Hash has leading/trailing whitespace! This breaks bcrypt.")

if not stored_hash.startswith("$2b$") and not stored_hash.startswith("$2a$"):
    print("❌ PROBLEM: Hash does not look like a valid bcrypt hash!")
    print("   → The password was probably stored in plain text or incorrectly.")
    conn.close()
    exit()

# Try bcrypt verification
print(f"\n🔑 Testing password: '{PASSWORD}'")
try:
    result = bcrypt.checkpw(PASSWORD.encode("utf-8"), stored_hash.strip().encode("utf-8"))
    print(f"bcrypt.checkpw result: {'✅ MATCH — login should work!' if result else '❌ NO MATCH — wrong password or hash is corrupted'}")
except Exception as e:
    print(f"❌ bcrypt ERROR: {e}")
    print("   → Hash is corrupted. You need to reset the password.")

conn.close()

print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("If bcrypt says NO MATCH, run this SQL in MySQL to reset your password:")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

# Generate a fresh hash for the entered password and show the SQL
new_hash = bcrypt.hashpw(PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
print(f"\nUPDATE users SET password_hash = '{new_hash}' WHERE email = '{EMAIL}';\n")
print("Copy that SQL, paste it in MySQL Workbench or terminal, run it, then try login again.")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
