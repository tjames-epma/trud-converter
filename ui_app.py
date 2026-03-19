import streamlit as st
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
import io
import re
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter

# 1. Page Configuration
st.set_page_config(page_title="TRUD Data Toolkit", page_icon="💊", layout="wide")

# --- 2. PASSWORD GATEKEEPER ---
def check_password():
    if "auth" not in st.secrets:
        st.sidebar.warning("🔓 Local Mode: No secrets found.")
        return True
    def password_entered():
        if st.session_state["password_input"] == st.secrets["auth"]["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password_input"]
        else:
            st.session_state["password_correct"] = False
    if "password_correct" not in st.session_state:
        st.text_input("Please enter the access password", type="password", on_change=password_entered, key="password_input")
        return False
    return st.session_state.get("password_correct", False)

if not check_password():
    st.stop()

# --- 3. LOGIC FUNCTIONS ---

def xml_to_excel_buffer(element_list, sheet_name):
    rows = []
    for record in element_list:
        entry = {child.tag.split('}')[-1]: child.text for child in record if child.text}
        if entry: rows.append(entry)
    if not rows: return None
    df = pd.DataFrame(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    return output.getvalue()

def process_complex_xml(xml_content, zip_out, base_name):
    try:
        tree = ET.parse(xml_content)
        root = tree.getroot()
        tags_found = set([child.tag for child in root])
        local_count = 0
        for tag in tags_found:
            clean_tag = tag.split('}')[-1]
            records = root.findall(f".//{tag}")
            if records:
                xlsx_data = xml_to_excel_buffer(records, clean_tag)
                if xlsx_data:
                    fn = base_name.split('/')[-1].replace('.xml', '')
                    new_filename = f"{fn}_{clean_tag}.xlsx"
                    zip_out.writestr(new_filename, xlsx_data)
                    local_count += 1
        return local_count
    except: return 0

# --- 4. SIDEBAR LOGIC ---
def render_sidebar():
    with st.sidebar:
        st.title("Settings & Info")
        if 'mapped_df' in st.session_state:
            st.divider()
            st.subheader("🔍 Live Search Preview")
            q = st.text_input("Search by Name or ID", key="active_search")
            df = st.session_state['mapped_df']
            id_col = st.session_state['id_col']
            if q:
                filtered = df[df['NM'].str.contains(q, case=False, na=False) | df[id_col].str.contains(q, case=False, na=False)]
                st.dataframe(filtered[['NM', 'GTIN', id_col]].head(10), hide_index=True)
            else:
                st.dataframe(df[['NM', 'GTIN', id_col]].head(10), hide_index=True)
        st.divider()
        st.caption("v3.1 | Sticky Button Build")

# --- 5. MAIN UI ---
st.title("💊 TRUD Data Toolkit")
render_sidebar()

uploaded_file = st.file_uploader("Upload TRUD ZIP", type="zip")

if uploaded_file:
    # Clear previous results if a new file is uploaded
    if "last_uploaded" not in st.session_state or st.session_state.last_uploaded != uploaded_file.name:
        st.session_state.last_uploaded = uploaded_file.name
        if 'zip_data' in st.session_state: del st.session_state['zip_data']
        if 'mapped_df' in st.session_state: del st.session_state['mapped_df']

    date_match = re.search(r'_(\d{8})', uploaded_file.name)
    file_date = date_match.group(1) if date_match else "Processed"

    mode = st.radio("**Select Action:**", ["🔗 GTIN Mapper", "📦 Bulk Multi-File (Legacy)"])

    if mode == "📦 Bulk Multi-File (Legacy)":
        options = ["amp", "ampp", "vmp", "vmpp", "vtm", "gtin", "ingredient", "lookup"]
        if 'sel_all' not in st.session_state: st.session_state.sel_all = True
        if st.button("Toggle Select All/None"): 
            st.session_state.sel_all = not st.session_state.sel_all
            st.rerun()
        selected_files = st.multiselect("Select components:", options, default=options if st.session_state.sel_all else [])

    # Action Button
    if st.button("🚀 Run Processor", use_container_width=True):
        try:
            with zipfile.ZipFile(uploaded_file, 'r') as outer_zip:
                all_names = outer_zip.namelist()
                
                if mode == "🔗 GTIN Mapper":
                    with st.status("Mapping...", expanded=True):
                        ampp_file = [f for f in all_names if 'f_ampp2' in f.lower()][0]
                        tree = ET.parse(outer_zip.open(ampp_file))
                        root = tree.getroot()
                        ampp_rows = [{child.tag.split('}')[-1]: child.text for child in record} for record in root.findall(".//{*}AMPP")]
                        df_ampp = pd.DataFrame(ampp_rows)
                        id_col = next((c for c in ['AMPPID', 'APPID', 'APID'] if c in df_ampp.columns), None)
                        
                        gtin_zip = [f for f in all_names if 'gtin' in f.lower()][0]
                        with outer_zip.open(gtin_zip) as zd:
                            with zipfile.ZipFile(io.BytesIO(zd.read())) as iz:
                                g_xml = [f for f in iz.namelist() if f.endswith('.xml')][0]
                                g_root = ET.parse(iz.open(g_xml)).getroot()
                                g_rows = []
                                for b in g_root.findall(".//{*}AMPP"):
                                    id_v = b.find(".//{*}AMPPID").text if b.find(".//{*}AMPPID") is not None else b.find(".//{*}APPID").text
                                    for g in b.findall(".//{*}GTINDATA"):
                                        ge = g.find(".//{*}GTIN")
                                        if ge is not None: g_rows.append({'JOIN_ID': id_v, 'GTIN': ge.text})
                                df_gtin = pd.DataFrame(g_rows)

                        final_df = pd.merge(df_ampp, df_gtin, left_on=id_col, right_on='JOIN_ID', how='left').dropna(subset=['GTIN'])
                        st.session_state['mapped_df'] = final_df
                        st.session_state['id_col'] = id_col
                        
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            final_df.to_excel(writer, index=False)
                        st.session_state['zip_data'] = output.getvalue()
                        st.session_state['file_name'] = f"TRUD_GTIN_{file_date}.xlsx"

                else: # BULK LEGACY
                    with st.status("Processing...", expanded=True):
                        buf = io.BytesIO()
                        count = 0
                        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
                            for f in all_names:
                                if any(f"f_{o}" in f.lower() for o in selected_files) and f.endswith('.xml'):
                                    count += process_complex_xml(outer_zip.open(f), zout, f)
                                elif f.lower().endswith('.zip') and any(o in f.lower() for o in selected_files):
                                    with outer_zip.open(f) as nd:
                                        with zipfile.ZipFile(io.BytesIO(nd.read())) as iz:
                                            for iname in iz.namelist():
                                                if iname.endswith('.xml'):
                                                    count += process_complex_xml(iz.open(iname), zout, iname)
                        st.session_state['zip_data'] = buf.getvalue()
                        st.session_state['file_name'] = f"Legacy_Split_{file_date}.zip"
                        st.session_state['count'] = count
            st.rerun() # Refresh to show the sticky download button
        except Exception as e:
            st.error(f"❌ Error: {e}")

    # 6. STICKY DOWNLOAD SECTION (This stays on screen)
    if 'zip_data' in st.session_state:
        st.divider()
        st.success(f"✅ Processing Complete! {st.session_state.get('count', '')} files ready.")
        st.download_button(
            label=f"📥 Download {st.session_state['file_name']}",
            data=st.session_state['zip_data'],
            file_name=st.session_state['file_name'],
            mime="application/zip" if mode != "🔗 GTIN Mapper" else "application/vnd.ms-excel",
            use_container_width=True
        )
