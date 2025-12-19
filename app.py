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

# Hàm gọi AI (Được cache để tối ưu)
def ask_gemini_macro(debt_increase, shock_percent, new_rate):
    """Hàm gọi AI để phân tích vĩ mô"""
    try:
        # SỬA LỖI 1: Dùng 'gemini-pro' thay vì 'gemini-1.5-flash' để tương thích tốt hơn
        model = genai.GenerativeModel('gemini-2.0-flash') 
        
        prompt = f"""
        Đóng vai một Cố vấn Kinh tế cấp cao của Chính phủ (Economic Advisor).
        
        Tình huống hiện tại:
        - Đồng nội tệ vừa mất giá: {shock_percent}%
        - Tỷ giá mới: {new_rate:,.0f} VND/USD
        - Hậu quả tài khóa: Gánh nặng nợ công quốc gia vừa tăng thêm {debt_increase:,.0f} Tỷ VND do chênh lệch tỷ giá.
        
        Yêu cầu:
        Hãy viết một báo cáo ngắn gọn (khoảng 3 gạch đầu dòng lớn) cảnh báo Chính phủ về 3 tác động thực tế đến đời sống người dân và doanh nghiệp (Ví dụ: Lạm phát nhập khẩu, Giá xăng dầu, Áp lực thuế).
        Văn phong: Trang trọng, cảnh báo rủi ro, chuyên nghiệp. Không dùng Markdown đậm nhạt quá nhiều.
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg:
            return "⚠️ Hệ thống đang quá tải (Hết lượt dùng miễn phí). Vui lòng thử lại sau 1-2 phút."
        elif "404" in error_msg:
            return "⚠️ Lỗi Model AI: Tài khoản Google của bạn không hỗ trợ Model này. Vui lòng tạo API Key bằng Gmail cá nhân."
        else:
            return f"⚠️ Lỗi kết nối AI: {error_msg}"

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
st.caption("Hệ thống Mô phỏng Nghiệp vụ Tài chính Quốc tế")

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
    st.info("💡 **Gợi ý:** Sau khi bấm nút tính toán, hãy mở các mục **'Giải thích chi tiết'** để hiểu bản chất nghiệp vụ.")
    
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
            
            # --- PHẦN GIẢI THÍCH ---
            with st.expander("🎓 GIẢI THÍCH CÔNG THỨC & NGHIỆP VỤ", expanded=True):
                st.markdown(r"""
                **1. Công thức toán học:**
                $$
                \text{EUR/VND}_{Bid} = \text{EUR/USD}_{Bid} \times \text{USD/VND}_{Bid}
                $$
                $$
                \text{EUR/VND}_{Ask} = \text{EUR/USD}_{Ask} \times \text{USD/VND}_{Ask}
                $$
                
                **2. Giải thích nghiệp vụ:**
                Tại sao lại nhân `Bid x Bid`?
                * Để Ngân hàng Mua EUR (trả VND) cho khách, ngân hàng phải thực hiện 2 bước trên thị trường quốc tế:
                    1.  Mua EUR (trả bằng USD) -> Dùng tỷ giá **EUR/USD Bid**.
                    2.  Bán ngay số USD đó (để lấy VND trả khách) -> Dùng tỷ giá mua USD của thị trường (tức **USD/VND Bid**).
                * Do đó, Tỷ giá chéo Bid là tích của 2 tỷ giá Bid thành phần.
                """)

    with tab2:
        st.write("Vốn kinh doanh: **1,000,000 USD**")
        k1, k2, k3 = st.columns(3)
        with k1: bank_a = st.number_input("Bank A (USD/VND):", value=25000.0)
        with k2: bank_b = st.number_input("Bank B (EUR/USD):", value=1.1000)
        with k3: bank_c = st.number_input("Bank C (EUR/VND):", value=28000.0)
        
        if st.button("🔍 CHẠY MÔ HÌNH DÒNG TIỀN"):
            step1_eur = 1000000 / bank_b
            step2_vnd = step1_eur * bank_c
            step3_usd = step2_vnd / bank_a
            profit = step3_usd - 1000000
            
            st.markdown("### 📝 Nhật ký giao dịch chi tiết:")
            st.markdown(f"""
            <div class="step-box">
            1. <b>Bán USD tại Bank B:</b> 1,000,000 / {bank_b} = <b>{step1_eur:,.2f} EUR</b><br>
            2. <b>Bán EUR tại Bank C:</b> {step1_eur:,.2f} x {bank_c} = <b>{step2_vnd:,.0f} VND</b><br>
            3. <b>Mua lại USD tại Bank A:</b> {step2_vnd:,.0f} / {bank_a} = <b>{step3_usd:,.2f} USD</b>
            </div>
            """, unsafe_allow_html=True)
            
            if profit > 0:
                st.markdown(f'<div class="result-box">🎉 LỢI NHUẬN: +{profit:,.2f} USD</div>', unsafe_allow_html=True)
            else:
                st.error(f"⚠️ THUA LỖ: {profit:,.2f} USD")
            
            with st.expander("🎓 BẢN CHẤT ARBITRAGE"):
                st.write("""
                Cơ hội kinh doanh chênh lệch giá (Arbitrage) xuất hiện khi tỷ giá chéo tính toán (Lý thuyết) khác với tỷ giá chéo thực tế trên thị trường.
                Trong trường hợp này, dòng tiền chạy theo vòng tròn (USD -> EUR -> VND -> USD) để tận dụng sự định giá sai lệch giữa các ngân hàng.
                """)

# ==============================================================================
# PHÒNG 2: RISK MANAGEMENT
# ==============================================================================
elif "2." in room:
    st.markdown('<p class="header-style">🛡️ Phòng Quản trị Rủi ro (Risk Management)</p>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="role-card">
        <div class="role-title">👤 Vai diễn: Giám đốc Tài chính (CFO)</div>
        <div class="mission-text">"Nhiệm vụ: Tính toán tỷ giá kỳ hạn (Forward) theo lãi suất và chọn công cụ phòng vệ (Hedging) tối ưu cho khoản phải trả 1 triệu USD sau 90 ngày."</div>
    </div>
    """, unsafe_allow_html=True)

    st.subheader("1. Tính toán Tỷ giá Kỳ hạn (IRP Model)")
    col_irp1, col_irp2 = st.columns(2)
    with col_irp1:
        spot_irp = st.number_input("Spot Rate (Hiện tại):", value=25000.0)
        days = st.number_input("Kỳ hạn vay (Ngày):", value=90)
    with col_irp2:
        r_vnd = st.number_input("Lãi suất VND (%/năm):", value=6.0)
        r_usd = st.number_input("Lãi suất USD (%/năm):", value=3.0)
        
    fwd_cal = spot_irp * (1 + (r_vnd/100)*(days/360)) / (1 + (r_usd/100)*(days/360))
    st.success(f"👉 Tỷ giá Forward lý thuyết (theo IRP): **{fwd_cal:,.2f} VND/USD**")

    with st.expander("🎓 GIẢI THÍCH CÔNG THỨC IRP"):
        st.latex(r"F = S \times \frac{1 + r_{VND} \times \frac{n}{360}}{1 + r_{USD} \times \frac{n}{360}}")
        st.write("""
        **Quy luật Ngang giá Lãi suất (Interest Rate Parity):**
        Đồng tiền nào có lãi suất cao hơn (ở đây là VND: 6% > USD: 3%) thì đồng tiền đó sẽ bị giảm giá trong tương lai (Forward > Spot) để bù trừ cho phần chênh lệch lãi suất. 
        Nếu không, nhà đầu tư sẽ đổ xô đi gửi tiết kiệm đồng tiền lãi suất cao, gây mất cân bằng thị trường.
        """)

    st.markdown("---")
    st.subheader("2. Ma trận Ra quyết định (Decision Matrix)")
    
    c1, c2 = st.columns([1, 2])
    with c1:
        f_rate_input = st.number_input("Giá Forward ký với NH:", value=fwd_cal)
        strike = st.number_input("Giá thực hiện (Strike Price):", value=25200.0)
        premium = st.number_input("Phí Option (VND/USD):", value=150.0)
    with c2:
        future_spot = st.slider("Dự báo Tỷ giá thị trường ngày đáo hạn:", 24000.0, 26000.0, 25300.0)
        
        cost_open = 1000000 * future_spot
        cost_fwd = 1000000 * f_rate_input
        
        if future_spot > strike:
            opt_action = "Thực hiện quyền"
            final_price = strike
        else:
            opt_action = "Bỏ quyền (Mua giá chợ)"
            final_price = future_spot
        cost_opt = (1000000 * final_price) + (1000000 * premium)
            
        df = pd.DataFrame({
            "Chiến lược": ["1. Không phòng vệ (Open)", "2. Hợp đồng Kỳ hạn (Forward)", "3. Quyền chọn Mua (Option)"],
            "Diễn giải": [f"Mua giá {future_spot:,.0f}", f"Mua giá {f_rate_input:,.0f} (Cố định)", f"{opt_action} + Phí"],
            "Tổng chi phí (VND)": [cost_open, cost_fwd, cost_opt]
        })
        st.table(df)
        
        best = df.loc[df['Tổng chi phí (VND)'].idxmin()]
        st.markdown(f'<div class="result-box">🏆 KIẾN NGHỊ: Chọn <b>{best["Chiến lược"]}</b> (Tiết kiệm nhất).</div>', unsafe_allow_html=True)

# ==============================================================================
# PHÒNG 3: TRADE FINANCE
# ==============================================================================
elif "3." in room:
    st.markdown('<p class="header-style">🚢 Phòng Thanh toán Quốc tế (Trade Finance)</p>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="role-card">
        <div class="role-title">👤 Vai diễn: Chuyên viên Thanh toán Quốc tế</div>
        <div class="mission-text">"Nhiệm vụ: Tư vấn phương thức thanh toán tối ưu chi phí và kiểm tra bộ chứng từ (Checking) theo chuẩn UCP 600."</div>
    </div>
    """, unsafe_allow_html=True)
    
    tab_cost, tab_check = st.tabs(["💰 Bài toán Chi phí (L/C vs T/T)", "📝 Kiểm tra Chứng từ (Checking)"])
    
    with tab_cost:
        val = st.number_input("Giá trị hợp đồng (USD):", value=100000)
        if st.button("TÍNH PHÍ GIAO DỊCH"):
            tt_fee = val * 0.002 + 20
            lc_fee = val * 0.01 + 100
            
            st.write(f"🔹 **Chuyển tiền (T/T):** {tt_fee:,.2f} USD")
            st.write(f"🔹 **Tín dụng thư (L/C):** {lc_fee:,.2f} USD")
            
            with st.expander("🎓 TẠI SAO L/C ĐẮT HƠN?"):
                st.write("""
                * **T/T (Chuyển tiền):** Ngân hàng chỉ đóng vai trò người chuyển tiền (Shipper tiền), không chịu trách nhiệm nếu người bán không giao hàng. -> Phí rẻ.
                * **L/C (Tín dụng thư):** Ngân hàng dùng uy tín của mình để **cam kết thanh toán** thay cho người nhập khẩu. Ngân hàng chịu rủi ro tín dụng. -> Phí đắt (Bao gồm phí xử lý chứng từ và phí rủi ro).
                """)

    with tab_check:
        c1, c2 = st.columns(2)
        with c1: 
            ship_last = st.date_input("Latest Shipment Date (Hạn giao hàng):")
            lc_exp = st.date_input("L/C Expiry Date (Hạn L/C):")
        with c2:
            bl_date = st.date_input("B/L Date (Ngày vận đơn):")
            pres_date = st.date_input("Presentation Date (Ngày xuất trình):")
            
        if st.button("KIỂM TRA CHỨNG TỪ"):
            errs = []
            if bl_date > ship_last: errs.append("❌ Late Shipment (Giao hàng trễ hơn quy định)")
            if pres_date > lc_exp: errs.append("❌ L/C Expired (Xuất trình khi L/C đã hết hạn)")
            if (pres_date - bl_date).days > 21: errs.append("❌ Stale Documents (Chứng từ quá hạn > 21 ngày)")
            
            if errs:
                for e in errs: st.error(e)
            else:
                st.success("✅ Clean Documents (Bộ chứng từ hoàn hảo).")
        
        with st.expander("🎓 QUY TẮC UCP 600"):
             st.markdown("""
             **Điều 14c UCP 600:**
             Một bộ chứng từ phải được xuất trình không muộn hơn **21 ngày** theo lịch sau ngày giao hàng (Date of Shipment), nhưng trong bất kỳ trường hợp nào cũng không được muộn hơn ngày hết hạn hiệu lực của L/C.
             """)

# ==============================================================================
# PHÒNG 4: INVESTMENT DEPT
# ==============================================================================
elif "4." in room:
    st.markdown('<p class="header-style">🏭 Phòng Đầu tư Quốc tế (Investment Dept)</p>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="role-card">
        <div class="role-title">👤 Vai diễn: Chuyên viên Phân tích Đầu tư (Investment Analyst)</div>
        <div class="mission-text">"Nhiệm vụ: Thẩm định dự án FDI bằng mô hình DCF, có tính đến sự trượt giá của đồng nội tệ (Currency Depreciation)."</div>
    </div>
    """, unsafe_allow_html=True)
    
    c1, c2 = st.columns(2)
    with c1:
        inv = st.number_input("Vốn đầu tư ban đầu (USD):", value=1000000)
        cf = st.number_input("Dòng tiền ròng/năm (USD):", value=400000)
        years = st.slider("Vòng đời dự án (năm):", 1, 10, 3)
    with c2:
        fx = st.number_input("Tỷ giá Spot hiện tại:", value=25000.0)
        depre = st.number_input("Mức độ mất giá VND (%/năm):", value=3.0)
        wacc = st.number_input("Chi phí vốn (WACC %):", value=12.0)
        
    if st.button("📊 LẬP BẢNG DÒNG TIỀN (CF)"):
        st.subheader("Bảng chiết khấu dòng tiền chi tiết:")
        data = []
        total_pv = 0
        
        # Năm 0
        cf0_vnd = -inv * fx
        data.append(["Năm 0", fx, f"{-inv:,.0f}", f"{cf0_vnd:,.0f}", f"{cf0_vnd:,.0f}"])
        
        # Vòng lặp tính toán
        for i in range(1, years + 1):
            fx_future = fx * ((1 + depre/100) ** i) # Tỷ giá tương lai
            cf_vnd = cf * fx_future                 # Quy đổi ra VND
            pv = cf_vnd / ((1 + wacc/100) ** i)     # Chiết khấu về hiện tại
            total_pv += pv
            data.append([f"Năm {i}", f"{fx_future:,.0f}", f"{cf:,.0f}", f"{cf_vnd:,.0f}", f"{pv:,.0f}"])
            
        npv = total_pv + cf0_vnd
        
        df_cf = pd.DataFrame(data, columns=["Năm", "Tỷ giá (Dự báo)", "CF (USD)", "CF Quy đổi (VND)", "PV (Hiện giá)"])
        st.table(df_cf)
        
        st.markdown(f"### 🏁 KẾT QUẢ NPV: {npv:,.0f} VND")
        
        with st.expander("🎓 GIẢI THÍCH MÔ HÌNH NPV QUỐC TẾ"):
            st.latex(r"NPV = CF_0 + \sum_{t=1}^{n} \frac{CF_{USD, t} \times S_t}{(1 + WACC)^t}")
            st.write("""
            Khác với NPV thông thường, dự án quốc tế chịu tác động kép:
            1.  **Dòng tiền kinh doanh:** (CF USD)
            2.  **Rủi ro tỷ giá:** ($S_t$) - Nếu VND mất giá, doanh thu quy đổi sẽ tăng (lợi cho xuất khẩu/đầu tư mang ngoại tệ về), nhưng chi phí vốn cũng thay đổi.
            """)

# ==============================================================================
# PHÒNG 5: MACRO STRATEGY (CÓ TÍCH HỢP AI)
# ==============================================================================
elif "5." in room:
    st.markdown('<p class="header-style">📉 Ban Chiến lược Vĩ mô (Macro Strategy)</p>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="role-card">
        <div class="role-title">👤 Vai diễn: Cố vấn Kinh tế Chính phủ</div>
        <div class="mission-text">"Nhiệm vụ: Đánh giá tác động của cú sốc tỷ giá lên nợ công quốc gia (Currency Mismatch) và đề xuất chính sách ứng phó."</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Input
    debt = st.number_input("Tổng nợ nước ngoài (Tỷ USD):", value=50.0)
    base_rate = 25000
    shock = st.slider("Kịch bản: Đồng nội tệ mất giá (%):", 0, 50, 10)
    
    # Calculation (Chạy Real-time khi kéo slider)
    new_rate = base_rate * (1 + shock/100)
    debt_old = debt * base_rate
    debt_new = debt * new_rate
    diff = debt_new - debt_old
    
    # Hiển thị kết quả tính toán
    c1, c2, c3 = st.columns(3)
    c1.metric("Tỷ giá sau cú sốc", f"{new_rate:,.0f}", f"+{shock}%")
    c2.metric("Nợ công quy đổi", f"{debt_new:,.0f} Tỷ VND")
    c3.metric("Gánh nặng tăng thêm", f"{diff:,.0f} Tỷ VND", delta_color="inverse")
    
    st.markdown("---")
    
    # Nút bấm gọi AI (On-demand)
    col_ai_btn, col_ai_space = st.columns([1, 2])
    with col_ai_btn:
        run_ai = st.button("🤖 YÊU CẦU CHUYÊN GIA AI PHÂN TÍCH", type="primary", use_container_width=True)
    
    if run_ai:
        if not api_key:
            st.warning("⚠️ Chưa tìm thấy API Key. Vui lòng thêm Key vào 'Streamlit Secrets' để dùng tính năng AI.")
        else:
            with st.spinner("⏳ Chuyên gia AI đang soạn thảo báo cáo chính sách..."):
                report = ask_gemini_macro(diff, shock, new_rate)
                
                # Hiển thị kết quả trong box đẹp (Màu chữ đã fix đen)
                st.markdown(f"""
                <div class="ai-box">
                    <h4>📜 BÁO CÁO CỦA CỐ VẤN KINH TẾ (AI)</h4>
                    <p>{report}</p>
                </div>
                """, unsafe_allow_html=True)

    with st.expander("🎓 BÀI HỌC VĨ MÔ: CURRENCY MISMATCH"):
        st.markdown("""
        **Bất tương xứng tiền tệ (Currency Mismatch):**
        * Đây là nguyên nhân chính dẫn đến khủng hoảng tài chính châu Á 1997.
        * Chính phủ/Doanh nghiệp vay bằng USD (Nợ USD) nhưng nguồn thu lại bằng nội tệ (Thuế/Doanh thu VND).
        * Khi nội tệ mất giá, khoản nợ "tự động" phình to ra khi quy đổi, dù số tiền gốc USD không đổi.
        """)
