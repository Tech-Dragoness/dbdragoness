import keyring

# Clear PostgreSQL credentials
try:
    keyring.delete_password('dbdragoness_postgresql', 'postgresql_username')
    keyring.delete_password('dbdragoness_postgresql', 'postgresql_password')
    print("✅ PostgreSQL credentials cleared!")
except Exception as e:
    print(f"⚠️ Error: {e}")