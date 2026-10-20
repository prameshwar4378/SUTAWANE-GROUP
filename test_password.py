import os
import django
import hashlib
import hmac

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SUTAWANE_EDUCATION.settings')
django.setup()

from MyApp.models import User

for u in User.objects.all():
    print(f"Username: {u.username}")
    print(f"  Salt: {u.salt}")
    print(f"  Hash: {u.password}")
    
    # In Node.js: crypto.pbkdf2Sync(password, salt, 10000, 64, 'sha512').toString('hex')
    # Let's test with the salt as string (salt.encode('utf-8'))
    calc_str = hashlib.pbkdf2_hmac('sha512', ('sutawane@123' if u.username == 'sutawane' else 'developer@123').encode('utf-8'), u.salt.encode('utf-8'), 10000, 64).hex()
    match_str = (calc_str == u.password)
    print(f"  Match with string salt: {match_str}")
    
    # Or with hex-decoded salt
    try:
        calc_hex = hashlib.pbkdf2_hmac('sha512', ('sutawane@123' if u.username == 'sutawane' else 'developer@123').encode('utf-8'), bytes.fromhex(u.salt), 10000, 64).hex()
        match_hex = (calc_hex == u.password)
        print(f"  Match with bytes.fromhex salt: {match_hex}")
    except Exception as e:
        print(f"  Hex error: {e}")
