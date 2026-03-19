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

def xml_to_excel_buffer(df, sheet_name):
    """Converts a DataFrame to an Excel file buffer."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    return output.getvalue()

def split_and_zip_xml(xml_content, zip_out, base_name):
    """
    Robustly splits any XML by its top-level record tags.
    Ensures all sub-tables (PackInfo, PriceInfo, etc.) are captured.
    """
    try:
        tree = ET.parse(xml_content)
        root = tree.getroot()
        data_map = {}
        
        # Iterate over records (direct children of the root)
        for record in root:
            tag_name = record.tag.split('}')[-1]
            row = {child.tag.split('}')[-1]: child.text for child in record if child.text is not None}
            if row:
                if tag_name not in data_map:
                    data_map[tag_name] = []
                data_map[tag_name].append(row)
        
        files_count = 0
        for tag, rows in data_map.items():
            df = pd.DataFrame(rows)
            xlsx_data = xml_to_excel_buffer(df, tag)
            prefix = base_name.split('/')[-1].split('\\')[-1].replace('.xml', '')
            new_fn = f"{prefix}_{tag}.xlsx"
            zip_out.writestr(new_fn, xlsx_data)
            files_count += 1
        return files_count
    except Exception as e:
        return 0

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
                filtered = df[df['NM'].astype(str).str.contains(q, case=False, na=False) | 
                              df[id_col].astype(str).str.contains(q, case=False, na=False)]
                st.dataframe(filtered[['NM', 'GTIN', id_col]].head(10), hide_index=True)
            else:
                st.dataframe(df[['NM', 'GTIN', id_col]].head(10), hide_index=True)
        st.divider()
        st.caption("v3.3 | Stability Fix")

# --- 5. MAIN UI ---
st.title("💊 TRUD Data Toolkit")
render_sidebar()

uploaded_file = st.file_uploader("Upload TRUD ZIP", type="zip")

if uploaded_file:
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

    if st.button("🚀 Run Processor", use_container_width=True):
        try:
            with zipfile.ZipFile(uploaded_file, 'r') as outer_zip:
                all_names = outer_zip.namelist()
                
                if mode == "🔗 GTIN Mapper":
                    with st.status("Mapping...", expanded=True):
                        ampp_file = [f for f in all_names if 'f_ampp2' in f.lower() and f.endswith('.xml')][0]
                        ampp_tree = ET.parse(outer_zip.open(ampp_file))
                        ampp_rows = []
                        for record in ampp_tree.getroot().findall(".//{*}AMPP"):
                            ampp_rows.append({c.tag.split('}')[-1]: c.text for c in record})
                        df_ampp = pd.DataFrame(ampp_rows)
                        
                        id_col = next((c for c in ['AMPPID', 'APPID', 'APID'] if c in df_ampp.columns), None)
                        if not id_col:
                            st.error(f"Could not find an ID column in AMPP file. Found: {list(df_ampp.columns)}")
                            st.stop()
                        
                        gtin_zip_path = [f for f in all_names if 'gtin' in f.lower() and f.endswith('.zip')][0]
                        with outer_zip.open(gtin_zip_path) as zd:
                            with zipfile.ZipFile(io.BytesIO(zd.read())) as iz:
                                g_xml = [f for f in iz.namelist() if f.endswith('.xml')][0]
                                g_root = ET.parse(iz.open(g_xml)).getroot()
                                g_rows = []
                                for b in g_root.findall(".//{*}AMPP"):
                                    id_found = b.find(".//{*}AMPPID")
                                    if id_found is None: id_found = b.find(".//{*}APPID")
                                    if id_found is not None:
                                        id_v = id_found.text
                                        for g in b.findall(".//{*}GTINDATA"):
                                            ge = g.find(".//{*}GTIN")
                                            if ge is not None: g_rows.append({'JOIN_ID': id_v, 'GTIN': ge.text})
                                df_gtin = pd.DataFrame(g_rows)

                        final_df = pd.merge(df_ampp, df_gtin, left_on=id_col, right_on='JOIN_ID', how='left').dropna(subset=['GTIN'])
                        if 'JOIN_ID' in final_df.columns: final_df = final_df.drop(columns=['JOIN_ID'])
                        st.session_state['mapped_df'] = final_df
                        st.session_state['id_col'] = id_col
                        
                        excel_buf = io.BytesIO()
                        with pd.ExcelWriter(excel_buf, engine='openpyxl') as writer:
                            final_df.to_excel(writer, index=False)
                        st.session_state['zip_data'] = excel_buf.getvalue()
                        st.session_state['file_name'] = f"TRUD_GTIN_{file_date}.xlsx"
                        st.session_state['count'] = len(final_df)

                else: # --- BULK LEGACY ---
                    with st.status("Processing...", expanded=True):
                        buf = io.BytesIO()
                        total_count = 0
                        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
                            for f in all_names:
                                fn_l = f.lower()
                                if any(f"f_{o}" in fn_l for o in selected_files) and f.endswith('.xml'):
                                    st.write(f"📂 Splitting: `{f}`")
                                    total_count += split_and_zip_xml(outer_zip.open(f), zout, f)
                                elif fn_l.endswith('.zip') and any(o in fn_l for o in selected_files):
                                    st.write(f"📦 Sub-zip: `{f}`")
                                    with outer_zip.open(f) as nd:
                                        with zipfile.ZipFile(io.BytesIO(nd.read())) as iz:
                                            for iname in iz.namelist():
                                                if iname.endswith('.xml'):
                                                    total_count += split_and_zip_xml(iz.open(iname), zout, iname)
                        
                        if total_count > 0:
                            st.session_state['zip_data'] = buf.getvalue()
                            st.session_state['file_name'] = f"Legacy_Split_{file_date}.zip"
                            st.session_state['count'] = total_count
                        else:
                            st.error("No data found to extract.")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error: {e}")

    if 'zip_data' in st.session_state:
        st.divider()
        st.success(f"✅ Ready! {st.session_state.get('count', 0)} items/files generated.")
        st.download_button(
            label=f"📥 Download {st.session_state['file_name']}",
            data=st.session_state['zip_data'],
            file_name=st.session_state['file_name'],
            mime="application/zip" if "Legacy" in mode else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
