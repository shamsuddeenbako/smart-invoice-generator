import streamlit as st
import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFont
import io
import json
import re
import datetime
import os
import pandas as pd  # <--- NEW LIBRARY FOR DATA

# 1. SETUP PAGE
st.set_page_config(page_title="Alh Jibrin Store AI", page_icon="🛒", layout="wide")

# 2. SIDEBAR
with st.sidebar:
    st.title("⚙️ Settings")
    api_key = st.text_input("Google API Key", type="password")
    if api_key:
        os.environ["GOOGLE_API_KEY"] = api_key
        genai.configure(api_key=api_key)
    
    st.divider()
    st.write("📦 **Inventory Status**")
    
    # --- LOAD THE CSV DATABASE ---
    try:
        # Load the CSV file
        df = pd.read_csv("products.csv")
        
        # Clean the data: Convert Item names to lowercase for matching
        df['Item Description'] = df['Item Description'].astype(str).str.lower().str.strip()
        
        # Clean the price: Remove commas if they exist (e.g., "1,500" -> 1500)
        # Check if column is string before replacing
        if df['Sale Price'].dtype == 'O': 
            df['Sale Price'] = df['Sale Price'].astype(str).str.replace(',', '').astype(float)
            
        # Create a dictionary for fast lookup: {'sugar': 1500, ...}
        product_db = dict(zip(df['Item Description'], df['Sale Price']))
        
        st.success(f"✅ Loaded {len(product_db)} items from database.")
        
        # Optional: Show a few items
        with st.expander("View Price List"):
            st.dataframe(df[['Item Description', 'Sale Price']])
            
    except FileNotFoundError:
        st.error("⚠️ 'products.csv' not found. Please upload it.")
        product_db = {} # Empty fallback
    except Exception as e:
        st.error(f"Error loading database: {e}")
        product_db = {}

# 3. HELPER FUNCTIONS
def get_model():
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        flash = [m for m in models if 'flash' in m.lower()]
        return flash[0] if flash else models[0]
    except:
        return None

def generate_receipt_image(scanned_list, grand_total):
    width, height = 500, 350 + (len(scanned_list) * 50)
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    
    try:
        font_header = ImageFont.truetype("arial.ttf", 40)
        font_body = ImageFont.truetype("arial.ttf", 24)
        font_bold = ImageFont.truetype("arialbd.ttf", 24)
    except:
        font_header = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_bold = ImageFont.load_default()

    draw.text((width//2, 30), "ALH JIBRIN STORE", fill="black", font=font_header, anchor="mm")
    draw.text((width//2, 80), "Provision Store, Dukku", fill="black", font=font_body, anchor="mm")
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

# 4. MAIN UI
st.title("🛒 Smart Invoice Generator")
st.markdown("Automatic Price Lookup enabled for **Alh Jibrin Bako Provision Store**")

uploaded_file = st.file_uploader("Upload Handwritten List", type=["jpg", "jpeg", "png"])

if uploaded_file and st.button("Process Invoice"):
    if not api_key:
        st.error("Please enter API Key.")
        st.stop()
    
    # Check if DB is loaded
    if not product_db:
        st.warning("⚠️ Database not loaded. Prices will be 0 unless written on paper.")

    with st.spinner('🤖 Reading list & Looking up prices...'):
        os.environ["GOOGLE_API_KEY"] = api_key
        genai.configure(api_key=api_key)
        
        image = Image.open(uploaded_file)
        model_name = get_model()
        model = genai.GenerativeModel(model_name)
        
        prompt = """
        Analyze this handwritten list for a Nigerian provision store.
        1. Identify Quantity, Item Name (e.g. 'Indomie', 'Peak Milk').
        2. Ignore prices written on paper if they are messy; we will use the database.
        3. Correct spelling (e.g. 'Semov' -> 'Semovita', 'Spag' -> 'Spaghetti').
        4. Return ONLY JSON: [{"qty": 1, "item": "Item Name"}]
        """
        
        try:
            response = model.generate_content([prompt, image])
            match = re.search(r'\[.*\]', response.text, re.DOTALL)
            raw_data = json.loads(match.group(0)) if match else []
            
            final_total = 0
            clean_list = []
            
            # --- THE INTELLIGENT MATCHING LOGIC ---
            for row in raw_data:
                # Get the detected name (e.g., "Indomie")
                ai_item_name = row.get('item', '').lower().strip()
                qty = row.get('qty', 1)
                
                # LOOKUP PRICE
                # 1. Exact Match
                price = product_db.get(ai_item_name, 0)
                
                # 2. Fuzzy Match (If exact fails)
                # Example: AI sees "Indomie", DB has "Indomie Supreme".
                if price == 0:
                    for db_name, db_price in product_db.items():
                        # Check if one string is inside the other
                        if ai_item_name in db_name or db_name in ai_item_name:
                            price = db_price
                            # Update name to the official DB name
                            row['item'] = db_name.title() 
                            break
                
                line_total = qty * price
                final_total += line_total
                
                clean_list.append({
                    "qty": qty, 
                    "item": row.get('item').title(), 
                    "line_total": line_total
                })
            
            # Display
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Detected Items")
                st.table(clean_list)
                st.metric("Grand Total", f"N{final_total:,}")
            
            with col2:
                st.subheader("Receipt Preview")
                receipt_img = generate_receipt_image(clean_list, final_total)
                st.image(receipt_img, width=350)
                
                buf = io.BytesIO()
                receipt_img.save(buf, format="JPEG")
                st.download_button("Download Receipt", buf.getvalue(), "receipt.jpg", "image/jpeg")
                
        except Exception as e:
            st.error(f"Error: {e}")