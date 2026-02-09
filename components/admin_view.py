# ... (Imports remain the same, add these:)
from googleapiclient.http import MediaIoBaseDownload
from core.connection import get_services # To get Drive Service

# ... (Inside show_admin -> PDF Section)

# Helper function for PDF generation
def download_image(service, file_id):
    try:
        request = service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        fh.seek(0)
        return fh
    except:
        return None

# ... (Inside the loop `for i, row in fresh_att_subset.reset_index().iterrows():`)

    pdf.cell(110, 25, "", 1, 1)
    sig_id = row.get('SignatureBase64') # This is now File ID
    
    # Logic to check if it's a Drive ID (approx check) or old Base64
    if sig_id and len(str(sig_id)) > 5:
        
        img_data = None
        
        # Backward Compatibility: Check if it's still Base64 (Old records)
        if "data:image" in str(sig_id):
             img = base64_to_image(sig_id)
             if img:
                 buf = BytesIO()
                 img.save(buf, format="PNG")
                 buf.seek(0)
                 img_data = buf
        else:
            # It is a Drive File ID (New records)
            _, drive_svc = get_services()
            img_data = download_image(drive_svc, sig_id)
            
        if img_data:
            # Save to temp file for FPDF
            tmp_name = f"tmp_{m_id}_{i}_{random.randint(1000,9999)}.png"
            with open(tmp_name, "wb") as f:
                f.write(img_data.read())
            
            pdf.image(tmp_name, x+35, y+4, h=17)
            try: os.remove(tmp_name)
            except: pass
