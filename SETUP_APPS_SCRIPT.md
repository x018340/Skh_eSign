# Apps Script Bridge Setup (No credit card)

## 1) Create Apps Script project
- Go to https://script.google.com
- New project
- Paste apps_script/Code.gs
- (Optional) set appsscript.json manifest

## 2) Set API_KEY (Script Property)
Apps Script -> Project Settings -> Script Properties:
- Key: API_KEY
- Value: a long random secret (32+ chars)

## 3) Deploy as Web App
Deploy -> New deployment -> Web app:
- Execute as: Me
- Who has access: Anyone
Copy the Web App URL (ends with /exec)

## 4) Streamlit secrets
Add:

[gas]
upload_url = "YOUR_WEB_APP_URL"
api_key = "YOUR_API_KEY"
folder_id = "YOUR_DRIVE_FOLDER_ID"

## 5) Data format
Google Sheet column SignatureBase64 will store:
gas:<fileId>

PDF generation downloads the image via:
GET upload_url?action=download&fileId=...&api_key=...
