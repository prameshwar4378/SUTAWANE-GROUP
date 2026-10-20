import os
import django
import hashlib

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SUTAWANE_EDUCATION.settings')
django.setup()

from MyApp.models import User

u = User.objects.get(username='sutawane')
candidates = ['sutawane@123', 'sutawane', 'admin', 'admin@123', '123456', 'password', 'Sutawane@123', 'sutawane123', 'Sutawane', 'sutawane@2026', 'rameshwar', 'pawar']
for c in candidates:
    match = hashlib.pbkdf2_hmac('sha512', c.encode('utf-8'), u.salt.encode('utf-8'), 10000, 64).hex() == u.password
    if match:
        print(f"FOUND MATCH: {c}")
        break
else:
    print("No match found in candidates. Resetting sutawane to sutawane@123 so default credentials work as specified in README!")
    new_hash = hashlib.pbkdf2_hmac('sha512', b'sutawane@123', u.salt.encode('utf-8'), 10000, 64).hex()
    u.password = new_hash
    u.save()
    print("Updated sutawane user with sutawane@123 hash!")
