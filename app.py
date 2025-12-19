import streamlit as st
import pandas as pd
import numpy as np
import google.generativeai as genai
import os

# --- CẤU HÌNH TRANG ---
st.set_page_config(
    page_title="Finance Lab", 
    layout="wide", 
    initial_sidebar_state="expanded",
    page_icon="🏦"
)

# --- CẤU HÌNH API GEMINI (TỰ ĐỘNG LẤY TỪ SECRETS) ---
api_key = None
try:
    # Ưu tiên lấy từ Secrets (trên Cloud)
    api_key = st.secrets["GEMINI_API_KEY"]
except (FileNotFoundError, KeyError):
    # Fallback cho trường hợp chạy local mà chưa setup secrets
    api_key = os.getenv("GEMINI_API_KEY")

# Chỉ cấu hình nếu tìm thấy Key
if api_key:
    genai.configure(api_key=api_key)

# --- HÀM GỌI AI CHUNG (GENERIC AI FUNCTION) ---
def ask_gemini_generic(role, context_data, question_type):
    """
    Hàm gọi AI đa năng cho các phòng ban.
    - role: Vai trò của AI (VD: Senior Trader, Legal Advisor)
    - context_data: Dữ liệu đầu vào (Text hoặc số liệu)
    - question_type: Loại câu hỏi (VD: 'risk_warning', 'legal_check')
    """
    try:
        # Sử dụng model ổn định (gemini-1.5-flash hoặc gemini-pro)
        model = genai.GenerativeModel('gemini-1.5-flash') 
        
        # Xây dựng Prompt dựa trên ngữ cảnh
        prompt = f"""
        Bạn là: {role}.
        Dữ liệu hiện tại: {context_data}
        
        Nhiệm vụ:
        """
        
        if question_type == "arbitrage_check":
            prompt += "Phân tích rủi ro của cơ hội chênh lệch giá này. Cảnh báo về thanh khoản, độ trượt giá (slippage) và tốc độ khớp lệnh. Đưa ra lời khuyên ngắn gọn cho Trader mới."
        elif question_type == "hedging_advice":
            prompt += "Đóng vai 'Devil's Advocate' (Người phản biện). Hãy chỉ ra rủi ro tâm lý và tài chính nếu thị trường đi NGƯỢC lại dự đoán của người dùng. Tại sao công cụ họ chọn có thể gây tiếc nuối?"
        elif question_type == "ucp600_advice":
            prompt += "Dựa trên quy tắc UCP 600. Hãy giải thích tại sao các lỗi chứng từ trên lại nghiêm trọng và dẫn đến việc ngân hàng từ chối thanh toán? (Giải thích ngắn gọn pháp lý)."
        elif question_type == "fdi_swot":
            prompt += "Dự án có NPV dương nhưng rủi ro tỷ giá cao. Hãy phân tích SWOT nhanh về các yếu tố phi tài chính (Chính trị, lạm phát, chuyển lợi nhuận về nước) mà CFO cần lo lắng."
        elif question_type == "macro_shock":
            prompt += "Viết báo cáo ngắn (3 gạch đầu dòng) cảnh báo Chính phủ về tác động thực tế đến đời sống (Lạm phát, Xăng dầu, Thuế) do nợ công tăng."

        prompt += "\n\nVăn phong: Chuyên nghiệp, ngắn gọn, đi thẳng vào vấn đề. Định dạng rõ ràng."
        
        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg:
            return "⚠️ Hệ thống AI đang quá tải (Hết quota miễn phí). Vui lòng thử lại sau."
        elif "404" in error_msg:
            return "⚠️ Lỗi Model: Tài khoản của bạn chưa hỗ trợ model này. Hãy thử tạo Key mới."
        else:
            return f"⚠️ Lỗi kết nối: {error_msg}"

# --- CSS GIAO DIỆN (THEME XANH DƯƠNG CHUYÊN NGHIỆP) ---
st.markdown("""
<style>
    /* Card Vai diễn */
    .role-card {
        background-color: #e3f2fd;
        border-left: 6px solid #1565c0;
        padding: 20px;
        border-radius: 8px;
        margin-bottom: 25px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .role-title { 
        color: #1565c0; 
        font-weight: bold; 
        font-size: 20px; 
        margin-bottom: 8px;
        display: flex;
        align-items: center;
    }
    .mission-text { color: #424242; font-style: italic; font-size: 16px; line-height: 1.5; }
    
    /* Header phòng ban */
    .header-style { 
        font-size: 28px; font-weight: bold; color: #0d47a1; 
        border-bottom: 2px solid #eee; padding-bottom: 15px; margin-bottom: 25px;
    }
    
    /* Box kết quả & Giải thích */
    .result-box { background-color: #f1f8e9; padding: 15px; border-radius: 5px; border: 1px solid #c5e1a5; color: #33691e; font-weight: bold;}
    
    /* FIX LỖI HIỂN THỊ: Thêm color: #333 để chữ luôn đen */
    .step-box { 
        background-color: #fafafa; 
        color: #333333; 
        padding: 15px; 
        border-radius: 5px; 
        border: 1px dashed #bdbdbd; 
        margin-bottom: 10px; 
    }
    
    .explanation-box { background-color: #fff8e1; padding: 15px; border-radius: 5px; border-left: 4px solid #ffb300; margin-top: 10px; }
    
    /* SỬA LỖI 2: CSS AI Box - Ép màu chữ đen (#333) */
    .ai-box {
        background-color: #fff3e0;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #ff9800;
        margin-top: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        color: #333333 !important; /* Quan trọng: Ép màu chữ đen */
    }
    .ai-box h4 {
        color: #e65100 !important;
        font-weight: bold;
        margin-bottom: 10px;
    }
    .ai-box p, .ai-box li {
        color: #333333 !important; /* Đảm bảo nội dung con cũng màu đen */
    }
    
    /* Copyright Footer */
    .copyright {
        font-size: 12px;
        color: #888;
        text-align: center;
        margin-top: 50px;
    }
</style>
""", unsafe_allow_html=True)

st.title("🏦 INTERNATIONAL FINANCE LAB")
st.caption("Hệ thống Mô phỏng Nghiệp vụ Tài chính Quốc tế (AI Integrated)")

# --- MENU NAVIGATION (SIDEBAR CHUẨN) ---
with st.sidebar:
    st.header("🏢 SƠ ĐỒ TỔ CHỨC")
    st.write("Di chuyển đến:")
    
    room = st.radio(
        "Phòng nghiệp vụ:",
        [
            "1. Sàn Kinh doanh Ngoại hối (Dealing Room)",
            "2. Phòng Quản trị Rủi ro (Risk Management)",
            "3. Phòng Thanh toán Quốc tế (Trade Finance)",
            "4. Phòng Đầu tư Quốc tế (Investment Dept)",
            "5. Ban Chiến lược Vĩ mô (Macro Strategy)"
        ],
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    st.info("💡 **Tips:** Các phòng ban hiện đã có nút **'🤖 Hỏi AI'** để nhận tư vấn chuyên sâu.")
    
    # --- BẢN QUYỀN (Copyright) ---
    st.markdown("---")
    st.caption("© Copyright 2026 - Nguyễn Minh Hải")

# ==============================================================================
# PHÒNG 1: DEALING ROOM
# ==============================================================================
if "1." in room:
    st.markdown('<p class="header-style">💱 Sàn Kinh doanh Ngoại hối (Dealing Room)</p>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="role-card">
        <div class="role-title">👤 Vai diễn: Chuyên viên Kinh doanh Tiền tệ (FX Trader)</div>
        <div class="mission-text">"Nhiệm vụ: Niêm yết tỷ giá chéo (Cross-rate) và thực hiện kinh doanh chênh lệch giá (Arbitrage) khi phát hiện thị trường mất cân bằng."</div>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["🔢 Niêm yết Tỷ giá Chéo", "⚡ Săn Arbitrage (Tam giác)"])
    
    with tab1:
        # Code cũ của Tab 1
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Thị trường 1: USD/VND")
            usd_bid = st.number_input("BID (NH Mua vào):", value=25350.0, step=10.0)
            usd_ask = st.number_input("ASK (NH Bán ra):", value=25450.0, step=10.0)
        with c2:
            st.subheader("Thị trường 2: EUR/USD")
            eur_bid = st.number_input("BID (NH Mua EUR):", value=1.0820, format="%.4f")
            eur_ask = st.number_input("ASK (NH Bán EUR):", value=1.0850, format="%.4f")
            
        if st.button("🚀 TÍNH TOÁN & NIÊM YẾT"):
            cross_bid = eur_bid * usd_bid
            cross_ask = eur_ask * usd_ask
            spread = cross_ask - cross_bid
            st.success(f"✅ TỶ GIÁ EUR/VND NIÊM YẾT: {cross_bid:,.0f} - {cross_ask:,.0f}")
            st.info(f"Spread (Chênh lệch giá): {spread:,.0f} VND")
            
            with st.expander("🎓 GIẢI THÍCH CÔNG THỨC"):
                st.write("Bid chéo = Bid 1 x Bid 2 (Nguyên tắc: Ngân hàng luôn mua thấp)")

    with tab2:
        st.write("Vốn kinh doanh: **1,000,000 USD**")
        k1, k2, k3 = st.columns(3)
        with k1: bank_a = st.number_input("Bank A (USD/VND):", value=25000.0)
        with k2: bank_b = st.number_input("Bank B (EUR/USD):", value=1.1000)
        with k3: bank_c = st.number_input("Bank C (EUR/VND):", value=28000.0)
        
        col_calc, col_ai_1 = st.columns([1, 1])
        with col_calc:
            btn_calc = st.button("🔍 CHẠY MÔ HÌNH DÒNG TIỀN")
        
        # Biến tạm để lưu kết quả cho AI
        profit = 0
        
        if btn_calc:
            step1_eur = 1000000 / bank_b
            step2_vnd = step1_eur * bank_c
            step3_usd = step2_vnd / bank_a
            profit = step3_usd - 1000000
            
            st.markdown("### 📝 Nhật ký giao dịch:")
            st.markdown(f"""
            <div class="step-box">
            1. USD -> EUR: {step1_eur:,.2f} EUR<br>
            2. EUR -> VND: {step2_vnd:,.0f} VND<br>
            3. VND -> USD: {step3_usd:,.2f} USD
            </div>
            """, unsafe_allow_html=True)
            
            if profit > 0:
                st.markdown(f'<div class="result-box">🎉 LỢI NHUẬN: +{profit:,.2f} USD</div>', unsafe_allow_html=True)
            else:
                st.error(f"⚠️ THUA LỖ: {profit:,.2f} USD")
        
        # --- AI INTEGRATION ROOM 1 ---
        st.markdown("---")
        if st.button("🤖 AI TRADER: ĐÁNH GIÁ CƠ HỘI NÀY"):
            if not api_key:
                st.warning("⚠️ Cần nhập API Key để dùng AI.")
            else:
                # Tính lại để lấy số liệu mới nhất đưa vào Prompt
                s1 = 1000000 / bank_b
                s2 = s1 * bank_c
                s3 = s2 / bank_a
                prof = s3 - 1000000
                
                context = f"Vốn 1tr USD. Lợi nhuận Arbitrage tính toán: {prof:,.2f} USD. Tỷ giá các chặng: {bank_a}, {bank_b}, {bank_c}."
                
                with st.spinner("Senior Trader đang phân tích thanh khoản..."):
                    advice = ask_gemini_generic("Senior FX Trader", context, "arbitrage_check")
                    st.markdown(f'<div class="ai-box"><h4>🤖 LỜI KHUYÊN TỪ SENIOR TRADER</h4>{advice}</div>', unsafe_allow_html=True)

# ==============================================================================
# PHÒNG 2: RISK MANAGEMENT
# ==============================================================================
elif "2." in room:
    st.markdown('<p class="header-style">🛡️ Phòng Quản trị Rủi ro (Risk Management)</p>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="role-card">
        <div class="role-title">👤 Vai diễn: Giám đốc Tài chính (CFO)</div>
        <div class="mission-text">"Nhiệm vụ: Tính toán tỷ giá kỳ hạn (Forward) và chọn công cụ phòng vệ (Hedging)."</div>
    </div>
    """, unsafe_allow_html=True)

    # 1. IRP
    st.subheader("1. Tính toán Tỷ giá Forward")
    col_irp1, col_irp2 = st.columns(2)
    with col_irp1:
        spot_irp = st.number_input("Spot Rate:", value=25000.0)
        days = st.number_input("Kỳ hạn (Ngày):", value=90)
    with col_irp2:
        r_vnd = st.number_input("Lãi suất VND (%):", value=6.0)
        r_usd = st.number_input("Lãi suất USD (%):", value=3.0)
        
    fwd_cal = spot_irp * (1 + (r_vnd/100)*(days/360)) / (1 + (r_usd/100)*(days/360))
    st.success(f"👉 Tỷ giá Forward lý thuyết: **{fwd_cal:,.2f} VND/USD**")

    st.markdown("---")
    st.subheader("2. Ra quyết định Hedging")
    
    c1, c2 = st.columns([1, 2])
    with c1:
        f_rate_input = st.number_input("Giá Forward ký với NH:", value=fwd_cal)
        strike = st.number_input("Strike Price (Option):", value=25200.0)
        premium = st.number_input("Phí Option (VND/USD):", value=150.0)
    with c2:
        future_spot = st.slider("Dự báo Spot ngày đáo hạn:", 24000.0, 26000.0, 25300.0)
        
        # Logic tính toán
        cost_open = 1000000 * future_spot
        cost_fwd = 1000000 * f_rate_input
        if future_spot > strike:
            final_opt = strike
        else:
            final_opt = future_spot
        cost_opt = (1000000 * final_opt) + (1000000 * premium)
        
        df = pd.DataFrame({
            "Chiến lược": ["Open (Không làm gì)", "Forward", "Option"],
            "Tổng chi phí": [cost_open, cost_fwd, cost_opt]
        })
        st.table(df)
        
        # --- AI INTEGRATION ROOM 2 ---
        st.markdown("---")
        if st.button("🤖 AI RISK: PHẢN BIỆN KỊCH BẢN (WHAT-IF)"):
            if not api_key:
                st.warning("⚠️ Cần nhập API Key.")
            else:
                best_choice = df.loc[df['Tổng chi phí'].idxmin()]['Chiến lược']
                context = f"""
                User dự báo tỷ giá tương lai là {future_spot}. 
                Dựa trên dự báo này, chiến lược rẻ nhất là: {best_choice}.
                Spot hiện tại: {spot_irp}. Forward: {f_rate_input}. Strike: {strike}.
                """
                with st.spinner("Risk Manager đang chạy mô phỏng rủi ro..."):
                    advice = ask_gemini_generic("Risk Manager", context, "hedging_advice")
                    st.markdown(f'<div class="ai-box"><h4>🤖 GÓC NHÌN QUẢN TRỊ RỦI RO</h4>{advice}</div>', unsafe_allow_html=True)

# ==============================================================================
# PHÒNG 3: TRADE FINANCE
# ==============================================================================
elif "3." in room:
    st.markdown('<p class="header-style">🚢 Phòng Thanh toán Quốc tế (Trade Finance)</p>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="role-card">
        <div class="role-title">👤 Vai diễn: Chuyên viên Thanh toán Quốc tế</div>
        <div class="mission-text">"Nhiệm vụ: Tư vấn phương thức thanh toán và kiểm tra bộ chứng từ (Checking) theo UCP 600."</div>
    </div>
    """, unsafe_allow_html=True)
    
    tab_cost, tab_check = st.tabs(["💰 L/C vs T/T", "📝 Kiểm tra Chứng từ"])
    
    with tab_cost:
        st.info("Tính phí giao dịch (Đã có sẵn logic cũ)")
        val = st.number_input("Giá trị HĐ (USD):", value=100000)
        st.write(f"Phí L/C ước tính: {val * 0.01 + 100:,.2f} USD")

    with tab_check:
        c1, c2 = st.columns(2)
        with c1: 
            ship_last = st.date_input("Hạn giao hàng:", value=pd.to_datetime("2025-01-01"))
            lc_exp = st.date_input("Hạn L/C:", value=pd.to_datetime("2025-02-15"))
        with c2:
            bl_date = st.date_input("Ngày vận đơn (B/L):", value=pd.to_datetime("2025-01-05"))
            pres_date = st.date_input("Ngày xuất trình:", value=pd.to_datetime("2025-02-01"))
            
        errs = []
        if bl_date > ship_last: errs.append("Late Shipment (Giao trễ)")
        if pres_date > lc_exp: errs.append("L/C Expired (L/C hết hạn)")
        if (pres_date - bl_date).days > 21: errs.append("Stale Documents (Chứng từ quá hạn 21 ngày)")
        
        if st.button("KIỂM TRA CHỨNG TỪ"):
            if errs:
                for e in errs: st.error(f"❌ {e}")
            else:
                st.success("✅ Bộ chứng từ hợp lệ (Clean Docs)")

        # --- AI INTEGRATION ROOM 3 ---
        st.markdown("---")
        if st.button("🤖 AI LEGAL: TƯ VẤN LUẬT UCP 600"):
            if not api_key:
                st.warning("⚠️ Cần API Key.")
            else:
                if not errs:
                    context = "Bộ chứng từ sạch, không có lỗi."
                else:
                    context = f"Bộ chứng từ mắc các lỗi sau: {', '.join(errs)}."
                
                with st.spinner("Luật sư đang tra cứu UCP 600..."):
                    advice = ask_gemini_generic("Legal Advisor (UCP 600 Expert)", context, "ucp600_advice")
                    st.markdown(f'<div class="ai-box"><h4>🤖 TƯ VẤN PHÁP LÝ (UCP 600)</h4>{advice}</div>', unsafe_allow_html=True)

# ==============================================================================
# PHÒNG 4: INVESTMENT DEPT
# ==============================================================================
elif "4." in room:
    st.markdown('<p class="header-style">🏭 Phòng Đầu tư Quốc tế (Investment Dept)</p>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="role-card">
        <div class="role-title">👤 Vai diễn: Chuyên viên Phân tích Đầu tư</div>
        <div class="mission-text">"Nhiệm vụ: Thẩm định dự án FDI bằng mô hình DCF, tính đến sự trượt giá của đồng nội tệ."</div>
    </div>
    """, unsafe_allow_html=True)
    
    c1, c2 = st.columns(2)
    with c1:
        inv = st.number_input("Vốn đầu tư (USD):", value=1000000)
        cf = st.number_input("Dòng tiền ròng/năm (USD):", value=400000)
        years = st.slider("Số năm:", 1, 10, 3)
    with c2:
        fx = st.number_input("Tỷ giá Spot:", value=25000.0)
        depre = st.number_input("Mức mất giá VND (%/năm):", value=3.0)
        wacc = st.number_input("WACC (%):", value=12.0)
        
    if st.button("📊 TÍNH TOÁN NPV"):
        total_pv = 0
        cf0_vnd = -inv * fx
        
        # Logic tính NPV
        for i in range(1, years + 1):
            fx_future = fx * ((1 + depre/100) ** i)
            cf_vnd = cf * fx_future
            pv = cf_vnd / ((1 + wacc/100) ** i)
            total_pv += pv
            
        npv = total_pv + cf0_vnd
        st.markdown(f"### 🏁 NPV DỰ ÁN: {npv:,.0f} VND")
        
        if npv > 0:
            st.success("Dự án khả thi về mặt tài chính.")
        else:
            st.error("Dự án không khả thi.")

    # --- AI INTEGRATION ROOM 4 ---
    st.markdown("---")
    if st.button("🤖 AI ANALYST: PHÂN TÍCH SWOT & VĨ MÔ"):
        if not api_key:
            st.warning("⚠️ Cần API Key.")
        else:
            context = f"Vốn {inv}$. Dòng tiền {cf}$/năm. Mất giá nội tệ dự báo: {depre}%/năm. WACC: {wacc}%."
            with st.spinner("Chuyên gia đang đánh giá rủi ro phi tài chính..."):
                advice = ask_gemini_generic("Strategic Analyst", context, "fdi_swot")
                st.markdown(f'<div class="ai-box"><h4>🤖 PHÂN TÍCH CHIẾN LƯỢC</h4>{advice}</div>', unsafe_allow_html=True)

# ==============================================================================
# PHÒNG 5: MACRO STRATEGY
# ==============================================================================
elif "5." in room:
    st.markdown('<p class="header-style">📉 Ban Chiến lược Vĩ mô (Macro Strategy)</p>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="role-card">
        <div class="role-title">👤 Vai diễn: Cố vấn Kinh tế Chính phủ</div>
        <div class="mission-text">"Nhiệm vụ: Đánh giá tác động của cú sốc tỷ giá lên nợ công và đề xuất chính sách."</div>
    </div>
    """, unsafe_allow_html=True)
    
    debt = st.number_input("Tổng nợ nước ngoài (Tỷ USD):", value=50.0)
    base_rate = 25000
    shock = st.slider("Mức độ mất giá nội tệ (%):", 0, 50, 10)
    
    new_rate = base_rate * (1 + shock/100)
    debt_old = debt * base_rate
    debt_new = debt * new_rate
    diff = debt_new - debt_old
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Tỷ giá mới", f"{new_rate:,.0f}")
    c2.metric("Nợ công quy đổi", f"{debt_new:,.0f} Tỷ VND")
    c3.metric("Gánh nặng tăng thêm", f"{diff:,.0f} Tỷ VND", delta_color="inverse")
    
    st.markdown("---")
    if st.button("🤖 YÊU CẦU CỐ VẤN AI SOẠN BÁO CÁO", type="primary"):
        if not api_key:
            st.warning("⚠️ Cần API Key.")
        else:
            context = f"Tỷ giá tăng {shock}%. Nợ công tăng thêm {diff:,.0f} Tỷ VND."
            with st.spinner("Đang soạn thảo báo cáo..."):
                # Gọi hàm generic với type macro_shock
                report = ask_gemini_generic("Economic Advisor", context, "macro_shock")
                st.markdown(f'<div class="ai-box"><h4>📜 BÁO CÁO CỦA CỐ VẤN KINH TẾ</h4>{report}</div>', unsafe_allow_html=True)
