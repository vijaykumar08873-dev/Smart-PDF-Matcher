import streamlit as st
import fitz  # PyMuPDF
import zipfile
import io
import re
from PIL import Image, ImageEnhance, ImageOps
from pyzbar.pyzbar import decode
import pytesseract

def find_matching_docket(page, expected_dockets):
    # --- 1. NATIVE PDF TEXT CHECK (Sabse fast aur 100% accurate) ---
    native_text = page.get_text("text")
    clean_native = re.sub(r'[\W_]+', '', native_text)
    for expected in expected_dockets:
        if expected in native_text or expected in clean_native:
            return expected
            
    # --- Image Setup ---
    pix = page.get_pixmap(dpi=300)
    img = Image.frombytes("RGB",[pix.width, pix.height], pix.samples)
    
    # --- 2. BARCODE CHECK ---
    decoded_objects = decode(img)
    gray_img = ImageOps.grayscale(img)
    enhancer = ImageEnhance.Contrast(gray_img)
    sharp_img = enhancer.enhance(2.0)
    decoded_objects_2 = decode(sharp_img)
    
    all_barcodes = decoded_objects + decoded_objects_2
    for obj in all_barcodes:
        data = obj.data.decode('utf-8').strip()
        for expected in expected_dockets:
            if expected in data:
                return expected

    # --- 3. SMART OCR CHECK (Super Aggressive Matching 100% Fix) ---
    try:
        text1 = pytesseract.image_to_string(img)
        text2 = pytesseract.image_to_string(sharp_img)
        full_text = text1 + " \n " + text2
        
        # Tedhi images mein OCR ki common galtiya theek karke Match karna
        clean_ocr = re.sub(r'[\W_]+', '', full_text).upper()
        super_clean_ocr = clean_ocr.replace('O', '0').replace('Q', '0').replace('I', '1').replace('L', '1').replace('S', '5')
        
        for expected in expected_dockets:
            # 1. Direct check
            if expected in full_text:
                return expected
            # 2. Clean check (bina spaces ke)
            if expected in clean_ocr:
                return expected
            # 3. Super clean check (OCR errors theek karne ke baad)
            if expected in super_clean_ocr:
                return expected
    except:
        pass
        
    return None

def process_pdf(uploaded_file, docket_list_text):
    # User ki di hui raw data list ko saaf karna
    raw_dockets = docket_list_text.replace(",", "\n").split("\n")
    expected_dockets = set()
    for d in raw_dockets:
        clean_d = d.strip()
        if clean_d:
            expected_dockets.add(clean_d)
            
    found_dockets = set()
    
    pdf_document = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for page_num in range(len(pdf_document)):
            page = pdf_document.load_page(page_num)
            
            # Match finding function ko call karna
            matched_id = find_matching_docket(page, expected_dockets)
            
            if matched_id:
                file_name = f"{matched_id}.pdf"
                found_dockets.add(matched_id)
            else:
                # Unscanned wahi aayega jo aapki list mein nahi mila
                file_name = f"Unscanned_Page_{page_num + 1}.pdf"
                
            # --- SUPER COMPRESSION LOGIC (100 - 120 KB TARGET) ---
            pix_low = page.get_pixmap(dpi=130, colorspace=fitz.csGRAY)
            img_low = Image.frombytes("L",[pix_low.width, pix_low.height], pix_low.samples)
            
            img_byte_arr = io.BytesIO()
            img_low.save(img_byte_arr, format='JPEG', quality=40, optimize=True)
            img_bytes = img_byte_arr.getvalue()
            
            new_pdf = fitz.open()
            new_page = new_pdf.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, stream=img_bytes)
            
            pdf_bytes = new_pdf.write(garbage=4, deflate=True)
            new_pdf.close()
            # -----------------------------------------------------
            
            zip_file.writestr(file_name, pdf_bytes)
            
    # Pending dockets nikalna (Jo list mein the par PDF mein nahi mile)
    pending_dockets = expected_dockets - found_dockets
            
    return zip_buffer, list(found_dockets), list(pending_dockets)

# --- UI Setup ---
st.set_page_config(page_title="Smart PDF Matcher & Splitter", page_icon="🎯", layout="wide")
st.title("🎯 Smart PDF Matcher & Splitter")
st.write("Apne Dockets ki list (Raw Data) box mein daalein aur PDF upload karein. Ye app strictly aapke data se match karke rename karega.")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Enter Docket IDs")
    docket_input = st.text_area(
        "Yahan apna Row Data (Docket IDs) paste karein (Ek line mein ek ID):", 
        height=200, 
        placeholder="Example:\n7002010582\n7002010901\n7002038210..."
    )

with col2:
    st.subheader("2. Upload Main PDF")
    uploaded_pdf = st.file_uploader("Apna courier PDF upload karein", type=["pdf"])

if st.button("🚀 Match, Compress & Split PDF", use_container_width=True):
    if not docket_input.strip():
        st.error("Kripya pehle Docket IDs ka data box mein paste karein!")
    elif not uploaded_pdf:
        st.error("Kripya Main PDF file upload karein!")
    else:
        with st.spinner("Matching, Splitting & Compressing... Kripya intezaar karein..."):
            try:
                zip_data, found_list, pending_list = process_pdf(uploaded_pdf, docket_input)
                
                st.success("🎉 Process Complete! Aapki ZIP file taiyaar hai.")
                
                # Download Button
                st.download_button(
                    label="📥 Download Renamed & Compressed ZIP",
                    data=zip_data.getvalue(),
                    file_name="Matched_Dockets.zip",
                    mime="application/zip",
                    use_container_width=True
                )
                
                # --- PENDING BOX AUR RESULT REPORT YAHAN HAI ---
                st.markdown("---")
                st.header("📊 Result Report (Dhyan Se Dekhein)")
                
                # Bada Pending Box
                if pending_list:
                    st.error(f"❌ PENDING BOX: Ye {len(pending_list)} Dockets aapki PDF mein NAHI mile")
                    st.write("Inhe verify karein (Ya toh inki PDF missing hai, ya scan bilkul destroy ho chuka tha):")
                    for p in pending_list:
                        st.write(f"👉 **{p}**")
                else:
                    st.success("🎯 ALL CLEAR! Aapki list ke saare dockets PDF mein 100% mil gaye aur rename ho gaye.")
                    
                st.markdown("---")
                st.success(f"✅ MATCHED BOX: Ye {len(found_list)} Dockets successfully rename ho gaye hain")
                with st.expander("Matched Dockets ki list dekhne ke liye yahan click karein"):
                    st.write(", ".join(found_list))
                        
            except Exception as e:
                st.error(f"Kuch error aayi: {e}")
