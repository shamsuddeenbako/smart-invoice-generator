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

# 2. LOAD SALES HISTORY (New Feature)
SALES_FILE = "sales_history.csv"

def load_sales_data():
    if os.path.exists(SALES_FILE):
        return pd.read_csv(SALES_FILE)
    else:
        # Create new if doesn't exist
        df = pd.DataFrame(columns=["Date", "Time", "Items", "Total Amount"])
        return df

def save_sale(items_summary, total_amount):
    df = load_sales_data()
    new_row = {
        "Date": datetime.datetime.now().strftime("%Y-%m-%d"),
        "Time": datetime.datetime.now().strftime("%H:%M:%S"),
        "Items": items_summary,
        "Total Amount": total_amount
    }
    # Append new row
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(SALES_FILE, index=False)

# 3. SIDEBAR & SETTINGS
with st.sidebar:
    st.title("⚙️ Settings")
    api_key = st.text_input("Google API Key", type="password")
    if api_key:
        os.environ["GOOGLE_API_KEY"] = api_key
        genai.configure(api_key=api_key)
    
    st.divider()
    st.write("📦 **Inventory Status**")
    
    # Load Products Database
    try:
        df_products = pd.read_csv("products.csv")
        # Clean Data
        df_products['Item Description'] = df_products['Item Description'].astype(str).str.lower().str.strip()
        if df_products['Sale Price'].dtype == 'O': 
            df_products['Sale Price'] = df_products['Sale Price'].astype(str).str.replace(',', '').astype(float)
        
        product_db = dict(zip(df_products['Item Description'], df_products['Sale Price']))
        st.success(f"✅ Active Items: {len(product_db)}")
    except:
        st.error("⚠️ products.csv not found")
        product_db = {}

# 4. HELPER FUNCTIONS (AI & Receipt)
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

# 5. MAIN TABS (New Layout)
tab1, tab2 = st.tabs(["📝 New Sale", "📊 Manager Dashboard"])

with tab1:
    st.header("New Sale")
    uploaded_file = st.file_uploader("Upload List", type=["jpg", "jpeg", "png"])

    if uploaded_file and st.button("Process Invoice"):
        if not api_key:
            st.error("Enter API Key in Sidebar")
        else:
            with st.spinner('Calculating...'):
                try:
                    os.environ["GOOGLE_API_KEY"] = api_key
                    genai.configure(api_key=api_key)
                    image = Image.open(uploaded_file)
                    model = genai.GenerativeModel(get_model())
                    
                    prompt = """
                    Analyze handwritten list. 
                    Identify Qty, Item Name. 
                    Correct spelling. 
                    Return JSON: [{"qty":1, "item":"Milk"}]
                    """
                    
                    response = model.generate_content([prompt, image])
                    match = re.search(r'\[.*\]', response.text, re.DOTALL)
                    raw_data = json.loads(match.group(0)) if match else []
                    
                    final_total = 0
                    clean_list = []
                    item_names_summary = []
                    
                    for row in raw_data:
                        ai_name = row.get('item', '').lower().strip()
                        qty = row.get('qty', 1)
                        price = product_db.get(ai_name, 0)
                        
                        if price == 0:
                            # Fuzzy Match Logic
                            for db_name, db_price in product_db.items():
                                if ai_name in db_name or db_name in ai_name:
                                    price = db_price
                                    row['item'] = db_name.title()
                                    break
                        
                        line_total = qty * price
                        final_total += line_total
                        
                        clean_list.append({"qty": qty, "item": row.get('item').title(), "line_total": line_total})
                        item_names_summary.append(row.get('item'))

                    # 1. Display Invoice
                    col1, col2 = st.columns(2)
                    with col1:
                        st.table(clean_list)
                        st.metric("Total", f"N{final_total:,}")
                    with col2:
                        receipt = generate_receipt_image(clean_list, final_total)
                        st.image(receipt, width=300)
                        
                        # Download Button
                        buf = io.BytesIO()
                        receipt.save(buf, format="JPEG")
                        st.download_button("Download Image", buf.getvalue(), "receipt.jpg", "image/jpeg")

                    # 2. SAVE TO DATABASE (Auto-Save)
                    save_sale(", ".join(item_names_summary), final_total)
                    st.toast("✅ Sale Saved to History!", icon="💾")
                    
                except Exception as e:
                    if "429" in str(e):
                        st.warning("⏳ Speed Limit Hit. Please wait 1 minute.")
                    else:
                        st.error(f"Error: {e}")

with tab2:
    st.header("📊 Sales Dashboard")
    st.markdown("Track your store performance.")
    
    # Load Data
    df_sales = load_sales_data()
    
    if not df_sales.empty:
        # Metrics
        total_revenue = df_sales["Total Amount"].sum()
        total_transactions = len(df_sales)
        
        m1, m2 = st.columns(2)
        m1.metric("Total Revenue", f"₦{total_revenue:,.0f}")
        m2.metric("Transactions", total_transactions)
        
        st.divider()
        st.subheader("Recent Transactions")
        st.dataframe(df_sales.sort_index(ascending=False), use_container_width=True)
        
        # Download Report
        csv = df_sales.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Report (Excel)", csv, "store_report.csv", "text/csv")
    else:
        st.info("No sales recorded yet. Process an invoice to see data here.")