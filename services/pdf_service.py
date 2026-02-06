import qrcode
import textwrap
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from config import FONT_CH

def generate_qr_card(url, m_name, m_loc, m_time):
    # IDENTICAL LOGIC
    m_name = str(m_name)
    m_loc = str(m_loc)
    m_time = str(m_time)
    qr = qrcode.make(url)
    qr = qr.resize((350, 350))
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
    name_lines = wrapper.wrap(text=m_name)
    current_h = 60
    for line in name_lines:
        draw.text((W/2, current_h), line, fill="black", font=font_header, anchor="mm")
        current_h += 55 
    
    current_h += 20 
    info_text = f"地點：{m_loc}\n時間：{m_time}"
    draw.multiline_text((W/2, current_h), info_text, fill="black", font=font_body, anchor="ma", align="center")
    
    current_h += 100 
    draw.text((W/2, current_h), "會議簽到", fill="black", font=font_body, anchor="mm")
    
    current_h += 30 
    qr_x = (W - 350) // 2 
    img.paste(qr, (qr_x, current_h))
    
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
