import streamlit as st
import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFont
import io
import json
import re
import datetime
import os

# 1. SETUP THE PAGE
st.set_page_config(page_title="Smart Invoice Generator", page_icon="🧾", layout="wide")

# 2. SIDEBAR FOR SETTINGS
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2534/2534204.png", width=100)
    st.title("Settings")
    
    # Securely ask for API Key here so you don't hardcode it
    api_key = st.text_input("Enter Google API Key", type="password")
    
    st.divider()
    st.write("📦 **Product Database (Simulation)**")
    # This simulates your shop's database
    product_database = {
        "sugar": 1500, "maggi": 1200, "indomie": 11500,
        "cowbell": 850, "macaroni": 1100, "semovita": 9500,
        "milk": 500, "rice": 2000
    }
    st.write(product_database)

# 3. HELPER FUNCTIONS
def get_model():
    """Finds the best available model (Flash preferred)."""
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        flash = [m for m in models if 'flash' in m.lower()]
        return flash[0] if flash else models[0]
    except:
        return None

def generate_receipt_image(scanned_list, grand_total):
    """Draws the receipt image."""
    width, height = 500, 350 + (len(scanned_list) * 50)
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    
    # Fonts
    try:
        font_header = ImageFont.truetype("arial.ttf", 40)
        font_body = ImageFont.truetype("arial.ttf", 24)
        font_bold = ImageFont.truetype("arialbd.ttf", 24)
    except:
        font_header = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_bold = ImageFont.load_default()

    # Draw Content
    draw.text((width//2, 30), "ALH JIBRIN STORE", fill="black", font=font_header, anchor="mm")
    draw.text((width//2, 80), "Dukku, Gombe State", fill="black", font=font_body, anchor="mm")
    draw.text((width//2, 120), datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), fill="black", font=font_body, anchor="mm")
    
    draw.line([(20, 150), (width-20, 150)], fill="black", width=2)
    
    y = 170
    draw.text((30, y), "QTY", font=font_bold, fill="black")
    draw.text((100, y), "ITEM", font=font_bold, fill="black")
    draw.text((380, y), "PRICE", font=font_bold, fill="black")
    y += 40

    for row in scanned_list:
        item = row.get('item', 'Unknown')[:18]
        qty = str(row.get('qty', 1))
        total = row.get('line_total', 0)
        draw.text((30, y), qty, font=font_body, fill="black")
        draw.text((100, y), item, font=font_body, fill="black")
        draw.text((380, y), f"N{total:,}", font=font_body, fill="black")
        y += 40

    draw.line([(20, y+10), (width-20, y+10)], fill="black", width=2)
    y += 30
    draw.text((30, y), "TOTAL:", font=font_bold, fill="black")
    draw.text((380, y), f"N{grand_total:,}", font=font_bold, fill="black")
    y += 60
    draw.text((width//2, y), "Thank you for your patronage!", font=font_body, fill="black", anchor="mm")

    return img

# 4. MAIN USER INTERFACE
st.title("🧾 Smart Invoice Generator")
st.write("Upload a photo of a handwritten list to generate an invoice instantly.")

uploaded_file = st.file_uploader("Upload Image (JPG/PNG)", type=["jpg", "jpeg", "png"])

if uploaded_file and st.button("🚀 Process Invoice"):
    if not api_key:
        st.error("❌ Please enter your Google API Key in the sidebar first.")
    else:
        # Configure Key
        os.environ["GOOGLE_API_KEY"] = api_key
        genai.configure(api_key=api_key)
        
        with st.spinner('🤖 AI is reading your handwriting...'):
            image = Image.open(uploaded_file)
            
            # Call AI
            model_name = get_model()
            if not model_name:
                st.error("Could not find any Gemini models.")
                st.stop()
                
            model = genai.GenerativeModel(model_name)
            prompt = """
            Analyze this handwritten list.
            1. Identify Quantity, Item Name, and Unit Price.
            2. Correct spelling contextually for Nigerian retail (e.g. 'Semov' -> 'Semovita').
            3. Return ONLY valid JSON list: [{"qty": 1, "item": "Milk", "unit_price": 500}]
            """
            
            try:
                response = model.generate_content([prompt, image])
                match = re.search(r'\[.*\]', response.text, re.DOTALL)
                if match:
                    raw_data = json.loads(match.group(0))
                else:
                    raw_data = []
                    st.warning("AI saw the image but couldn't find a list. Try writing clearer.")

                # Calculate Totals
                final_total = 0
                clean_list = []
                for row in raw_data:
                    item_name = row.get('item', '').lower()
                    qty = row.get('qty', 1)
                    price = 0
                    
                    # Database Logic
                    for db_item, db_price in product_database.items():
                        if db_item in item_name:
                            price = db_price
                            break
                    if price == 0 and row.get('unit_price'):
                        price = row.get('unit_price')
                        
                    line_total = qty * price
                    final_total += line_total
                    clean_list.append({"qty": qty, "item": row.get('item'), "line_total": line_total})

                # Display Results
                st.success("✅ Done!")
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("📝 Detected Items")
                    st.table(clean_list)
                    st.info(f"Grand Total: N{final_total:,}")
                
                with col2:
                    st.subheader("🖼️ Digital Receipt")
                    receipt_img = generate_receipt_image(clean_list, final_total)
                    st.image(receipt_img, caption="Ready to Print", width=350)
                    
                    # Download Button
                    buf = io.BytesIO()
                    receipt_img.save(buf, format="JPEG")
                    byte_im = buf.getvalue()
                    
                    st.download_button(
                        label="📥 Download Receipt Image",
                        data=byte_im,
                        file_name="receipt.jpg",
                        mime="image/jpeg"
                    )

            except Exception as e:
                st.error(f"Error: {e}")