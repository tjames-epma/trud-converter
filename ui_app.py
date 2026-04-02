import streamlit as st
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
import io
import re

# 1. Page Config - Must be absolute first
st.set_page_config(page_title="TRUD Data Toolkit", page_icon="💊", layout="wide")

# 2. Simple Password Gate (More stable than on_change)
if "password_correct" not in st.session_state:
    st.title("🔐 Access Required")
    pwd = st.text_input("Enter Password", type="password")
    if st.button("Sign In"):
        if "auth" in st.secrets and pwd == st.secrets["auth"]["password"]:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("Invalid Password")
    st.stop()

# 3. Processing Logic
def get_sheet_name(tag, fn):
    t = tag.split('}')[-1]
    if "f_ampp" in fn:
        m = {"AMPP": "AmppType", "PACK_INFO": "PackInfoType", "CONTENT": "ContentType", 
             "PRESC_INFO": "PrescInfoType", "PRICE_INFO": "PriceInfoType", "REIMB_INFO": "ReimbInfoType"}
        return m.get(t, t)
    return t.replace("Type", "")

def process_xml(xml_data, fn):
    try:
        # Use streaming to keep RAM usage under 1GB
        rows_by_sheet = {}
        for event, elem in ET.iterparse(xml_data, events=("end",)):
            tag = elem.tag.split('}')[-1]
            sheet = get_sheet_name(tag, fn)
            
            # If element has children, it's a data row
            if len(elem) > 0:
                data = {c.tag.split('}')[-1]: (c.text if c.text else "") for c in elem}
                if sheet not in rows_by_sheet: rows_by_sheet[sheet] = []
                rows_by_sheet[sheet].append(data)
            elem.clear()

        final = {}
        for s, r in rows_by_sheet.items():
            df = pd.DataFrame(r).drop_duplicates()
            
            # FORCE ABBREVNM COLUMN
            if s in ["AmppType", "VMP", "VTM"] and "ABBREVNM" not in df.columns:
                df["ABBREVNM"] = ""
            
            if len(df.columns) > 1:
                # Column Order
                cols = list(df.columns)
                head = [c for c in ["APPID", "AMPPID", "NM", "ABBREVNM"] if c in cols]
                rest = [c for c in cols if c not in head]
                final[s] = df[head + rest]
        return final
    except: return {}

# 4. Main UI
st.title("💊 TRUD Data Toolkit")
uploaded = st.file_uploader("Upload TRUD ZIP", type="zip")

if uploaded:
    mode = st.radio("Action", ["📦 Bulk Export", "🔗 GTIN Mapper"])
    
    if st.button("🚀 Run Processor", use_container_width=True):
        with st.status("Processing..."):
            try:
                with zipfile.ZipFile(uploaded, 'r') as outer:
                    names = outer.namelist()
                    out_zip_buf = io.BytesIO()
                    
                    if mode == "📦 Bulk Export":
                        with zipfile.ZipFile(out_zip_buf, "w") as zout:
                            for n in names:
                                if n.lower().endswith('.xml'):
                                    sheets = process_xml(outer.open(n), n.lower())
                                    if sheets:
                                        xl_buf = io.BytesIO()
                                        with pd.ExcelWriter(xl_buf) as wr:
                                            for s_nm, s_df in sheets.items():
                                                s_df.to_excel(wr, index=False, sheet_name=s_nm[:31])
                                        
                                        clean_n = re.sub(r'\d+', '', n.split('/')[-1].split('.')[0]) + ".xlsx"
                                        zout.writestr(clean_n, xl_buf.getvalue())
                        
                        st.session_state['file'] = out_zip_buf.getvalue()
                        st.session_state['name'] = "TRUD_Export.zip"
                        
            except Exception as e:
                st.error(f"Error: {e}")

if 'file' in st.session_state:
    st.download_button("📥 Download", data=st.session_state['file'], file_name=st.session_state['name'], use_container_width=True)
