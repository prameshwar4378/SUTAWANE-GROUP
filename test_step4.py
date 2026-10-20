import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SUTAWANE_EDUCATION.settings')
django.setup()

from django.test import Client
from MyApp.models import User, SystemSetting
from MyApp.auth_utils import get_license_status

client = Client()

print("--- 1. Testing GET / (Unauthenticated Redirect) ---")
res = client.get('/')
print("Status Code:", res.status_code)
assert res.status_code == 302 and '/login/' in res.url, f"Expected redirect to login, got {res.status_code}"
print("Unauthenticated users correctly redirected to /login/!")

print("\n--- 2. Testing GET /login/ ---")
res_login = client.get('/login/')
print("Status Code:", res_login.status_code)
assert res_login.status_code == 200
content = res_login.content.decode('utf-8')
assert 'SUTAWANE CLASSES' in content
assert 'Class Owner' in content
assert 'Developer (OTP)' in content
print("Login page rendered with both Owner and Developer tabs!")

print("\n--- 3. Testing Owner Login with Bad Credentials ---")
res_bad = client.post('/login/', {'login_type': 'owner', 'username': 'sutawane', 'password': 'wrongpassword'})
print("Status Code:", res_bad.status_code)
assert res_bad.status_code == 200
assert 'Invalid username or password' in res_bad.content.decode('utf-8')
print("Bad credentials correctly rejected!")

print("\n--- 4. Testing Owner Login with sutawane / sutawane@123 ---")
res_auth = client.post('/login/', {'login_type': 'owner', 'username': 'sutawane', 'password': 'sutawane@123'})
print("Status Code:", res_auth.status_code)
assert res_auth.status_code == 302, f"Expected 302 redirect, got {res_auth.status_code}"
print("Owner authenticated successfully, session created!")

# Access Dashboard with authenticated session
res_dash = client.get('/')
print("Dashboard Status Code with session:", res_dash.status_code)
assert res_dash.status_code == 200
print("Authenticated dashboard access verified!")

print("\n--- 5. Testing Developer OTP Generation & Login ---")
dev_client = Client()
res_otp = dev_client.post('/api/developer/send-otp/', json.dumps({'email': 'prameshwar4378@gmail.com'}), content_type='application/json')
print("OTP Response Status:", res_otp.status_code)
otp_data = res_otp.json()
print("OTP Response Data:", otp_data)
assert otp_data['success'] is True
otp_code = otp_data['code']
print(f"Generated OTP: {otp_code}")

# Login with Developer OTP
res_dev_login = dev_client.post('/login/', {
    'login_type': 'developer',
    'email': 'prameshwar4378@gmail.com',
    'otp_code': otp_code
})
print("Developer Login Status:", res_dev_login.status_code)
assert res_dev_login.status_code == 302
assert '/developer-portal/' in res_dev_login.url or res_dev_login.url == '/developer-portal/'
print("Developer logged in via OTP successfully!")

# Access Developer Portal
res_portal = dev_client.get('/developer-portal/')
print("Developer Portal Status Code:", res_portal.status_code)
assert res_portal.status_code == 200
assert 'Developer Portal' in res_portal.content.decode('utf-8')
print("Developer Portal rendered with complete licensing and user controls!")

print("\n--- 6. Testing License Guard & Expiry Lock Screen ---")
# Deactivate license temporarily
SystemSetting.objects.update_or_create(key='license_is_active', defaults={'value': 'false'})

# Class Owner should get 403 Software Lock Screen
res_locked = client.get('/')
print("Locked Status Code for Owner:", res_locked.status_code)
assert res_locked.status_code == 403, f"Expected 403, got {res_locked.status_code}"
assert 'Software Subscription Plan Expired' in res_locked.content.decode('utf-8')
print("Software Lock Screen correctly displayed with 403!")

# Developer should be exempt from lock screen
res_dev_exempt = dev_client.get('/developer-portal/')
print("Developer Portal Status when license locked:", res_dev_exempt.status_code)
assert res_dev_exempt.status_code == 200
print("Developer is properly exempt from lock screen to perform maintenance!")

# Restore license back to active
SystemSetting.objects.update_or_create(key='license_is_active', defaults={'value': 'true'})
res_restored = client.get('/')
assert res_restored.status_code == 200
print("License restored, owner access operational!")

print("\nALL STEP 4 DELIVERABLES TESTED & VERIFIED WITH 100% SUCCESS!")
