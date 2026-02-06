import qrcode
import textwrap
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from fpdf import FPDF
from config import FONT_CH
from utils import base64_to_image
import random
import os

def generate_qr_card(url, m_name, m_loc, m_time):
    qr = qrcode.make(url).resize((350, 350))
    W, H = 600, 850 
    img = Image.new('RGB', (W, H), 'white')
    draw = ImageDraw.Draw(img)
    try:
        font_header = ImageFont.truetype(FONT_CH, 40)
        font_body = ImageFont.truetype(FONT_CH, 22)
    except:
        font_header = ImageFont.load_default()
        font_body = ImageFont.load_default()

    wrapper = textwrap.TextWrapper(width=14) 
    name_lines = wrapper.wrap(text=str(m_name))
    current_h = 60
    for line in name_lines:
        draw.text((W/2, current_h), line, fill="black", font=font_header, anchor="mm")
        current_h += 55 
    
    current_h += 20 
    info_text = f"地點：{m_loc}\n時間：{m_time}"
    draw.multiline_text((W/2, current_h), info_text, fill="black", font=font_body, anchor="ma", align="center")
    
    current_h += 130 
    img.paste(qr, ((W - 350) // 2, current_h))
    
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def create_attendance_pdf(meeting_info, attendees_df):
    pdf = FPDF()
    pdf.add_page()
    pdf.add_font('CustomFont', '', FONT_CH, uni=True)
    pdf.set_font('CustomFont', '', 24)
    
    pdf.multi_cell(w=0, h=12, txt=f"{meeting_info.get('MeetingName')}簽到", align="C")
    pdf.set_font_size(14)
    pdf.cell(0, 10, f"時間：{meeting_info.get('TimeRange')}", ln=True, align="C")
    pdf.cell(0, 10, f"地點：{meeting_info.get('Location')}", ln=True, align="C")
    pdf.ln(5)
    
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font_size(16)
    pdf.cell(80, 12, "出席人員", 1, 0, 'C', True)
    pdf.cell(110, 12, "簽名", 1, 1, 'C', True)
    
    for i, row in attendees_df.reset_index().iterrows():
        pdf.cell(80, 25, str(row.get('AttendeeName')), 1, 0, 'C')
        x, y = pdf.get_x(), pdf.get_y()
        pdf.cell(110, 25, "", 1, 1)
        sig = row.get('SignatureBase64')
        if sig and len(str(sig)) > 20:
            img = base64_to_image(sig)
            if img:
                tmp_name = f"tmp_{i}_{random.randint(1000,9999)}.png"
                img.save(tmp_name)
                pdf.image(tmp_name, x+35, y+4, h=17)
                try: os.remove(tmp_name)
                except: pass
    return pdf.output()
