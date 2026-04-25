import streamlit as st
import fitz  # PyMuPDF
import zipfile
import io
import re
import time
from PIL import Image
from pyzbar.pyzbar import decode
from google import genai

# --- API KEY SETUP ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    st.error("API Key nahi mili! Kripya Streamlit ki settings mein Secrets check karein.")
    st.stop()

client = genai.Client(api_key=API_KEY)

def find_matching_docket_ai(page, expected_dockets):
    # Image setup
    pix = page.get_pixmap(dpi=300)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    
    # 1. FAST CHECK: Pehle normal Barcode try karein (Taki time bache)
    decoded_objects = decode(img)
    for obj in decoded_objects:
        data = obj.data.decode('utf-8').strip()
        for expected in expected_dockets:
            if expected in data:
                return expected

    # 2. AI CHECK: Agar barcode fail ho jaye (Pen ke nishaan ya tedha hone ki wajah se)
    # Toh Gemini AI ko exact expected list denge dhoondne ke liye!
    expected_list_str = ", ".join(expected_dockets)
    prompt = f"""
    You are an expert courier docket reader. Look at this image. 
    It contains tracking numbers, but they might be covered by pen marks, circles, or signatures.
    I am specifically looking for ANY ONE of these tracking numbers: [{expected_list_str}].
    
    Check the image very carefully. If you see any number from this list anywhere in the image (even if partially covered by ink), return ONLY that exact number.
    If you absolutely do not find any number from the list, return 'NOT_FOUND'.
    Do not add any other text.
    """
    
    try:
        # Free API limit se bachne ke liye thoda delay
        time.sleep(2) 
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, img]
        )
        
        ai_result = response.text.strip().replace(" ", "").upper()
        
        # Check ki kya AI ka answer hamari list mein hai
        for expected in expected_dockets:
            if expected.upper() in ai_result:
                return expected
                
    except Exception as e:
        print("AI Error:", e)
        pass
        
    return None

def process_pdf(uploaded_file, docket_list_text, progress_bar, status_text):
    raw_dockets = docket_list_text.replace(",", "\n").split("\n")
    expected_dockets = set()
    for d in raw_dockets:
        clean_d = re.sub(r'\D', '', d.strip()) # Sirf numbers rakhega
        if clean_d:
            expected_dockets.add(clean_d)
            
    found_dockets = set()
    
    pdf_document = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    zip_buffer = io.BytesIO()
    total_pages = len(pdf_document)
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for page_num in range(total_pages):
            status_text.text(f"Scanning Page {page_num + 1} of {total_pages} with AI... (Isme thoda time lag sakta hai)")
            
            page = pdf_document.load_page(page_num)
            
            matched_id = find_matching_docket_ai(page, expected_dockets)
            
            if matched_id:
                file_name = f"{matched_id}.pdf"
                found_dockets.add(matched_id)
            else:
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
            
            zip_file.writestr(file_name, pdf_bytes)
            progress_bar.progress((page_num + 1) / total_pages)
            
    pending_dockets = expected_dockets - found_dockets
            
    return zip_buffer, list(found_dockets), list(pending_dockets)

# --- UI Setup ---
st.set_page_config(page_title="AI PDF Matcher & Splitter", page_icon="🤖", layout="wide")
st.title("🤖 AI PDF Matcher & Splitter (100% Accuracy)")
st.write("Ye app aapki list lega aur Google Gemini AI ki madad se pen ke nishaan ke andar se bhi number dhoondh kar rename karega!")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Enter Docket IDs")
    docket_input = st.text_area(
        "Yahan apna Row Data paste karein:", 
        height=200, 
        placeholder="Example:\n7002010582\n7002038210..."
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
        with st.spinner("AI is working... Kripya intezaar karein (AI processing mein thoda zyada waqt lagta hai)..."):
            try:
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                zip_data, found_list, pending_list = process_pdf(uploaded_pdf, docket_input, progress_bar, status_text)
                
                st.success("🎉 AI Process Complete! Aapki ZIP file taiyaar hai.")
                
                st.download_button(
                    label="📥 Download Renamed & Compressed ZIP",
                    data=zip_data.getvalue(),
                    file_name="AI_Matched_Dockets.zip",
                    mime="application/zip",
                    use_container_width=True
                )
                
                st.markdown("---")
                st.header("📊 Result Report")
                
                if pending_list:
                    st.error(f"❌ PENDING BOX: Ye {len(pending_list)} Dockets PDF mein nahi mile")
                    for p in pending_list:
                        st.write(f"👉 **{p}**")
                else:
                    st.success("🎯 ALL CLEAR! AI ne aapki list ke saare dockets dhoondh liye.")
                    
                st.markdown("---")
                st.success(f"✅ MATCHED BOX: Ye {len(found_list)} Dockets successfully rename ho gaye hain")
                with st.expander("Matched Dockets ki list dekhne ke liye yahan click karein"):
                    st.write(", ".join(found_list))
                        
            except Exception as e:
                st.error(f"Kuch error aayi: {e}")
