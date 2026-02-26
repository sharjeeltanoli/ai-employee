from google_auth_oauthlib.flow import InstalledAppFlow
import pickle
from pathlib import Path

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
CREDENTIALS_PATH = Path("/mnt/c/AI_Employee_Vault/ai-employee/credentials.json")
TOKEN_PATH = Path("/mnt/c/AI_Employee_Vault/ai-employee/token.pickle")

flow = InstalledAppFlow.from_client_secrets_file(
    str(CREDENTIALS_PATH), 
    SCOPES,
    redirect_uri='urn:ietf:wg:oauth:2.0:oob'
)

auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')

print("\n=== Copy this URL and open in Windows browser ===")
print(auth_url)
print("=================================================\n")

code = input("Paste the authorization code here: ")

flow.fetch_token(code=code)
creds = flow.credentials

with open(TOKEN_PATH, 'wb') as token:
    pickle.dump(creds, token)

print("Authentication successful! token.pickle saved.")
