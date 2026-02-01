import streamlit as st
import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFont
import io
import json
import re
import datetime
import os
import pandas as pd

# 1. SETUP PAGE
st.set_page_config(page_title="Alh Jibrin Store AI", page_icon="🛒", layout="wide")

# 2. SIDEBAR
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2534/2534204.png", width=80)
    st.title("Store Settings")
    api_key = st.text_input("Google API Key", type="password")
    
    # LOAD DATABASE
    try:
        df = pd.read_csv("products.csv")
        # Clean data for matching
        df['Item Description'] = df['Item Description'].astype(str).str.lower().str.strip()
        # Remove commas from price if they exist
        if df['Sale Price'].dtype == 'O':
            df['Sale Price'] = df['Sale Price'].astype(str).str.replace(',', '').astype(float)
        
        # Create Dictionary: {'sugar': 1500, 'milk': 500}
        product_db = dict(zip(df['Item Description'], df['Sale Price']))
        st.success(f"✅ Database Active: {len(product_db)} Items")
        
    except Exception as e:
        st.error(f"⚠️ Could not load products.csv: {e}")
        product_db = {}

# 3. HELPER FUNCTIONS
def get_model():
    # Find best model
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        flash = [m for m in models if 'flash' in m.lower()]
        return flash[0] if flash else models[0]
    except:
        return None

def generate_receipt_image(scanned_list, grand_total):
    # Draw Receipt
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

    # Header
    draw.text((width//2, 30), "ALH JIBRIN STORE", fill="black", font=font_header, anchor="mm")
    draw.text((width//2, 80), "Dukku, Gombe State", fill="black", font=font_body, anchor="mm")
    draw.text((width//2, 120), datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), fill="black", font=font_body, anchor="mm")
    draw.line([(20, 150), (width-20, 150)], fill="black", width=2)
    
    # Columns
    y = 170
    draw.text((30, y), "QTY", font=font_bold, fill="black")
    draw.text((100, y), "ITEM", font=font_bold, fill="black")
    draw.text((380, y), "PRICE", font=font_bold, fill="black")
    y += 40

    # Items
    for row in scanned_list:
        item = row.get('item', 'Unknown')[:18]
        qty = str(row.get('qty', 1))
        total = row.get('line_total', 0)
        draw.text((30, y), qty, font=font_body, fill="black")
        draw.text((100, y), item, font=font_body, fill="black")
        draw.text((380, y), f"N{total:,}", font=font_body, fill="black")
        y += 40

    # Footer
    draw.line([(20, y+10), (width-20, y+10)], fill="black", width=2)
    y += 30
    draw.text((30, y), "TOTAL:", font=font_bold, fill="black")
    draw.text((380, y), f"N{grand_total:,}", font=font_bold, fill="black")
    y += 60
    draw.text((width//2, y), "Thank you for your patronage!", font=font_body, fill="black", anchor="mm")
    return img

# 4. MAIN APP INTERFACE
st.title("🧾 Smart Invoice")
st.write("Upload a handwritten list to generate a receipt.")

uploaded_file = st.file_uploader("Take a picture", type=["jpg", "jpeg", "png"])

if uploaded_file and st.button("🚀 Process Invoice"):
    if not api_key:
        st.error("Please enter your Google API Key in the sidebar.")
    else:
        with st.spinner('Thinking...'):
            try:
                # Setup AI
                os.environ["GOOGLE_API_KEY"] = api_key
                genai.configure(api_key=api_key)
                
                image = Image.open(uploaded_file)
                model_name = get_model()
                model = genai.GenerativeModel(model_name)
                
                # AI Prompt
                prompt = """
                Analyze this handwritten shopping list.
                1. Identify Quantity and Item Name.
                2. Fix spelling errors (e.g. 'Semov' -> 'Semovita').
                3. Return JSON ONLY: [{"qty": 1, "item": "Milk"}]
                """
                
                response = model.generate_content([prompt, image])
                
                # Parse JSON
                match = re.search(r'\[.*\]', response.text, re.DOTALL)
                if match:
                    raw_data = json.loads(match.group(0))
                    
                    final_total = 0
                    clean_list = []
                    
                    # --- PRICE MATCHING ENGINE ---
                    for row in raw_data:
                        ai_name = row.get('item', '').lower().strip()
                        qty = row.get('qty', 1)
                        price = 0
                        
                        # 1. Try Exact Match
                        if ai_name in product_db:
                            price = product_db[ai_name]
                        
                        # 2. Try Fuzzy Match (if exact fails)
                        if price == 0:
                            for db_name, db_price in product_db.items():
                                if ai_name in db_name or db_name in ai_name:
                                    price = db_price
                                    # Rename item to the correct DB name
                                    row['item'] = db_name.title()
                                    break
                        
                        line_total = qty * price
                        final_total += line_total
                        
                        clean_list.append({
                            "qty": qty, 
                            "item": row.get('item').title(), 
                            "line_total": line_total
                        })
                    
                    # --- DISPLAY RESULTS ---
                    st.success("Done!")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.subheader("📝 List")
                        st.table(clean_list)
                        st.metric("Total To Pay", f"₦{final_total:,}")
                        
                    with col2:
                        st.subheader("🖼️ Receipt")
                        receipt_img = generate_receipt_image(clean_list, final_total)
                        st.image(receipt_img, width=300)
                        
                        # Download Button
                        buf = io.BytesIO()
                        receipt_img.save(buf, format="JPEG")
                        st.download_button(
                            "📥 Download Receipt",
                            data=buf.getvalue(),
                            file_name="receipt.jpg",
                            mime="image/jpeg"
                        )
                else:
                    st.error("AI could not find a list in this image.")

            except Exception as e:
                if "429" in str(e):
                    st.warning("🚦 Speed Limit Hit. Wait 30 seconds.")
                else:
                    st.error(f"Error: {e}")