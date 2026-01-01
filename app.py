import os
import re
import numpy as np
import pandas as pd
import altair as alt
import streamlit as st
import google.generativeai as genai
from supabase import create_client, Client
import hashlib
import time


MAX_AI_QUOTA = 10

# Đặt đoạn này ở ngay đầu file app.py (sau các lệnh import)
st.set_page_config(
    page_title="Finance Lab",
    page_icon="chart_with_upwards_trend",
    layout="wide",
    menu_items={        
        'About': """
        ### Finance Lab - International Finance Simulation
        **© 2026 - Nguyễn Minh Hải**
        
        Phiên bản Beta 2.0.
        Ứng dụng hỗ trợ giảng dạy môn Tài chính Quốc tế.
        """
    }
)

# --- CẤU HÌNH SUPABASE (Đặt ngay đầu file hoặc sau các dòng import) ---
# Dùng @st.cache_resource để không phải kết nối lại mỗi lần F5
@st.cache_resource
def init_supabase():
    try:
        url = st.secrets["connections"]["supabase"]["SUPABASE_URL"]
        key = st.secrets["connections"]["supabase"]["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"⚠️ Lỗi kết nối Supabase: {e}")
        return None

supabase_client = init_supabase()

@st.cache_data(show_spinner=False)
def load_student_registry():
    """
    Đọc dssv.xlsx và trả về dict:
    REG[mssv] = {"hoten": "...", "pin": "..."}
    """
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, "dssv.xlsx")
        df = pd.read_excel(file_path, dtype=str).fillna("")

        # Chuẩn hóa tên cột linh hoạt
        cols = {c.strip().lower(): c for c in df.columns}

        mssv_col = cols.get("mssv") or cols.get("ma sv") or cols.get("student_id") or cols.get("student id")
        pin_col  = cols.get("pin") or cols.get("pin4") or cols.get("pass") or cols.get("password")
        hoten_col = cols.get("hoten") or cols.get("họ tên") or cols.get("ho ten") or cols.get("fullname") or cols.get("full name")

        if not mssv_col or not pin_col:
            st.error("⚠️ File dssv.xlsx thiếu cột MSSV hoặc PIN.")
            return {}

        df[mssv_col] = df[mssv_col].astype(str).str.strip().str.upper()
        df[pin_col]  = df[pin_col].astype(str).str.strip()

        if hoten_col:
            df[hoten_col] = df[hoten_col].astype(str).str.strip()
        else:
            df["__hoten__"] = ""
            hoten_col = "__hoten__"

        reg = {}
        for _, r in df.iterrows():
            m = (r.get(mssv_col) or "").strip().upper()
            p = (r.get(pin_col) or "").strip()
            h = (r.get(hoten_col) or "").strip()
            if m and p:
                reg[m] = {"hoten": h, "pin": p}
        return reg

    except Exception as e:
        st.error(f"⚠️ Lỗi đọc file Excel: {e}")
        return {}


def get_student_name(mssv: str) -> str:
    m = str(mssv).strip().upper()
    reg = load_student_registry()
    return (reg.get(m, {}) or {}).get("hoten", "").strip()

def verify_mssv_pin(mssv: str, pin: str) -> tuple[bool, str]:
    reg = load_student_registry()
    m = str(mssv).strip().upper()
    p = str(pin).strip()
    info = reg.get(m)

    if not info:
        return False, "❌ MSSV không có trong danh sách lớp."
    if p != str(info.get("pin", "")).strip():
        return False, "❌ PIN không đúng."
    return True, ""


# ------------------------------------------------------------------
# PHẦN CODE MỚI: QUẢN LÝ QUOTA BẰNG SUPABASE
# (Thay thế hoàn toàn phần RAM tracker cũ)
# ------------------------------------------------------------------

def get_usage_from_supabase(student_id):
    """Hàm phụ: Lấy số lượt dùng hiện tại từ Database"""
    if not supabase_client:
        return None  # báo DB không sẵn sàng

    
    try:
        # Query bảng 'user_quota', tìm dòng có mssv tương ứng
        response = supabase_client.table("user_quota").select("usage").eq("mssv", student_id).execute()
        
        # Nếu tìm thấy dữ liệu -> Trả về số usage
        if response.data:
            return response.data[0]['usage']
        else:
            # Nếu chưa có trong DB -> Coi như là 0
            return 0
    except Exception as e:
        print(f"Lỗi đọc DB: {e}") # Log ra terminal server để debug
        return 0

def update_usage_to_supabase(student_id, current_usage):
    """Hàm phụ: Cập nhật (Ghi đè) số lượt dùng mới"""
    if not supabase_client: return
    
    try:
        # Dữ liệu cần lưu
        # Upsert: Nếu chưa có thì Thêm mới, Có rồi thì Cập nhật
        data = {"mssv": student_id, "usage": current_usage + 1}
        supabase_client.table("user_quota").upsert(data, on_conflict="mssv").execute()
    except Exception as e:
        st.error(f"Lỗi ghi Database: {e}")

# --- HÀM LOGIC CHÍNH (Đã sửa đổi để gọi Supabase) ---

def verify_and_check_quota(student_id, max_limit=MAX_AI_QUOTA):
    """
    Kiểm tra 2 lớp:
    1. Có trong file Excel không? (Hợp lệ)
    2. Check Supabase xem còn lượt không? (Quota)
    """
    # Load danh sách cho phép từ Excel
    valid_list = load_student_registry()
    
    # Chuẩn hóa input đầu vào (Viết hoa để khớp với Excel/DB)
    clean_id = str(student_id).strip().upper()
    
    # LỚP 1: KIỂM TRA DANH TÍNH
    if clean_id not in valid_list:
        return "INVALID", 0
    
    # LỚP 2: KIỂM TRA QUOTA TỪ SUPABASE (Thay vì RAM)
    current_usage = get_usage_from_supabase(clean_id)
    
    if current_usage >= max_limit:
        return "LIMIT_REACHED", current_usage
    
    # Trả về OK và số lượt hiện tại
    return "OK", current_usage

def consume_quota(student_id):
    """
    Gọi hàm này sau khi AI chạy thành công để trừ lượt
    (Lưu thẳng vào Supabase)
    """
    clean_id = str(student_id).strip().upper()
    
    # Lấy số hiện tại để đảm bảo tính đúng
    current_usage = get_usage_from_supabase(clean_id)
    
    # Ghi số mới (cộng thêm 1) vào DB
    update_usage_to_supabase(clean_id, current_usage)

# =========================
# LEADERBOARD PRACTICE HELPERS
# =========================
def stable_seed(*parts) -> int:
    """Seed ổn định và luôn nằm trong miền BIGINT signed của Postgres."""
    s = "|".join(str(p) for p in parts)
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()
    # lấy 16 hex (64-bit) rồi ép về miền signed 63-bit để không overflow bigint
    return int(h[:16], 16) & ((1 << 63) - 1)


def gen_case_D01(seed: int) -> tuple[dict, dict]:
    """
    D01: Cross-rate EUR/VND từ EUR/USD & USD/VND (Bid/Ask/Spread)
    Trả về (params, answers)
    """
    rng = np.random.default_rng(seed)

    # USD/VND: bid bội số 10, ask = bid + spread(80..160)
    usd_bid = int(rng.integers(2400, 2701) * 10)  # 24,000 .. 27,000
    usd_spread = int(rng.choice([80, 90, 100, 110, 120, 130, 140, 150, 160]))
    usd_ask = usd_bid + usd_spread

    # EUR/USD: bid 4 decimals, ask = bid + (0.0010..0.0030)
    # EUR/USD bid theo bước 0.0005 (tick = 5 trên thang 1/10000)
    eur_bid_ticks = int(rng.integers(10200 // 5, 11500 // 5 + 1) * 5)
    eur_bid = eur_bid_ticks / 10000

    eur_mark = float(rng.integers(10, 31) / 10000)          # 0.0010..0.0030
    eur_ask = round(eur_bid + eur_mark, 4)

    # Theo code room_1_dealing: cross_bid=eur_bid*usd_bid; cross_ask=eur_ask*usd_ask
    # Hiển thị dạng 0f => chấm theo làm tròn integer VND/EUR
    cross_bid = int(round(eur_bid * usd_bid, 0))
    cross_ask = int(round(eur_ask * usd_ask, 0))
    spread = int(cross_ask - cross_bid)

    params = {
        "usd_bid": usd_bid, "usd_ask": usd_ask,
        "eur_bid": eur_bid, "eur_ask": eur_ask,
    }
    answers = {
        "cross_bid": cross_bid,
        "cross_ask": cross_ask,
        "spread": spread,
    }
    return params, answers

def fetch_attempt(mssv: str, exercise_code: str, attempt_no: int):
    """Kiểm tra attempt đã nộp chưa."""
    if not supabase_client:
        return None
    try:
        res = (
            supabase_client.table("lab_attempts")
            .select("id,is_correct,score,created_at,answer_json,params_json")
            .eq("mssv", mssv)
            .eq("exercise_code", exercise_code)
            .eq("attempt_no", attempt_no)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception as e:
        st.error(f"⚠️ Lỗi đọc lab_attempts: {e}")
        return None

def insert_attempt(payload: dict) -> bool:
    """Ghi attempt vào DB."""
    if not supabase_client:
        st.error("⚠️ Chưa kết nối Supabase.")
        return False
    try:
        supabase_client.table("lab_attempts").insert(payload).execute()
        return True
    except Exception as e:
        st.error(f"⚠️ Lỗi ghi lab_attempts: {e}")
        return False

def reward_ai_calls_by_decreasing_usage(mssv: str, bonus_calls: int = 2):
    """
    Thưởng thêm lượt gọi AI theo mô hình hiện tại:
    - DB đang lưu 'usage' (đã dùng).
    - Thưởng = GIẢM usage đi bonus_calls (tối thiểu = 0).
    => SV sẽ có thêm 'remaining' lượt dùng.
    """
    if not supabase_client:
        return
    try:
        cur = int(get_usage_from_supabase(mssv))
        if cur >= 999:
            return
        new_usage = max(cur - bonus_calls, 0)
        supabase_client.table("user_quota").upsert(
            {"mssv": mssv, "usage": new_usage},
            on_conflict="mssv"
        ).execute()
    except Exception as e:
        st.error(f"⚠️ Lỗi thưởng lượt AI: {e}")


# ==============================================================================
# 0) PAGE CONFIG
# ==============================================================================
st.set_page_config(
    page_title="Finance Lab",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="🏦",
)

# =========================
# EXERCISE CATALOG (APPROVED)
# =========================
EXERCISE_CATALOG = {
    # PHÒNG 1: DEALING ROOM
    "DEALING": [
        {"code": "D01", "title": "Niêm yết Cross-rate Bid–Ask–Spread (EUR/VND từ EUR/USD & USD/VND)"},
        {"code": "D02", "title": "Arbitrage tam giác (Có/Không + hướng giao dịch tối ưu)"},
    ],

    # PHÒNG 2: RISK MANAGEMENT (loại R2-03 nâng cao)
    "RISK": [
        {"code": "R01", "title": "Forward Rate hợp lý theo IRP (tính F từ S, i_dom, i_for, số ngày)"},
        {"code": "R02", "title": "Chọn công cụ phòng vệ tối ưu (Forward vs Option vs No Hedge)"},
    ],

    # PHÒNG 3: TRADE FINANCE
    "TRADE": [
        {"code": "T01", "title": "Tối ưu chi phí phương thức thanh toán (T/T vs Nhờ thu vs L/C)"},
        {"code": "T02", "title": "UCP 600 – Phát hiện Discrepancy (Checking bộ chứng từ)"},
    ],

    # PHÒNG 4: INVESTMENT
    "INVEST": [
        {"code": "I01", "title": "Thẩm định dự án FDI: NPV + Quyết định Đầu tư/Không"},
        {"code": "I02", "title": "IRR vs WACC: Dự án đạt chuẩn hay không"},        
    ],

    # PHÒNG 5: MACRO STRATEGY
    "MACRO": [
        {"code": "M01", "title": "Cú sốc tỷ giá lên Nợ công (tỷ giá mới + gánh nặng tăng thêm)"},
        {"code": "M02", "title": "Carry Trade: ROI/P&L khi chênh lệch lãi suất + biến động FX"},
    ],
}

ROOM_LABELS = {
    "DEALING": "💱 Sàn Kinh doanh Ngoại hối (Dealing Room)",
    "RISK": "🛡️ Phòng Quản trị Rủi ro (Risk Management)",
    "TRADE": "🚢 Phòng Thanh toán Quốc tế (Trade Finance)",
    "INVEST": "🏭 Phòng Đầu tư Quốc tế (Investment Dept)",
    "MACRO": "📉 Ban Chiến lược Vĩ mô (Macro Strategy)",
}

# ==============================================================================
# 1) STYLE (UI + MOBILE RESPONSIVE)
# ==============================================================================
def init_style():
    st.markdown(
        """
<style>
/* -----------------------------
   Global
------------------------------*/
:root{
  --blue:#0d47a1;
  --blue2:#1565c0;
  --green:#28a745;
  --green2:#218838;
  --orange:#ff9800;
  --red:#ff2b2b;
  --text:#333;
}
.block-container { padding-top: 1.2rem; padding-bottom: 2.0rem; }
h1, h2, h3, h4 { letter-spacing: 0.2px; }
small, .stCaption { color: #666 !important; }

/* ===== Buttons (CHUẨN) ===== */

/* PRIMARY: đỏ/cam (AI + nút đang chọn) */
div[data-testid="stButton"] > button[kind="primary"]{
  background-color: #ff2b2b !important;
  color: #fff !important;
  border: none !important;
  border-radius: 10px !important;
  font-weight: 800 !important;
  box-shadow: 0 2px 6px rgba(255,43,43,.35) !important;
  font-family: "Segoe UI Emoji","Noto Color Emoji","Apple Color Emoji","Android Emoji",sans-serif !important;
}
div[data-testid="stButton"] > button[kind="primary"]:hover{
  background-color: #d32f2f !important;
  box-shadow: 0 6px 14px rgba(255,43,43,.45) !important;
}

/* ========================================================= */
/* 1. STYLE MẶC ĐỊNH TOÀN APP (Nút Tính toán, Phân tích...)  */
/* ========================================================= */

/* Secondary mặc định => MÀU XANH (Giống cũ) */
div[data-testid="stButton"] > button[kind="secondary"] {
    background-color: #28a745 !important;
    color: #fff !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
    box-shadow: 0 2px 4px rgba(0,0,0,.18) !important;
}

/* Hover của nút xanh */
div[data-testid="stButton"] > button[kind="secondary"]:hover {
    background-color: #218838 !important; /* Xanh đậm hơn */
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 12px rgba(0,0,0,.18) !important;
    color: #fff !important;
}

/* ========================================================= */
/* 2. NGOẠI LỆ: RIÊNG CÁC NÚT TRONG EXPANDER (Gợi ý kịch bản) */
/* ========================================================= */

/* Tìm thẻ stExpander chứa nút secondary => Ép thành TRONG SUỐT */
div[data-testid="stExpander"] div[data-testid="stButton"] > button[kind="secondary"] {
    background-color: #f8f9fa !important; /* <--- ĐỔI Ở ĐÂY (Xám siêu nhạt chuẩn UI) */
    color: #333 !important;
    border: 1px solid #d1d5db !important; /* Đổi viền sang xám lợt hơn chút cho tiệp màu */
    box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important; /* Thêm tí bóng nhẹ cho đẹp */
}

/* Hover của nút trong suốt => Hiện màu cam nhạt gợi ý */
div[data-testid="stExpander"] div[data-testid="stButton"] > button[kind="secondary"]:hover {
    background-color: #fff3e0 !important;
    border-color: #ff9800 !important;
    color: #e65100 !important;
    transform: none !important; /* Không nảy lên để đỡ rối mắt */
}

/* -----------------------------
   Cards / Boxes
------------------------------*/
.role-card {
    background-color: #e3f2fd;
    border-left: 6px solid var(--blue2);
    padding: 18px 18px;
    border-radius: 12px;
    margin-bottom: 18px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.08);
}
.role-title {
    color: var(--blue2);
    font-weight: 800;
    font-size: 18px;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.mission-text { color: #424242; font-style: italic; font-size: 15px; line-height: 1.55; }

.header-style {
    font-size: 26px;
    font-weight: 900;
    color: var(--blue);
    border-bottom: 2px solid #eee;
    padding-bottom: 10px;
    margin-bottom: 18px;
}

.result-box {
    background-color: #f1f8e9;
    padding: 14px 14px;
    border-radius: 10px;
    border: 1px solid #c5e1a5;
    color: #33691e;
    font-weight: 800;
}
.step-box {
    background-color: #fafafa;
    color: var(--text);
    padding: 14px 14px;
    border-radius: 10px;
    border: 1px dashed #bdbdbd;
    margin-bottom: 10px;
}
.explanation-box {
    background-color: #fff8e1;
    padding: 14px 14px;
    border-radius: 10px;
    border-left: 5px solid #ffb300;
    margin-top: 10px;
}
.ai-box {
    background-color: #fff3e0;
    padding: 18px;
    border-radius: 14px;
    border-left: 6px solid var(--orange);
    margin-top: 16px;
    box-shadow: 0 4px 8px rgba(0,0,0,0.05);
    color: var(--text) !important;
}
.ai-box h4 { color: #e65100 !important; font-weight: 900; margin: 0 0 8px 0; }
.ai-box p, .ai-box li { color: var(--text) !important; }

/* -----------------------------
   Sidebar cosmetics
------------------------------*/
section[data-testid="stSidebar"] { border-right: 1px solid #eee; }
section[data-testid="stSidebar"] .block-container { padding-top: 1rem; }

/* -----------------------------
   Mobile responsiveness
   (Stack columns, reduce paddings, fix overflow)
------------------------------*/
@media (max-width: 768px){
  .block-container { padding-left: 0.9rem; padding-right: 0.9rem; }
  .header-style { font-size: 22px; }
  .role-title { font-size: 16px; }
  .mission-text { font-size: 14px; }

  /* Stack Streamlit columns */
  div[data-testid="stHorizontalBlock"]{
      flex-direction: column !important;
      align-items: stretch !important;
      gap: 0.75rem !important;
  }
  div[data-testid="column"]{
      width: 100% !important;
      flex: 1 1 100% !important;
  }

  /* Make tables and charts scroll nicely */
  .stDataFrame, .stTable { overflow-x: auto; }
}

/* Footer */
.copyright {
    font-size: 12px;
    color: #888;
    text-align: center;
    margin-top: 36px;
}

/* ========================================================= */
/* 3. SIDEBAR NAV BUTTONS (CHỈ ÁP DỤNG CHO MENU ĐIỀU HƯỚNG)   */
/* ========================================================= */

.nav-menu div[data-testid="stButton"] > button {
  border-radius: 14px !important;
  padding: 0.85rem 0.9rem !important;
  font-weight: 800 !important;
  border: 1px solid rgba(0,0,0,0.06) !important;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08) !important;
  transition: all .18s ease-in-out !important;
  margin-bottom: 10px !important;
}

/* Nút menu bình thường (secondary) -> MÀU XANH DƯƠNG/THANH LỊCH */
.nav-menu div[data-testid="stButton"] > button[kind="secondary"]{
  background: linear-gradient(180deg, #1e88e5 0%, #1565c0 100%) !important;
  color: #fff !important;
}

/* Hover menu bình thường */
.nav-menu div[data-testid="stButton"] > button[kind="secondary"]:hover{
  background: linear-gradient(180deg, #42a5f5 0%, #1976d2 100%) !important;
  transform: translateY(-1px) !important;
  box-shadow: 0 10px 18px rgba(21,101,192,0.25) !important;
}

/* Nút menu đang chọn (primary) -> MÀU TÍM/ĐỎ RƯỢU (khác AI button đỏ) */
.nav-menu div[data-testid="stButton"] > button[kind="primary"]{
  background: linear-gradient(180deg, #8e24aa 0%, #6a1b9a 100%) !important;
  color: #fff !important;
  border: none !important;
}

/* Hover nút menu đang chọn */
.nav-menu div[data-testid="stButton"] > button[kind="primary"]:hover{
  background: linear-gradient(180deg, #ab47bc 0%, #7b1fa2 100%) !important;
  transform: translateY(-1px) !important;
  box-shadow: 0 10px 20px rgba(106,27,154,0.25) !important;
}

/* ========================================================= */
/* FORCE OVERRIDE MENU BUTTONS IN SIDEBAR                    */
/* ========================================================= */

/* Chỉ áp dụng cho nút trong SIDEBAR */
section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"]{
  background: linear-gradient(180deg, #1e88e5 0%, #1565c0 100%) !important;
  color: #fff !important;
  border: 1px solid rgba(0,0,0,0.06) !important;
  border-radius: 14px !important;
  font-weight: 800 !important;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08) !important;
  transition: all .18s ease-in-out !important;
}

section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="secondary"]:hover{
  background: linear-gradient(180deg, #42a5f5 0%, #1976d2 100%) !important;
  transform: translateY(-1px) !important;
  box-shadow: 0 10px 18px rgba(21,101,192,0.25) !important;
}

/* Nút đang chọn (primary) trong sidebar */
section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"]{
  background: linear-gradient(180deg, #8e24aa 0%, #6a1b9a 100%) !important;
  color: #fff !important;
  border: none !important;
  border-radius: 14px !important;
  font-weight: 900 !important;
  box-shadow: 0 6px 14px rgba(106,27,154,0.25) !important;
}

section[data-testid="stSidebar"] div[data-testid="stButton"] > button[kind="primary"]:hover{
  background: linear-gradient(180deg, #ab47bc 0%, #7b1fa2 100%) !important;
  transform: translateY(-1px) !important;
}

/* spacing đẹp hơn */
section[data-testid="stSidebar"] div[data-testid="stButton"]{
  margin-bottom: 10px !important;
}


</style>
        """,
        unsafe_allow_html=True,
    )


init_style()

# ==============================================================================
# 2) GEMINI CONFIG + HELPERS
# ==============================================================================
def get_api_key():
    api_key = None
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        api_key = os.getenv("GEMINI_API_KEY")
    return api_key


API_KEY = get_api_key()
if API_KEY:
    genai.configure(api_key=API_KEY)


def _force_vietnamese(text: str) -> str:
    """
    Gemini đôi khi trả về tiếng Anh. Ta ép lại nhẹ bằng:
    - Nếu có nhiều từ/phrase tiếng Anh phổ biến -> nhắc người dùng "AI trả lời VN"
    - Và cố gắng làm sạch vài heading/labels thường gặp.
    (Không dịch máy để tránh phụ thuộc API dịch; chủ yếu là ép prompt + cleanup nhẹ.)
    """
    if not text:
        return ""

    # Cleanup các nhãn hay xuất hiện
    replacements = {
        "Risk": "Rủi ro",
        "Recommendation": "Khuyến nghị",
        "Conclusion": "Kết luận",
        "Decision": "Quyết định",
        "GO": "GO (Vào lệnh)",
        "NO-GO": "NO-GO (Hủy)",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)

    # Nếu vẫn có nhiều tiếng Anh (heuristic đơn giản)
    en_hits = len(re.findall(r"\b(the|and|or|but|because|therefore|however|recommend|risk|should)\b", text.lower()))
    if en_hits >= 3:
        text = (
            "⚠️ (AI đôi lúc trả lời lẫn tiếng Anh) Dưới đây là nội dung đã được yêu cầu trả lời **tiếng Việt**:\n\n"
            + text
        )
    return text


def ask_gemini_advisor(role: str, context_data: str, task: str) -> str:
    """
    AI Advisor dùng chung.
    - Ép trả lời tiếng Việt.
    - Ngắn gọn 3–4 câu, tập trung rủi ro & khuyến nghị.
    """
    if not API_KEY:
        return "⚠️ Chưa cấu hình GEMINI_API_KEY. Vui lòng nhập key ở Sidebar hoặc môi trường."

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        prompt = f"""
Bạn là: {role}.

Dữ liệu đầu vào:
{context_data}

Yêu cầu:
{task}

Ràng buộc bắt buộc:
- Trả lời hoàn toàn bằng TIẾNG VIỆT.
- Không dùng câu tiếng Anh, không chèn thuật ngữ tiếng Anh trừ ký hiệu chuẩn (NPV, IRR, WACC, UCP 600, BID/ASK).
- Văn phong: ngắn gọn, súc tích (khoảng 4-5 câu), đi thẳng vào rủi ro và khuyến nghị chuyên môn.
"""
        response = model.generate_content(prompt)
        return _force_vietnamese(getattr(response, "text", "") or "")
    except Exception as e:
        msg = str(e)
        if "429" in msg:
            return "⚠️ AI đang bận (quá tải). Vui lòng thử lại sau."
        if "404" in msg:
            return "⚠️ Lỗi Model: Tài khoản chưa hỗ trợ gemini-2.0-flash."
        return f"⚠️ Lỗi kết nối: {msg}"


def ask_gemini_macro(debt_increase, shock_percent, new_rate):
    """Giữ riêng cho Macro (bạn yêu cầu giữ như cũ), nhưng cũng ép tiếng Việt."""
    if not API_KEY:
        return "⚠️ Chưa cấu hình GEMINI_API_KEY. Vui lòng nhập key ở Sidebar hoặc môi trường."

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        prompt = f"""
Đóng vai một Cố vấn Kinh tế cấp cao của Chính phủ.

Tình huống hiện tại:
- Đồng nội tệ vừa mất giá: {shock_percent}%
- Tỷ giá mới: {new_rate:,.0f} VND/USD
- Gánh nặng nợ công quốc gia vừa tăng thêm {debt_increase:,.0f} Tỷ VND do chênh lệch tỷ giá.

Yêu cầu:
- Viết báo cáo ngắn gọn (khoảng 4 gạch đầu dòng lớn) cảnh báo 4 tác động thực tế đến đời sống người dân và doanh nghiệp.
- Trả lời hoàn toàn bằng TIẾNG VIỆT (không dùng câu tiếng Anh).
- Văn phong trang trọng, cảnh báo rủi ro, chuyên nghiệp. Không lạm dụng Markdown đậm/nhạt.
"""
        response = model.generate_content(prompt)
        return _force_vietnamese(getattr(response, "text", "") or "")
    except Exception as e:
        return f"⚠️ Lỗi kết nối AI: {str(e)}"


# ==============================================================================
# 3) HEADER
# ==============================================================================
st.title("🏦 INTERNATIONAL FINANCE LAB")
st.caption("Hệ thống Mô phỏng Nghiệp vụ Tài chính Quốc tế với Trợ lý AI Gemini")

# ==============================================================================
# 4) SIDEBAR NAV + API KEY INPUT (OPTIONAL)
# ==============================================================================
with st.sidebar:

    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=50)
    st.markdown("### 🎓 Cổng Lab")      

    # 1. Nhập liệu
    # Dùng key='login_mssv' để Streamlit tự nhớ giá trị trong ô input
    input_mssv_raw = st.text_input("Nhập MSSV kích hoạt AI:", key="login_mssv").strip()
    input_mssv = input_mssv_raw.upper()
    
    # 2. Xử lý logic xác thực
    valid_list = list(load_student_registry().keys()) 
    
    # Mặc định là chưa đăng nhập
    st.session_state['CURRENT_USER'] = None 
    
    if input_mssv:
        # Kiểm tra xem có trong danh sách lớp không
        if input_mssv in valid_list:
            # A. Đăng nhập thành công -> Lưu vào Session State (QUAN TRỌNG)
            st.session_state['CURRENT_USER'] = input_mssv
            
            hoten = get_student_name(input_mssv)
            hello = f"Xin chào: {hoten} ({input_mssv})" if hoten else f"Xin chào: {input_mssv}"
            st.success(hello)
            
            # [QUAN TRỌNG] Tạo một cái hộp rỗng và gán vào biến 'quota_placeholder'
            quota_placeholder = st.empty()
            # B. Hiển thị số lượt đã dùng ngay tại đây cho SV thấy
            current_used = get_usage_from_supabase(input_mssv)

            if current_used is None:
                quota_placeholder.error("⛔ Không kết nối được Database quota nên tạm khóa AI. Bạn vẫn thực hành bình thường.")
            elif current_used < MAX_AI_QUOTA:
                quota_placeholder.caption(f"✅ Đã dùng: **{current_used}/{MAX_AI_QUOTA}** lượt gọi AI.")
            else:
                quota_placeholder.error(f"⛔ Đã dùng hết: **{current_used}/{MAX_AI_QUOTA}** lượt gọi AI.")                
        else:
            # C. Nhập sai
            st.error("⛔ Danh sách lớp không có MSSV này! Bạn vẫn thực hành bình thường nhưng không được dùng AI.")
    else:
        st.info("Vui lòng nhập MSSV để được kích hoạt AI tư vấn.")
   
    # (Tuỳ chọn) nhập API key nhanh nếu chưa có
    # if not API_KEY:
    #     with st.expander("🔑 Nhập GEMINI_API_KEY (tuỳ chọn)", expanded=False):
    #         key_in = st.text_input("GEMINI_API_KEY", type="password", help="Nếu bạn chạy local và chưa set secrets/env.")
    #         if key_in:
    #             os.environ["GEMINI_API_KEY"] = key_in
    #             API_KEY = key_in
    #             genai.configure(api_key=API_KEY)
    #             st.success("Đã nạp API Key cho phiên chạy hiện tại.")
    st.markdown("---")    

    # ==============================
    # SIDEBAR – BUTTON NAVIGATION
    # ==============================

    if "ROOM" not in st.session_state:
        st.session_state["ROOM"] = "DEALING"

    def room_button(label, key):
        is_active = st.session_state.get("ROOM", "DEALING") == key

        if st.button(
            label,
            use_container_width=True,
            type="primary" if is_active else "secondary",
            key=f"nav_{key}",  # nên có key riêng
        ):
            if st.session_state.get("ROOM") != key:
                st.session_state["ROOM"] = key
                st.rerun()  # <<< QUAN TRỌNG: rerender để đổi màu ngay


    st.header("🏢 SƠ ĐỒ TỔ CHỨC")
    st.write("Di chuyển đến:")

    st.markdown('<div class="nav-menu">', unsafe_allow_html=True)

    room_button("💱 Sàn Kinh doanh Ngoại hối", "DEALING")
    room_button("🛡️ Phòng Quản trị Rủi ro", "RISK")
    room_button("🚢 Phòng Thanh toán Quốc tế", "TRADE")
    room_button("📈 Phòng Đầu tư Quốc tế", "INVEST")
    room_button("🌍 Ban Chiến lược Vĩ mô", "MACRO")
    room_button("🏆 Bảng vàng Thành tích", "LEADERBOARD")

    st.markdown('</div>', unsafe_allow_html=True)


    st.markdown("---")
    st.info("💡 Sau khi tính toán, hãy xem **Giải thích** hoặc gọi **Chuyên gia AI** để được tư vấn chuyên sâu.")
    st.markdown("---")
    #st.caption("© 2026 - Nguyễn Minh Hải", help="Finance Lab – International Finance Simulation") 
    # Tạo nút bấm trải dài hết chiều rộng sidebar
    # Người dùng bấm vào dòng chữ bản quyền -> Hiện About
    with st.popover("© 2026 - Nguyễn Minh Hải", use_container_width=True):        
        st.write("Mô phỏng Tài chính Quốc tế")
        st.image("about.png") # Nhớ thay tên file ảnh của bạn
    
    # st.markdown("---")
    # # --- PHẦN UI HƯỚNG DẪN CÀI ĐẶT ---
    # # Bạn có thể đặt đoạn này ở Sidebar hoặc cuối trang
    # with st.expander("📲 **Bấm vào đây để cài App lên điện thoại**", expanded=False):
    #     st.write("Chọn iOS hoặc Android và làm theo 2 bước sau:")
        
    #     # Tạo 2 tab hướng dẫn cho iPhone và Android
    #     tab_ios, tab_android = st.tabs(["🍏 iPhone (iOS)", "🤖 Android"])
        
    #     with tab_ios:
    #         st.markdown("""
    #         **Bước 1:** Bấm vào nút **Chia sẻ** (Share) trên thanh menu dưới cùng của Safari.  
    #         *(Biểu tượng hình vuông có mũi tên đi lên)* <div style="text-align: center; margin: 10px 0;">
    #             <span style="font-size: 30px;">↥</span> 
    #         </div>

    #         **Bước 2:** Kéo xuống và chọn dòng **"Thêm vào MH chính"** (Add to Home Screen).
            
    #         <div style="text-align: center; margin: 10px 0;">
    #             <span style="font-size: 30px;">➕</span>
    #         </div>
    #         """, unsafe_allow_html=True)
            
    #     with tab_android:
    #         st.markdown("""
    #         **Bước 1:** Bấm vào nút **Menu** (3 chấm dọc) ở góc trên bên phải Chrome.
            
    #         <div style="text-align: center; margin: 10px 0;">
    #             <span style="font-size: 30px;">⋮</span>
    #         </div>

    #         **Bước 2:** Chọn **"Cài đặt ứng dụng"** hoặc **"Thêm vào màn hình chính"**.
            
    #         <div style="text-align: center; margin: 10px 0;">
    #             <span style="font-size: 30px;">📲</span>
    #         </div>
    #         """, unsafe_allow_html=True)

    #     st.info("💡 **Mẹo:** Sau khi cài xong, App sẽ hiện icon trên màn hình chính và chạy toàn màn hình (không còn thanh địa chỉ web), giúp trải nghiệm mượt mà hơn!")


def footer():
    st.markdown(
        """
<div class="copyright">
© 2026 Designed by Nguyễn Minh Hải
</div>
        """,
        unsafe_allow_html=True,
    )


# ==============================================================================
# PHÒNG 1: DEALING ROOM
# ==============================================================================
def room_1_dealing():
    st.markdown('<p class="header-style">💱 Sàn Kinh doanh Ngoại hối (Dealing Room)</p>', unsafe_allow_html=True)
    st.markdown(
        """
<div class="role-card">
  <div class="role-title">👤 Vai diễn: Chuyên viên Kinh doanh Tiền tệ (FX Trader)</div>
  <div class="mission-text">"Nhiệm vụ: Niêm yết tỷ giá chéo (Cross-rate) và thực hiện kinh doanh chênh lệch giá (Arbitrage) khi phát hiện thị trường mất cân bằng."</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    tab1, tab2 = st.tabs(["🔢 Niêm yết Tỷ giá Chéo", "⚡ Săn Arbitrage (Tam giác)"])

    # -------------------------
    # TAB 1: Cross-rate
    # -------------------------
    with tab1:
        st.subheader("🏦 Bảng điện tử Tỷ giá liên ngân hàng")
        st.caption("Nhập tỷ giá thị trường quốc tế và nội địa để tính tỷ giá chéo (EUR/VND).")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 🇺🇸 Thị trường 1: USD/VND")
            usd_bid = st.number_input("BID (NH Mua USD):", value=25350.0, step=10.0, format="%.0f", key="r1_usd_bid")
            usd_ask = st.number_input("ASK (NH Bán USD):", value=25450.0, step=10.0, format="%.0f", key="r1_usd_ask")
        with c2:
            st.markdown("##### 🇪🇺 Thị trường 2: EUR/USD")
            eur_bid = st.number_input("BID (NH Mua EUR):", value=1.0820, step=0.0001, format="%.4f", key="r1_eur_bid")
            eur_ask = st.number_input("ASK (NH Bán EUR):", value=1.0850, step=0.0001, format="%.4f", key="r1_eur_ask")

        st.markdown("---")

        if st.button("🚀 TÍNH TOÁN & NIÊM YẾT", key="btn_cross_rate", use_container_width=True):
            cross_bid = eur_bid * usd_bid
            cross_ask = eur_ask * usd_ask
            spread = cross_ask - cross_bid

            st.success(f"✅ TỶ GIÁ NIÊM YẾT (EUR/VND): {cross_bid:,.0f} - {cross_ask:,.0f}")
            st.info(f"📊 Spread (Chênh lệch Mua-Bán): {spread:,.0f} VND/EUR")

            with st.expander("🎓 GÓC HỌC TẬP: GIẢI MÃ CÔNG THỨC & SỐ LIỆU", expanded=False):
                st.markdown("#### 1. Công thức Toán học")
                st.latex(r"\text{EUR/VND}_{Bid} = \text{EUR/USD}_{Bid} \times \text{USD/VND}_{Bid}")
                st.latex(r"\text{EUR/VND}_{Ask} = \text{EUR/USD}_{Ask} \times \text{USD/VND}_{Ask}")

                st.divider()

                st.markdown("#### 2. Áp dụng số liệu bạn vừa nhập")
                st.write("Hệ thống đã thực hiện phép tính cụ thể như sau:")

                st.markdown(
                    f"""
**a) Tính Tỷ giá Mua (BID):**
$$
{eur_bid:.4f} \\times {usd_bid:,.0f} = \\mathbf{{{cross_bid:,.0f}}}
$$

**b) Tính Tỷ giá Bán (ASK):**
$$
{eur_ask:.4f} \\times {usd_ask:,.0f} = \\mathbf{{{cross_ask:,.0f}}}
$$

**c) Tính Spread:**
$$
{cross_ask:,.0f} - {cross_bid:,.0f} = \\mathbf{{{spread:,.0f}}}
$$
"""
                )

                st.divider()

                st.markdown("#### 3. Tại sao lại nhân `Bid × Bid`?")
                st.info(
                    """
Để Ngân hàng Việt Nam **mua EUR** từ khách hàng (trả VND), họ đi “đường vòng” qua USD:
1) **Bước 1:** Bán EUR lấy USD trên thị trường quốc tế → dùng **EUR/USD Bid** (giá đối tác mua EUR).
2) **Bước 2:** Bán USD lấy VND tại Việt Nam → dùng **USD/VND Bid** (giá thị trường mua USD).

👉 Kết luận: **Cross Bid = Bid × Bid**. Tương tự **Cross Ask = Ask × Ask**.
"""
                )

    # -------------------------
    # TAB 2: Triangular arbitrage
    # -------------------------
    with tab2:
        st.subheader("⚡ Săn Arbitrage (Kinh doanh chênh lệch giá)")
        st.caption("Mô phỏng arbitrage tam giác giữa 3 báo giá. Hệ thống tự chọn chiều giao dịch tối ưu.")

        # 1) Inputs
        capital = st.number_input("Vốn kinh doanh (USD):", value=1_000_000.0, step=10_000.0, format="%.0f", key="r1_capital")

        st.markdown("---")
        k1, k2, k3 = st.columns(3)
        with k1:
            bank_a = st.number_input("Bank A (USD/VND):", value=25_000.0, help="Giá bán USD lấy VND", key="r1_bank_a")
        with k2:
            bank_b = st.number_input("Bank B (EUR/USD):", value=1.1000, help="Giá bán EUR lấy USD", key="r1_bank_b")
        with k3:
            bank_c = st.number_input("Bank C (EUR/VND):", value=28_000.0, help="Giá bán EUR lấy VND", key="r1_bank_c")

        # Core compute (always compute to feed AI)
        fair_rate_c = bank_a * bank_b

        # Path 1: USD -> EUR -> VND -> USD
        path1_eur = capital / bank_b
        path1_vnd = path1_eur * bank_c
        path1_usd_final = path1_vnd / bank_a
        profit1 = path1_usd_final - capital

        # Path 2: USD -> VND -> EUR -> USD
        path2_vnd = capital * bank_a
        path2_eur = path2_vnd / bank_c
        path2_usd_final = path2_eur * bank_b
        profit2 = path2_usd_final - capital

        if profit1 > profit2 and profit1 > 0:
            best_direction = "Mua EUR (Bank B) ➔ Bán tại Bank C ➔ Đổi về Bank A"
            best_profit = profit1
        elif profit2 >= profit1 and profit2 > 0:
            best_direction = "Đổi VND (Bank A) ➔ Mua EUR (Bank C) ➔ Bán tại Bank B"
            best_profit = profit2
        else:
            best_direction = "Không có cơ hội (Thị trường cân bằng hoặc lỗ)"
            best_profit = 0.0

        st.markdown("---")

        if st.button("🚀 KÍCH HOẠT THUẬT TOÁN ARBITRAGE", key="btn_arbitrage", use_container_width=True):
            st.markdown("### 📝 Nhật ký giao dịch tối ưu:")

            # tránh nhiễu do làm tròn
            if profit1 > 1.0:
                st.success("✅ PHÁT HIỆN CƠ HỘI: Mua EUR (Bank B) ➔ Bán tại Bank C ➔ Đổi về Bank A")
                st.markdown(
                    f"""
<div class="step-box">
1. <b>Dùng USD mua EUR (tại Bank B):</b><br>
{capital:,.0f} / {bank_b} = <b>{path1_eur:,.2f} EUR</b><br><br>
2. <b>Bán EUR đổi lấy VND (tại Bank C):</b><br>
{path1_eur:,.2f} × {bank_c:,.0f} = <b>{path1_vnd:,.0f} VND</b> (Giá EUR ở C đang cao)<br><br>
3. <b>Đổi VND về lại USD (tại Bank A):</b><br>
{path1_vnd:,.0f} / {bank_a:,.0f} = <b>{path1_usd_final:,.2f} USD</b>
</div>
""",
                    unsafe_allow_html=True,
                )
                st.markdown(f'<div class="result-box">🎉 LỢI NHUẬN: +{profit1:,.2f} USD</div>', unsafe_allow_html=True)
                st.info(f"💡 Gợi ý cân bằng: chỉnh **Bank C** về **{fair_rate_c:,.0f}** (= {bank_a:,.0f} × {bank_b}).")

            elif profit2 > 1.0:
                st.success("✅ PHÁT HIỆN CƠ HỘI: Đổi VND (Bank A) ➔ Mua EUR (Bank C) ➔ Bán tại Bank B")
                st.markdown(
                    f"""
<div class="step-box">
1. <b>Đổi USD sang VND (tại Bank A):</b><br>
{capital:,.0f} × {bank_a:,.0f} = <b>{path2_vnd:,.0f} VND</b><br><br>
2. <b>Dùng VND mua EUR (tại Bank C):</b><br>
{path2_vnd:,.0f} / {bank_c:,.0f} = <b>{path2_eur:,.2f} EUR</b> (Giá EUR ở C đang rẻ)<br><br>
3. <b>Bán EUR đổi về USD (tại Bank B):</b><br>
{path2_eur:,.2f} × {bank_b} = <b>{path2_usd_final:,.2f} USD</b>
</div>
""",
                    unsafe_allow_html=True,
                )
                st.markdown(f'<div class="result-box">🎉 LỢI NHUẬN: +{profit2:,.2f} USD</div>', unsafe_allow_html=True)
                st.info(f"💡 Gợi ý cân bằng: chỉnh **Bank C** về **{fair_rate_c:,.0f}** (= {bank_a:,.0f} × {bank_b}).")

            else:
                st.balloons()
                st.warning("⚖️ Thị trường cân bằng (No Arbitrage). Cả 2 chiều giao dịch đều không sinh lời.")
                st.success(f"👏 Bạn đang ở vùng cân bằng: {bank_c:,.0f} ≈ {fair_rate_c:,.0f} (= {bank_a:,.0f} × {bank_b})")

            with st.expander("🎓 BẢN CHẤT: Tại sao có tiền lời?"):
                st.markdown(
                    """
**Nguyên lý:** Arbitrage tam giác (Triangular Arbitrage).

Máy tính so sánh 2 con đường:
- **Vòng 1:** USD ➔ EUR (Bank B) ➔ VND (Bank C) ➔ USD (Bank A)
- **Vòng 2:** USD ➔ VND (Bank A) ➔ EUR (Bank C) ➔ USD (Bank B)

Nếu chênh lệch đủ lớn, đi một vòng sẽ “đẻ” ra lợi nhuận.
"""
                )

        # Minh họa (cố định, tránh lệch)
        with st.container(border=True):
            st.markdown("##### 🔄 Minh họa dòng tiền kiếm lời:")
            st.graphviz_chart(
                """
digraph {
    rankdir=LR;
    node [fontname="Arial", shape=box, style="filled,rounded", fillcolor="#f0f2f6", color="#d1d5db"];
    edge [color="#555555", fontname="Arial", fontsize=10];

    MarketA [label="📉 Thị trường A\\n(Giá Thấp)", fillcolor="#e8f5e9", color="#4caf50", penwidth=2];
    MarketB [label="📈 Thị trường B\\n(Giá Cao)", fillcolor="#ffebee", color="#f44336", penwidth=2];
    Wallet [label="💰 TÚI TIỀN\\n(Lợi nhuận)", shape=ellipse, fillcolor="#fff9c4", color="#fbc02d", style=filled];

    MarketA -> MarketB [label="1. Mua thấp & Chuyển sang", color="#4caf50", penwidth=2];
    MarketB -> Wallet [label="2. Bán cao & Chốt lời", color="#f44336", penwidth=2];
}
""",
                use_container_width=True,
            )
            st.info("💡 Dễ hiểu: mua ở nơi rẻ hơn và bán ngay ở nơi đắt hơn, trước khi giá kịp điều chỉnh.")

        # AI
        st.markdown("---")
        if st.button("AI Advisor – FX Arbitrage", type="primary", icon="🤖", key="btn_ai_risk"):
            # BƯỚC 1: KIỂM TRA ĐĂNG NHẬP (Lấy từ Session State)
            # Lấy ID từ session ra, nếu không có thì trả về None
            user_id = st.session_state.get('CURRENT_USER') 

            if not user_id:
                st.error("🔒 Bạn chưa đăng nhập đúng MSSV ở thanh bên trái!")
                st.toast("Vui lòng nhập MSSV để tiếp tục!", icon="🔒")
                st.stop() # Dừng lại ngay, không chạy tiếp

            # BƯỚC 2: KIỂM TRA HẠN MỨC (QUOTA)
            current_used = get_usage_from_supabase(user_id)
            
            if current_used >= MAX_AI_QUOTA:
                st.warning(f"⚠️ Sinh viên {user_id} đã hết lượt dùng AI ({MAX_AI_QUOTA}/{MAX_AI_QUOTA}).")
                st.stop()

            # 3. Chuẩn bị dữ liệu
            context = f"""
            Tình huống: Arbitrage Tam giác.
            - Vốn: {capital:,.0f} USD
            - Tỷ giá: A={bank_a}, B={bank_b}, C={bank_c}
            - Kết quả: {best_direction}
            - Lợi nhuận: {best_profit:,.2f} USD
            """
            
            task = "Phân tích rủi ro khớp lệnh, chi phí vốn và đưa ra quyết định GO/NO-GO."

            # 4. Gọi AI và Xử lý lỗi
            with st.spinner(f"AI đang phân tích... (Lượt gọi AI thứ {current_used + 1}/{MAX_AI_QUOTA})"):
                try:
                    advise_result = ask_gemini_advisor("Senior FX Trader", context, task)

                    # KIỂM TRA: Nếu kết quả trả về bắt đầu bằng ⚠️ nghĩa là có lỗi
                    if advise_result.startswith("⚠️"):
                        st.error(advise_result) # Hiện lỗi cho GV/SV biết
                        st.info("Lượt này chưa bị trừ do lỗi hệ thống.")
                    else:
                        # 1. Trừ quota trong Database/File
                        consume_quota(user_id)
                        
                        # 2. CẬP NHẬT SIDEBAR NGAY LẬP TỨC (Không cần Rerun)
                        # Lấy số mới để hiển thị
                        new_usage = current_used + 1
                        
                        # Bắn nội dung mới vào cái hộp "quota_placeholder" đang nằm bên Sidebar
                        # Lưu ý: Bạn cần đảm bảo biến 'quota_placeholder' truy cập được từ đây
                        quota_placeholder.info(f"Đã dùng: {new_usage}/{MAX_AI_QUOTA} lượt")
                        
                        # 3. Hiện kết quả AI ra màn hình chính
                        st.markdown(f'<div class="ai-box"><h4>🤖 LỜI KHUYÊN CỦA NHÀ GIAO DỊCH AI</h4>{advise_result}</div>', unsafe_allow_html=True)                        
                except Exception as e:
                    st.error(f"⚠️ Lỗi khi gọi AI: {str(e)}")

    footer()


# ==============================================================================
# PHÒNG 2: RISK MANAGEMENT
# ==============================================================================
def room_2_risk():
    st.markdown('<p class="header-style">🛡️ Phòng Quản trị Rủi ro (Risk Management)</p>', unsafe_allow_html=True)

    st.subheader("1. Hồ sơ Khoản nợ (Debt Profile)")
    c1, c2 = st.columns(2)
    with c1:
        debt_amount = st.number_input("Giá trị khoản phải trả (USD):", value=1_000_000.0, step=10_000.0, format="%.0f", key="r2_debt")
    with c2:
        days_loan_profile = st.number_input("Thời hạn thanh toán (Ngày):", value=90, step=30, key="r2_days_profile")

    st.markdown(
        f"""
<div class="role-card">
  <div class="role-title">👤 Vai diễn: Giám đốc Tài chính (CFO)</div>
  <div class="mission-text">"Nhiệm vụ: Tính toán tỷ giá kỳ hạn hợp lý và lựa chọn công cụ phòng vệ (Forward/Option) tối ưu cho khoản nợ <b>{debt_amount:,.0f} USD</b> đáo hạn sau <b>{days_loan_profile} ngày</b>."</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # IRP
    st.subheader("2. Tính Tỷ giá Kỳ hạn (Fair Forward Rate)")
    st.caption("Định giá Forward dựa trên chênh lệch lãi suất VND và USD (IRP).")

    c_input1, c_input2, c_input3, c_input4 = st.columns(4)
    with c_input1:
        spot_irp = st.number_input("Spot Rate (Hiện tại):", value=25_000.0, step=10.0, format="%.0f", key="r2_spot")
    with c_input2:
        r_vnd = st.number_input("Lãi suất VND (%/năm):", value=6.0, step=0.1, key="r2_rvnd")
    with c_input3:
        r_usd = st.number_input("Lãi suất USD (%/năm):", value=3.0, step=0.1, key="r2_rusd")
    with c_input4:
        days_loan = st.number_input("Kỳ hạn (Ngày):", value=90, step=30, key="r2_days_irp")

    numerator = 1 + (r_vnd / 100) * (days_loan / 360)
    denominator = 1 + (r_usd / 100) * (days_loan / 360)
    fwd_cal = spot_irp * (numerator / denominator)
    swap_point = fwd_cal - spot_irp

    st.markdown("---")
    col_res_irp1, col_res_irp2 = st.columns([1, 1.5])

    with col_res_irp1:
        st.markdown("##### 🏁 KẾT QUẢ TÍNH TOÁN")
        st.metric("Tỷ giá Forward (F)", f"{fwd_cal:,.0f} VND", help="Tỷ giá kỳ hạn hợp lý theo IRP")
        st.metric(
            "Điểm kỳ hạn (Swap Point)",
            f"{swap_point:,.0f} VND",
            delta="VND giảm giá (Forward > Spot)" if swap_point > 0 else "VND tăng giá (Forward < Spot)",
            delta_color="inverse",
        )

        if r_vnd > r_usd:
            st.warning(f"📉 Lãi suất VND cao hơn USD ({r_vnd}% > {r_usd}%) ⇒ VND thường bị “trừ điểm” (Forward cao hơn Spot).")
        else:
            st.success("📈 Lãi suất VND thấp hơn USD ⇒ VND thường được “cộng điểm” (Forward thấp hơn Spot).")

    with col_res_irp2:
        with st.expander("🎓 GÓC HỌC TẬP: GIẢI MÃ IRP & CÔNG THỨC", expanded=False):
            st.markdown("#### 1. IRP là gì?")
            st.info(
                """
**IRP (Interest Rate Parity – Ngang giá lãi suất)**:
Chênh lệch lãi suất giữa hai đồng tiền sẽ phản ánh vào chênh lệch giữa **Forward** và **Spot**.

Nói ngắn gọn: **Chênh lệch lãi suất = Chênh lệch tỷ giá kỳ hạn** (trong điều kiện không arbitrage).
"""
            )

            st.markdown("#### 2. Công thức tính Forward")
            st.latex(r"F = S \times \frac{1 + r_{VND} \times \frac{n}{360}}{1 + r_{USD} \times \frac{n}{360}}")
            st.caption("Thay số theo dữ liệu bạn nhập:")
            st.latex(
                f"F = {spot_irp:,.0f} \\times \\frac{{1 + {r_vnd}\\% \\times \\frac{{{days_loan}}}{{360}}}}{{1 + {r_usd}\\% \\times \\frac{{{days_loan}}}{{360}}}} = \\mathbf{{{fwd_cal:,.0f}}}"
            )

            st.divider()

            st.markdown("#### 3. Điểm kỳ hạn (Swap Point)")
            st.latex(f"\\text{{Swap}} = {fwd_cal:,.0f} - {spot_irp:,.0f} = \\mathbf{{{swap_point:,.0f}}}")

            st.divider()

            st.markdown("#### 4. Tại sao có quy luật này?")
            st.write(
                f"""
Theo nguyên lý **No Arbitrage**:
- Nếu lãi VND cao ({r_vnd}%) mà tỷ giá tương lai không giảm, nhà đầu tư sẽ bán USD để nắm VND gửi hưởng chênh lệch.
- Để triệt tiêu “bữa trưa miễn phí”, thị trường thường buộc VND **mất giá trong tương lai** tương ứng phần lãi suất cao hơn.
"""
            )

    st.markdown("---")
    st.subheader("3. So sánh Chiến lược Phòng vệ")

    st.info(
        """
💡 **HƯỚNG DẪN SINH VIÊN (TRY IT):**
- Để **Option thắng Forward**: đặt `Strike + Phí` < `Forward`, đồng thời kéo `Dự báo tỷ giá` lên cao.
- Để **Forward thắng Option**: chỉnh `Forward` thấp hơn tổng chi phí Option.
- Để **Thả nổi thắng**: kéo `Dự báo tỷ giá` xuống thấp hơn cả Forward và Option.
"""
    )

    col_strat1, col_strat2 = st.columns(2)
    with col_strat1:
        st.markdown("#### 🏦 Chốt Deal với Ngân hàng")
        f_rate_input = st.number_input(
            "Giá Forward Bank chào:",
            value=float(f"{fwd_cal:.2f}"),
            help="Thường Bank sẽ chào giá này hoặc cao hơn chút ít.",
            key="r2_fwd_offer",
        )
        st.markdown("**Thông số Quyền chọn (Option):**")
        strike = st.number_input("Strike Price (Giá thực hiện):", value=25_100.0, key="r2_strike")
        premium = st.number_input("Phí Option (VND/USD):", value=100.0, key="r2_premium")

    with col_strat2:
        st.markdown("#### 🔮 Dự báo Thị trường")
        future_spot = st.slider(
            f"Dự báo Spot sau {days_loan} ngày:",
            24_000.0,
            26_000.0,
            25_400.0,
            step=10.0,
            key="r2_future_spot",
        )

        if future_spot > f_rate_input:
            st.warning(
                f"""
🔥 **Cảnh báo:** Spot dự báo ({future_spot:,.0f}) cao hơn Forward ({f_rate_input:,.0f}).

👉 **Nên phòng vệ:** Forward/Option đều giúp né mức giá cao.
"""
            )
        else:
            st.success(
                f"""
❄️ **Thị trường hạ nhiệt:** Spot dự báo ({future_spot:,.0f}) thấp hơn Forward ({f_rate_input:,.0f}).

👉 **Cân nhắc:** Thả nổi hoặc Option (bỏ quyền) có thể lợi hơn Forward.
"""
            )

    # Costs
    cost_open = debt_amount * future_spot
    formula_open = f"{debt_amount:,.0f} × {future_spot:,.0f}"

    cost_fwd = debt_amount * f_rate_input
    formula_fwd = f"{debt_amount:,.0f} × {f_rate_input:,.0f}"

    if future_spot > strike:
        action_text = "Thực hiện quyền"
        price_base = strike
        explanation_opt = "✅Đã được bảo hiểm (Dùng Strike)"
        formula_opt = f"{debt_amount:,.0f} × ({strike:,.0f} + {premium:,.0f})"
    else:
        action_text = "Bỏ quyền (Lapse)"
        price_base = future_spot
        explanation_opt = "📉Mua giá chợ (Rẻ hơn Strike)"
        formula_opt = f"{debt_amount:,.0f} × ({future_spot:,.0f} + {premium:,.0f})"

    effective_opt_rate = price_base + premium
    cost_opt = debt_amount * effective_opt_rate

    
    # --- BƯỚC 1: TẠO DATAFRAME ---
    df_compare = pd.DataFrame(
        {
            "Chiến lược": ["1. Thả nổi (No Hedge)", "2. Kỳ hạn (Forward)", "3. Quyền chọn (Option)"],
            "Trạng thái": ["Chấp nhận rủi ro", "Khóa cứng tỷ giá", explanation_opt],
            "Tỷ giá thực tế": [future_spot, f_rate_input, effective_opt_rate],
            "Tổng chi phí (VND)": [cost_open, cost_fwd, cost_opt],
        }
    )

    # --- BƯỚC 1: ÉP KIỂU SỐ (Để đảm bảo tính toán đúng) ---
    df_compare["Tỷ giá thực tế"] = df_compare["Tỷ giá thực tế"].astype(float)
    df_compare["Tổng chi phí (VND)"] = df_compare["Tổng chi phí (VND)"].astype(float)

    # --- BƯỚC 2: CẤU HÌNH COLUMN CONFIG (Chỉ dùng để chỉnh độ rộng và tiêu đề) ---
    # LƯU Ý: Đã XÓA dòng format="%,.0f" ở đây để tránh xung đột
    column_config_setup = {
        "Chiến lược": st.column_config.TextColumn("Chiến lược", width="medium", pinned=True),
        "Trạng thái": st.column_config.TextColumn("Trạng thái", width="medium"),
        "Tỷ giá thực tế": st.column_config.Column("Tỷ giá", width="small"), # Dùng Column thường
        "Tổng chi phí (VND)": st.column_config.Column("Chi phí (VND)", width="medium"),
    }

    # --- BƯỚC 3: XỬ LÝ STYLE (Tô màu + Format dấu phẩy + Canh phải) ---
    min_cost = df_compare["Tổng chi phí (VND)"].min()

    # Hàm tô màu nền
    def highlight_best(s):
        return ['background-color: #d1e7dd; color: #0f5132; font-weight: bold' if v == min_cost else '' for v in s]

    # TẠO STYLER OBJECT (Chuỗi xử lý liên hoàn)
    styled_df = (
        df_compare.style
        .apply(highlight_best, subset=["Tổng chi phí (VND)"])             # 1. Tô màu dòng tốt nhất
        .format("{:,.0f}", subset=["Tỷ giá thực tế", "Tổng chi phí (VND)"]) # 2. Format dấu phẩy (25000 -> 25,000)
        # 3. QUAN TRỌNG: Ép canh lề phải bằng CSS (Vì sau khi format nó biến thành text)
        .set_properties(subset=["Tỷ giá thực tế", "Tổng chi phí (VND)"], **{'text-align': 'right'})
    )

    st.markdown("##### 📊 So sánh hiệu quả các chiến lược:")

    st.dataframe(
        styled_df, 
        column_config=column_config_setup,
        use_container_width=False, 
        hide_index=True 
    )
    
    # --- BƯỚC 3: KẾT LUẬN & GIẢI THÍCH ---

    best_idx = df_compare["Tổng chi phí (VND)"].idxmin()
    best_strat = df_compare.loc[best_idx, "Chiến lược"]
    st.markdown(f"### 🏆 KẾT LUẬN: Chọn **{best_strat}**")

    if best_idx == 1:
        st.success(
            f"""
**Vì sao chọn Forward?**
- Forward ({f_rate_input:,.0f}) rẻ hơn Spot dự báo ({future_spot:,.0f}).
- Rẻ hơn Option (vì Option phải cộng premium thành {effective_opt_rate:,.0f}).

👉 Hợp doanh nghiệp thích “chốt chi phí” chắc chắn.
"""
        )
    elif best_idx == 2:
        st.success(
            f"""
**Vì sao chọn Option?**
- Tổng chi phí Option đang thấp nhất (đã gồm premium).
- Khi thị trường bùng nổ, Option “chặn trần” bằng Strike ({strike:,.0f}) thay vì mua theo Spot cao.

👉 Option mạnh khi biến động lớn và bạn muốn giữ “quyền chọn cơ hội”.
"""
        )
    else:
        st.warning(
            f"""
**Vì sao chọn Thả nổi?**
- Bạn kỳ vọng tỷ giá giảm ({future_spot:,.0f}) ⇒ chốt Forward/Option lúc này có thể lãng phí.

👉 *Rủi ro cao*: dự báo sai sẽ đội chi phí rất mạnh.
"""
        )

    st.markdown("---")
    # --- PHẦN NÚT BẤM AI ---
    if st.button("AI Advisor – FX Hedging", type="primary", icon="🤖", key="btn_ai_cfo"):
        
        # BƯỚC 1: LẤY USER ID
        user_id = st.session_state.get('CURRENT_USER') 

        # TRƯỜNG HỢP 1: CHƯA ĐĂNG NHẬP
        if not user_id:
            st.error("🔒 Bạn chưa đăng nhập đúng MSSV ở thanh bên trái!")
            st.toast("Vui lòng nhập MSSV để tiếp tục!", icon="🔒")
            # QUAN TRỌNG: Không có st.stop() ở đây.
            # Code sẽ bỏ qua phần 'else' bên dưới và chạy thẳng xuống Mục 4.

        # TRƯỜNG HỢP 2: ĐÃ ĐĂNG NHẬP (Xử lý tiếp Quota và AI trong khối này)
        else:
            # BƯỚC 2: KIỂM TRA HẠN MỨC (QUOTA)
            current_used = get_usage_from_supabase(user_id)
            
            if current_used >= MAX_AI_QUOTA:
                # Hết lượt -> Báo cảnh báo
                st.warning(f"⚠️ Sinh viên {user_id} đã hết lượt dùng AI ({MAX_AI_QUOTA}/{MAX_AI_QUOTA}).")
            
            else:
                # Còn lượt -> Chạy AI (Toàn bộ logic AI nằm trong này)
                
                # 3. Chuẩn bị dữ liệu
                context = f"""
    Bài toán: Nợ {debt_amount:,.0f} USD.
    Spot hiện tại: {spot_irp:,.0f}; Kỳ hạn: {days_loan} ngày.

    Phương án:
    1) Thả nổi @ {future_spot:,.0f} ⇒ {cost_open:,.0f} VND
    2) Forward @ {f_rate_input:,.0f} ⇒ {cost_fwd:,.0f} VND
    3) Option: Strike {strike:,.0f} + Premium {premium:,.0f} (tỷ giá hiệu dụng {effective_opt_rate:,.0f}) ⇒ {cost_opt:,.0f} VND

    Kết quả máy tính chọn: {best_strat}
    """
                task = "Nhận xét kết quả. Phân tích 'chi phí cơ hội' của Forward và 'giá trị quyền' của Option (trong 3-4 câu)."
                
                with st.spinner(f"AI đang phân tích chiến lược...(Lượt gọi AI thứ {current_used + 1}/{MAX_AI_QUOTA})"):
                    try:
                        advise = ask_gemini_advisor("CFO Expert", context, task)
                        
                        if advise.startswith("⚠️"):
                            st.error(advise)
                            st.info("Lượt này chưa bị trừ do lỗi hệ thống.")
                        else:
                            # 1. Trừ quota
                            consume_quota(user_id)
                            
                            # 2. Cập nhật Sidebar (nếu có placeholder)
                            if 'quota_placeholder' in locals() or 'quota_placeholder' in globals():
                                new_usage = current_used + 1
                                quota_placeholder.info(f"Đã dùng: {new_usage}/{MAX_AI_QUOTA} lượt")
                            
                            # 3. Hiện kết quả
                            st.markdown(f'<div class="ai-box"><h4>🤖 GÓC NHÌN TỪ GIÁM ĐỐC TÀI CHÍNH AI</h4>{advise}</div>', unsafe_allow_html=True)
                        
                    except Exception as e:
                        st.error(f"⚠️ Lỗi khi gọi AI: {str(e)}")

    # =========================================================
    # MỤC 4 (NẰM NGOÀI MỌI KHỐI IF CỦA BUTTON)
    # =========================================================
    # Vì không dùng st.stop() ở trên, nên dù chưa đăng nhập hay lỗi gì
    # Code vẫn trôi xuống đây và hiển thị mục 4 bình thường.
    st.markdown("---")
    st.subheader("4. Tình huống nâng cao: Xử lý khi Lệch dòng tiền (Swap)")
    
    with st.expander("🔄 MỞ RỘNG: Dòng tiền bị trễ hạn, phải làm sao?", expanded=False):
        st.markdown(
            """
            <div class="mission-text">
            🚨 <b>Tình huống:</b> Hợp đồng Forward cũ đã đến ngày đáo hạn, nhưng đối tác báo 
            <b>delay thanh toán thêm 30 ngày</b> nữa. Bạn chưa cần USD ngay lúc này, nhưng ngân hàng bắt buộc tất toán Deal cũ.
            <br>👉 <b>Giải pháp:</b> Dùng <b>FX Swap</b> (Bán Spot tất toán cũ - Mua Forward kỳ hạn mới).
            </div>
            """, unsafe_allow_html=True
        )

        c_swap1, c_swap2 = st.columns(2)
        with c_swap1:
            delay_days = st.number_input("Số ngày delay:", value=30, step=15, key="swap_days")
            # Giả định Spot tại thời điểm đáo hạn Deal cũ
            spot_at_maturity = st.number_input(
                "Spot rate tại ngày đáo hạn Deal cũ:", 
                value=spot_irp, # Lấy tạm giá hiện tại làm ví dụ
                help="Giá thị trường tại thời điểm Deal cũ hết hạn",
                key="swap_spot_mat"
            )
        
        with c_swap2:
            # Tính lại Forward mới cho kỳ hạn delay
            # Công thức đơn giản hóa giả định lãi suất không đổi
            num_swap = 1 + (r_vnd / 100) * (delay_days / 360)
            den_swap = 1 + (r_usd / 100) * (delay_days / 360)
            new_fwd_rate = spot_at_maturity * (num_swap / den_swap)
            
            st.metric("Tỷ giá Forward mới (cho kỳ hạn delay)", f"{new_fwd_rate:,.0f} VND")
            swap_points_new = new_fwd_rate - spot_at_maturity
            st.metric("Điểm Swap (Swap Point)", f"{swap_points_new:,.0f} VND")

        st.markdown("#### 🧮 Hạch toán chi phí Swap (Rollover)")
        
        # 1. Tất toán Deal cũ: Mua Forward giá f_rate_input, giờ bán lại giá Spot thị trường (spot_at_maturity)
        # Nếu Spot < Forward cũ => Lỗ (vì cam kết mua cao, giờ bán ra thấp)
        settlement_pl = (spot_at_maturity - f_rate_input) * debt_amount
        
        # 2. Chi phí giữ trạng thái thêm X ngày (Swap cost)
        # Chênh lệch lãi suất thể hiện qua Swap Point
        swap_cost_total = swap_points_new * debt_amount

        col_cal1, col_cal2 = st.columns(2)
        
        with col_cal1:
            st.markdown("**1. Tất toán Deal cũ (Realized P/L):**")
            st.latex(r"\text{P/L} = (S_{maturity} - F_{old}) \times \text{Volume}")
            st.write(f"= ({spot_at_maturity:,.0f} - {f_rate_input:,.0f}) × {debt_amount:,.0f}")
            if settlement_pl >= 0:
                st.success(f"💰 Lãi từ chênh lệch giá: {settlement_pl:,.0f} VND")
            else:
                st.error(f"💸 Lỗ tất toán vị thế cũ: {settlement_pl:,.0f} VND")
        
        with col_cal2:
            st.markdown("**2. Chi phí Swap (Time Value):**")
            st.latex(r"\text{Cost} = \text{Swap Point} \times \text{Volume}")
            st.write(f"= ({new_fwd_rate:,.0f} - {spot_at_maturity:,.0f}) × {debt_amount:,.0f}")
            
            if swap_points_new > 0:
                 st.warning(f"📉 Bạn phải trả thêm (VND lãi cao hơn USD): {swap_cost_total:,.0f} VND")
            else:
                 st.success(f"📈 Bạn được nhận thêm (Swap Point âm): {abs(swap_cost_total):,.0f} VND")

        total_swap_impact = settlement_pl - swap_cost_total # P/L cũ - Chi phí Swap mới (tùy convention, ở đây để đơn giản ta cộng gộp)
        
        st.info(
            f"""
            💡 **Bài học:** Khi gia hạn nợ bằng Swap, bạn không chỉ quan tâm tỷ giá mới, mà phải xử lý phần chênh lệch (Lãi/Lỗ) của hợp đồng cũ ngay lập tức.
            """
        )

    footer()


# ==============================================================================
# PHÒNG 3: TRADE FINANCE
# ==============================================================================
def room_3_trade():
    st.markdown('<p class="header-style">🚢 Phòng Thanh toán Quốc tế (Trade Finance)</p>', unsafe_allow_html=True)
    st.markdown(
        """
<div class="role-card">
  <div class="role-title">👤 Vai diễn: Chuyên viên Thanh toán Quốc tế</div>
  <div class="mission-text">"Nhiệm vụ: Tư vấn phương thức thanh toán tối ưu chi phí và kiểm tra bộ chứng từ (Checking) theo chuẩn UCP 600."</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    tab_cost, tab_check = st.tabs(["💰 Bài toán Chi phí (T/T, Nhờ thu, L/C)", "📝 Kiểm tra Chứng từ (Checking)"])

    # -------------------------
    # TAB COST
    # -------------------------
    with tab_cost:
        st.subheader("💸 Bài toán Tối ưu Chi phí Thanh toán Quốc tế")
        st.caption("So sánh: Phí ngân hàng & Chi phí vốn (lãi) giữa T/T, Nhờ thu, L/C.")

        with st.expander("📝 BƯỚC 1: NHẬP GIÁ TRỊ HỢP ĐỒNG & LÃI SUẤT", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                val = st.number_input("Giá trị hợp đồng (USD):", value=100_000.0, step=1_000.0, key="r3_val")
                interest_rate = st.number_input(
                    "Lãi suất vay vốn (%/năm):",
                    value=7.0,
                    step=0.1,
                    help="Dùng để tính chi phí cơ hội/lãi vay trong thời gian chờ thanh toán",
                    key="r3_ir",
                )
            with c2:
                days_tt = st.number_input("Số ngày đọng vốn T/T:", value=5, help="Thời gian tiền đi trên đường", key="r3_days_tt")
                days_col = st.number_input("Số ngày đọng vốn Nhờ thu:", value=15, help="Thời gian gửi chứng từ", key="r3_days_col")
                days_lc = st.number_input("Số ngày đọng vốn L/C:", value=30, help="Thời gian xử lý bộ chứng từ", key="r3_days_lc")

        st.markdown("---")
        st.subheader("🏦 BƯỚC 2: CẤU HÌNH BIỂU PHÍ NGÂN HÀNG")

        col_tt, col_col, col_lc = st.columns(3)

        with col_tt:
            st.markdown("#### 1) T/T (Chuyển tiền)")
            tt_pct = st.number_input("Phí chuyển tiền (%):", value=0.2, step=0.01, format="%.2f", key="r3_tt_pct")
            tt_min = st.number_input("Min (USD) - T/T:", value=10.0, key="r3_tt_min")
            tt_max = st.number_input("Max (USD) - T/T:", value=200.0, key="r3_tt_max")
            tt_other = st.number_input("Điện phí (USD):", value=20.0, key="r3_tt_other")

        with col_col:
            st.markdown("#### 2) Nhờ thu (D/P, D/A)")
            col_pct = st.number_input("Phí nhờ thu (%):", value=0.15, step=0.01, format="%.2f", key="r3_col_pct")
            col_min = st.number_input("Min (USD) - Col:", value=20.0, key="r3_col_min")
            col_max = st.number_input("Max (USD) - Col:", value=250.0, key="r3_col_max")
            col_other = st.number_input("Bưu điện phí (USD):", value=50.0, key="r3_col_other")

        with col_lc:
            st.markdown("#### 3) L/C (Tín dụng thư)")
            lc_open_pct = st.number_input("Phí mở L/C (%):", value=0.3, step=0.01, format="%.2f", key="r3_lc_open")
            lc_pay_pct = st.number_input("Phí thanh toán (%):", value=0.2, step=0.01, format="%.2f", key="r3_lc_pay")
            lc_min = st.number_input("Min (USD) - L/C:", value=50.0, key="r3_lc_min")
            lc_other = st.number_input("Phí khác (USD):", value=100.0, help="Tu chỉnh, bất hợp lệ...", key="r3_lc_other")

        st.markdown("---")

        if st.button("🚀 TÍNH TOÁN & SO SÁNH NGAY", key="btn_tf_cost", use_container_width=True):
            def calculate_fee_min_max(amount, pct, fee_min, fee_max):
                raw_fee = amount * (pct / 100)
                final_fee = max(fee_min, min(raw_fee, fee_max))
                return final_fee, raw_fee

            # T/T
            tt_bank_fee, tt_raw = calculate_fee_min_max(val, tt_pct, tt_min, tt_max)
            tt_total_bank = tt_bank_fee + tt_other
            tt_interest = val * (interest_rate / 100) * (days_tt / 360)
            tt_final = tt_total_bank + tt_interest

            # Collection
            col_bank_fee, col_raw = calculate_fee_min_max(val, col_pct, col_min, col_max)
            col_total_bank = col_bank_fee + col_other
            col_interest = val * (interest_rate / 100) * (days_col / 360)
            col_final = col_total_bank + col_interest

            # L/C
            lc_open_fee = max(lc_min, val * (lc_open_pct / 100))
            lc_pay_fee = val * (lc_pay_pct / 100)
            lc_total_bank = lc_open_fee + lc_pay_fee + lc_other
            lc_interest = val * (interest_rate / 100) * (days_lc / 360)
            lc_final = lc_total_bank + lc_interest

            st.subheader("📊 Kết quả Tổng hợp")
            m1, m2, m3 = st.columns(3)
            best_price = min(tt_final, col_final, lc_final)

            m1.metric("1) Tổng phí T/T", f"${tt_final:,.2f}", delta="Rẻ nhất (rủi ro cao)" if tt_final == best_price else None, delta_color="inverse")
            m2.metric("2) Tổng phí Nhờ thu", f"${col_final:,.2f}", delta=f"+${col_final - tt_final:,.2f} vs T/T", delta_color="off")
            m3.metric("3) Tổng phí L/C", f"${lc_final:,.2f}", delta=f"+${lc_final - tt_final:,.2f} vs T/T", delta_color="off")

            chart_data = pd.DataFrame(
                {
                    "Phương thức": ["T/T", "Nhờ thu", "L/C"],
                    "Phí Ngân hàng": [tt_total_bank, col_total_bank, lc_total_bank],
                    "Chi phí Vốn (Lãi)": [tt_interest, col_interest, lc_interest],
                }
            )
            st.bar_chart(chart_data.set_index("Phương thức"), stack=True, color=["#FF6C6C", "#4B4BFF"])

            st.markdown("### 🧮 Bảng chi tiết lời giải (Step-by-step)")
            st.info("Dưới đây là cách tính chi tiết giúp bạn hiểu rõ nguồn gốc các con số:")

            with st.expander("1️⃣ Chi tiết tính toán: T/T (Chuyển tiền)", expanded=False):
                st.latex(r"Cost_{T/T} = \text{Phí Bank} + \text{Lãi Vốn}")
                st.markdown(
                    f"""
**A) Phí dịch vụ Ngân hàng**
- Sơ bộ: {val:,.0f} × {tt_pct}% = {tt_raw:,.2f}
- Áp dụng Min/Max ({tt_min} – {tt_max}) ⇒ **{tt_bank_fee:,.2f}**
- Cộng điện phí {tt_other:,.2f} ⇒ **Tổng phí bank: {tt_total_bank:,.2f}**

**B) Chi phí vốn (lãi)**
- Công thức: Giá trị × Lãi suất × Ngày/360
- Thế số: {val:,.0f} × {interest_rate}% × ({days_tt}/360) = **{tt_interest:,.2f}**
"""
                )

            with st.expander("2️⃣ Chi tiết tính toán: Nhờ thu (Collection)", expanded=False):
                st.latex(r"Cost_{Col} = \text{Phí Nhờ Thu} + \text{Phí Khác} + \text{Lãi Vốn}")
                st.markdown(
                    f"""
**A) Phí dịch vụ Ngân hàng**
- Sơ bộ: {val:,.0f} × {col_pct}% = {col_raw:,.2f}
- Áp dụng Min/Max ({col_min} – {col_max}) ⇒ **{col_bank_fee:,.2f}**
- Cộng phí khác {col_other:,.2f} ⇒ **Tổng phí bank: {col_total_bank:,.2f}**

**B) Chi phí vốn**
- {val:,.0f} × {interest_rate}% × ({days_col}/360) = **{col_interest:,.2f}**
"""
                )

            with st.expander("3️⃣ Chi tiết tính toán: L/C (Tín dụng thư)", expanded=False):
                st.latex(r"Cost_{LC} = \text{Phí Mở} + \text{Phí T.Toán} + \text{Phí Khác} + \text{Lãi Vốn}")
                st.markdown(
                    f"""
**A) Các loại phí**
- Phí mở: {val:,.0f} × {lc_open_pct}% = {val*(lc_open_pct/100):,.2f} ⇒ áp Min {lc_min} ⇒ **{lc_open_fee:,.2f}**
- Phí thanh toán: {val:,.0f} × {lc_pay_pct}% = **{lc_pay_fee:,.2f}**
- Phí khác: **{lc_other:,.2f}**
⇒ **Tổng phí bank: {lc_total_bank:,.2f}**

**B) Chi phí vốn**
- Do giữ vốn {days_lc} ngày:
- {val:,.0f} × {interest_rate}% × ({days_lc}/360) = **{lc_interest:,.2f}**
"""
                )

            diff_lc = lc_final - tt_final
            diff_col = col_final - tt_final

            st.markdown("---")
            st.success(
                f"""
#### 💡 GÓC NHÌN QUẢN TRỊ (MANAGEMENT INSIGHT)

Chênh lệch chi phí chính là **“phí mua sự an toàn”** cho lô hàng **{val:,.0f} USD**:

**Nếu chọn Nhờ thu (Collection):**
- Trả thêm **{diff_col:,.2f} USD** so với T/T.
- Ngân hàng kiểm soát chứng từ nhưng **không cam kết trả tiền thay** người mua.

**Nếu chọn L/C:**
- Trả thêm **{diff_lc:,.2f} USD** so với T/T.
- Đổi lại, bạn mua **cam kết thanh toán của ngân hàng** ⇒ giảm rủi ro đối tác.

👉 Nếu rủi ro mất trắng là đáng kể, thì **{diff_lc:,.2f} USD** có thể là “phí bảo hiểm” hợp lý.
"""
            )

        footer()

    # -------------------------
    # TAB CHECKING
    # -------------------------
    with tab_check:
        st.subheader("📝 Kiểm tra Chứng từ (Checking) – UCP 600")
        st.caption("Giả lập bộ chứng từ và phát hiện lỗi bất hợp lệ (discrepancy).")

        # init session
        flags = ["s_late_ship", "s_late_pres", "s_over_amt", "s_dirty_bl"]
        for f in flags:
            if f not in st.session_state:
                st.session_state[f] = False

        if "chk_ship" not in st.session_state:
            st.session_state["chk_ship"] = pd.to_datetime("2025-01-15")
        if "chk_exp" not in st.session_state:
            st.session_state["chk_exp"] = pd.to_datetime("2025-02-28")
        if "chk_pres" not in st.session_state:
            st.session_state["chk_pres"] = pd.to_datetime("2025-01-20")
        if "chk_inv" not in st.session_state:
            st.session_state["chk_inv"] = 100_000.0
        if "chk_dirty" not in st.session_state:
            st.session_state["chk_dirty"] = False

        def update_inputs():
            ship = pd.to_datetime("2025-01-15")
            exp = pd.to_datetime("2025-02-28")
            pres = pd.to_datetime("2025-01-20")
            amt = 100_000.0
            is_dirty = False

            if st.session_state["s_late_ship"]:
                ship = pd.to_datetime("2025-03-01")

            if st.session_state["s_late_pres"]:
                pres = ship + pd.Timedelta(days=24)
            else:
                pres = ship + pd.Timedelta(days=5)

            if st.session_state["s_over_amt"]:
                amt = 110_000.0

            if st.session_state["s_dirty_bl"]:
                is_dirty = True

            st.session_state["chk_ship"] = ship
            st.session_state["chk_exp"] = exp
            st.session_state["chk_pres"] = pres
            st.session_state["chk_inv"] = amt
            st.session_state["chk_dirty"] = is_dirty

        def reset_scenarios():
            for f in flags:
                st.session_state[f] = False
            update_inputs()

        def toggle_scenario(key):
            st.session_state[key] = not st.session_state[key]
            update_inputs()

        with st.expander("🎯 GỢI Ý KỊCH BẢN (Cho phép chọn nhiều lỗi cùng lúc)", expanded=True):
            st.write("Bấm để **Bật/Tắt** tình huống lỗi. (Nút đỏ = đang chọn)")

            # st.markdown('<div class="scenario-toggle">', unsafe_allow_html=True)

            sc1, sc2, sc3, sc4, sc5 = st.columns(5)

            with sc1:
                btn_type = "primary" if st.session_state["s_late_ship"] else "secondary"
                if st.button("🚢 Giao trễ", key="btn_late", type=btn_type, use_container_width=True):
                    toggle_scenario("s_late_ship")
                    st.rerun()

            with sc2:
                btn_type = "primary" if st.session_state["s_late_pres"] else "secondary"
                if st.button("🕒 Trình muộn", key="btn_pres", type=btn_type, use_container_width=True):
                    toggle_scenario("s_late_pres")
                    st.rerun()

            with sc3:
                btn_type = "primary" if st.session_state["s_over_amt"] else "secondary"
                if st.button("💸 Vượt tiền", key="btn_amt", type=btn_type, use_container_width=True):
                    toggle_scenario("s_over_amt")
                    st.rerun()

            with sc4:
                btn_type = "primary" if st.session_state["s_dirty_bl"] else "secondary"
                if st.button("📝 B/L bẩn", key="btn_dirty", type=btn_type, use_container_width=True):
                    toggle_scenario("s_dirty_bl")
                    st.rerun()

            with sc5:
                if st.button("🔄 Reset", key="btn_reset", type="secondary", use_container_width=True):
                    reset_scenarios()
                    st.rerun()

            # st.markdown("</div>", unsafe_allow_html=True)  # ✅ ĐÓNG DIV ĐÚNG: nằm trong expander


        st.markdown("---")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 📅 Yếu tố Thời gian")
            lc_issue_date = st.date_input("Ngày phát hành L/C:", value=pd.to_datetime("2025-01-01"), key="r3_lc_issue")
            ship_date = st.date_input("Ngày giao hàng (On Board Date):", key="chk_ship")
            lc_exp_date = st.date_input("Ngày hết hạn L/C (Expiry Date):", key="chk_exp")
            pres_date = st.date_input("Ngày xuất trình (Presentation Date):", key="chk_pres")

        with c2:
            st.markdown("#### 💰 Yếu tố Tài chính & Hàng hóa")
            lc_amount = st.number_input("Giá trị L/C (USD):", value=100_000.0, step=1_000.0, key="r3_lc_amt")
            tolerance = st.number_input("Dung sai cho phép (+/- %):", value=5.0, step=1.0, key="r3_tol")
            inv_amount = st.number_input("Giá trị Hóa đơn (Invoice):", step=1_000.0, key="chk_inv")

            st.markdown("#### 📝 Tình trạng Vận đơn (B/L)")
            is_dirty_bl = st.checkbox("Trên B/L có ghi chú xấu? (VD: 'Bao bì rách')", key="chk_dirty")

        st.markdown("---")

        if st.button("🔍 SOÁT XÉT CHỨNG TỪ (CHECKING)", type="secondary", use_container_width=True, key="btn_check_docs"):
            errors = []

            # Time checks
            if ship_date > lc_exp_date:
                errors.append(("Late Shipment", "Ngày giao hàng diễn ra SAU ngày hết hạn L/C.", "Điều 14c"))

            if pres_date > lc_exp_date:
                errors.append(("L/C Expired", "Ngày xuất trình diễn ra SAU ngày hết hạn L/C.", "Điều 6d"))

            presentation_period = (pres_date - ship_date).days
            if presentation_period > 21:
                errors.append(("Stale Documents", f"Xuất trình muộn {presentation_period} ngày (tối đa 21 ngày).", "Điều 14c"))

            if presentation_period < 0:
                errors.append(("Impossible Date", "Ngày xuất trình TRƯỚC ngày giao hàng (phi logic).", "Logic"))

            # Amount checks
            max_allowed = lc_amount * (1 + tolerance / 100)
            if inv_amount > max_allowed:
                errors.append(("Overdrawn Credit", f"Hóa đơn ({inv_amount:,.0f}) vượt dung sai ({max_allowed:,.0f}).", "Điều 30b"))

            # B/L checks
            if is_dirty_bl:
                errors.append(("Unclean B/L", "Vận đơn không hoàn hảo (Dirty/Claused B/L) – có thể bị từ chối.", "Điều 27"))

            if not errors:
                st.success("✅ CLEAN DOCUMENTS (BỘ CHỨNG TỪ HỢP LỆ)")
                st.balloons()
                st.info("💡 Kết luận: Ngân hàng phát hành **bắt buộc thanh toán** (Honour).")
            else:
                st.error(f"❌ DISCREPANT DOCUMENTS (PHÁT HIỆN {len(errors)} LỖI)")
                for idx, (err_name, err_desc, ucp_art) in enumerate(errors, 1):
                    st.markdown(
                        f"""
<div style="background-color:#ffeded;color:#333;padding:12px;border-radius:10px;margin-bottom:10px;border-left:6px solid #ff4b4b;">
  <strong>{idx}. Lỗi: {err_name}</strong><br>
  Giải thích: <em>{err_desc}</em><br>
  ⚖️ Căn cứ: <strong>UCP 600 - {ucp_art}</strong>
</div>
                        """,
                        unsafe_allow_html=True,
                    )
                st.warning("👉 Hậu quả: Ngân hàng có quyền **từ chối thanh toán** và thu phí discrepancy (thường 50–100 USD/lỗi).")

        st.markdown("---")
        if st.button("AI Advisor – Trade Checking", type="primary", icon="🤖", key="btn_ai_ucp"):
            curr_errs = []
            if ship_date > lc_exp_date:
                curr_errs.append("Late Shipment")
            if pres_date > lc_exp_date:
                curr_errs.append("L/C Expired")
            if (pres_date - ship_date).days > 21:
                curr_errs.append("Stale Documents")
            if inv_amount > (lc_amount * (1 + tolerance / 100)):
                curr_errs.append("Overdrawn Credit")
            if is_dirty_bl:
                curr_errs.append("Unclean B/L")

            user_id = st.session_state.get('CURRENT_USER') 

            if not user_id:
                st.error("🔒 Bạn chưa đăng nhập đúng MSSV ở thanh bên trái!")
                st.toast("Vui lòng nhập MSSV để tiếp tục!", icon="🔒")
                st.stop() # Dừng lại ngay, không chạy tiếp

                # BƯỚC 2: KIỂM TRA HẠN MỨC (QUOTA)
            current_used = get_usage_from_supabase(user_id)
                
            if current_used >= MAX_AI_QUOTA:
                st.warning(f"⚠️ Sinh viên {user_id} đã hết lượt dùng AI ({MAX_AI_QUOTA}/{MAX_AI_QUOTA}).")
                st.stop()

            context = f"""
Dữ liệu:
- Ship: {ship_date}
- Exp: {lc_exp_date}
- Pres: {pres_date}
- L/C Amount: {lc_amount:,.0f}
- Tolerance: {tolerance}%
- Invoice: {inv_amount:,.0f}
- Dirty B/L: {is_dirty_bl}

Lỗi phát hiện: {", ".join(curr_errs) if curr_errs else "Không có"}
"""
            task = "Giải thích ngắn gọn các lỗi (nếu có) và 1–2 cách khắc phục thực tế cho doanh nghiệp."
            with st.spinner(f"AI đang tư vấn ... (Lượt gọi AI thứ {current_used + 1}/{MAX_AI_QUOTA})"):
                try:
                    advise = ask_gemini_advisor("Chuyên gia UCP 600", context, task)
                    if advise.startswith("⚠️"):
                        st.error(advise) # Hiện lỗi cho GV/SV biết
                        st.info("Lượt này chưa bị trừ do lỗi hệ thống.")
                    else:
                        # 1. Trừ quota trong Database/File
                        consume_quota(user_id)
                        
                        # 2. CẬP NHẬT SIDEBAR NGAY LẬP TỨC (Không cần Rerun)
                        # Lấy số mới để hiển thị
                        new_usage = current_used + 1
                        
                        # Bắn nội dung mới vào cái hộp "quota_placeholder" đang nằm bên Sidebar
                        # Lưu ý: Bạn cần đảm bảo biến 'quota_placeholder' truy cập được từ đây
                        quota_placeholder.info(f"Đã dùng: {new_usage}/{MAX_AI_QUOTA} lượt")
                        
                        # 3. Hiện kết quả AI ra màn hình chính
                        st.markdown(f'<div class="ai-box"><h4>🤖 LUẬT SƯ AI TƯ VẤN UCP 600</h4>{advise}</div>', unsafe_allow_html=True)
                        
                except Exception as e:
                    st.error(f"⚠️ Lỗi khi gọi AI: {str(e)}")

        footer()


# ==============================================================================
# PHÒNG 4: INVESTMENT
# ==============================================================================
def room_4_invest():
    # Import numpy_financial (optional)
    try:
        import numpy_financial as npf
    except ImportError:
        st.error("⚠️ Thiếu 'numpy_financial'. Cài bằng: `pip install numpy-financial` để tính IRR chuẩn.")
        npf = None

    st.markdown('<p class="header-style">🏭 Phòng Đầu tư Quốc tế (Investment Dept)</p>', unsafe_allow_html=True)
    st.markdown(
        """
<div class="role-card">
  <div class="role-title">👤 Vai diễn: Chuyên viên Phân tích Đầu tư (Investment Analyst)</div>
  <div class="mission-text">"Nhiệm vụ: Thẩm định dự án FDI, tính IRR/NPV và đánh giá rủi ro tỷ giá."</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("📝 THÔNG SỐ DỰ ÁN ĐẦU TƯ", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 1) Dòng tiền Dự án (USD)")
            inv = st.number_input("Vốn đầu tư ban đầu (CapEx):", value=1_000_000.0, step=10_000.0, format="%.0f", key="r4_inv")
            cf_yearly = st.number_input("Dòng tiền ròng hằng năm (Operating CF):", value=300_000.0, step=5_000.0, format="%.0f", key="r4_cf")
            salvage_val = st.number_input("Giá trị thanh lý cuối kỳ (Terminal Value):", value=200_000.0, key="r4_salvage")
            years = st.slider("Vòng đời dự án (năm):", 3, 10, 5, key="r4_years")
        with c2:
            st.markdown("##### 2) Thị trường & Vĩ mô")
            fx_spot = st.number_input("Tỷ giá Spot hiện tại (VND/USD):", value=25_000.0, step=10.0, key="r4_fx")
            depre = st.number_input("Mức độ mất giá VND (%/năm):", value=3.0, step=0.1, key="r4_depre")
            wacc = st.number_input("Chi phí vốn (WACC %):", value=12.0, step=0.5, key="r4_wacc")

    st.markdown("---")

    if "run_dcf" not in st.session_state:
        st.session_state.run_dcf = False

    if st.button("📊 CHẠY MÔ HÌNH DCF & PHÂN TÍCH ĐỘ NHẠY", key="btn_run_dcf", use_container_width=True):
        st.session_state.run_dcf = True

    if st.session_state.run_dcf:
        data_cf = []
        cf_stream_vnd_nominal = []
        cumulative_pv = 0.0
        payback_period = None

        # Year 0
        cf0_vnd = -inv * fx_spot
        cumulative_pv += cf0_vnd
        cf_stream_vnd_nominal.append(cf0_vnd)

        data_cf.append(
            {
                "Năm": 0,
                "Tỷ giá (VND/USD)": fx_spot,
                "CF (USD)": -inv,
                "CF Quy đổi (VND)": cf0_vnd,
                "PV (Hiện giá VND)": cf0_vnd,
                "Lũy kế PV": cumulative_pv,
            }
        )

        for i in range(1, years + 1):
            fx_future = fx_spot * ((1 + depre / 100) ** i)
            cf_usd = cf_yearly + (salvage_val if i == years else 0)
            cf_vnd = cf_usd * fx_future
            cf_stream_vnd_nominal.append(cf_vnd)

            pv_vnd = cf_vnd / ((1 + wacc / 100) ** i)

            prev_cumulative = cumulative_pv
            cumulative_pv += pv_vnd

            if payback_period is None and cumulative_pv >= 0:
                # fraction of year to recover
                fraction = abs(prev_cumulative) / pv_vnd if pv_vnd != 0 else 0
                payback_period = (i - 1) + fraction

            data_cf.append(
                {
                    "Năm": i,
                    "Tỷ giá (VND/USD)": fx_future,
                    "CF (USD)": cf_usd,
                    "CF Quy đổi (VND)": cf_vnd,
                    "PV (Hiện giá VND)": pv_vnd,
                    "Lũy kế PV": cumulative_pv,
                }
            )

        npv = cumulative_pv

        # IRR
        irr_value = 0.0
        if npf is not None:
            try:
                irr_value = float(npf.irr(cf_stream_vnd_nominal)) * 100
                if np.isnan(irr_value) or np.isinf(irr_value):
                    irr_value = 0.0
            except Exception:
                irr_value = 0.0

        st.subheader("1. Kết quả Thẩm định")
        m1, m2, m3 = st.columns(3)
        m1.metric("NPV (Giá trị hiện tại ròng)", f"{npv:,.0f} VND", delta="Đáng đầu tư" if npv > 0 else "Lỗ vốn")
        if payback_period is not None:
            m2.metric("Thời gian hoàn vốn (DPP)", f"{payback_period:.2f} năm")
        else:
            m2.metric("Thời gian hoàn vốn (DPP)", "Chưa hoàn vốn", delta_color="inverse")
        m3.metric("IRR (Hoàn vốn nội bộ)", f"{irr_value:.2f}%", delta=f"WACC: {wacc}%", delta_color="normal")

        is_feasible = (npv > 0) and (irr_value > wacc)
        if is_feasible:
            st.success(f"✅ KẾT LUẬN: NÊN ĐẦU TƯ. NPV dương ({npv:,.0f} VND) và IRR ({irr_value:.2f}%) > WACC.")
        else:
            reason = []
            if npv <= 0:
                reason.append("NPV âm")
            if irr_value <= wacc:
                reason.append(f"IRR ({irr_value:.2f}%) ≤ WACC")
            st.error(f"⛔ KẾT LUẬN: KHÔNG NÊN ĐẦU TƯ. Lý do: {', '.join(reason)}.")

        df_chart = pd.DataFrame(data_cf)
        st.bar_chart(df_chart.set_index("Năm")[["PV (Hiện giá VND)"]], color="#4B4BFF")

        with st.expander("🔎 Xem bảng dòng tiền chi tiết (Cashflow Table)"):
            # 1. Tạo DataFrame từ list data_cf
            df_display = pd.DataFrame(data_cf)
            
            # 2. QUAN TRỌNG: Thiết lập cột "Năm" làm Index (Trục cố định)
            # Việc này giúp loại bỏ cột số thứ tự 0,1,2 thừa thãi
            # Và giúp cột "Năm" luôn đứng yên bên trái khi bạn kéo thanh cuộn ngang
            df_display.set_index("Năm", inplace=True)
            
            # 3. Hiển thị bảng
            st.dataframe(
                df_display.style.format("{:,.0f}"), # Format số phân cách hàng nghìn
                use_container_width=True,           # Tràn viền màn hình                
            )

        with st.expander("🎓 GÓC HỌC TẬP: GIẢI MÃ CÔNG THỨC & SỐ LIỆU", expanded=False):
            st.markdown("#### 1) NPV điều chỉnh theo tỷ giá")
            st.markdown("Dòng tiền USD được **quy đổi sang VND theo tỷ giá kỳ vọng** từng năm trước khi chiết khấu.")
            st.latex(
                r"NPV = -I_0 \times S_0 + \sum_{t=1}^{n} \frac{(CF_{t,USD} + TV_n)\times S_t}{(1+\text{WACC})^t}"
            )
            st.markdown(
                f"""
                Trong đó:
                - $I_0$ = Vốn đầu tư ban đầu ({inv:,.0f} USD).
                - $CF_{{t,USD}}$ = Dòng tiền hoạt động ({cf_yearly:,.0f} USD).
                - $TV_n$ = Giá trị thanh lý tài sản chỉ ở năm cuối ({salvage_val:,.0f} USD)
                - $S_t$ = Tỷ giá dự báo năm t, tính bằng $S_0(1+{depre}\\%)^t$
                - WACC = Chi phí vốn bình quân ({wacc}\\%)
                """
            )

            st.divider()

            st.markdown("#### 2) Thời gian hoàn vốn chiết khấu (DPP)")
            st.latex(r"DPP = Y_{negative} + \frac{|PV_{Cumulative}|}{PV_{NextYear}}")
            if payback_period:
                y_neg_idx = int(payback_period)
                try:
                    val_missing = abs(data_cf[y_neg_idx]["Lũy kế PV"])
                    val_next = data_cf[y_neg_idx + 1]["PV (Hiện giá VND)"]
                    
                    st.markdown("👇 **Áp dụng số liệu dự án:**")
                    st.latex(f"DPP = {y_neg_idx} + \\frac{{|{val_missing:,.0f}|}}{{{val_next:,.0f}}} = \\mathbf{{{payback_period:.2f} \\text{{ Năm}}}}")
                    
                    st.info(f"""
                    💡 **Diễn giải:** * Sau **{y_neg_idx} năm**, dự án vẫn còn lỗ lũy kế **{val_missing:,.0f} VND**. 
                    * Sang năm thứ **{y_neg_idx + 1}**, dự án kiếm được **{val_next:,.0f} VND**, đủ để bù phần lỗ đó.
                    """)
                except Exception:
                    st.warning("Đã hoàn vốn nhưng không hiển thị được chi tiết phép tính.")
            else:
                st.info("Dự án chưa hoàn vốn nên không thể áp dụng công thức chi tiết.")

            st.divider()

            st.markdown("#### 3) Suất sinh lời nội bộ (IRR)")
            st.markdown("IRR là mức lãi suất làm cho **NPV = 0**.")
            st.latex(r"\sum_{t=0}^{n}\frac{CF_{t,VND}}{(1+IRR)^t}=0")
            st.markdown(f"Trong bài này: IRR = **{irr_value:.2f}%** so với WACC = **{wacc}%**.")

        st.subheader("2. Phân tích Độ nhạy (Sensitivity Analysis)")
        st.markdown("Kiểm tra NPV khi **WACC** và **mức mất giá VND** thay đổi. Trong thực tế, Tỷ giá và WACC là hai biến số khó dự đoán nhất. Ma trận bên dưới (Sensitivity Matrix) giúp trả lời câu hỏi: Nếu Tỷ giá biến động xấu hơn dự kiến (ví dụ mất giá 5% thay vì 3%), dự án có còn lãi không?")


        wacc_range = [wacc - 2, wacc - 1, wacc, wacc + 1, wacc + 2]
        depre_range = [depre - 2, depre - 1, depre, depre + 1, depre + 2]

        sensitivity_data = []
        for w in wacc_range:
            row = []
            for d in depre_range:
                sim_npv = -inv * fx_spot
                for t in range(1, years + 1):
                    sim_fx = fx_spot * ((1 + d / 100) ** t)
                    sim_cf_usd = cf_yearly + (salvage_val if t == years else 0)
                    sim_npv += (sim_cf_usd * sim_fx) / ((1 + w / 100) ** t)
                row.append(sim_npv)
            sensitivity_data.append(row)

        df_sens = pd.DataFrame(
            sensitivity_data,
            index=[f"WACC {w:.1f}%" for w in wacc_range],
            columns=[f"Mất giá {d:.1f}%" for d in depre_range],
        )

        def color_negative_red(val):
            color = "#ffcccc" if val < 0 else "#ccffcc"
            return f"background-color: {color}; color: black"

        st.dataframe(df_sens.style.applymap(color_negative_red).format("{:,.0f}"))

        st.markdown("---")
        if st.button("AI Advisor – FDI Analysis", type="primary", icon="🤖", key="btn_ai_invest"):
            user_id = st.session_state.get('CURRENT_USER') 

            if not user_id:
                st.error("🔒 Bạn chưa đăng nhập đúng MSSV ở thanh bên trái!")
                st.toast("Vui lòng nhập MSSV để tiếp tục!", icon="🔒")
                st.stop() # Dừng lại ngay, không chạy tiếp

                # BƯỚC 2: KIỂM TRA HẠN MỨC (QUOTA)
            current_used = get_usage_from_supabase(user_id)
                
            if current_used >= MAX_AI_QUOTA:
                st.warning(f"⚠️ Sinh viên {user_id} đã hết lượt dùng AI ({MAX_AI_QUOTA}/{MAX_AI_QUOTA}).")
                st.stop()
            context = f"""
Dự án FDI:
- Vốn: {inv:,.0f} USD; CF/năm: {cf_yearly:,.0f} USD; Thanh lý: {salvage_val:,.0f} USD
- Số năm: {years}
- FX Spot: {fx_spot:,.0f}; Mất giá VND: {depre}%
- WACC: {wacc}%
- NPV: {npv:,.0f} VND; IRR: {irr_value:.2f}%; DPP: {payback_period}
"""
            task = """
1) Nhận xét tính khả thi (NPV, IRR so với WACC).
2) Nêu 2 rủi ro tỷ giá/khả năng chuyển lợi nhuận về nước.
3) Khuyến nghị: Duyệt hay Từ chối (1 câu chốt).
"""
            with st.spinner(f"Chuyên viên đang phân tích...(Lượt gọi AI thứ {current_used + 1}/{MAX_AI_QUOTA})"):
                try:
                    advise = ask_gemini_advisor("Investment Specialist", context, task)
                    # advise = ask_gemini_advisor("CFO Advisor", context, task)
                    if advise.startswith("⚠️"):
                        st.error(advise) # Hiện lỗi cho GV/SV biết
                        st.info("Lượt này chưa bị trừ do lỗi hệ thống.")
                    else:
                        # 1. Trừ quota trong Database/File
                        consume_quota(user_id)
                        
                        # 2. CẬP NHẬT SIDEBAR NGAY LẬP TỨC (Không cần Rerun)
                        # Lấy số mới để hiển thị
                        new_usage = current_used + 1
                        
                        # Bắn nội dung mới vào cái hộp "quota_placeholder" đang nằm bên Sidebar
                        # Lưu ý: Bạn cần đảm bảo biến 'quota_placeholder' truy cập được từ đây
                        quota_placeholder.info(f"Đã dùng: {new_usage}/{MAX_AI_QUOTA} lượt")
                        
                        # 3. Hiện kết quả AI ra màn hình chính
                        st.markdown(f'<div class="ai-box"><h4>🤖 CHUYÊN VIÊN AI NHẬN ĐỊNH</h4>{advise}</div>', unsafe_allow_html=True)
                        
                except Exception as e:
                    st.error(f"⚠️ Lỗi khi gọi AI: {str(e)}")        

    footer()


# ==============================================================================
# PHÒNG 5: MACRO STRATEGY
# ==============================================================================
def room_5_macro():
    st.markdown('<p class="header-style">📉 Ban Chiến lược Vĩ mô (Macro Strategy)</p>', unsafe_allow_html=True)
    st.markdown(
        """
<div class="role-card">
  <div class="role-title">👤 Vai diễn: Chuyên gia Chiến lược Vĩ mô (Macro Strategist)</div>
  <div class="mission-text">"Nhiệm vụ: Phân tích 'tác động kép' của tỷ giá: (1) Nợ công và (2) rủi ro dòng tiền nóng (Carry Trade Unwind)."</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    tab_debt, tab_carry = st.tabs(["📉 Khủng hoảng Nợ công", "💸 Chiến lược Carry Trade"])

    # TAB 1
    with tab_debt:
        st.subheader("1. Mô phỏng Cú sốc Tỷ giá lên Nợ công")
        col_macro1, col_macro2 = st.columns(2)
        with col_macro1:
            debt_val = st.number_input("Tổng nợ nước ngoài (Tỷ USD):", value=50.0, step=1.0, key="r5_debt_val")
            base_rate = st.number_input("Tỷ giá hiện tại (VND/USD):", value=25_000.0, step=100.0, key="r5_base_rate")
        with col_macro2:
            st.markdown("#### Kịch bản Tỷ giá")
            shock_pct = st.slider(
                "Đồng nội tệ mất giá bao nhiêu %?",
                min_value=0.0,
                max_value=100.0,
                value=20.0,
                step=1.0,
                key="r5_shock",
            )

        new_rate = base_rate * (1 + shock_pct / 100)
        base_debt_vnd = debt_val * base_rate
        new_debt_vnd = debt_val * new_rate
        loss_vnd = new_debt_vnd - base_debt_vnd

        st.markdown("---")
        m1, m2, m3 = st.columns(3)
        m1.metric("Tỷ giá sau cú sốc", f"{new_rate:,.0f} VND", f"-{shock_pct}% (Mất giá)", delta_color="inverse")
        m2.metric("Nợ quy đổi ban đầu", f"{base_debt_vnd:,.0f} Tỷ VND")
        m3.metric("Gánh nặng TĂNG THÊM", f"{loss_vnd:,.0f} Tỷ VND", delta="RỦI RO VỠ NỢ", delta_color="inverse")

        # Cảnh báo động
        if shock_pct > 30:
            st.error(f"🚨 **BÁO ĐỘNG ĐỎ:** Mức mất giá {shock_pct}% tương đương kịch bản Khủng hoảng Châu Á 1997. Nguy cơ vỡ nợ quốc gia (Sovereign Default) là rất cao.")
        elif shock_pct > 10:
            st.warning(f"⚠️ **Cảnh báo:** Gánh nặng nợ tăng thêm {loss_vnd/1000:,.1f} nghìn tỷ VND sẽ gây áp lực cực lớn lên ngân sách.")


        with st.expander("🧮 GÓC HỌC TẬP: GIẢI MÃ SỐ LIỆU NỢ CÔNG", expanded=False):
            st.markdown("#### 1) Vì sao nợ tăng dù không vay thêm?")
            st.write("Nợ USD không đổi, nhưng **VND cần để mua USD trả nợ tăng** khi tỷ giá tăng.")

            st.markdown("#### 2) Công thức & thay số")
            st.markdown(
                f"""
- Nợ ban đầu: $$ {debt_val} \\times {base_rate:,.0f} = \\mathbf{{{base_debt_vnd:,.0f}}} $$
- Nợ sau cú sốc: $$ {debt_val} \\times {new_rate:,.0f} = \\mathbf{{{new_debt_vnd:,.0f}}} $$
- Tăng thêm: $$ {new_debt_vnd:,.0f} - {base_debt_vnd:,.0f} = \\mathbf{{{loss_vnd:,.0f}}} $$
"""
            )

        # --- PHẦN MINH HỌA LỊCH SỬ ---
        with st.expander("📚 BÀI HỌC LỊCH SỬ: KHỦNG HOẢNG TÀI CHÍNH 1997"):
            c_hist1, c_hist2 = st.columns([1, 2])
            with c_hist1:
                st.write("### 📉")
                st.caption("**Đồng Baht Thái sụp đổ**")
                # Kích hoạt tìm kiếm hình ảnh biểu đồ khủng hoảng
                st.markdown("")
            
            with c_hist2:
                st.write("""
                **Nguyên nhân sụp đổ:**
                Vào năm 1997, Thái Lan vay nợ nước ngoài rất lớn (giống ví dụ trên). Khi đồng Baht mất giá 50%, gánh nặng nợ quy đổi tăng gấp đôi, khiến các công ty không thể trả nợ và phá sản hàng loạt.
                """)

        macro_context = f"""
        Quốc gia nợ {debt_val} tỷ USD. Tỷ giá mất giá {shock_pct}%.
        Gánh nặng nợ tăng thêm {loss_vnd:,.0f} tỷ VND.
        So sánh với kịch bản khủng hoảng 1997.
        """

    # TAB 2
    with tab_carry:
        st.subheader("2. Đầu cơ Chênh lệch lãi suất (Carry Trade)")
        st.caption("Vay đồng tiền lãi thấp ➜ mua đồng tiền lãi cao. Lợi nhuận = lãi suất chênh + biến động tỷ giá.")

        c1, c2 = st.columns(2)
        with c1:
            capital = st.number_input("Vốn đầu tư (Triệu USD):", value=10.0, step=1.0, key="r5_capital")
            rate_borrow = st.number_input("Lãi vay (Funding Rate %):", value=0.5, step=0.1, key="r5_borrow")
        with c2:
            rate_invest = st.number_input("Lãi đầu tư (Target Rate %):", value=5.5, step=0.1, key="r5_invest")
            fx_move = st.slider("Biến động tỷ giá (%):", -10.0, 10.0, -2.0, 0.5, key="r5_fx_move")

        st.markdown("---")
        interest_diff = rate_invest - rate_borrow
        profit_interest = capital * (interest_diff / 100)
        profit_fx = capital * (fx_move / 100)
        total_pnl = profit_interest + profit_fx
        roi = (total_pnl / capital) * 100 if capital != 0 else 0

        c_res1, c_res2, c_res3 = st.columns(3)
        c_res1.metric("1) Lãi từ lãi suất (Spread)", f"${profit_interest:,.2f} M", f"Chênh lệch: {interest_diff:.1f}%")
        c_res2.metric("2) Lãi/Lỗ từ tỷ giá (FX)", f"${profit_fx:,.2f} M", f"Biến động: {fx_move}%")
        c_res3.metric("3) TỔNG LỢI NHUẬN", f"${total_pnl:,.2f} M", f"ROI: {roi:.1f}%")

        with st.expander("🧮 GÓC HỌC TẬP: GIẢI MÃ CÁCH TÍNH CARRY TRADE", expanded=False):
            st.markdown("Tổng lợi nhuận đến từ 2 nguồn:")

            st.markdown("#### A) Lợi nhuận từ lãi suất")
            st.latex(r"\text{Profit}_{Rate} = \text{Vốn} \times (r_{Invest} - r_{Borrow})")
            st.markdown(f"Áp dụng: {capital} × ({rate_invest}% - {rate_borrow}%) = **{profit_interest:,.2f} triệu USD**")

            st.divider()

            st.markdown("#### B) Lợi nhuận từ tỷ giá")
            st.latex(r"\text{Profit}_{FX} = \text{Vốn} \times \% \Delta FX")
            st.markdown(f"Áp dụng: {capital} × {fx_move}% = **{profit_fx:,.2f} triệu USD**")

            st.info(
                """
Carry Trade giống như “nhặt tiền lẻ (lãi suất) trước đầu xe lu (tỷ giá)”.
Bạn có thể lời đều từ chênh lãi suất, nhưng một cú đảo chiều tỷ giá có thể xóa sạch thành quả.
"""
            )

    st.markdown("---")
    if st.button("AI Advisor – Macro Strategist", type="primary", icon="🤖", key="btn_ai_macro"):
        user_id = st.session_state.get('CURRENT_USER') 

        if not user_id:
            st.error("🔒 Bạn chưa đăng nhập đúng MSSV ở thanh bên trái!")
            st.toast("Vui lòng nhập MSSV để tiếp tục!", icon="🔒")
            st.stop() # Dừng lại ngay, không chạy tiếp

                # BƯỚC 2: KIỂM TRA HẠN MỨC (QUOTA)
        current_used = get_usage_from_supabase(user_id)
                
        if current_used >= MAX_AI_QUOTA:
            st.warning(f"⚠️ Sinh viên {user_id} đã hết lượt dùng AI ({MAX_AI_QUOTA}/{MAX_AI_QUOTA}).")
            st.stop() 

        full_context = f"""
TÌNH HUỐNG MÔ PHỎNG:
1) Nợ công: nợ {debt_val} tỷ USD, mất giá {shock_pct}%, nợ tăng thêm {loss_vnd:,.0f} tỷ VND.
2) Carry Trade: vốn {capital} triệu USD, chênh lãi {interest_diff:.2f}%, FX {fx_move}% ⇒ ROI {roi:.1f}%.
"""
        task = f"""
Làm báo cáo nhanh:
1) Giải thích rủi ro “unwind carry trade” và vì sao FX đảo chiều có thể gây chao đảo thị trường.
2) Đánh giá rủi ro nợ công trong kịch bản mất giá {shock_pct}% (nêu 1-2 dấu hiệu cảnh báo).
3) Lời khuyên hành động: thiên về Risk-On hay Risk-Off? (1 câu chốt).
"""
        with st.spinner(f"Đang tổng hợp tín hiệu vĩ mô... (Lượt gọi AI thứ {current_used + 1}/{MAX_AI_QUOTA})"):
            try:
                advise = ask_gemini_advisor("Macro Strategist", full_context, task)
                if advise.startswith("⚠️"):
                    st.error(advise) # Hiện lỗi cho GV/SV biết
                    st.info("Lượt này chưa bị trừ do lỗi hệ thống.")
                else:
                        # 1. Trừ quota trong Database/File
                        consume_quota(user_id)
                        
                        # 2. CẬP NHẬT SIDEBAR NGAY LẬP TỨC (Không cần Rerun)
                        # Lấy số mới để hiển thị
                        new_usage = current_used + 1
                        
                        # Bắn nội dung mới vào cái hộp "quota_placeholder" đang nằm bên Sidebar
                        # Lưu ý: Bạn cần đảm bảo biến 'quota_placeholder' truy cập được từ đây
                        quota_placeholder.info(f"Đã dùng: {new_usage}/{MAX_AI_QUOTA} lượt")
                        
                        # 3. Hiện kết quả AI ra màn hình chính
                        st.markdown(f'<div class="ai-box"><h4>🤖 CHUYÊN GIA AI BÁO CÁO CHIẾN LƯỢC</h4>{advise}</div>', unsafe_allow_html=True)
                    
            except Exception as e:
                st.error(f"⚠️ Lỗi khi gọi AI: {str(e)}")
            
    footer()

# =========================
# LEADERBOARD HELPERS
# =========================
@st.cache_resource
def load_student_lookup():
    """
    Đọc dssv.xlsx và tạo dict: MSSV -> Họ tên
    - Nếu file hiện chỉ có 1 cột MSSV thì name sẽ rỗng
    - Khi bạn upload file mới có cột họ tên, hàm tự nhận
    """
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, "dssv.xlsx")
        df = pd.read_excel(file_path, dtype=str)

        # Chuẩn hóa tên cột linh hoạt
        cols = {c.strip().lower(): c for c in df.columns}
        mssv_col = cols.get("mssv") or cols.get("ma sv") or cols.get("student_id") or cols.get("student id")
        hoten_col = cols.get("hoten") or cols.get("họ tên") or cols.get("ho ten") or cols.get("fullname") or cols.get("full name")

        if not mssv_col:
            return {}

        df[mssv_col] = df[mssv_col].astype(str).str.strip().str.upper()
        if hoten_col:
            df[hoten_col] = df[hoten_col].astype(str).str.strip()
            return dict(zip(df[mssv_col], df[hoten_col]))
        else:
            return {m: "" for m in df[mssv_col].tolist()}

    except Exception:
        return {}

def get_student_name(mssv: str) -> str:
    mp = load_student_lookup()
    name = mp.get(str(mssv).strip().upper(), "")
    return name.strip()

def fetch_my_attempts(mssv: str, limit: int = 2000):
    if not supabase_client:
        return []
    try:
        res = (
            supabase_client.table("lab_attempts")
            .select("mssv,hoten,lop,room,exercise_code,attempt_no,score,is_correct,duration_sec,created_at")
            .eq("mssv", mssv)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception as e:
        st.error(f"⚠️ Lỗi đọc lab_attempts: {e}")
        return []

def fetch_class_leaderboard_from_view(limit: int = 200):
    if not supabase_client:
        return None
    try:
        res = (
            supabase_client.table("lab_leaderboard")
            .select("mssv,hoten,lop,total_score,num_solved_exercises,num_exercises_attempted")
            .order("total_score", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception as e:
        st.warning(f"⚠️ Không đọc được VIEW lab_leaderboard: {e}")
        return None


def compute_class_leaderboard_fallback(limit: int = 200):
    """
    Fallback: Tự tính leaderboard từ lab_attempts:
    - best-of-3 mỗi bài: lấy MAX(score) theo (mssv, exercise_code)
    - Tổng điểm = sum(best_score) theo mssv
    """
    if not supabase_client:
        return []

    try:
        res = (
            supabase_client.table("lab_attempts")
            .select("mssv,hoten,room,exercise_code,attempt_no,score,is_correct,created_at")
            .limit(5000)
            .execute()
        )
        rows = res.data or []
        if not rows:
            return []

        df = pd.DataFrame(rows)
        df["mssv"] = df["mssv"].astype(str).str.strip().str.upper()
        df["exercise_code"] = df["exercise_code"].astype(str).str.strip().str.upper()

        # Ép is_correct về 0/1 an toàn (trường hợp bool hoặc chuỗi)
        def to01(x):
            if isinstance(x, bool):
                return 1 if x else 0
            s = str(x).strip().lower()
            return 1 if s in ("true", "1", "t", "yes", "y") else 0

        df["is_correct_01"] = df["is_correct"].apply(to01)
        df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0).astype(int)


        # best-of-3: attempt_no đã là 1..3
        g = (
            df.groupby(["mssv", "exercise_code"], as_index=False)
            .agg(
                best_score=("score", "max"),
                best_correct=("is_correct_01", "max"),   # ✅ dùng 0/1
                room=("room", "last"),
                hoten=("hoten", "last"),
                last_submit=("created_at", "max"),
            )
        )


        lb = (
            g.groupby("mssv", as_index=False)
             .agg(
                 total_score=("best_score", "sum"),
                 total_correct=("best_correct", "sum"),
                 exercises_done=("exercise_code", "nunique"),
                 hoten=("hoten", "last"),
                 room=("room", "last"),
                 last_submit=("last_submit", "max"),
             )
        )

        lb = lb.sort_values(["total_score", "total_correct", "exercises_done", "last_submit"], ascending=[False, False, False, False])
        lb = lb.head(limit)

        return lb.to_dict(orient="records")

    except Exception as e:
        st.error(f"⚠️ Lỗi tính leaderboard fallback: {e}")
        return []


def render_practice_router():
    st.markdown("### 🧩 Khu vực làm bài (Workspace)")

    mssv = st.session_state.get("LAB_MSSV", "").strip().upper()
    room_key = st.session_state.get("ACTIVE_ROOM", "DEALING")
    ex_code = st.session_state.get("ACTIVE_EX_CODE", "D01")
    attempt_no = int(st.session_state.get("ACTIVE_ATTEMPT", 1))

    ROUTER = {
        ("DEALING", "D01"): render_exercise_D01,
        # ("DEALING", "D02"): render_exercise_D02,
        # ("RISK", "R01"): render_exercise_R01,
        # ...
    }

    fn = ROUTER.get((room_key, ex_code))
    if not fn:
        st.info("👉 Bài này chưa được triển khai. Bạn chọn **D01** để demo.")
        return

    fn(mssv=mssv, ex_code=ex_code, attempt_no=attempt_no)

# BÀI D01: XỬ LÝ GIAO DỊCH NGOẠI HỐI
def render_exercise_D01(mssv: str, ex_code: str, attempt_no: int):
    # Chỉ demo D01
    if ex_code != "D01":
        st.info("👉 Demo hiện tại chỉ kích hoạt cho **D01**.")
        return

    # 1) Nếu attempt đã nộp rồi -> khóa, hiển thị lại
    existing = fetch_attempt(mssv, ex_code, attempt_no)
    if existing:
        st.warning(f"🔒 Bạn đã nộp **{ex_code} – Lần {attempt_no}** rồi. (Mỗi lần làm chỉ nộp 1 lần)")
        params = existing.get("params_json", {}) or {}
        ans = existing.get("answer_json", {}) or {}

        st.write("**Đề bài bạn đã nhận (từ DB):**")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 🇺🇸 USD/VND")
            st.write(f"BID: **{params.get('usd_bid','-'):,.0f}**")
            st.write(f"ASK: **{params.get('usd_ask','-'):,.0f}**")
        with c2:
            st.markdown("##### 🇪🇺 EUR/USD")
            st.write(f"BID: **{float(params.get('eur_bid',0.0)):.4f}**" if params.get("eur_bid") else "BID: **-**")
            st.write(f"ASK: **{float(params.get('eur_ask',0.0)):.4f}**" if params.get("eur_ask") else "ASK: **-**")

        st.markdown("**Đáp án chuẩn (để bạn đối chiếu học tập):**")
        st.success(
            f"EUR/VND = **{ans.get('cross_bid','-'):,.0f} - {ans.get('cross_ask','-'):,.0f}** | Spread = **{ans.get('spread','-'):,.0f}**"
        )
        return  # ✅ thay st.stop()

    # 2) Seed ổn định + clamp để ghi BIGINT an toàn
    seed_raw = stable_seed(mssv, ex_code, attempt_no)
    seed = int(seed_raw) & ((1 << 63) - 1)   # ✅ chống lỗi bigint
    params, answers = gen_case_D01(seed)

    # 3) Ghi nhận thời điểm bắt đầu
    start_key = f"START_{mssv}_{ex_code}_{attempt_no}"
    if start_key not in st.session_state:
        st.session_state[start_key] = time.time()

    # 4) Hiển thị đề
    st.markdown(
        """
<div class="role-card">
  <div class="role-title">📝 Bài D01 — Niêm yết tỷ giá chéo EUR/VND (Bid–Ask–Spread)</div>
  <div class="mission-text">
    Dựa trên báo giá thị trường dưới đây, hãy tính <b>EUR/VND Bid</b>, <b>EUR/VND Ask</b> và <b>Spread</b>.
    (Làm tròn đến <b>đơn vị VND</b>)
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### 🇺🇸 Thị trường 1: USD/VND")
        st.write(f"BID (NH mua USD): **{params['usd_bid']:,.0f}**")
        st.write(f"ASK (NH bán USD): **{params['usd_ask']:,.0f}**")
    with c2:
        st.markdown("##### 🇪🇺 Thị trường 2: EUR/USD")
        st.write(f"BID (NH mua EUR): **{params['eur_bid']:.4f}**")
        st.write(f"ASK (NH bán EUR): **{params['eur_ask']:.4f}**")

    st.markdown("---")
    st.caption("✍️ Nhập kết quả (làm tròn 0 chữ số thập phân – VND/EUR)")

    a1, a2, a3 = st.columns(3)
    with a1:
        in_bid = st.number_input("EUR/VND BID", min_value=0.0, step=1.0, format="%.0f", key=f"d01_in_bid_{attempt_no}")
    with a2:
        in_ask = st.number_input("EUR/VND ASK", min_value=0.0, step=1.0, format="%.0f", key=f"d01_in_ask_{attempt_no}")
    with a3:
        in_spread = st.number_input("SPREAD", min_value=0.0, step=1.0, format="%.0f", key=f"d01_in_spread_{attempt_no}")

    # 5) Nộp bài
    TOL = 2

    if st.button("📩 NỘP BÀI (Submit)", type="primary", use_container_width=True, key=f"btn_submit_d01_{attempt_no}"):
        is_ok = (
            abs(int(in_bid) - answers["cross_bid"]) <= TOL
            and abs(int(in_ask) - answers["cross_ask"]) <= TOL
            and abs(int(in_spread) - answers["spread"]) <= TOL
        )
        score = 10 if is_ok else 0
        duration_sec = int(time.time() - st.session_state[start_key])

        payload = {
            "mssv": mssv,
            "hoten": get_student_name(mssv) or None,
            "lop": None,
            "room": "DEALING",
            "exercise_code": ex_code,
            "attempt_no": attempt_no,
            "seed": int(seed),
            "params_json": params,
            "answer_json": answers,
            "is_correct": bool(is_ok),
            "score": int(score),
            "duration_sec": int(duration_sec),
            "note": f"D01 attempt {attempt_no}",
        }

        ok = insert_attempt(payload)
        if not ok:
            # ✅ không st.stop() để không chặn tab khác
            st.error("Không ghi được bài nộp. Vui lòng thử lại.")
            return

        if is_ok:
            st.success(f"✅ CHÍNH XÁC! Bạn được **+{score} điểm**.")
        else:
            st.error("❌ CHƯA ĐÚNG. Bạn được **0 điểm**.")

        st.info(
            f"📌 Đáp án chuẩn: EUR/VND = **{answers['cross_bid']:,.0f} - {answers['cross_ask']:,.0f}** | Spread = **{answers['spread']:,.0f}**"
        )
        st.rerun()


# ======= PHÒNG 6 BẢNG VÀNG THÀNH TÍCH ========
def room_6_leaderboard():

    st.markdown(
        '<p class="header-style">🏆 PHÒNG BẢNG VÀNG THÀNH TÍCH</p>',
        unsafe_allow_html=True
    )

    st.markdown(
        """
<div class="role-card">
  <div class="role-title">👤 Vai diễn: Sinh viên – Nhà vô địch Lab</div>
  <div class="mission-text">
  "Nhiệm vụ: Hoàn thành các bài tập nghiệp vụ, tích lũy điểm số và cạnh tranh thứ hạng cá nhân & toàn lớp."
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    # ====== LOGIN MSSV + PIN (CHỈ ROOM 6) ======
    if "LAB_MSSV" not in st.session_state:
        st.session_state["LAB_MSSV"] = ""
    if "LAB_AUTH" not in st.session_state:
        st.session_state["LAB_AUTH"] = False

    with st.container():
        st.caption("🔒 Nhập **MSSV + PIN** (theo danh sách lớp) để xem bài tập và bảng xếp hạng.")
        col1, col2 = st.columns([1.2, 1.0])

        with col1:
            lab_input = st.text_input(
                "MSSV",
                value=st.session_state["LAB_MSSV"],
                key="lab_mssv_input",
            )
        with col2:
            lab_pin = st.text_input(
                "PIN",
                value="",
                type="password",
                key="lab_pin_input",
                help="PIN trong file dssv.xlsx",
            )

        colA, colB = st.columns([1, 1])
        with colA:
            if st.button("✅ Đăng nhập", use_container_width=True, key="btn_lab_login"):
                clean_id = str(lab_input).strip().upper()
                clean_pin = str(lab_pin).strip()

                ok, msg = verify_mssv_pin(clean_id, clean_pin)
                if not ok:
                    st.error(msg)
                    st.session_state["LAB_MSSV"] = ""
                    st.session_state["LAB_AUTH"] = False
                    st.stop()

                st.session_state["LAB_MSSV"] = clean_id
                st.session_state["LAB_AUTH"] = True

                hoten = get_student_name(clean_id)
                st.success(f"✅ Xin chào: {hoten} ({clean_id})" if hoten else f"✅ Xin chào: {clean_id}")
                st.rerun()

        with colB:
            if st.button("🚪 Đổi SV / Thoát", use_container_width=True, key="btn_lab_logout"):
                st.session_state["LAB_MSSV"] = ""
                st.session_state["LAB_AUTH"] = False
                st.rerun()

    # Nếu chưa auth thì KHÔNG cho hiện tab
    if not st.session_state.get("LAB_AUTH", False) or not st.session_state.get("LAB_MSSV"):
        st.stop()


    tab_practice, tab_my, tab_class = st.tabs(
        [
            "🎯 Làm bài tập",
            "🥇 Thành tích cá nhân",
            "🏫 Bảng xếp hạng lớp",
        ]
    )

    # =========================================================
    # TAB 1: PRACTICE
    # =========================================================
    with tab_practice:
        st.subheader("🎯 Thực hành & tính điểm")
        st.info(
            """
- Mỗi bài tập có **tham số ngẫu nhiên** (không trùng đề).
- Mỗi bài được làm **tối đa 3 lần**.
"""
        )

        # --- Session defaults ---
        if "ACTIVE_ROOM" not in st.session_state:
            st.session_state["ACTIVE_ROOM"] = "DEALING"
        if "ACTIVE_EX_CODE" not in st.session_state:
            st.session_state["ACTIVE_EX_CODE"] = "D01"
        if "ACTIVE_ATTEMPT" not in st.session_state:
            st.session_state["ACTIVE_ATTEMPT"] = 1

        # --- A) Bộ chọn phòng / mã bài ---
        c1, c2 = st.columns([1.2, 1.8])
        with c1:
            room_key = st.selectbox(
                "Chọn phòng nghiệp vụ",
                options=list(ROOM_LABELS.keys()),
                format_func=lambda k: ROOM_LABELS[k],
                index=list(ROOM_LABELS.keys()).index(st.session_state["ACTIVE_ROOM"]),
                key="sel_room_key",
            )
            st.session_state["ACTIVE_ROOM"] = room_key

        # Tạo list bài theo phòng
        exercises = EXERCISE_CATALOG.get(room_key, [])
        ex_options = [f'{e["code"]} — {e["title"]}' for e in exercises]
        ex_codes = [e["code"] for e in exercises]

        with c2:
            # Nếu mã bài hiện tại không thuộc phòng đang chọn -> reset về bài đầu
            if st.session_state["ACTIVE_EX_CODE"] not in ex_codes and len(ex_codes) > 0:
                st.session_state["ACTIVE_EX_CODE"] = ex_codes[0]

            ex_idx = ex_codes.index(st.session_state["ACTIVE_EX_CODE"]) if st.session_state["ACTIVE_EX_CODE"] in ex_codes else 0
            ex_pick = st.selectbox(
                "Chọn mã bài tập",
                options=ex_options,
                index=ex_idx,
                key="sel_ex_pick",
            )
            # Parse code
            picked_code = ex_pick.split("—")[0].strip() if "—" in ex_pick else ex_pick.split("-")[0].strip()

            st.session_state["ACTIVE_EX_CODE"] = picked_code

        # --- B) Chọn lần làm (Attempt 1/2/3) ---
        st.caption("Chọn **lần làm bài** (tối đa 3 lần). Sau này hệ thống sẽ lấy **điểm cao nhất (best-of-3)** cho mỗi mã bài.")
        a1, a2, a3 = st.columns(3)

        def attempt_btn(label, n, key):
            btn_type = "primary" if st.session_state["ACTIVE_ATTEMPT"] == n else "secondary"
            if st.button(label, type=btn_type, use_container_width=True, key=key):
                st.session_state["ACTIVE_ATTEMPT"] = n
                st.rerun()

        with a1:
            attempt_btn("1️⃣ Lần 1", 1, "btn_attempt_1")
        with a2:
            attempt_btn("2️⃣ Lần 2", 2, "btn_attempt_2")
        with a3:
            attempt_btn("3️⃣ Lần 3", 3, "btn_attempt_3")

        st.markdown("---")

        # --- C) Tóm tắt lựa chọn + vùng “workspace” để lát nữa render đề ---
        mssv = st.session_state.get("LAB_MSSV", "")
        st.info(
            f"👤 SV: **{mssv}**  |  🏢 Phòng: **{st.session_state['ACTIVE_ROOM']}**  |  📌 Bài: **{st.session_state['ACTIVE_EX_CODE']}**  |  🔁 Lần: **{st.session_state['ACTIVE_ATTEMPT']}**"
        )

        render_practice_router()


    # =========================================================
    # TAB 2: MY STATS
    # =========================================================
    with tab_my:
        st.subheader("🥇 Thành tích cá nhân")
        st.info(
            """
- Tổng điểm tích lũy
- Số bài đã làm / đúng
"""
        )

        mssv = st.session_state.get("LAB_MSSV", "").strip().upper()
        hoten = get_student_name(mssv)
        
        if hoten:
            st.success(f"Xin chào **{hoten}** ({mssv})")
        else:
            st.success(f"Xin chào **{mssv}**")

        rows = fetch_my_attempts(mssv)
        if not rows:
            st.info("Chưa có dữ liệu bài nộp. Hãy vào tab **🎯 Làm bài tập** để bắt đầu.")
            st.stop()

        df = pd.DataFrame(rows)
        # chuẩn hóa
        df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0).astype(int)
        df["attempt_no"] = pd.to_numeric(df["attempt_no"], errors="coerce").fillna(0).astype(int)
        df["is_correct"] = df["is_correct"].astype(bool)

        # Best-of-3 theo từng bài
        per_ex = (
            df.groupby("exercise_code", as_index=False)
            .agg(
                best_score=("score", "max"),
                best_correct=("is_correct", "max"),
                attempts_done=("attempt_no", "nunique"),
                last_submit=("created_at", "max"),
            )
            .sort_values(["best_score", "best_correct", "attempts_done", "last_submit"], ascending=[False, False, False, False])
        )

        total_score = int(per_ex["best_score"].sum())
        total_correct = int(per_ex["best_correct"].sum())
        exercises_done = int(per_ex["exercise_code"].nunique())
        attempts_total = int(df.shape[0])

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🎯 Tổng điểm (best-of-3)", f"{total_score}")
        c2.metric("✅ Số bài đúng", f"{total_correct}")
        c3.metric("📌 Số mã bài đã làm", f"{exercises_done}")
        c4.metric("🧾 Tổng lượt nộp", f"{attempts_total}")

        st.markdown("---")
        st.subheader("📌 Điểm tốt nhất theo từng mã bài (Best-of-3)")

        show_ex = per_ex.rename(columns={
            "exercise_code": "Mã bài",
            "best_score": "Điểm cao nhất",
            "best_correct": "Đúng (1/0)",
            "attempts_done": "Số lần đã nộp",
            "last_submit": "Nộp gần nhất",
        })
        show_ex["Đúng (1/0)"] = show_ex["Đúng (1/0)"].astype(int)
        # Format datetime đẹp hơn (giờ VN) - chỉ cột Nộp gần nhất
        if "Nộp gần nhất" in show_ex.columns:
            show_ex["Nộp gần nhất"] = (
                pd.to_datetime(show_ex["Nộp gần nhất"], errors="coerce", utc=True)
                .dt.tz_convert("Asia/Ho_Chi_Minh")
                .dt.strftime("%Y-%m-%d %H:%M")
            )

        st.dataframe(show_ex, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("🕒 Lịch sử nộp gần nhất")
        recent = df.sort_values("created_at", ascending=False).head(15).copy()
        recent = recent[["created_at","room","exercise_code","attempt_no","score","is_correct"]]
        recent = recent.rename(columns={
            "created_at":"Thời điểm",
            "room":"Phòng",
            "exercise_code":"Mã bài",
            "attempt_no":"Lần",
            "score":"Điểm",
            "is_correct":"Đúng?",
        })
        recent["Đúng?"] = recent["Đúng?"].astype(bool).map({True:"✅", False:"❌"})
        recent["Thời điểm"] = (
            pd.to_datetime(recent["Thời điểm"], errors="coerce", utc=True)
            .dt.tz_convert("Asia/Ho_Chi_Minh")
            .dt.strftime("%Y-%m-%d %H:%M")  
        )


        st.dataframe(recent, use_container_width=True, hide_index=True)

    # =========================================================
    # TAB 3: CLASS LEADERBOARD
    # =========================================================
    with tab_class:
        st.subheader("🏫 Bảng xếp hạng toàn lớp")
        st.info(
            """
- Xếp hạng theo **tổng điểm**
- Dùng để quay số **chọn Top 5 cuối kỳ**
"""
        )

        mssv = st.session_state.get("LAB_MSSV", "").strip().upper()
        my_name = get_student_name(mssv)

        st.markdown("### 🏫 Bảng xếp hạng lớp (Class Leaderboard)")
        st.caption("Xếp hạng dựa trên **tổng điểm best-of-3** của mỗi mã bài.")

        # 1) Ưu tiên view
        data = fetch_class_leaderboard_from_view(limit=300)

        # 2) Fallback nếu view chưa có / lỗi
        if data is None or len(data) == 0:
            st.info("ℹ️ Chưa đọc được VIEW `lab_leaderboard` → dùng chế độ tính tạm từ `lab_attempts`.")
            data = compute_class_leaderboard_fallback(limit=300)

        if not data:
            st.warning("Chưa có dữ liệu xếp hạng. Lớp chưa nộp bài nào.")
            st.stop()

        df = pd.DataFrame(data)

        # Chuẩn hóa vài cột phổ biến (view/fallback có thể khác nhau)
        # ưu tiên các cột: mssv, hoten, total_score, total_correct, exercises_done, last_submit
        if "mssv" in df.columns:
            df["mssv"] = df["mssv"].astype(str).str.strip().str.upper()

        # Nếu view chưa có hoten thì tạo
        if "hoten" not in df.columns:
            df["hoten"] = ""

        # ✅ Bổ sung: nếu hoten bị NULL/None/rỗng -> lấy từ Excel
        df["hoten"] = df["hoten"].fillna("").astype(str)
        mask_missing_name = df["hoten"].str.strip().isin(["", "none", "nan", "null"])
        df.loc[mask_missing_name, "hoten"] = df.loc[mask_missing_name, "mssv"].apply(get_student_name)

        # =========================
        # Chuẩn hoá các cột từ VIEW lab_leaderboard
        # VIEW có: total_score, num_solved_exercises, num_exercises_attempted
        # App muốn dùng: total_score, total_correct, exercises_done
        # =========================

        # total_score
        if "total_score" not in df.columns and "total" in df.columns:
            df["total_score"] = df["total"]
        if "total_score" not in df.columns:
            df["total_score"] = 0

        # ✅ Ưu tiên cột đúng từ view
        if "num_solved_exercises" in df.columns:
            df["total_correct"] = df["num_solved_exercises"]
        elif "total_correct" not in df.columns:
            df["total_correct"] = 0

        if "num_exercises_attempted" in df.columns:
            df["exercises_done"] = df["num_exercises_attempted"]
        elif "exercises_done" not in df.columns:
            df["exercises_done"] = 0

        # ép kiểu số
        for col in ["total_score", "total_correct", "exercises_done"]:
            if col not in df.columns:
                df[col] = 0
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)


        # 4) Sort + Rank
        sort_cols = ["total_score", "total_correct", "exercises_done"]
        df = df.sort_values(sort_cols, ascending=[False, False, False]).reset_index(drop=True)
        df.insert(0, "Rank", df.index + 1)



        # Bộ lọc/search
        c1, c2 = st.columns([2, 1])
        with c1:
            kw = st.text_input("🔎 Tìm theo MSSV / Họ tên", value="", key="lb_search")
        with c2:
            top_n = st.selectbox("Hiển thị Top", [20, 50, 100, 200], index=1, key="lb_top_n")

        show = df.copy()
        if kw.strip():
            k = kw.strip().lower()
            show = show[
                show["mssv"].astype(str).str.lower().str.contains(k)
                | show["hoten"].astype(str).str.lower().str.contains(k)
            ]

        show = show.head(int(top_n))

        # Bảng hiển thị
        show2 = show[["Rank","hoten","mssv","total_score","total_correct","exercises_done"]].rename(columns={
            "hoten":"Họ tên",
            "mssv":"MSSV",
            "total_score":"Tổng điểm",
            "total_correct":"Bài đúng",
            "exercises_done":"Số mã bài",
        })

        st.dataframe(show2, use_container_width=True, hide_index=True)

        # Hiển thị rank cá nhân
        my_row = df[df["mssv"] == mssv]
        st.markdown("---")
        if not my_row.empty:
            r = int(my_row.iloc[0]["Rank"])
            sc = int(my_row.iloc[0]["total_score"])
            cr = int(my_row.iloc[0]["total_correct"])
            exd = int(my_row.iloc[0]["exercises_done"])
            if my_name:
                st.success(f"📌 Vị trí của **{my_name} ({mssv})**: **#{r}** | Điểm: **{sc}** | Đúng: **{cr}** | Mã bài: **{exd}**")
            else:
                st.success(f"📌 Vị trí của bạn ({mssv}): **#{r}** | Điểm: **{sc}** | Đúng: **{cr}** | Mã bài: **{exd}**")
        else:
            st.info("Bạn chưa có dữ liệu xếp hạng (chưa nộp bài hoặc chưa đồng bộ).")

    footer()

# ==============================================================================
# ROUTER
# ==============================================================================
room = st.session_state.get("ROOM", "DEALING")

if room == "DEALING":
    room_1_dealing()
elif room == "RISK":
    room_2_risk()
elif room == "TRADE":
    room_3_trade()
elif room == "INVEST":
    room_4_invest()
elif room == "MACRO":
    room_5_macro()
elif room == "LEADERBOARD":
    room_6_leaderboard()

