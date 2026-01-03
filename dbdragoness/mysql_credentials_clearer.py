import keyring

try:
    keyring.delete_password('dbdragoness_mysql', 'mysql_username')  
    keyring.delete_password('dbdragoness_mysql', 'mysql_password')
    print("✅ MySQL credentials cleared!")
except Exception as e:
    print(f"⚠️ Error: {e}")