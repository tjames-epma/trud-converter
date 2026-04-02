import streamlit as st
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
import io
import re
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter

# 1. Page Config
st.set_page_config(page_title="TRUD XML Converter", page_icon="💊", layout="wide")

# --- 2. PASSWORD GATEKEEPER ---
if "password_correct" not in st.session_state:
    st.title("🔐 Access Required")
    pwd = st.text_input("Please enter the access password", type="password")
    if st.button("Sign In"):
        if "auth" in st.secrets and pwd == st.secrets["auth"]["password"]:
            st.session_state["password_correct"] = True
            st.rerun()
        else: st.error("Invalid password")
    st.stop()

# --- 3. LOGIC FUNCTIONS ---

def get_ampp_data(zip_obj, file_pattern):
    matches = [f for f in zip_obj.namelist() if file_pattern in f.lower() and f.endswith('.xml')]
    if not matches: return pd.DataFrame()
    with zip_obj.open(matches[0]) as f:
        tree = ET.parse(f)
        root = tree.getroot()
        rows = []
        for record in root.findall(".//{*}AMPP"):
            # Cleanly extract tags and force IDs to strings to prevent rounding
            entry = {child.tag.split('}')[-1]: (str(child.text).strip() if child.text else "") for child in record}
            if "ABBREVNM" not in entry: entry["ABBREVNM"] = ""
            rows.append(entry)
        return pd.DataFrame(rows)

def get_gtin_mapping(zip_obj):
    xml_files = [f for f in zip_obj.namelist() if f.endswith('.xml')]
    if not xml_files: return pd.DataFrame(columns=['JOIN_ID', 'GTIN'])
    with zip_obj.open(xml_files[0]) as f:
        tree = ET.parse(f)
        root = tree.getroot()
        rows = []
        # Search for AMPP or APP blocks
        for block in root.findall(".//{*}AMPP") + root.findall(".//{*}APP"):
            # Look for ANY ID field in the block
            id_elem = block.find(".//{*}AMPPID") or block.find(".//{*}APPID") or block.find(".//{*}ID")
            if id_elem is not None and id_elem.text:
                clean_id = str(id_elem.text).strip()
                for gtin_data in block.findall(".//{*}GTINDATA"):
                    gtin_elem = gtin_data.find(".//{*}GTIN")
                    if gtin_elem is not None and gtin_elem.text:
                        rows.append({'JOIN_ID': clean_id, 'GTIN': str(gtin_elem.text).strip()})
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=['JOIN_ID', 'GTIN'])

# --- 4. MAIN UI ---

st.title("💊 TRUD AMPP + GTIN Processor")
uploaded_file = st.file_uploader("Upload TRUD ZIP", type="zip")

if uploaded_file and st.button("🚀 Process Data", use_container_width=True):
    with st.status("Extracting and Joining...", expanded=True) as status:
        try:
            with zipfile.ZipFile(uploaded_file, 'r') as outer_zip:
                # 1. AMPP Data
                df_ampp = get_ampp_data(outer_zip, 'f_ampp2')
                
                # 2. GTIN Data
                gtin_zips = [f for f in outer_zip.namelist() if 'gtin' in f.lower()]
                if not gtin_zips:
                    st.error("No GTIN zip found in the main archive.")
                else:
                    with outer_zip.open(gtin_zips[0]) as z_in:
                        with zipfile.ZipFile(io.BytesIO(z_in.read())) as inner_zip:
                            df_gtin = get_gtin_mapping(inner_zip)
                    
                    # 3. Double-Join Logic
                    # First try matching GTIN JOIN_ID to AMPP APPID
                    res = pd.merge(df_ampp, df_gtin, left_on='APPID', right_on='JOIN_ID', how='inner')
                    
                    # If that failed, try matching GTIN JOIN_ID to AMPP AMPPID
                    if res.empty and 'AMPPID' in df_ampp.columns:
                        res = pd.merge(df_ampp, df_gtin, left_on='AMPPID', right_on='JOIN_ID', how='inner')
                    
                    if not res.empty:
                        if 'JOIN_ID' in res.columns: res = res.drop(columns=['JOIN_ID'])
                        
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            res.to_excel(writer, index=False, sheet_name='GTIN_Mapped')
                            ws = writer.sheets['GTIN_Mapped']
                            last_col = get_column_letter(res.shape[1])
                            tab = Table(displayName="TRUD", ref=f"A1:{last_col}{len(res)+1}")
                            tab.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
                            ws.add_table(tab)
                        
                        st.download_button("📥 Download Mapped Excel", output.getvalue(), "TRUD_GTIN_Mapped.xlsx", use_container_width=True)
                        status.update(label="Success!", state="complete")
                        st.balloons()
                    else:
                        st.warning("Still no matches. Ensure the uploaded ZIP contains the matching GTIN release for this dm+d week.")
        except Exception as e:
            st.error(f"Error: {e}")
