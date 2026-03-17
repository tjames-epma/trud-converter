import streamlit as st
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
import io
import re
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter

st.set_page_config(page_title="TRUD Data Toolkit", page_icon="💊", layout="wide")

# --- 1. PASSWORD GATEKEEPER ---
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

# --- 2. LOGIC FUNCTIONS ---

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
    """Splits XML into sub-files based on root children (Legacy Style)."""
    try:
        tree = ET.parse(xml_content)
        root = tree.getroot()
        tags_found = set([child.tag for child in root])
        for tag in tags_found:
            clean_tag = tag.split('}')[-1]
            records = root.findall(f".//{tag}")
            if records:
                xlsx_data = xml_to_excel_buffer(records, clean_tag)
                if xlsx_data:
                    # e.g. f_ampp2_PackInfo.xlsx
                    new_filename = f"{base_name.replace('.xml','')}_{clean_tag}.xlsx"
                    zip_out.writestr(new_filename, xlsx_data)
        return True
    except: return False

# --- 3. UI LAYOUT ---

st.title("💊 TRUD Data Toolkit (Legacy Support)")
uploaded_file = st.file_uploader("Upload the main TRUD ZIP file", type="zip")

if uploaded_file:
    date_match = re.search(r'_(\d{8})', uploaded_file.name)
    file_date = date_match.group(1) if date_match else "Export"

    mode = st.radio("**Select Mode:**", ["🔗 GTIN Mapper (Standard)", "📦 Bulk Multi-File Export (Legacy Style)"])

    if mode == "📦 Bulk Multi-File Export (Legacy Style)":
        st.divider()
        st.subheader("Filter Exports")
        
        options = ["amp", "ampp", "vmp", "vmpp", "vtm", "gtin", "ingredient", "lookup", "bnf"]
        
        # Select All / Deselect All Logic
        if 'select_all' not in st.session_state:
            st.session_state.select_all = True

        def toggle_select():
            st.session_state.select_all = not st.session_state.select_all

        st.button("Toggle Select All / None", on_click=toggle_select)
        
        selected_files = st.multiselect(
            "Which components do you want to extract?",
            options,
            default=options if st.session_state.select_all else []
        )
    else:
        selected_files = []

    if st.button("🚀 Run Processor", use_container_width=True):
        try:
            with zipfile.ZipFile(uploaded_file, 'r') as outer_zip:
                
                if "GTIN Mapper" in mode:
                    # Your existing GTIN Mapping logic here
                    st.info("Processing GTIN Mapping...")
                
                else: # --- BULK MULTI-FILE EXPORT ---
                    if not selected_files:
                        st.warning("Please select at least one component to extract.")
                        st.stop()
                        
                    with st.status("Performing Filtered Split Conversion...", expanded=True) as status:
                        bulk_zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(bulk_zip_buffer, "w") as zip_out:
                            
                            namelist = outer_zip.namelist()
                            
                            def is_selected(fname):
                                fname_lower = fname.lower()
                                return any(f"f_{opt}" in fname_lower or (opt in fname_lower and ".zip" in fname_lower) for opt in selected_files)

                            for filename in namelist:
                                if not is_selected(filename):
                                    continue
                                
                                if filename.endswith('.xml'):
                                    st.write(f"Processing `{filename}`...")
                                    with outer_zip.open(filename) as xml_f:
                                        process_complex_xml(xml_f, zip_out, filename)
                                
                                elif filename.endswith('.zip'):
                                    st.write(f"Scanning nested ZIP: `{filename}`...")
                                    with outer_zip.open(filename) as nested_data:
                                        with zipfile.ZipFile(io.BytesIO(nested_data.read())) as inner_zip:
                                            for inner_name in inner_zip.namelist():
                                                # Check if the inner XML matches the selected filters
                                                if inner_name.endswith('.xml') and any(opt in inner_name.lower() for opt in selected_files):
                                                    with inner_zip.open(inner_name) as inner_xml:
                                                        process_complex_xml(inner_xml, zip_out, inner_name)

                        status.update(label="Filtered Conversion Complete!", state="complete")
                        st.success(f"✅ Successfully processed {len(selected_files)} categories.")
                        st.download_button("📥 Download Filtered ZIP", 
                                         bulk_zip_buffer.getvalue(), 
                                         f"Filtered_Legacy_{file_date}.zip")

        except Exception as e:
            st.error(f"❌ Error: {e}")
