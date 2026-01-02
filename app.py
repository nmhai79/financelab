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
import random
import math



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

import numpy as np

def gen_case_D02(seed: int) -> tuple[dict, dict]:
    """
    D02 — Tam giác VND–USD–EUR.
    Cho 3 báo giá: USD/VND, EUR/USD, EUR/VND (direct).
    Hỏi: Có arbitrage không? Nếu có thì theo hướng nào và lợi nhuận (VND) với số vốn ban đầu.
    """
    rng = np.random.default_rng(int(seed) % 2_000_000_000)  # an toàn bigint

    # 1) Báo giá USD/VND
    usd_bid = int(rng.integers(23500, 25501))              # VND/USD
    usd_ask = usd_bid + int(rng.integers(10, 61))          # spread 10–60

    # 2) Báo giá EUR/USD
    eur_bid = float(rng.integers(10200, 11501) / 10000)    # 1.0200–1.1500
    eur_ask = round(eur_bid + float(rng.integers(10, 41) / 10000), 4)  # +0.0010..0.0040

    # 3) Cross implied EUR/VND
    implied_bid = eur_bid * usd_bid
    implied_ask = eur_ask * usd_ask

    # 4) Tạo market EUR/VND direct có thể lệch để tạo arbitrage (có xác suất)
    spread_eurvnd = int(rng.integers(40, 121))  # 40–120 VND
    mid = (implied_bid + implied_ask) / 2

    # delta: tạo lệch vừa phải + thỉnh thoảng lệch mạnh để chắc chắn có case arbitrage
    if rng.random() < 0.55:
        delta = int(rng.integers(-120, 121))    # thường: nhỏ
    else:
        delta = int(rng.integers(-600, 601))    # đôi lúc: lớn

    market_mid = mid + delta
    eurvnd_bid = int(round(market_mid - spread_eurvnd / 2))
    eurvnd_ask = int(round(eurvnd_bid + spread_eurvnd))

    # đảm bảo hợp lý
    eurvnd_bid = max(eurvnd_bid, 1000)
    eurvnd_ask = max(eurvnd_ask, eurvnd_bid + 1)

    # 5) Vốn ban đầu
    start_vnd = int(rng.integers(200_000_000, 1_200_000_000))  # 200m–1.2b

    # 6) Xác định arbitrage
    # Điều kiện A: EUR rẻ direct so với cross -> mua EUR direct (ask), bán EUR->USD (bid), bán USD->VND (bid)
    cond_A = eurvnd_ask < implied_bid

    # Điều kiện B: EUR đắt direct so với cross -> mua EUR qua cross, bán EUR direct (bid)
    cond_B = eurvnd_bid > implied_ask

    # Tính profit theo 2 hướng (nếu âm thì coi như 0)
    profit_A = 0
    profit_B = 0

    if cond_A:
        eur = start_vnd / eurvnd_ask
        usd = eur * eur_bid
        end_vnd = usd * usd_bid
        profit_A = int(round(end_vnd - start_vnd))

    if cond_B:
        usd = start_vnd / usd_ask
        eur = usd / eur_ask
        end_vnd = eur * eurvnd_bid
        profit_B = int(round(end_vnd - start_vnd))

    # Chọn đáp án đúng nhất
    if profit_A > 0 and profit_A >= profit_B:
        correct_option = "A"
        profit_vnd = profit_A
    elif profit_B > 0:
        correct_option = "B"
        profit_vnd = profit_B
    else:
        correct_option = "C"
        profit_vnd = 0

    params = {
        "usd_bid": usd_bid,
        "usd_ask": usd_ask,
        "eur_bid": eur_bid,
        "eur_ask": eur_ask,
        "eurvnd_bid": eurvnd_bid,
        "eurvnd_ask": eurvnd_ask,
        "start_vnd": start_vnd,
    }

    answers = {
        "correct_option": correct_option,   # A/B/C
        "profit_vnd": int(profit_vnd),
        "implied_bid": int(round(implied_bid)),
        "implied_ask": int(round(implied_ask)),
    }

    return params, answers

def gen_case_R01(seed: int) -> tuple[dict, dict]:
    """
    R01: Tính tỷ giá kỳ hạn theo IRP + chi phí hedge Forward cho khoản nợ USD.
    Output:
      - params: dữ liệu đề bài
      - answers: đáp án chuẩn
    """
    rng = random.Random(int(seed))

    usd_amount = rng.randrange(200_000, 2_000_001, 50_000)     # USD nợ
    days = rng.choice([30, 60, 90, 180])                       # kỳ hạn (ngày)

    # Spot USD/VND (BID/ASK) - step 10 VND
    spot_bid = rng.randrange(23200, 25801, 10)
    spread = rng.randrange(20, 71, 5)
    spot_ask = spot_bid + spread

    # Lãi suất năm (decimal)
    i_vnd = rng.choice([0.045, 0.050, 0.055, 0.060, 0.065, 0.070, 0.075, 0.080])
    i_usd = rng.choice([0.020, 0.025, 0.030, 0.035, 0.040, 0.045, 0.050, 0.055])

    t = days / 360.0
    factor = (1.0 + i_vnd * t) / (1.0 + i_usd * t)

    fwd_bid = spot_bid * factor
    fwd_ask = spot_ask * factor

    fwd_bid_i = int(round(fwd_bid))   # làm tròn đến VND
    fwd_ask_i = int(round(fwd_ask))

    # Hedge khoản nợ USD => DN cần MUA USD tương lai => dùng Forward ASK
    hedged_cost_vnd = int(round(usd_amount * fwd_ask_i))

    params = {
        "usd_amount": usd_amount,
        "days": days,
        "spot_bid": spot_bid,
        "spot_ask": spot_ask,
        "i_vnd": i_vnd,   # decimal
        "i_usd": i_usd,   # decimal
    }

    answers = {
        "fwd_bid": fwd_bid_i,
        "fwd_ask": fwd_ask_i,
        "hedged_cost_vnd": hedged_cost_vnd,
    }
    return params, answers

def gen_case_R02(seed: int) -> tuple[dict, dict]:
    """
    R02: So sánh Hedge Forward vs Option cho khoản nợ USD
    - Sinh Spot USD/VND, lãi suất -> tính Forward (ASK)
    - Sinh Option: strike K, premium (VND/USD)
    - Sinh kịch bản Spot tại đáo hạn (S_T)
    Yêu cầu SV: tính chi phí Forward, chi phí Option, và chọn phương án rẻ hơn.
    """
    rng = random.Random(int(seed))

    usd_amount = rng.randrange(200_000, 2_000_001, 50_000)
    days = rng.choice([30, 60, 90, 180])

    # Spot USD/VND
    spot_bid = rng.randrange(23200, 25801, 10)
    spr = rng.randrange(20, 71, 5)
    spot_ask = spot_bid + spr

    # Lãi suất (năm)
    i_vnd = rng.choice([0.045, 0.050, 0.055, 0.060, 0.065, 0.070, 0.075, 0.080])
    i_usd = rng.choice([0.020, 0.025, 0.030, 0.035, 0.040, 0.045, 0.050, 0.055])

    t = days / 360.0
    factor = (1.0 + i_vnd * t) / (1.0 + i_usd * t)

    fwd_ask = int(round(spot_ask * factor))
    fwd_bid = int(round(spot_bid * factor))

    # Option: USD Call (DN mua USD để trả nợ)
    # Strike quanh forward ± (0..200) cho đa dạng
    strike = int(round(fwd_ask + rng.choice([-200, -100, 0, 100, 200])))
    premium = rng.choice([30, 40, 50, 60, 70, 80, 100, 120])   # VND/USD

    # Kịch bản Spot tại đáo hạn (S_T ask) quanh forward ± (0..400)
    sT = int(round(fwd_ask + rng.choice([-400, -250, -150, -50, 50, 150, 250, 400])))

    # Chi phí hedge:
    forward_cost = int(round(usd_amount * fwd_ask))

    # Option cost: trả premium + mua USD theo min(S_T, K) (vì có quyền mua tại K)
    option_rate = min(sT, strike) + premium  # VND/USD (all-in)
    option_cost = int(round(usd_amount * option_rate))

    if option_cost < forward_cost:
        best = "OPTION"
    elif option_cost > forward_cost:
        best = "FORWARD"
    else:
        best = "TIE"

    params = {
        "usd_amount": usd_amount,
        "days": days,
        "spot_bid": spot_bid,
        "spot_ask": spot_ask,
        "i_vnd": i_vnd,
        "i_usd": i_usd,
        "fwd_bid": fwd_bid,
        "fwd_ask": fwd_ask,
        "strike": strike,
        "premium": premium,
        "spot_T": sT,
    }

    answers = {
        "forward_cost": forward_cost,
        "option_cost": option_cost,
        "best_choice": best,  # "FORWARD" | "OPTION" | "TIE"
    }
    return params, answers

def gen_case_T01(seed: int) -> tuple[dict, dict]:
    rng = np.random.default_rng(int(seed))

    # Invoice & kỳ hạn
    amount_usd = int(rng.integers(20_000, 200_001) // 1000 * 1000)   # bội 1,000
    tenor_days = int(rng.choice([30, 60, 90, 120]))

    # Lãi suất cơ hội (nếu trả sớm sẽ mất lãi cơ hội)
    opp_rate = float(rng.uniform(0.04, 0.09))  # 4% -> 9%

    # --- Fees ---
    # T/T
    tt_fixed = float(rng.integers(10, 31))  # USD
    tt_pct = float(rng.choice([0.0005, 0.0010, 0.0015, 0.0020]))  # 0.05% -> 0.20%

    # Nhờ thu (D/A)
    da_fixed = float(rng.integers(20, 61))
    da_pct = float(rng.choice([0.0008, 0.0012, 0.0018, 0.0025]))  # 0.08% -> 0.25%

    # L/C trả chậm
    lc_fixed = float(rng.integers(50, 121))
    lc_pct_per_quarter = float(rng.choice([0.0015, 0.0020, 0.0025, 0.0035, 0.0040]))  # 0.15% -> 0.40% / quý
    lc_margin = float(rng.choice([0.05, 0.10, 0.15, 0.20]))  # ký quỹ 5% -> 20%
    quarters = int(math.ceil(tenor_days / 90))

    # --- Cost model (USD) ---
    # T/T: trả ngay => opportunity cost trên toàn bộ invoice trong tenor_days
    opp_cost_tt = amount_usd * opp_rate * (tenor_days / 360.0)
    cost_tt = tt_fixed + tt_pct * amount_usd + opp_cost_tt

    # D/A: trả cuối kỳ => giả định không mất opp cost (chỉ fee)
    cost_da = da_fixed + da_pct * amount_usd

    # L/C trả chậm: phí mở theo quý + fixed + opp cost trên phần ký quỹ
    opp_cost_margin = amount_usd * lc_margin * opp_rate * (tenor_days / 360.0)
    cost_lc = lc_fixed + (lc_pct_per_quarter * quarters * amount_usd) + opp_cost_margin

    costs = {
        "TT": round(cost_tt, 2),
        "DA": round(cost_da, 2),
        "LC": round(cost_lc, 2),
    }
    best_method = min(costs, key=costs.get)

    params = {
        "amount_usd": amount_usd,
        "tenor_days": tenor_days,
        "opp_rate": opp_rate,
        "tt_fixed": tt_fixed,
        "tt_pct": tt_pct,
        "da_fixed": da_fixed,
        "da_pct": da_pct,
        "lc_fixed": lc_fixed,
        "lc_pct_per_quarter": lc_pct_per_quarter,
        "lc_margin": lc_margin,
        "quarters": quarters,
    }
    answers = {
        "best_method": best_method,   # "TT" | "DA" | "LC"
        "costs": costs,
        "min_cost": costs[best_method],
    }
    return params, answers

from datetime import date, timedelta

def gen_case_T02(seed: int) -> tuple[dict, dict]:
    rng = np.random.default_rng(int(seed))

    # --- Basic L/C terms (đơn giản nhưng đúng logic checking) ---
    issue_date = date(2025, 1, 1) + timedelta(days=int(rng.integers(0, 330)))
    latest_ship = issue_date + timedelta(days=int(rng.choice([30, 45, 60])))
    expiry_date = latest_ship + timedelta(days=int(rng.choice([15, 21, 30])))

    amount = int(rng.integers(50_000, 300_001) // 1000 * 1000)
    tolerance = int(rng.choice([0, 5, 10]))  # % tolerance
    goods = rng.choice([
        "Coffee beans (Robusta)",
        "Pepper (Black Pepper)",
        "Cashew kernels",
        "Frozen seafood",
        "Textile garments",
    ])

    incoterm = rng.choice(["CIF", "FOB", "CFR"])
    port_load = rng.choice(["Ho Chi Minh City, VN", "Hai Phong, VN", "Da Nang, VN"])
    port_discharge = rng.choice(["Los Angeles, US", "Hamburg, DE", "Rotterdam, NL", "Tokyo, JP"])

    # Buyer/Seller (dùng tên giả lập)
    applicant = rng.choice(["ABC Import LLC", "Global Traders GmbH", "Sunrise Foods Co."])
    beneficiary = rng.choice(["VN Export JSC", "Mekong Trading Co., Ltd.", "Saigon Agro Ltd."])

    # --- Presented documents (đề sẽ hiển thị) ---
    # Các giá trị dưới đây sẽ bị "bẻ" tùy sai biệt được chọn
    presented = {
        "invoice_amount": amount,
        "invoice_currency": "USD",
        "invoice_goods_desc": goods,
        "invoice_incoterm": incoterm,

        "bl_shipped_on_board": True,
        "bl_ship_date": latest_ship,          # sẽ bị đổi nếu sai
        "bl_port_load": port_load,
        "bl_port_discharge": port_discharge,
        "bl_originals": int(rng.choice([1, 2, 3])),  # sẽ bị đổi nếu sai

        "insurance_present": True if incoterm == "CIF" else bool(rng.choice([True, False])),
        "insurance_coverage_pct": 110 if incoterm == "CIF" else int(rng.choice([0, 100, 110])),
        "insurance_currency": "USD",

        "co_present": True,
        "packing_list_present": True,
        "documents_presented_within_days": int(rng.choice([5, 10, 15, 21])),
    }

    # --- Pool sai biệt (codes + description) ---
    # Lưu ý: mô tả để SV hiểu, nhưng máy chấm dựa vào code.
    DISCREPANCY_POOL = [
        ("T02-01", "Invoice amount vượt quá mức cho phép theo L/C tolerance"),
        ("T02-02", "Mô tả hàng hóa trên Invoice không phù hợp L/C"),
        ("T02-03", "B/L ship date sau Latest shipment date"),
        ("T02-04", "Thiếu số bản gốc B/L theo yêu cầu"),
        ("T02-05", "Cảng xếp/dỡ trên B/L không đúng L/C"),
        ("T02-06", "Không xuất trình Insurance trong điều kiện CIF"),
        ("T02-07", "Insurance coverage < 110% (với CIF)"),
        ("T02-08", "Xuất trình chứng từ trễ (late presentation)"),
        ("T02-09", "Thiếu C/O (Certificate of Origin)"),
        ("T02-10", "Thiếu Packing List"),
    ]

    # Random số sai biệt (1-3)
    k = int(rng.integers(1, 4))
    chosen = rng.choice(len(DISCREPANCY_POOL), size=k, replace=False)
    chosen_codes = [DISCREPANCY_POOL[i][0] for i in chosen]

    # --- Apply sai biệt vào bộ chứng từ ---
    # 01: invoice amount vượt tolerance
    if "T02-01" in chosen_codes:
        # tăng vượt tolerance một chút
        max_allowed = amount * (1 + tolerance/100.0)
        presented["invoice_amount"] = int(max_allowed + rng.integers(500, 3000))

    # 02: mô tả hàng hóa khác
    if "T02-02" in chosen_codes:
        presented["invoice_goods_desc"] = rng.choice(["Spare parts", "Rice", "Electronics components"])

    # 03: ship date sau latest_ship
    if "T02-03" in chosen_codes:
        presented["bl_ship_date"] = latest_ship + timedelta(days=int(rng.integers(1, 8)))

    # 04: thiếu originals
    if "T02-04" in chosen_codes:
        presented["bl_originals"] = int(rng.choice([0, 1]))  # thiếu rõ

    # 05: sai cảng
    if "T02-05" in chosen_codes:
        presented["bl_port_discharge"] = rng.choice(["Singapore, SG", "Shanghai, CN", "Sydney, AU"])

    # 06: thiếu insurance khi CIF
    if "T02-06" in chosen_codes:
        presented["insurance_present"] = False

    # 07: coverage <110% khi CIF
    if "T02-07" in chosen_codes:
        presented["insurance_present"] = True
        presented["insurance_coverage_pct"] = int(rng.choice([100, 105, 108]))

    # 08: late presentation
    if "T02-08" in chosen_codes:
        presented["documents_presented_within_days"] = int(rng.choice([22, 25, 30]))

    # 09: thiếu C/O
    if "T02-09" in chosen_codes:
        presented["co_present"] = False

    # 10: thiếu packing list
    if "T02-10" in chosen_codes:
        presented["packing_list_present"] = False

    # --- L/C terms ---
    lc_terms = {
        "issue_date": issue_date,
        "latest_ship": latest_ship,
        "expiry_date": expiry_date,
        "amount": amount,
        "currency": "USD",
        "tolerance_pct": tolerance,
        "goods": goods,
        "incoterm": incoterm,
        "port_load": port_load,
        "port_discharge": port_discharge,
        "applicant": applicant,
        "beneficiary": beneficiary,
        "required_bl_originals": 3,             # cố định để rõ checking
        "max_presentation_days": 21,            # thông lệ (bài tập)
    }

    params = {
        "lc_terms": lc_terms,
        "presented": presented,
        "discrepancy_pool": DISCREPANCY_POOL,  # để render options đồng nhất
    }

    answers = {
        "correct_codes": sorted(chosen_codes),
    }

    return params, answers

def gen_case_I01(seed: int) -> tuple[dict, dict]:
    rng = np.random.default_rng(int(seed))

    # Initial investment (USD)
    I0 = int(rng.integers(80_000, 200_001) // 1000 * 1000)

    # 3-year cash flows (USD)
    cf1 = int(rng.integers(30_000, 90_001) // 1000 * 1000)
    cf2 = int(rng.integers(30_000, 90_001) // 1000 * 1000)
    cf3 = int(rng.integers(30_000, 90_001) // 1000 * 1000)

    # Discount rate (USD) 8% - 15%
    r = float(rng.integers(8, 16)) / 100.0

    npv = -I0 + (cf1 / (1 + r) ** 1) + (cf2 / (1 + r) ** 2) + (cf3 / (1 + r) ** 3)
    npv_round = int(round(npv))  # làm tròn USD

    decision = "ACCEPT" if npv_round > 0 else "REJECT"

    params = {
        "I0": I0,
        "cf1": cf1,
        "cf2": cf2,
        "cf3": cf3,
        "r": r,  # decimal, ví dụ 0.12
    }
    answers = {
        "npv": npv_round,
        "decision": decision,
    }
    return params, answers

def irr_bisect(cashflows, low=-0.9, high=1.5, tol=1e-7, max_iter=200):
    """
    Tính IRR bằng bisection trên NPV(r)=0.
    cashflows: list[float] với CF0 âm.
    Trả về irr dạng decimal (vd 0.1543).
    """
    def npv(rate):
        return sum(cf / ((1 + rate) ** t) for t, cf in enumerate(cashflows))

    f_low = npv(low)
    f_high = npv(high)

    # Nếu không đổi dấu -> không đảm bảo có nghiệm trong khoảng
    if f_low == 0:
        return low
    if f_high == 0:
        return high
    if f_low * f_high > 0:
        # fallback: trả None để báo không tính được
        return None

    for _ in range(max_iter):
        mid = (low + high) / 2
        f_mid = npv(mid)
        if abs(f_mid) < tol:
            return mid
        if f_low * f_mid < 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid
    return (low + high) / 2


def compute_irr_decimal(cashflows):
    """
    Ưu tiên numpy_financial nếu có, nếu không thì bisection.
    """
    try:
        import numpy_financial as npf
        irr = npf.irr(cashflows)
        if irr is None or (isinstance(irr, float) and (np.isnan(irr) or np.isinf(irr))):
            return None
        return float(irr)
    except Exception:
        return irr_bisect(cashflows)
    
def gen_case_I02(seed: int) -> tuple[dict, dict]:
    rng = np.random.default_rng(int(seed))

    I0 = int(rng.integers(80_000, 220_001) // 1000 * 1000)

    # 4 năm để IRR "đẹp" hơn
    cf1 = int(rng.integers(25_000, 90_001) // 1000 * 1000)
    cf2 = int(rng.integers(25_000, 95_001) // 1000 * 1000)
    cf3 = int(rng.integers(25_000, 100_001) // 1000 * 1000)
    cf4 = int(rng.integers(25_000, 110_001) // 1000 * 1000)

    # WACC 8% - 16%
    wacc = float(rng.integers(8, 17)) / 100.0

    cashflows = [-I0, cf1, cf2, cf3, cf4]
    irr = compute_irr_decimal(cashflows)

    # Nếu hiếm khi irr None do dữ liệu không đổi dấu trong khoảng -> regen nhẹ bằng seed+1
    if irr is None:
        rng = np.random.default_rng(int(seed) + 1)
        I0 = int(rng.integers(80_000, 220_001) // 1000 * 1000)
        cf1 = int(rng.integers(30_000, 90_001) // 1000 * 1000)
        cf2 = int(rng.integers(30_000, 95_001) // 1000 * 1000)
        cf3 = int(rng.integers(30_000, 100_001) // 1000 * 1000)
        cf4 = int(rng.integers(30_000, 110_001) // 1000 * 1000)
        wacc = float(rng.integers(8, 17)) / 100.0
        cashflows = [-I0, cf1, cf2, cf3, cf4]
        irr = compute_irr_decimal(cashflows)

    irr_pct = float(irr) * 100.0
    irr_pct_round = round(irr_pct, 2)  # làm tròn 2 chữ số thập phân

    decision = "ACCEPT" if irr > wacc else "REJECT"

    params = {
        "I0": I0,
        "cf1": cf1, "cf2": cf2, "cf3": cf3, "cf4": cf4,
        "wacc": wacc,              # decimal
        "cashflows": cashflows,    # lưu để debug/học
    }
    answers = {
        "irr_pct": irr_pct_round,  # %
        "decision": decision,
    }
    return params, answers

def gen_case_M01(seed: int) -> tuple[dict, dict]:
    """
    M01: Cú sốc tỷ giá lên nợ công
    - Random: nợ nước ngoài (tỷ USD), tỷ giá gốc, shock %
    - Yêu cầu SV tính: tỷ giá mới, gánh nặng tăng thêm (nghìn tỷ VND)
    """
    import numpy as np

    # tránh seed quá lớn (an toàn cho DB nếu bạn có lưu seed)
    seed = int(seed) % 2_000_000_000
    rng = np.random.default_rng(seed)

    debt_usd_bn = int(rng.integers(20, 101))  # 20..100 (tỷ USD)
    base_rate = int(rng.integers(23000, 27001) // 50 * 50)  # bội 50 cho “đẹp”
    shock_pct = float(rng.choice([5, 7, 10, 12, 15, 18, 20, 25, 30]))

    new_rate = int(round(base_rate * (1 + shock_pct / 100), 0))

    # Quy đổi đơn vị:
    # debt_usd_bn (tỷ USD) * base_rate (VND/USD) -> nghìn tỷ VND vì: bn * rate / 1000
    base_debt_tril = round(debt_usd_bn * base_rate / 1000, 1)
    new_debt_tril = round(debt_usd_bn * new_rate / 1000, 1)
    increase_tril = round(new_debt_tril - base_debt_tril, 1)

    params = {
        "debt_usd_bn": debt_usd_bn,
        "base_rate": base_rate,
        "shock_pct": shock_pct,
    }
    answers = {
        "new_rate": new_rate,
        "increase_tril": increase_tril,
        "base_debt_tril": base_debt_tril,
        "new_debt_tril": new_debt_tril,
    }
    return params, answers

def gen_case_M02(seed: int) -> tuple[dict, dict]:
    """
    M02: Carry Trade Unwind (Option A)
    SV nhập:
    1) VND nhận được khi mở carry (JPY->VND)
    2) P/L (VND) sau horizon_days khi JPY mạnh lên shock_pct
    3) Margin call? dựa equity_vnd và margin_trigger
    """
    import numpy as np

    seed = int(seed) % 2_000_000_000
    rng = np.random.default_rng(seed)

    # Notional vay JPY (triệu JPY -> đổi ra JPY)
    notional_mjpy = int(rng.integers(50, 301))          # 50..300 (million JPY)
    notional_jpy = int(notional_mjpy * 1_000_000)

    # Spot JPY/VND (VND/JPY) - làm tròn theo bước 0.5 cho "đẹp"
    s0 = float(rng.integers(160, 211) / 10)             # 16.0 .. 21.0 (VND/JPY)

    # Lãi suất năm
    i_vnd = float(rng.choice([0.05, 0.06, 0.07, 0.08, 0.09, 0.10]))
    i_jpy = float(rng.choice([0.001, 0.003, 0.005, 0.01, 0.015, 0.02]))

    horizon_days = int(rng.choice([30, 60, 90]))
    t = horizon_days / 360.0

    # Shock: JPY mạnh lên so với VND => JPY/VND tăng => VND/JPY (s) cũng tăng
    shock_pct = float(rng.choice([3, 5, 8, 10, 12, 15]))
    s1 = s0 * (1 + shock_pct / 100)

    # Vốn tự có + ngưỡng margin call
    equity_vnd = int(rng.integers(100, 401) * 1_000_000)  # 100..400 triệu VND
    margin_trigger = float(rng.choice([0.10, 0.15]))      # 10% hoặc 15%

    # ---- Tính đáp án ----
    vnd_open = notional_jpy * s0
    vnd_end = vnd_open * (1 + i_vnd * t)

    jpy_debt = notional_jpy * (1 + i_jpy * t)
    jpy_repay_capacity = vnd_end / s1

    pl_jpy = jpy_repay_capacity - jpy_debt
    pl_vnd = pl_jpy * s1  # định giá theo tỷ giá unwind

    loss_vnd = max(0.0, -pl_vnd)
    loss_pct = loss_vnd / max(1.0, equity_vnd)
    margin_call = bool(loss_pct >= margin_trigger)

    # Làm tròn để chấm dễ (VND làm tròn 1,000)
    vnd_open_r = int(round(vnd_open / 1000) * 1000)
    pl_vnd_r = int(round(pl_vnd / 1000) * 1000)

    params = {
        "notional_mjpy": notional_mjpy,
        "notional_jpy": notional_jpy,
        "s0": s0,
        "i_vnd": i_vnd,
        "i_jpy": i_jpy,
        "horizon_days": horizon_days,
        "shock_pct": shock_pct,
        "s1": s1,
        "equity_vnd": equity_vnd,
        "margin_trigger": margin_trigger,
    }
    answers = {
        "vnd_open": vnd_open_r,
        "pl_vnd": pl_vnd_r,
        "margin_call": margin_call,
        # thêm vài số để bạn debug/giải thích nếu cần
        "vnd_end": float(vnd_end),
        "jpy_debt": float(jpy_debt),
        "loss_pct": float(loss_pct),
    }
    return params, answers

#======= KẾT THÚC CÁC HÀM gen_case ======

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
        {"code": "D01", "title": "Niêm yết tỷ giá chéo EUR/VND (Bid–Ask–Spread)"},
        {"code": "D02", "title": "Săn Arbitrage tam giác (VND–USD–EUR)"},
    ],

    # PHÒNG 2: RISK MANAGEMENT (loại R2-03 nâng cao)
    "RISK": [
        {"code": "R01", "title": "Tính tỷ giá kỳ hạn (IRP) & chi phí Forward cho khoản nợ USD"},
        {"code": "R02", "title": "Forward vs Option (Premium & Break-even)"},
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
        {"code": "M02", "title": "Carry Trade Unwind (JPY funding → VND asset) + Margin call"},
    ],
}

ROOM_LABELS = {
    "DEALING": "💱 Sàn Kinh doanh Ngoại hối (Dealing Room)",
    "RISK": "🛡️ Phòng Quản trị Rủi ro (Risk Management)",
    "TRADE": "🚢 Phòng Thanh toán Quốc tế (Trade Finance)",
    "INVEST": "🏭 Phòng Đầu tư Quốc tế (Investment Dept)",
    "MACRO": "📉 Ban Chiến lược Vĩ mô (Macro Strategy)",
}

# BÀI D01: XỬ LÝ GIAO DỊCH NGOẠI HỐI
def render_exercise_D01(mssv: str, room_key: str, ex_code: str, attempt_no: int):
    room_key = str(room_key).strip().upper()
    ex_code = str(ex_code).strip().upper()
    if ex_code != "D01":
        return  # an toàn

    # 1) Nếu attempt đã nộp rồi -> khóa, hiển thị lại
    existing = fetch_attempt(mssv, ex_code, attempt_no)
    # ✅ Hiện kết quả chấm nếu attempt đã nộp
    if existing:
        score = int(existing.get("score", 0) or 0)
        is_correct = bool(existing.get("is_correct", False))

        st.markdown("### 📌 Kết quả lần nộp này")
        (st.success if is_correct else st.error)(
            f"{'✅ Đúng' if is_correct else '❌ Chưa đúng'} - **{score} điểm** (Lần {attempt_no}/3)"
        )

        st.warning(f"🔒 Bạn đã nộp **{ex_code} – Lần {attempt_no}** rồi.")
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
            st.error("⚠️ Không ghi được bài nộp (lỗi hệ thống/DB). Vui lòng thử lại sau 10–20 giây hoặc báo GV.")
            return

        if is_ok:
            st.success(f"✅ CHÍNH XÁC! Bạn được **+{score} điểm**.")
        else:
            st.error("❌ CHƯA ĐÚNG. Bạn được **0 điểm**.")

        st.info(
            f"📌 Đáp án chuẩn: EUR/VND = **{answers['cross_bid']:,.0f} - {answers['cross_ask']:,.0f}** | Spread = **{answers['spread']:,.0f}**"
        )
        # ✅ Lưu kết quả để sau rerun vẫn hiện
        st.session_state[f"LAST_GRADE_{ex_code}_{attempt_no}"] = {
            "is_ok": bool(is_ok),
            "score": int(score),
            "attempt_no": int(attempt_no),
        }
        st.rerun()

# BÀI D02: XỬ LÝ GIAO DỊCH NGOẠI HỐI
def render_exercise_D02(mssv: str, room_key: str, ex_code: str, attempt_no: int):
    room_key = str(room_key).strip().upper()
    ex_code = str(ex_code).strip().upper()
    if ex_code != "D02":
        return  # an toàn

    # 1) Nếu attempt đã nộp rồi -> khóa và hiện lại đề + đáp án
    existing = fetch_attempt(mssv, ex_code, attempt_no)
    # ✅ Hiện kết quả chấm nếu attempt đã nộp
    if existing:
        score = int(existing.get("score", 0) or 0)
        is_correct = bool(existing.get("is_correct", False))

        st.markdown("### 📌 Kết quả lần nộp này")
        (st.success if is_correct else st.error)(
            f"{'✅ Đúng' if is_correct else '❌ Chưa đúng'} - **{score} điểm** (Lần {attempt_no}/3)"
        )

        st.warning(f"🔒 Bạn đã nộp **{ex_code} – Lần {attempt_no}** rồi.")
        params = existing.get("params_json", {}) or {}
        ans = existing.get("answer_json", {}) or {}

        st.write("**Đề bài bạn đã nhận (từ DB):**")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("##### 🇺🇸 USD/VND")
            st.write(f"BID: **{params.get('usd_bid','-'):,.0f}**")
            st.write(f"ASK: **{params.get('usd_ask','-'):,.0f}**")
        with c2:
            st.markdown("##### 🇪🇺 EUR/USD")
            st.write(f"BID: **{params.get('eur_bid','-')}**")
            st.write(f"ASK: **{params.get('eur_ask','-')}**")
        with c3:
            st.markdown("##### 🇪🇺 EUR/VND (Direct)")
            st.write(f"BID: **{params.get('eurvnd_bid','-'):,.0f}**")
            st.write(f"ASK: **{params.get('eurvnd_ask','-'):,.0f}**")

        st.info(f"💰 Vốn ban đầu: **{params.get('start_vnd','-'):,.0f} VND**")
        st.markdown("**Đáp án chuẩn (để bạn đối chiếu học tập):**")
        st.success(
            f"Đáp án đúng: **{ans.get('correct_option','-')}** | Lợi nhuận: **{ans.get('profit_vnd',0):,} VND**"
        )
        st.caption(
            f"Cross implied (tham khảo): {ans.get('implied_bid','-'):,.0f} – {ans.get('implied_ask','-'):,.0f}"
        )
        return

    # 2) Sinh đề theo seed ổn định
    seed = stable_seed(mssv, ex_code, attempt_no)
    params, answers = gen_case_D02(seed)

    # 3) Start time (nếu sau này cần)
    start_key = f"START_{mssv}_{ex_code}_{attempt_no}"
    if start_key not in st.session_state:
        st.session_state[start_key] = time.time()

    # 4) Hiển thị đề bài
    st.markdown(
        """
<div class="role-card">
  <div class="role-title">⚡ Bài D02 — Săn Arbitrage tam giác (VND–USD–EUR)</div>
  <div class="mission-text">
    Dựa trên 3 báo giá dưới đây, hãy xác định <b>có Arbitrage hay không</b>.
    Nếu có, chọn <b>hướng Arbitrage đúng</b> và nhập <b>lợi nhuận (VND)</b> với số vốn ban đầu.
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("##### 🇺🇸 USD/VND")
        st.write(f"BID: **{params['usd_bid']:,.0f}**")
        st.write(f"ASK: **{params['usd_ask']:,.0f}**")
    with c2:
        st.markdown("##### 🇪🇺 EUR/USD")
        st.write(f"BID: **{params['eur_bid']:.4f}**")
        st.write(f"ASK: **{params['eur_ask']:.4f}**")
    with c3:
        st.markdown("##### 🇪🇺 EUR/VND (Direct)")
        st.write(f"BID: **{params['eurvnd_bid']:,.0f}**")
        st.write(f"ASK: **{params['eurvnd_ask']:,.0f}**")

    st.info(f"💰 Vốn ban đầu: **{params['start_vnd']:,.0f} VND**")
    st.markdown("---")

    # 5) Chọn đáp án (MCQ) + nhập lợi nhuận
    st.caption("Chọn phương án đúng và nhập lợi nhuận (VND). Nếu không có arbitrage, nhập 0.")

    options = {
        "A": "Có arbitrage: Mua EUR trực tiếp (EUR/VND ASK) → Bán EUR lấy USD (EUR/USD BID) → Bán USD lấy VND (USD/VND BID)",
        "B": "Có arbitrage: Mua EUR qua cross (VND→USD ASK, USD→EUR ASK) → Bán EUR trực tiếp lấy VND (EUR/VND BID)",
        "C": "Không có arbitrage (trong vùng bid–ask)",
        "D": "Có arbitrage: Mua USD rồi bán lại ngay (đánh lạc hướng)",
    }

    pick = st.radio(
        "✅ Chọn phương án:",
        options=list(options.keys()),
        format_func=lambda k: f"{k}. {options[k]}",
        horizontal=False,
        key=f"d02_pick_{attempt_no}",
    )

    in_profit = st.number_input(
        "💵 Lợi nhuận (VND) — nhập 0 nếu không có arbitrage",
        min_value=0.0,
        step=1_000.0,
        format="%.0f",
        key=f"d02_profit_{attempt_no}",
    )

    # 6) Nộp bài
    # tolerance: vì tính ra số lẻ/ làm tròn, cho lệch 10,000 VND là hợp lý với vốn lớn
    PROFIT_TOL = 10_000

    if st.button("📩 NỘP BÀI (Submit)", type="primary", use_container_width=True, key=f"btn_submit_d02_{attempt_no}"):
        correct_opt = answers["correct_option"]
        correct_profit = int(answers["profit_vnd"])

        ok_choice = (pick == correct_opt)
        ok_profit = (abs(int(in_profit) - correct_profit) <= PROFIT_TOL) if correct_opt in ("A","B") else (int(in_profit) == 0)

        is_ok = ok_choice and ok_profit
        score = 10 if is_ok else 0
        duration_sec = int(time.time() - st.session_state[start_key])

        payload = {
            "mssv": mssv,
            "hoten": None,      # bạn có thể fill từ Excel map sau
            "lop": None,
            "room": room_key,
            "exercise_code": ex_code,
            "attempt_no": int(attempt_no),
            "seed": int(int(seed) % 2_000_000_000),
            "params_json": params,
            "answer_json": answers,
            "is_correct": bool(is_ok),
            "score": int(score),
            "duration_sec": int(duration_sec),
            "note": f"D02 attempt {attempt_no}",
        }

        ok = insert_attempt(payload)
        if not ok:
            st.error("⚠️ Không ghi được bài nộp (lỗi hệ thống/DB). Vui lòng thử lại sau 10–20 giây hoặc báo GV.")
            return

        if is_ok:
            st.success(f"✅ CHÍNH XÁC! Bạn được **+{score} điểm**.")
        else:
            st.error("❌ CHƯA ĐÚNG.")
            st.info(
                f"📌 Đáp án: **{correct_opt}** | Lợi nhuận chuẩn: **{correct_profit:,} VND** "
                f"(Cross implied tham khảo: {answers['implied_bid']:,.0f} – {answers['implied_ask']:,.0f})"
            )

        # ✅ Lưu kết quả để sau rerun vẫn hiện
        st.session_state[f"LAST_GRADE_{ex_code}_{attempt_no}"] = {
            "is_ok": bool(is_ok),
            "score": int(score),
            "attempt_no": int(attempt_no),
        }
        st.rerun()

# BÀI R01: TỶ GIÁ KỲ HẠN VÀ HEDGE FORWARD CHO KHOẢN NỢ USD

def render_exercise_R01(mssv: str, room_key: str, ex_code: str, attempt_no: int):
    room_key = str(room_key).strip().upper()
    ex_code = str(ex_code).strip().upper()

    # Guard an toàn: chỉ chạy đúng bài R01 của phòng RISK
    if room_key != "RISK" or ex_code != "R01":
        return

    # 1) nếu attempt đã nộp -> khóa, show lại đề + đáp án từ DB
    existing = fetch_attempt(mssv, ex_code, attempt_no)
    # ✅ Hiện kết quả chấm nếu attempt đã nộp
    if existing:
        score = int(existing.get("score", 0) or 0)
        is_correct = bool(existing.get("is_correct", False))

        st.markdown("### 📌 Kết quả lần nộp này")
        (st.success if is_correct else st.error)(
            f"{'✅ Đúng' if is_correct else '❌ Chưa đúng'} - **{score} điểm** (Lần {attempt_no}/3)"
        )

        st.warning(f"🔒 Bạn đã nộp **{ex_code} – Lần {attempt_no}** rồi.")
        params = existing.get("params_json", {}) or {}
        ans = existing.get("answer_json", {}) or {}

        st.write("**Đề bài bạn đã nhận (từ DB):**")
        st.write(f"- Khoản nợ: **{params.get('usd_amount','-'):,.0f} USD**, đáo hạn **{params.get('days','-')} ngày**")
        st.write(f"- Spot USD/VND: **{params.get('spot_bid','-'):,.0f} / {params.get('spot_ask','-'):,.0f}**")
        st.write(f"- i(VND): **{float(params.get('i_vnd',0))*100:.2f}%** | i(USD): **{float(params.get('i_usd',0))*100:.2f}%**")

        st.markdown("**Đáp án chuẩn (để đối chiếu):**")
        st.success(
            f"Forward USD/VND = **{ans.get('fwd_bid','-'):,.0f} / {ans.get('fwd_ask','-'):,.0f}**  |  "
            f"Chi phí hedge (Forward ASK) = **{ans.get('hedged_cost_vnd','-'):,.0f} VND**"
        )
        return

    # 2) sinh đề theo seed ổn định
    seed = stable_seed(mssv, ex_code, attempt_no)
    params, answers = gen_case_R01(seed)

    # 3) ghi nhận thời điểm bắt đầu (optional)
    start_key = f"START_{mssv}_{ex_code}_{attempt_no}"
    if start_key not in st.session_state:
        st.session_state[start_key] = time.time()

    # 4) hiển thị đề
    st.markdown(
        f"""
<div class="role-card">
  <div class="role-title">🧾 Bài R01 — Tỷ giá kỳ hạn (IRP) & Hedge Forward cho khoản nợ USD</div>
  <div class="mission-text">
    Doanh nghiệp có khoản nợ <b>{params['usd_amount']:,.0f} USD</b> đáo hạn sau <b>{params['days']} ngày</b>.
    Dựa trên Spot và lãi suất, hãy tính <b>Forward USD/VND (ASK)</b> và <b>chi phí hedge (VND)</b> nếu dùng Forward.
    <br>(Làm tròn đến <b>VND</b>)
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### 🌐 Spot USD/VND")
        st.write(f"BID: **{params['spot_bid']:,.0f}**")
        st.write(f"ASK: **{params['spot_ask']:,.0f}**")
    with c2:
        st.markdown("##### 📈 Lãi suất năm (Act/360)")
        st.write(f"i(VND): **{params['i_vnd']*100:.2f}%**")
        st.write(f"i(USD): **{params['i_usd']*100:.2f}%**")

    st.markdown("---")
    st.caption("✍️ Nhập kết quả (làm tròn 0 chữ số thập phân)")

    a1, a2 = st.columns(2)
    with a1:
        in_fwd_ask = st.number_input(
            "Forward USD/VND (ASK)",
            min_value=0.0, step=1.0, format="%.0f",
            key=f"r01_in_fwdask_{attempt_no}"
        )
    with a2:
        in_cost = st.number_input(
            "Chi phí hedge (VND) = USD nợ × Forward ASK",
            min_value=0.0, step=1000.0, format="%.0f",
            key=f"r01_in_cost_{attempt_no}"
        )

    # 5) submit + chấm
    TOL_FWD = 5  # sai số ±5 VND do làm tròn
    tol_cost = int(params["usd_amount"] * TOL_FWD)  # sai số cost tương ứng

    if st.button("📩 NỘP BÀI (Submit)", type="primary", use_container_width=True, key=f"btn_submit_r01_{attempt_no}"):
        ok_fwd = abs(int(in_fwd_ask) - int(answers["fwd_ask"])) <= TOL_FWD
        ok_cost = abs(int(in_cost) - int(answers["hedged_cost_vnd"])) <= tol_cost

        is_ok = bool(ok_fwd and ok_cost)
        score = 10 if is_ok else 0
        duration_sec = int(time.time() - st.session_state[start_key])

        payload = {
            "mssv": mssv,
            "hoten": get_student_name(mssv) or None,
            "lop": None,
            "room": room_key,
            "exercise_code": ex_code,
            "attempt_no": int(attempt_no),
            "seed": int(seed),
            "params_json": params,
            "answer_json": answers,
            "is_correct": is_ok,
            "score": int(score),
            "duration_sec": int(duration_sec),
            "note": f"R01 attempt {attempt_no}",
        }

        ok = insert_attempt(payload)
        if not ok:
            st.error("⚠️ Không ghi được bài nộp (lỗi hệ thống/DB). Vui lòng thử lại sau 10–20 giây hoặc báo GV.")
            return

        if is_ok:
            st.success(f"✅ CHÍNH XÁC! Bạn được **+{score} điểm**.")
        else:
            st.error("❌ CHƯA ĐÚNG. (0 điểm)")

        st.info(
            f"📌 Đáp án chuẩn: Forward USD/VND = **{answers['fwd_bid']:,.0f} / {answers['fwd_ask']:,.0f}**  |  "
            f"Chi phí hedge = **{answers['hedged_cost_vnd']:,.0f} VND**"
        )
        # ✅ Lưu kết quả để sau rerun vẫn hiện
        st.session_state[f"LAST_GRADE_{ex_code}_{attempt_no}"] = {
            "is_ok": bool(is_ok),
            "score": int(score),
            "attempt_no": int(attempt_no),
        }
        st.rerun()

# R02: FORWARD VS OPTION (PREMIUM & BREAK-EVEN)
def render_exercise_R02(mssv: str, room_key: str, ex_code: str, attempt_no: int):
    room_key = str(room_key).strip().upper()
    ex_code = str(ex_code).strip().upper()

    # Guard an toàn giống D01/D02/R01
    if room_key != "RISK" or ex_code != "R02":
        return

    # 1) Nếu attempt đã nộp -> khóa và hiển thị lại từ DB
    existing = fetch_attempt(mssv, ex_code, attempt_no)
    # ✅ Hiện kết quả chấm nếu attempt đã nộp
    if existing:
        score = int(existing.get("score", 0) or 0)
        is_correct = bool(existing.get("is_correct", False))

        st.markdown("### 📌 Kết quả lần nộp này")
        (st.success if is_correct else st.error)(
            f"{'✅ Đúng' if is_correct else '❌ Chưa đúng'} - **{score} điểm** (Lần {attempt_no}/3)"
        )

        st.warning(f"🔒 Bạn đã nộp **{ex_code} – Lần {attempt_no}** rồi.")
        params = existing.get("params_json", {}) or {}
        ans = existing.get("answer_json", {}) or {}

        st.write("**Đề bài bạn đã nhận (từ DB):**")
        st.write(f"- Khoản nợ: **{params.get('usd_amount','-'):,.0f} USD**, đáo hạn **{params.get('days','-')} ngày**")
        st.write(f"- Spot USD/VND: **{params.get('spot_bid','-'):,.0f} / {params.get('spot_ask','-'):,.0f}**")
        st.write(f"- Forward USD/VND: **{params.get('fwd_bid','-'):,.0f} / {params.get('fwd_ask','-'):,.0f}**")
        st.write(f"- Option Call: Strike **{params.get('strike','-'):,.0f}**, Premium **{params.get('premium','-'):,.0f} VND/USD**")
        st.write(f"- Kịch bản Spot tại đáo hạn (S_T): **{params.get('spot_T','-'):,.0f}**")

        st.markdown("**Đáp án chuẩn (để đối chiếu):**")
        st.success(
            f"Chi phí Forward = **{ans.get('forward_cost','-'):,.0f} VND** | "
            f"Chi phí Option = **{ans.get('option_cost','-'):,.0f} VND** | "
            f"Chọn: **{ans.get('best_choice','-')}**"
        )
        return

    # 2) Sinh đề theo seed ổn định
    seed = stable_seed(mssv, ex_code, attempt_no)
    params, answers = gen_case_R02(seed)

    # 3) Start time (optional)
    start_key = f"START_{mssv}_{ex_code}_{attempt_no}"
    if start_key not in st.session_state:
        st.session_state[start_key] = time.time()

    # 4) Render đề
    st.markdown(
        f"""
<div class="role-card">
  <div class="role-title">🧾 Bài R02 — So sánh Hedge Forward vs Option (Call USD)</div>
  <div class="mission-text">
    DN có khoản nợ <b>{params['usd_amount']:,.0f} USD</b> đáo hạn sau <b>{params['days']} ngày</b>.
    So sánh 2 phương án hedge:
    <br>① <b>Forward</b> theo báo giá kỳ hạn.
    <br>② <b>Option Call USD</b> (Strike + Premium), kịch bản tại đáo hạn có Spot S<sub>T</sub>.
    <br>Hãy tính <b>Chi phí Forward</b>, <b>Chi phí Option</b> và chọn phương án <b>rẻ hơn</b>.
    <br>(Làm tròn đến <b>VND</b>)
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("##### 🌐 Spot USD/VND")
        st.write(f"BID: **{params['spot_bid']:,.0f}**")
        st.write(f"ASK: **{params['spot_ask']:,.0f}**")
    with c2:
        st.markdown("##### 📌 Forward USD/VND")
        st.write(f"BID: **{params['fwd_bid']:,.0f}**")
        st.write(f"ASK: **{params['fwd_ask']:,.0f}**")
    with c3:
        st.markdown("##### 🎯 Option Call USD")
        st.write(f"Strike (K): **{params['strike']:,.0f}**")
        st.write(f"Premium: **{params['premium']:,.0f} VND/USD**")

    st.markdown("##### 🔮 Kịch bản tại đáo hạn")
    st.write(f"Spot tại đáo hạn S_T (ASK): **{params['spot_T']:,.0f}**")

    st.markdown("---")
    st.caption("✍️ Nhập kết quả (VND).")

    a1, a2 = st.columns(2)
    with a1:
        in_forward_cost = st.number_input(
            "Chi phí Hedge bằng Forward (VND)",
            min_value=0.0, step=100000.0, format="%.0f",
            key=f"r02_forward_cost_{attempt_no}"
        )
    with a2:
        in_option_cost = st.number_input(
            "Chi phí Hedge bằng Option (VND)",
            min_value=0.0, step=100000.0, format="%.0f",
            key=f"r02_option_cost_{attempt_no}"
        )

    choice = st.radio(
        "Chọn phương án rẻ hơn:",
        options=["FORWARD", "OPTION", "TIE"],
        horizontal=True,
        key=f"r02_choice_{attempt_no}"
    )

    # 5) Nộp bài
    # Tolerance theo quy mô khoản nợ: sai lệch do nhập/làm tròn
    TOL_RATE = 5  # ±5 VND/USD
    tol_cost = int(params["usd_amount"] * TOL_RATE)

    if st.button("📩 NỘP BÀI (Submit)", type="primary", use_container_width=True, key=f"btn_submit_r02_{attempt_no}"):
        ok_forward = abs(int(in_forward_cost) - int(answers["forward_cost"])) <= tol_cost
        ok_option = abs(int(in_option_cost) - int(answers["option_cost"])) <= tol_cost
        ok_choice = (choice == answers["best_choice"])

        is_ok = bool(ok_forward and ok_option and ok_choice)
        score = 10 if is_ok else 0
        duration_sec = int(time.time() - st.session_state[start_key])

        payload = {
            "mssv": mssv,
            "hoten": get_student_name(mssv) or None,
            "lop": None,
            "room": room_key,
            "exercise_code": ex_code,
            "attempt_no": int(attempt_no),
            "seed": int(seed),
            "params_json": params,
            "answer_json": answers,
            "is_correct": is_ok,
            "score": int(score),
            "duration_sec": int(duration_sec),
            "note": f"R02 attempt {attempt_no}",
        }

        ok = insert_attempt(payload)
        if not ok:
            st.error("⚠️ Không ghi được bài nộp (lỗi hệ thống/DB). Vui lòng thử lại sau 10–20 giây hoặc báo GV.")
            return

        if is_ok:
            st.success(f"✅ CHÍNH XÁC! Bạn được **+{score} điểm**.")
        else:
            st.error("❌ CHƯA ĐÚNG. (0 điểm)")

        st.info(
            f"📌 Đáp án chuẩn: Forward = **{answers['forward_cost']:,.0f} VND** | "
            f"Option = **{answers['option_cost']:,.0f} VND** | "
            f"Chọn: **{answers['best_choice']}**"
        )
        # ✅ Lưu kết quả để sau rerun vẫn hiện
        st.session_state[f"LAST_GRADE_{ex_code}_{attempt_no}"] = {
            "is_ok": bool(is_ok),
            "score": int(score),
            "attempt_no": int(attempt_no),
        }
        st.rerun()

# BÀI T01: TỐI ƯU CHI PHÍ PHƯƠNG THỨC THANH TOÁN QUỐC TẾ
def render_exercise_T01(mssv: str, room_key: str, ex_code: str, attempt_no: int):
    room_key = str(room_key).strip().upper()
    ex_code  = str(ex_code).strip().upper()
    if ex_code != "T01":
        return  # an toàn

    # 1) Nếu attempt đã nộp -> khóa + hiện lại
    existing = fetch_attempt(mssv, ex_code, attempt_no)
    # ✅ Hiện kết quả chấm nếu attempt đã nộp
    if existing:
        score = int(existing.get("score", 0) or 0)
        is_correct = bool(existing.get("is_correct", False))

        st.markdown("### 📌 Kết quả lần nộp này")
        (st.success if is_correct else st.error)(
            f"{'✅ Đúng' if is_correct else '❌ Chưa đúng'} - **{score} điểm** (Lần {attempt_no}/3)"
        )

        st.warning(f"🔒 Bạn đã nộp **{ex_code} – Lần {attempt_no}** rồi.")
        params = existing.get("params_json", {}) or {}
        ans = existing.get("answer_json", {}) or {}
        costs = (ans.get("costs") or {})

        st.markdown("**Đề bài (từ DB):**")
        st.write(f"- Invoice: **{params.get('amount_usd','-'):,} USD** | Kỳ hạn: **{params.get('tenor_days','-')} ngày**")
        st.write(f"- Lãi suất cơ hội: **{float(params.get('opp_rate',0))*100:.2f}%/năm**")

        st.markdown("**Đáp án chuẩn (để đối chiếu học tập):**")
        st.success(
            f"Phương án rẻ nhất: **{ans.get('best_method','-')}** | "
            f"T/T={costs.get('TT','-')} | D/A={costs.get('DA','-')} | L/C={costs.get('LC','-')} (USD)"
        )
        return

    # 2) Sinh đề theo seed ổn định
    seed = stable_seed(mssv, ex_code, attempt_no)
    params, answers = gen_case_T01(seed)

    st.markdown(
        """
<div class="role-card">
  <div class="role-title">📝 Bài T01 — Tối ưu chi phí phương thức thanh toán</div>
  <div class="mission-text">
    So sánh tổng chi phí (USD) của 3 phương thức: <b>T/T</b>, <b>Nhờ thu D/A</b>, <b>L/C trả chậm</b>.
    Chọn phương thức có <b>chi phí thấp nhất</b>.
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    # 3) Hiển thị dữ kiện
    st.write(f"**Invoice:** {params['amount_usd']:,} USD")
    st.write(f"**Kỳ hạn thanh toán:** {params['tenor_days']} ngày")
    st.write(f"**Lãi suất cơ hội (cost of funds):** {params['opp_rate']*100:.2f}%/năm (360 ngày)")

    st.markdown("#### 📌 Phí ngân hàng")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**T/T**")
        st.write(f"Fixed: {params['tt_fixed']:.0f} USD")
        st.write(f"% fee: {params['tt_pct']*100:.2f}%")
        st.caption("T/T trả ngay ⇒ có opportunity cost")
    with col2:
        st.markdown("**Nhờ thu (D/A)**")
        st.write(f"Fixed: {params['da_fixed']:.0f} USD")
        st.write(f"% fee: {params['da_pct']*100:.2f}%")
        st.caption("Giả định trả cuối kỳ ⇒ không tính opp cost")
    with col3:
        st.markdown("**L/C trả chậm**")
        st.write(f"Fixed: {params['lc_fixed']:.0f} USD")
        st.write(f"Opening fee: {params['lc_pct_per_quarter']*100:.2f}% / quý × {params['quarters']} quý")
        st.write(f"Ký quỹ: {params['lc_margin']*100:.0f}% (tính opp cost trên phần ký quỹ)")

    st.markdown("---")

    # 4) SV chọn đáp án
    METHOD_LABELS = {
        "TT": "T/T (chuyển tiền)",
        "DA": "Nhờ thu D/A",
        "LC": "L/C trả chậm",
    }
    pick = st.selectbox(
        "✅ Chọn phương thức có chi phí thấp nhất:",
        options=["TT", "DA", "LC"],
        format_func=lambda k: METHOD_LABELS[k],
        key=f"t01_pick_{attempt_no}"
    )

    # 5) Nộp bài
    if st.button("📩 NỘP BÀI (Submit)", type="primary", use_container_width=True, key=f"btn_submit_t01_{attempt_no}"):
        is_ok = (pick == answers["best_method"])
        score = 10 if is_ok else 0

        payload = {
            "mssv": mssv,
            "hoten": get_student_name(mssv) or None,
            "lop": None,
            "room": "TRADE",
            "exercise_code": ex_code,
            "attempt_no": attempt_no,
            "seed": int(seed),  # seed của bạn đã fix tránh overflow bigint rồi
            "params_json": params,
            "answer_json": answers,
            "is_correct": bool(is_ok),
            "score": int(score),
            "duration_sec": None,
            "note": f"T01 attempt {attempt_no}",
        }

        ok = insert_attempt(payload)
        if not ok:
            st.error("⚠️ Không ghi được bài nộp (lỗi hệ thống/DB). Vui lòng thử lại sau 10–20 giây hoặc báo GV.")
            return

        if is_ok:
            st.success(f"✅ CHÍNH XÁC! Bạn được **+{score} điểm**.")
        else:
            st.error("❌ CHƯA ĐÚNG. Bạn được **0 điểm**.")

        c = answers["costs"]
        st.info(
            f"📌 Chi phí chuẩn (USD): T/T={c['TT']} | D/A={c['DA']} | L/C={c['LC']}  →  Rẻ nhất: **{answers['best_method']}**"
        )
        # ✅ Lưu kết quả để sau rerun vẫn hiện
        st.session_state[f"LAST_GRADE_{ex_code}_{attempt_no}"] = {
            "is_ok": bool(is_ok),
            "score": int(score),
            "attempt_no": int(attempt_no),
        }
        st.rerun()

# T02
def render_exercise_T02(mssv: str, room_key: str, ex_code: str, attempt_no: int):
    room_key = str(room_key).strip().upper()
    ex_code  = str(ex_code).strip().upper()
    if ex_code != "T02":
        return

    # 1) Nếu attempt đã nộp -> khóa + hiện lại
    existing = fetch_attempt(mssv, ex_code, attempt_no)
    # ✅ Hiện kết quả chấm nếu attempt đã nộp
    if existing:
        score = int(existing.get("score", 0) or 0)
        is_correct = bool(existing.get("is_correct", False))

        st.markdown("### 📌 Kết quả lần nộp này")
        (st.success if is_correct else st.error)(
            f"{'✅ Đúng' if is_correct else '❌ Chưa đúng'} - **{score} điểm** (Lần {attempt_no}/3)"
        )

        st.warning(f"🔒 Bạn đã nộp **{ex_code} – Lần {attempt_no}** rồi.")
        params = existing.get("params_json", {}) or {}
        ans = existing.get("answer_json", {}) or {}

        lc = (params.get("lc_terms") or {})
        pr = (params.get("presented") or {})
        pool = (params.get("discrepancy_pool") or [])

        st.markdown("**Đề bài (từ DB):**")
        st.write(f"- Beneficiary: **{lc.get('beneficiary','-')}** | Applicant: **{lc.get('applicant','-')}**")
        st.write(f"- Amount: **{lc.get('amount','-'):,} {lc.get('currency','')}** | Tolerance: **±{lc.get('tolerance_pct','-')}%**")
        st.write(f"- Latest shipment: **{lc.get('latest_ship','-')}** | Max presentation: **{lc.get('max_presentation_days','-')} ngày**")

        st.markdown("**Đáp án chuẩn (codes):**")
        st.success(", ".join(ans.get("correct_codes", [])) or "(Không có)")

        # (Tuỳ chọn) hiển thị mô tả
        mp = {c: d for c, d in pool}
        if ans.get("correct_codes"):
            st.markdown("**Mô tả sai biệt:**")
            for c in ans["correct_codes"]:
                st.write(f"- **{c}**: {mp.get(c,'')}")
        return

    # 2) Sinh đề theo seed ổn định
    seed = stable_seed(mssv, ex_code, attempt_no)
    params, answers = gen_case_T02(seed)

    lc = params["lc_terms"]
    pr = params["presented"]
    pool = params["discrepancy_pool"]

    st.markdown(
        """
<div class="role-card">
  <div class="role-title">📝 Bài T02 — Checking chứng từ theo L/C</div>
  <div class="mission-text">
    Bạn là chuyên viên TTQT. Hãy kiểm tra bộ chứng từ xuất trình so với L/C terms và chọn các <b>sai biệt</b> (discrepancies).
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    # 3) Hiển thị L/C terms
    with st.expander("📄 L/C Terms", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            st.write(f"**Beneficiary:** {lc['beneficiary']}")
            st.write(f"**Applicant:** {lc['applicant']}")
            st.write(f"**Amount:** {lc['amount']:,} {lc['currency']} (±{lc['tolerance_pct']}%)")
            st.write(f"**Goods:** {lc['goods']}")
            st.write(f"**Incoterm:** {lc['incoterm']}")
        with c2:
            st.write(f"**Port of Loading:** {lc['port_load']}")
            st.write(f"**Port of Discharge:** {lc['port_discharge']}")
            st.write(f"**Latest shipment date:** {lc['latest_ship']}")
            st.write(f"**Expiry date:** {lc['expiry_date']}")
            st.write(f"**B/L originals required:** {lc['required_bl_originals']}")
            st.write(f"**Max presentation days:** {lc['max_presentation_days']}")

    # 4) Hiển thị chứng từ xuất trình
    with st.expander("🧾 Bộ chứng từ xuất trình", expanded=True):
        st.markdown("**Commercial Invoice**")
        st.write(f"- Amount: **{pr['invoice_amount']:,} {pr['invoice_currency']}**")
        st.write(f"- Goods: **{pr['invoice_goods_desc']}**")
        st.write(f"- Incoterm: **{pr['invoice_incoterm']}**")

        st.markdown("**Bill of Lading (B/L)**")
        st.write(f"- Shipped on board: **{'Yes' if pr['bl_shipped_on_board'] else 'No'}**")
        st.write(f"- Ship date: **{pr['bl_ship_date']}**")
        st.write(f"- POL: **{pr['bl_port_load']}**")
        st.write(f"- POD: **{pr['bl_port_discharge']}**")
        st.write(f"- Originals: **{pr['bl_originals']}**")

        st.markdown("**Insurance**")
        st.write(f"- Presented: **{'Yes' if pr['insurance_present'] else 'No'}**")
        st.write(f"- Coverage: **{pr['insurance_coverage_pct']}%**")
        st.write(f"- Currency: **{pr['insurance_currency']}**")

        st.markdown("**Other docs**")
        st.write(f"- C/O presented: **{'Yes' if pr['co_present'] else 'No'}**")
        st.write(f"- Packing List presented: **{'Yes' if pr['packing_list_present'] else 'No'}**")
        st.write(f"- Presented within: **{pr['documents_presented_within_days']} days**")

    st.markdown("---")

    # 5) SV chọn sai biệt
    options = [f"{code} — {desc}" for code, desc in pool]
    option_codes = [code for code, _ in pool]

    picked = st.multiselect(
        "✅ Chọn các sai biệt (discrepancies) bạn phát hiện:",
        options=options,
        default=[],
        key=f"t02_pick_{attempt_no}",
    )

    picked_codes = []
    for x in picked:
        # lấy code phía trước "—"
        c = x.split("—")[0].strip()
        if c in option_codes:
            picked_codes.append(c)
    picked_codes = sorted(set(picked_codes))

    # 6) Nộp bài
    if st.button("📩 NỘP BÀI (Submit)", type="primary", use_container_width=True, key=f"btn_submit_t02_{attempt_no}"):
        correct = sorted(answers["correct_codes"])
        is_ok = (picked_codes == correct)
        score = 10 if is_ok else 0

        payload = {
            "mssv": mssv,
            "hoten": get_student_name(mssv) or None,
            "lop": None,
            "room": "TRADE",
            "exercise_code": ex_code,
            "attempt_no": attempt_no,
            "seed": int(seed),
            "params_json": params,
            "answer_json": answers,
            "is_correct": bool(is_ok),
            "score": int(score),
            "duration_sec": None,
            "note": f"T02 attempt {attempt_no}",
        }

        ok = insert_attempt(payload)
        if not ok:
            st.error("⚠️ Không ghi được bài nộp (lỗi hệ thống/DB). Vui lòng thử lại sau 10–20 giây hoặc báo GV.")
            return

        if is_ok:
            st.success(f"✅ CHÍNH XÁC! Bạn được **+{score} điểm**.")
        else:
            st.error("❌ CHƯA ĐÚNG. Bạn được **0 điểm**.")
            st.info(f"📌 Đáp án chuẩn: **{', '.join(correct) if correct else '(Không có)'}**")

        # ✅ Lưu kết quả để sau rerun vẫn hiện
        st.session_state[f"LAST_GRADE_{ex_code}_{attempt_no}"] = {
            "is_ok": bool(is_ok),
            "score": int(score),
            "attempt_no": int(attempt_no),
        }
        st.rerun()

# BÀI I01: THẨM ĐỊNH DỰ ÁN FDI - NPV & QUYẾT ĐỊNH
def render_exercise_I01(mssv: str, room_key: str, ex_code: str, attempt_no: int):
    room_key = str(room_key).strip().upper()
    ex_code  = str(ex_code).strip().upper()
    if ex_code != "I01":
        return

    # 1) Nếu attempt đã nộp -> khóa và hiện lại đề + đáp án
    existing = fetch_attempt(mssv, ex_code, attempt_no)
    # ✅ Hiện kết quả chấm nếu attempt đã nộp
    if existing:
        score = int(existing.get("score", 0) or 0)
        is_correct = bool(existing.get("is_correct", False))

        st.markdown("### 📌 Kết quả lần nộp này")
        (st.success if is_correct else st.error)(
            f"{'✅ Đúng' if is_correct else '❌ Chưa đúng'} - **{score} điểm** (Lần {attempt_no}/3)"
        )

        st.warning(f"🔒 Bạn đã nộp **{ex_code} – Lần {attempt_no}** rồi.")
        params = existing.get("params_json", {}) or {}
        ans = existing.get("answer_json", {}) or {}

        st.markdown("**Đề bài bạn đã nhận (từ DB):**")
        st.write(f"- I0: **{params.get('I0',0):,} USD**")
        st.write(f"- CF1: **{params.get('cf1',0):,} USD**, CF2: **{params.get('cf2',0):,} USD**, CF3: **{params.get('cf3',0):,} USD**")
        r = float(params.get("r", 0))
        st.write(f"- Discount rate r: **{r*100:.0f}%/năm**")

        st.markdown("**Đáp án chuẩn (để đối chiếu học tập):**")
        dec = ans.get("decision","-")
        dec_vn = "Chấp nhận" if dec == "ACCEPT" else "Từ chối"
        st.success(f"NPV = **{ans.get('npv','-'):,.0f} USD** | Quyết định: **{dec_vn}**")
        return

    # 2) Sinh đề theo seed ổn định
    seed = stable_seed(mssv, ex_code, attempt_no)
    params, answers = gen_case_I01(seed)

    # 3) ghi thời điểm bắt đầu (để sau này bạn muốn tính time thì có sẵn)
    start_key = f"START_{mssv}_{ex_code}_{attempt_no}"
    if start_key not in st.session_state:
        st.session_state[start_key] = time.time()

    # 4) UI đề bài
    st.markdown(
        """
<div class="role-card">
  <div class="role-title">📝 Bài I01 — Thẩm định dự án FDI: NPV & Quyết định</div>
  <div class="mission-text">
    Tính <b>NPV (USD)</b> của dự án 3 năm và đưa ra quyết định <b>Chấp nhận/Từ chối</b>.
    (Làm tròn NPV đến <b>USD</b>)
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### 📌 Thông tin dự án")
        st.write(f"I0 (t=0): **{params['I0']:,} USD**")
        st.write(f"CF1 (t=1): **{params['cf1']:,} USD**")
        st.write(f"CF2 (t=2): **{params['cf2']:,} USD**")
        st.write(f"CF3 (t=3): **{params['cf3']:,} USD**")
    with c2:
        st.markdown("##### 📉 Chiết khấu")
        st.write(f"r (USD discount rate): **{params['r']*100:.0f}%/năm**")
        st.caption("Công thức: NPV = -I0 + Σ CFt/(1+r)^t")

    st.markdown("---")

    # 5) SV nhập đáp án
    st.caption("✍️ Nhập kết quả")
    a1, a2 = st.columns([1.3, 1.0])
    with a1:
        in_npv = st.number_input(
            "NPV (USD, làm tròn)",
            min_value=-10_000_000.0,
            step=1.0,
            format="%.0f",
            key=f"i01_npv_{attempt_no}",
        )
    with a2:
        in_decision = st.radio(
            "Quyết định",
            ["Chấp nhận", "Từ chối"],
            horizontal=False,
            key=f"i01_dec_{attempt_no}",
        )

    # 6) Chấm điểm + ghi DB
    TOL = 5  # sai số ±5 USD
    if st.button("📩 NỘP BÀI (Submit)", type="primary", use_container_width=True, key=f"btn_submit_i01_{attempt_no}"):
        npv_ok = abs(int(in_npv) - int(answers["npv"])) <= TOL

        dec_code = "ACCEPT" if in_decision == "Chấp nhận" else "REJECT"
        dec_ok = (dec_code == answers["decision"])

        is_ok = bool(npv_ok and dec_ok)
        score = 10 if is_ok else 0

        payload = {
            "mssv": mssv,
            "hoten": get_student_name(mssv) or None,
            "lop": None,
            "room": "INVEST",
            "exercise_code": ex_code,
            "attempt_no": attempt_no,
            "seed": int(seed),
            "params_json": params,
            "answer_json": answers,
            "is_correct": is_ok,
            "score": int(score),
            "duration_sec": int(time.time() - st.session_state[start_key]),
            "note": f"I01 attempt {attempt_no}",
        }

        ok = insert_attempt(payload)
        if not ok:
            st.error("⚠️ Không ghi được bài nộp (lỗi hệ thống/DB). Vui lòng thử lại sau 10–20 giây hoặc báo GV.")
            return

        # Feedback
        if is_ok:
            st.success("✅ CHÍNH XÁC! Bạn được **+10 điểm**.")
        else:
            st.error("❌ CHƯA ĐÚNG. Bạn được **0 điểm**.")
            dec_vn = "Chấp nhận" if answers["decision"] == "ACCEPT" else "Từ chối"
            st.info(f"📌 Đáp án chuẩn: NPV = **{answers['npv']:,.0f} USD** | Quyết định: **{dec_vn}**")

        # ✅ Lưu kết quả để sau rerun vẫn hiện
        st.session_state[f"LAST_GRADE_{ex_code}_{attempt_no}"] = {
            "is_ok": bool(is_ok),
            "score": int(score),
            "attempt_no": int(attempt_no),
        }
        st.rerun()

# I02
def render_exercise_I02(mssv: str, room_key: str, ex_code: str, attempt_no: int):
    room_key = str(room_key).strip().upper()
    ex_code  = str(ex_code).strip().upper()
    if ex_code != "I02":
        return

    # 1) Nếu attempt đã nộp -> khóa, hiện lại đề + đáp án
    existing = fetch_attempt(mssv, ex_code, attempt_no)
    # ✅ Hiện kết quả chấm nếu attempt đã nộp
    if existing:
        score = int(existing.get("score", 0) or 0)
        is_correct = bool(existing.get("is_correct", False))

        st.markdown("### 📌 Kết quả lần nộp này")
        (st.success if is_correct else st.error)(
            f"{'✅ Đúng' if is_correct else '❌ Chưa đúng'} - **{score} điểm** (Lần {attempt_no}/3)"
        )

        st.warning(f"🔒 Bạn đã nộp **{ex_code} – Lần {attempt_no}** rồi.")
        params = existing.get("params_json", {}) or {}
        ans = existing.get("answer_json", {}) or {}

        st.markdown("**Đề bài bạn đã nhận (từ DB):**")
        st.write(f"- I0: **{params.get('I0',0):,} USD**")
        st.write(f"- CF1: **{params.get('cf1',0):,}**, CF2: **{params.get('cf2',0):,}**, CF3: **{params.get('cf3',0):,}**, CF4: **{params.get('cf4',0):,}** (USD)")
        wacc = float(params.get("wacc", 0))
        st.write(f"- WACC: **{wacc*100:.0f}%/năm**")

        dec = ans.get("decision","-")
        dec_vn = "Chấp nhận" if dec == "ACCEPT" else "Từ chối"
        st.success(f"IRR = **{ans.get('irr_pct','-')}%** | Quyết định: **{dec_vn}**")
        return

    # 2) Sinh đề theo seed ổn định
    seed = stable_seed(mssv, ex_code, attempt_no)
    params, answers = gen_case_I02(seed)

    start_key = f"START_{mssv}_{ex_code}_{attempt_no}"
    if start_key not in st.session_state:
        st.session_state[start_key] = time.time()

    # 3) UI đề bài
    st.markdown(
        """
<div class="role-card">
  <div class="role-title">📝 Bài I02 — IRR vs WACC (Tính IRR & Quyết định)</div>
  <div class="mission-text">
    Tính <b>IRR</b> của dự án và so sánh với <b>WACC</b> để quyết định <b>Chấp nhận/Từ chối</b>.
    (Nhập IRR theo <b>%</b>, làm tròn <b>2 chữ số</b>)
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### 📌 Dòng tiền dự án (USD)")
        st.write(f"I0 (t=0): **-{params['I0']:,}**")
        st.write(f"CF1 (t=1): **{params['cf1']:,}**")
        st.write(f"CF2 (t=2): **{params['cf2']:,}**")
        st.write(f"CF3 (t=3): **{params['cf3']:,}**")
        st.write(f"CF4 (t=4): **{params['cf4']:,}**")
    with c2:
        st.markdown("##### 🧮 WACC")
        st.write(f"WACC: **{params['wacc']*100:.0f}%/năm**")
        st.caption("Quy tắc: Accept nếu IRR > WACC")

    st.markdown("---")

    # 4) SV nhập IRR và chọn quyết định
    a1, a2 = st.columns([1.3, 1.0])
    with a1:
        in_irr = st.number_input(
            "IRR (%)",
            min_value=-90.0,
            max_value=200.0,
            value=0.0,
            step=0.01,
            format="%.2f",
            key=f"i02_irr_{attempt_no}",
        )
    with a2:
        in_decision = st.radio(
            "Quyết định",
            ["Chấp nhận", "Từ chối"],
            key=f"i02_dec_{attempt_no}",
        )

    # 5) Nộp bài -> chấm
    TOL_PCT = 0.10  # cho phép sai số ±0.10% do làm tròn/nhập
    if st.button("📩 NỘP BÀI (Submit)", type="primary", use_container_width=True, key=f"btn_submit_i02_{attempt_no}"):

        irr_ok = abs(float(in_irr) - float(answers["irr_pct"])) <= TOL_PCT

        dec_code = "ACCEPT" if in_decision == "Chấp nhận" else "REJECT"
        dec_ok = (dec_code == answers["decision"])

        is_ok = bool(irr_ok and dec_ok)
        score = 10 if is_ok else 0

        payload = {
            "mssv": mssv,
            "hoten": get_student_name(mssv) or None,
            "lop": None,
            "room": "INVEST",
            "exercise_code": ex_code,
            "attempt_no": attempt_no,
            "seed": int(seed),
            "params_json": params,
            "answer_json": answers,
            "is_correct": is_ok,
            "score": int(score),
            "duration_sec": int(time.time() - st.session_state[start_key]),
            "note": f"I02 attempt {attempt_no}",
        }

        ok = insert_attempt(payload)
        if not ok:
            st.error("⚠️ Không ghi được bài nộp (lỗi hệ thống/DB). Vui lòng thử lại sau 10–20 giây hoặc báo GV.")
            return

        if is_ok:
            st.success("✅ CHÍNH XÁC! Bạn được **+10 điểm**.")
        else:
            st.error("❌ CHƯA ĐÚNG. Bạn được **0 điểm**.")
            dec_vn = "Chấp nhận" if answers["decision"] == "ACCEPT" else "Từ chối"
            st.info(f"📌 Đáp án chuẩn: IRR = **{answers['irr_pct']}%** | Quyết định: **{dec_vn}**")

        # ✅ Lưu kết quả để sau rerun vẫn hiện
        st.session_state[f"LAST_GRADE_{ex_code}_{attempt_no}"] = {
            "is_ok": bool(is_ok),
            "score": int(score),
            "attempt_no": int(attempt_no),
        }
        st.rerun()

# M01
def render_exercise_M01(mssv: str, room_key: str, ex_code: str, attempt_no: int):
    room_key = str(room_key).strip().upper()
    ex_code = str(ex_code).strip().upper()
    attempt_no = int(attempt_no)

    if ex_code != "M01":
        return  # an toàn

    # 1) Nếu attempt đã nộp -> khóa, hiển thị lại đề + đáp án
    existing = fetch_attempt(mssv, ex_code, attempt_no)
    # ✅ Hiện kết quả chấm nếu attempt đã nộp
    if existing:
        score = int(existing.get("score", 0) or 0)
        is_correct = bool(existing.get("is_correct", False))

        st.markdown("### 📌 Kết quả lần nộp này")
        (st.success if is_correct else st.error)(
            f"{'✅ Đúng' if is_correct else '❌ Chưa đúng'} - **{score} điểm** (Lần {attempt_no}/3)"
        )

        st.warning(f"🔒 Bạn đã nộp **{ex_code} – Lần {attempt_no}** rồi.")
        params = existing.get("params_json", {}) or {}
        ans = existing.get("answer_json", {}) or {}

        st.markdown("**Đề bài bạn đã nhận (từ DB):**")
        st.write(f"- Nợ nước ngoài: **{params.get('debt_usd_bn','-')} tỷ USD**")
        st.write(f"- Tỷ giá gốc: **{params.get('base_rate','-'):,.0f} VND/USD**")
        st.write(f"- Mất giá: **{params.get('shock_pct','-')}%**")

        st.markdown("**Đáp án chuẩn (đối chiếu học tập):**")
        st.success(
            f"Tỷ giá mới: **{int(ans.get('new_rate',0)):,.0f} VND/USD**  |  "
            f"Gánh nặng tăng thêm: **{ans.get('increase_tril','-')} nghìn tỷ VND**"
        )
        return

    # 2) Sinh đề theo seed ổn định
    seed = stable_seed(mssv, ex_code, attempt_no)
    params, answers = gen_case_M01(seed)

    # 3) Ghi thời điểm bắt đầu (nếu sau này bạn muốn tính thời gian)
    start_key = f"START_{mssv}_{ex_code}_{attempt_no}"
    if start_key not in st.session_state:
        st.session_state[start_key] = time.time()

    # 4) UI đề bài
    st.markdown(
        """
<div class="role-card">
  <div class="role-title">📝 Bài M01 — Cú sốc tỷ giá lên Nợ công</div>
  <div class="mission-text">
    Bạn là <b>Macro Strategist</b>. Tính <b>tỷ giá mới</b> sau cú sốc và <b>gánh nặng nợ tăng thêm</b> do VND mất giá.
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Nợ nước ngoài", f"{params['debt_usd_bn']} tỷ USD")
    with c2:
        st.metric("Tỷ giá gốc", f"{params['base_rate']:,.0f} VND/USD")
    with c3:
        st.metric("Mức mất giá", f"{params['shock_pct']}%")

    st.markdown("---")
    st.caption("✍️ Nhập đáp án:")
    a1, a2 = st.columns(2)
    with a1:
        in_new_rate = st.number_input(
            "Tỷ giá mới (VND/USD)",
            min_value=0.0, step=1.0, format="%.0f",
            key=f"m01_newrate_{attempt_no}"
        )
    with a2:
        in_increase = st.number_input(
            "Gánh nặng tăng thêm (nghìn tỷ VND)",
            min_value=0.0, step=0.1, format="%.1f",
            key=f"m01_increase_{attempt_no}"
        )

    # 5) Chấm điểm
    # - new_rate: cho lệch ±5 VND
    # - increase_tril: cho lệch ±0.2 nghìn tỷ (200 tỷ VND) do làm tròn
    TOL_RATE = 5
    TOL_TRIL = 0.2

    if st.button("📩 NỘP BÀI (Submit)", type="primary", use_container_width=True, key=f"btn_submit_m01_{attempt_no}"):
        ok_rate = abs(int(in_new_rate) - int(answers["new_rate"])) <= TOL_RATE
        ok_inc = abs(float(in_increase) - float(answers["increase_tril"])) <= TOL_TRIL

        is_ok = bool(ok_rate and ok_inc)

        # điểm: 10 nếu đúng hoàn toàn, 4 nếu đúng 1 phần (đỡ “gắt”), 0 nếu sai hết
        if is_ok:
            score = 10
        elif ok_rate or ok_inc:
            score = 4
        else:
            score = 0

        duration_sec = int(time.time() - st.session_state.get(start_key, time.time()))

        payload = {
            "mssv": mssv,
            "hoten": None,      # nếu bạn đã map họ tên từ Excel thì fill ở đây
            "lop": None,
            "room": room_key,   # "MACRO"
            "exercise_code": ex_code,  # "M01"
            "attempt_no": attempt_no,
            "seed": int(int(seed) % 2_000_000_000),
            "params_json": params,
            "answer_json": answers,
            "is_correct": bool(is_ok),
            "score": int(score),
            "duration_sec": int(duration_sec),
            "note": f"M01 attempt {attempt_no}",
        }

        ok = insert_attempt(payload)
        if not ok:
            st.error("⚠️ Không ghi được bài nộp (lỗi hệ thống/DB). Vui lòng thử lại sau 10–20 giây hoặc báo GV.")
            return

        if is_ok:
            st.success(f"✅ CHÍNH XÁC! Bạn được **+{score} điểm**.")
        elif score > 0:
            st.warning(f"🟡 GẦN ĐÚNG! Bạn được **+{score} điểm** (đúng 1 phần).")
        else:
            st.error("❌ CHƯA ĐÚNG. Bạn được **0 điểm**.")

        st.info(
            f"📌 Đáp án: Tỷ giá mới **{answers['new_rate']:,.0f}** | "
            f"Tăng thêm **{answers['increase_tril']} nghìn tỷ VND**"
        )
        # ✅ Lưu kết quả để sau rerun vẫn hiện
        st.session_state[f"LAST_GRADE_{ex_code}_{attempt_no}"] = {
            "is_ok": bool(is_ok),
            "score": int(score),
            "attempt_no": int(attempt_no),
        }
        st.rerun()

# M02
def render_exercise_M02(mssv: str, room_key: str, ex_code: str, attempt_no: int):
    room_key = str(room_key).strip().upper()
    ex_code = str(ex_code).strip().upper()
    attempt_no = int(attempt_no)

    if ex_code != "M02":
        return  # an toàn

    # 1) Nếu attempt đã nộp rồi -> khóa, hiển thị lại đề + đáp án
    existing = fetch_attempt(mssv, ex_code, attempt_no)
    # ✅ Hiện kết quả chấm nếu attempt đã nộp
    if existing:
        score = int(existing.get("score", 0) or 0)
        is_correct = bool(existing.get("is_correct", False))

        st.markdown("### 📌 Kết quả lần nộp này")
        (st.success if is_correct else st.error)(
            f"{'✅ Đúng' if is_correct else '❌ Chưa đúng'} - **{score} điểm** (Lần {attempt_no}/3)"
        )

        st.warning(f"🔒 Bạn đã nộp **{ex_code} – Lần {attempt_no}** rồi.")
        params = existing.get("params_json", {}) or {}
        ans = existing.get("answer_json", {}) or {}

        st.markdown("**Đề bài bạn đã nhận (từ DB):**")
        st.write(f"- Vay: **{params.get('notional_mjpy','-')} triệu JPY**")
        st.write(f"- Spot JPY/VND (t0): **{float(params.get('s0',0)):,.1f} VND/JPY**")
        st.write(f"- iVND: **{float(params.get('i_vnd',0))*100:.1f}%/năm**, iJPY: **{float(params.get('i_jpy',0))*100:.2f}%/năm**")
        st.write(f"- Kỳ hạn: **{params.get('horizon_days','-')} ngày**")
        st.write(f"- Shock: **JPY mạnh lên {params.get('shock_pct','-')}%**")
        st.write(f"- Equity: **{int(params.get('equity_vnd',0)):,.0f} VND**, Margin trigger: **{float(params.get('margin_trigger',0))*100:.0f}%**")

        st.markdown("**Đáp án chuẩn (đối chiếu học tập):**")
        mc = "YES" if bool(ans.get("margin_call", False)) else "NO"
        st.success(
            f"VND mở carry: **{int(ans.get('vnd_open',0)):,.0f}** | "
            f"P/L: **{int(ans.get('pl_vnd',0)):,.0f} VND** | "
            f"Margin call: **{mc}**"
        )
        return

    # 2) Sinh đề theo seed ổn định
    seed = stable_seed(mssv, ex_code, attempt_no)
    params, answers = gen_case_M02(seed)

    # 3) Start time (nếu sau này cần)
    start_key = f"START_{mssv}_{ex_code}_{attempt_no}"
    if start_key not in st.session_state:
        st.session_state[start_key] = time.time()

    # 4) UI đề bài
    st.markdown(
        """
<div class="role-card">
  <div class="role-title">📝 Bài M02 — Carry Trade Unwind (JPY funding → VND asset)</div>
  <div class="mission-text">
    Bạn vay JPY (lãi suất thấp) đổi sang VND để đầu tư (lãi suất cao). Khi thị trường risk-off, JPY mạnh lên → unwind.
    Hãy tính: <b>(1) VND nhận khi mở carry</b>, <b>(2) P/L (VND)</b>, <b>(3) Có margin call không</b>.
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Vay (Funding)", f"{params['notional_mjpy']} triệu JPY")
        st.metric("Spot t0 (JPY/VND)", f"{params['s0']:.1f} VND/JPY")
    with c2:
        st.metric("iVND", f"{params['i_vnd']*100:.1f}%/năm")
        st.metric("iJPY", f"{params['i_jpy']*100:.2f}%/năm")
    with c3:
        st.metric("Kỳ hạn", f"{params['horizon_days']} ngày")
        st.metric("Shock (JPY mạnh lên)", f"{params['shock_pct']:.0f}%")

    st.markdown("---")
    st.caption("Thông tin margin:")
    m1, m2 = st.columns(2)
    with m1:
        st.write(f"Equity ban đầu: **{params['equity_vnd']:,.0f} VND**")
    with m2:
        st.write(f"Margin trigger: **{params['margin_trigger']*100:.0f}% (lỗ/equity)**")

    st.markdown("---")
    st.caption("✍️ Nhập đáp án (làm tròn **1,000 VND** để nhập nhanh):")

    a1, a2, a3 = st.columns([1.3, 1.3, 1.0])
    with a1:
        in_vnd_open = st.number_input(
            "1) VND khi mở carry (JPY→VND)",
            min_value=0.0, step=1000.0, format="%.0f",
            key=f"m02_vndopen_{attempt_no}"
        )
    with a2:
        in_pl_vnd = st.number_input(
            "2) P/L (VND) sau unwind",
            min_value=-1e15, max_value=1e15, step=1000.0, format="%.0f",
            key=f"m02_plvnd_{attempt_no}"
        )
    with a3:
        in_mc = st.selectbox(
            "3) Margin call?",
            options=["NO", "YES"],
            index=0,
            key=f"m02_mc_{attempt_no}",
        )

    # 5) Chấm theo “mỗi ý 1 phần điểm”
    # đề xuất trọng số: open=3, pl=5, margin=2 => tổng 10
    W_OPEN, W_PL, W_MC = 3, 5, 2

    # tolerance
    TOL_OPEN = 2000  # ±2,000 VND
    # P/L: cho lệch 0.5% hoặc tối thiểu 200,000 VND
    pl_true = int(answers["pl_vnd"])
    TOL_PL = max(200_000, int(round(abs(pl_true) * 0.005)))

    if st.button("📩 NỘP BÀI (Submit)", type="primary", use_container_width=True, key=f"btn_submit_m02_{attempt_no}"):
        ok_open = abs(int(in_vnd_open) - int(answers["vnd_open"])) <= TOL_OPEN
        ok_pl = abs(int(in_pl_vnd) - int(answers["pl_vnd"])) <= TOL_PL
        ok_mc = (str(in_mc).strip().upper() == ("YES" if answers["margin_call"] else "NO"))
        is_correct = bool(ok_open and ok_pl and ok_mc)

        score = 0
        score += W_OPEN if ok_open else 0
        score += W_PL if ok_pl else 0
        score += W_MC if ok_mc else 0
       
        duration_sec = int(time.time() - st.session_state.get(start_key, time.time()))

        payload = {
            "mssv": mssv,
            "hoten": None,
            "lop": None,
            "room": room_key,           # "MACRO"
            "exercise_code": ex_code,   # "M02"
            "attempt_no": attempt_no,
            "seed": int(int(seed) % 2_000_000_000),
            "params_json": params,
            "answer_json": {
                "vnd_open": int(answers["vnd_open"]),
                "pl_vnd": int(answers["pl_vnd"]),
                "margin_call": bool(answers["margin_call"]),
            },
            "is_correct": is_correct,
            "score": int(score),
            "duration_sec": int(duration_sec),
            "note": f"M02 attempt {attempt_no}",
        }

        ok = insert_attempt(payload)
        if not ok:
            st.error("⚠️ Không ghi được bài nộp (lỗi hệ thống/DB). Vui lòng thử lại sau 10–20 giây hoặc báo GV.")
            return
        
        if is_correct:
            st.success(f"✅ CHÍNH XÁC! Bạn được **+{score} điểm**.")
        elif score > 0:
            st.warning(f"🟡 GẦN ĐÚNG! Bạn được **+{score} điểm** (đúng 1 phần).")
        else:
            st.error("❌ CHƯA ĐÚNG. Bạn được **0 điểm**.")

        # Feedback theo từng ý
        st.markdown("### ✅ Kết quả chấm")
        st.write(f"- (1) VND mở carry: {'✅' if ok_open else '❌'}  (+{W_OPEN if ok_open else 0})")
        st.write(f"- (2) P/L (VND): {'✅' if ok_pl else '❌'}  (+{W_PL if ok_pl else 0})")
        st.write(f"- (3) Margin call: {'✅' if ok_mc else '❌'}  (+{W_MC if ok_mc else 0})")
        st.success(f"🎯 Tổng điểm lần này: **{score}/10**")

        mc_ans = "YES" if answers["margin_call"] else "NO"
        st.info(
            f"📌 Đáp án: VND mở carry **{answers['vnd_open']:,.0f}** | "
            f"P/L **{answers['pl_vnd']:,.0f} VND** | "
            f"Margin call **{mc_ans}**"
        )

        # ✅ Lưu kết quả để sau rerun vẫn hiện
        st.session_state[f"LAST_GRADE_{ex_code}_{attempt_no}"] = {
            "is_correct": bool(is_correct),
            "score": int(score),
            "attempt_no": int(attempt_no),
        }
        st.rerun()


#====== KẾT THÚC ĐỊNH NGHĨA HÀM RENDER CHO CÁC BÀI TẬP ======#

# =========================================================
# EXERCISE ROUTER MAP: (ROOM, EX_CODE) -> render_function
# Mỗi render_function phải có chữ ký: fn(mssv: str, ex_code: str, attempt_no: int)
# =========================================================

EX_RENDERERS = {
    ("DEALING", "D01"): render_exercise_D01,
    ("DEALING", "D02"): render_exercise_D02,    
    ("RISK", "R01"): render_exercise_R01,
    ("RISK", "R02"): render_exercise_R02,
    ("TRADE", "T01"): render_exercise_T01,
    ("TRADE", "T02"): render_exercise_T02,
    ("INVEST", "I01"): render_exercise_I01,
    ("INVEST", "I02"): render_exercise_I02,
    ("MACRO", "M01"): render_exercise_M01,
    ("MACRO", "M02"): render_exercise_M02,
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

/* =============================
   Sidebar NAV buttons (mobile wrap fix)
   ============================= */
section[data-testid="stSidebar"] div[data-testid="stButton"] > button{
  white-space: normal !important;      /* cho phép xuống dòng */
  text-align: center !important;       /* canh giữa */
  line-height: 1.15 !important;        /* đẹp khi 2 dòng */
  padding: 12px 12px !important;
  min-height: 56px !important;         /* tránh bị rớt lẻ */
}

/* Mobile nhỏ: tăng min-height + giảm font chút */
@media (max-width: 430px){
  section[data-testid="stSidebar"] div[data-testid="stButton"] > button{
    font-size: 16px !important;
    min-height: 68px !important;       /* đủ chỗ cho 2 dòng */
    padding: 12px 10px !important;
  }
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
    """Router cấp bài tập: đọc lựa chọn từ session_state và render đúng bài."""
    mssv = str(st.session_state.get("LAB_MSSV", "")).strip().upper()
    room_key = str(st.session_state.get("ACTIVE_ROOM", "DEALING")).strip().upper()
    ex_code = str(st.session_state.get("ACTIVE_EX_CODE", "D01")).strip().upper()
    attempt_no = int(st.session_state.get("ACTIVE_ATTEMPT", 1))

    st.markdown("### 🧩 Khu vực làm bài")

    # Guard: chưa login
    if not mssv:
        st.warning("Bạn chưa đăng nhập MSSV/PIN.")
        return

    fn = EX_RENDERERS.get((room_key, ex_code))
    if fn is None:
        st.info(f"👉 Bài **{ex_code}** của phòng **{room_key}** chưa được triển khai.")
        return

    # gọi renderer
    fn(mssv, room_key, ex_code, attempt_no)


# ==============================================================================
# BADGES: Chuyên cần 3/3 theo từng mã bài
# ==============================================================================

BADGE_CATALOG = {
    "DEALING": {
        "title": "💱 Sàn Kinh doanh Ngoại hối",
        "items": [
            {"code": "D01", "icon": "🧮", "name": "Niêm yết Tỷ giá Chéo"},
            {"code": "D02", "icon": "🔺", "name": "Săn Arbitrage Tam giác"},
        ],
    },
    "RISK": {
        "title": "🛡️ Phòng Quản trị Rủi ro",
        "items": [
            {"code": "R01", "icon": "🛡️", "name": "Phòng vệ Forward"},
            {"code": "R02", "icon": "🎯", "name": "Chọn Hedge Tối ưu"},
        ],
    },
    "TRADE": {
        "title": "🚢 Phòng Thanh toán Quốc tế",
        "items": [
            {"code": "T01", "icon": "💰", "name": "Tối ưu Chi phí Thanh toán"},
            {"code": "T02", "icon": "🧾", "name": "Soi Sai Biệt Chứng từ"},
        ],
    },
    "INVEST": {
        "title": "🏭 Phòng Đầu tư Quốc tế",
        "items": [
            {"code": "I01", "icon": "📈", "name": "Thẩm định NPV"},
            {"code": "I02", "icon": "⚖️", "name": "IRR vs WACC"},
        ],
    },
    "MACRO": {
        "title": "📉 Ban Chiến lược Vĩ mô",
        "items": [
            {"code": "M01", "icon": "🌍", "name": "Cú sốc Tỷ giá & Nợ công"},
            {"code": "M02", "icon": "💸", "name": "Carry Trade Unwind"},
        ],
    },
}

BADGE_ORDER = ["DEALING", "RISK", "TRADE", "INVEST", "MACRO"]


def _badge_progress_map(df_attempts: "pd.DataFrame") -> dict:
    """
    Trả về dict: {exercise_code: attempts_done_distinct}
    attempts_done_distinct = số attempt_no khác nhau đã nộp (tối đa 3).
    """
    if df_attempts is None or df_attempts.empty:
        return {}

    if "exercise_code" not in df_attempts.columns or "attempt_no" not in df_attempts.columns:
        return {}

    tmp = df_attempts.copy()
    tmp["exercise_code"] = tmp["exercise_code"].astype(str).str.strip().str.upper()
    tmp["attempt_no"] = pd.to_numeric(tmp["attempt_no"], errors="coerce").fillna(0).astype(int)

    # đếm số attempt khác nhau theo mã bài
    g = tmp.groupby("exercise_code")["attempt_no"].nunique()
    # cap tối đa 3
    return {k: int(min(v, 3)) for k, v in g.to_dict().items()}


def render_my_badges(df: "pd.DataFrame"):
    """
    - Progress Journey (5 phòng)
    - Mỗi phòng 1 card 3D, bên trong 2 badge
    - Badge có progress bar (0-100%) theo số lần nộp (x/3)
    - Khi vừa đạt 3/3: chỉ GLOW đúng badge đó (không balloons, không toast)
    - Fix lỗi HTML bị render thành code: dùng textwrap.dedent để bỏ indent
    """
    import pandas as pd
    import streamlit as st
    from textwrap import dedent

    # =========================
    # 0) Catalog huy hiệu
    # =========================
    BADGE_ORDER = ["DEALING", "RISK", "TRADE", "INVEST", "MACRO"]

    BADGE_CATALOG = {
        "DEALING": {
            "title": "💱 Sàn Kinh doanh Ngoại hối",
            "items": [
                {"code": "D01", "name": "Niêm yết Tỷ giá Chéo", "icon": "🧮"},
                {"code": "D02", "name": "Săn Arbitrage Tam giác", "icon": "🚩"},
            ],
        },
        "RISK": {
            "title": "🛡️ Phòng Quản trị Rủi ro",
            "items": [
                {"code": "R01", "name": "Phòng vệ Forward", "icon": "🛡️"},
                {"code": "R02", "name": "Chọn Hedge Tối ưu", "icon": "🎯"},
            ],
        },
        "TRADE": {
            "title": "🚢 Phòng Thanh toán Quốc tế",
            "items": [
                {"code": "T01", "name": "Tối ưu Chi phí Thanh toán", "icon": "💰"},
                {"code": "T02", "name": "Soi Sai Biệt Chứng từ", "icon": "🧾"},
            ],
        },
        "INVEST": {
            "title": "🏭 Phòng Đầu tư Quốc tế",
            "items": [
                {"code": "I01", "name": "Thẩm định NPV", "icon": "📈"},
                {"code": "I02", "name": "IRR vs WACC", "icon": "⚖️"},
            ],
        },
        "MACRO": {
            "title": "📉 Ban Chiến lược Vĩ mô",
            "items": [
                {"code": "M01", "name": "Cú sốc Tỷ giá & Nợ công", "icon": "🌍"},
                {"code": "M02", "name": "Carry Trade Unwind", "icon": "💸"},
            ],
        },
    }

    all_codes = [it["code"] for rk in BADGE_ORDER for it in BADGE_CATALOG[rk]["items"]]
    all_codes_u = [str(c).strip().upper() for c in all_codes]

    # =========================
    # 1) CSS UI (3D card + badge progress + journey + glow)
    # =========================
    st.markdown(
        dedent(
            """
            <style>
            /* ===== Journey ===== */
            .journey-wrap{
              margin: 10px 0 14px 0;
              padding: 12px 12px;
              border-radius: 16px;
              border: 1px solid rgba(148,163,184,.35);
              background: linear-gradient(180deg, rgba(255,255,255,.94), rgba(248,250,252,.94));
              box-shadow: 0 10px 22px rgba(15,23,42,.08);
            }
            .journey-title{
              font-weight: 900; color:#0f172a; margin-bottom: 10px;
              display:flex; justify-content:space-between; align-items:center; gap:10px;
            }
            .journey-bar{ display:flex; gap: 10px; align-items:center; }
            .j-step{
              flex:1; height: 36px; position: relative; overflow:hidden;
              border-radius: 14px;
              border: 1px solid rgba(148,163,184,.35);
              background: rgba(148,163,184,.18);
              box-shadow: inset 0 0 0 1px rgba(255,255,255,.25);
            }
            .j-fill{ height:100%; width:0%; background: rgba(59,130,246,.82); }
            .j-label{
              position:absolute; inset:0;
              display:flex; align-items:center; justify-content:center;
              font-weight: 900; font-size: 13px;
              color:#0f172a;
              text-shadow: 0 1px 0 rgba(255,255,255,.65);
            }
            .j-done .j-fill{ background: rgba(34,197,94,.85); }
            .j-done .j-label{ color:#052e16; }

            /* ===== Room Card 3D ===== */
            .room-card{
              border: 1px solid rgba(148,163,184,.35);
              border-radius: 18px;
              padding: 14px 14px 10px 14px;
              background: linear-gradient(180deg, rgba(255,255,255,.96), rgba(248,250,252,.96));
              box-shadow: 0 10px 22px rgba(15,23,42,.10);
              margin: 12px 0;
              transition: transform .15s ease, box-shadow .15s ease;
            }
            .room-card:hover{
              transform: translateY(-2px);
              box-shadow: 0 14px 30px rgba(15,23,42,.14);
            }
            .room-head{
              display:flex; justify-content:space-between; align-items:center;
              gap: 10px; padding: 8px 10px; border-radius: 14px;
              background: rgba(219,234,254,.85);
              border: 1px solid rgba(147,197,253,.55);
            }
            .room-title{
              font-weight: 900; font-size: 18px; color:#0b4aa2;
              display:flex; align-items:center; gap:10px;
            }
            .room-meta{
              font-weight: 900; font-size: 13px; color:#0f172a;
              opacity:.85;
            }

            /* ===== Badges ===== */
            .badges-grid{
              display:grid;
              grid-template-columns: 1fr 1fr;
              gap: 10px;
              padding: 12px 4px 6px 4px;
            }
            .badge-tile{
              border-radius: 16px;
              border: 1px solid rgba(148,163,184,.35);
              background: #fff;
              padding: 12px 12px;
              display:flex; gap: 10px; align-items:flex-start;
              box-shadow: 0 6px 14px rgba(15,23,42,.06);
              position: relative;
            }
            .badge-ico{ font-size: 22px; line-height: 1; }
            .badge-name{ font-weight: 900; color:#0f172a; }
            .badge-code{ font-size: 12px; color:#64748b; margin-left: 6px; }
            .badge-sub{ font-size: 12px; color:#64748b; margin-top: 2px; }

            .badge-progress{
              margin-top: 8px;
              height: 8px;
              width: 100%;
              border-radius: 999px;
              background: rgba(148,163,184,.25);
              overflow:hidden;
            }
            .badge-progress > div{
              height:100%;
              width: 0%;
              border-radius: 999px;
              background: rgba(59,130,246,.85);
            }

            /* Locked vs Unlocked */
            .locked{ opacity:.50; filter: grayscale(1); }
            .unlocked{
              opacity:1; filter:none;
              box-shadow: 0 8px 18px rgba(34,197,94,.12);
            }
            .unlocked .badge-progress > div{ background: rgba(34,197,94,.85); }

            /* Glow (run once) */
            @keyframes glowPulse {
              0%   { box-shadow: 0 0 0 rgba(34,197,94,.0); transform: translateY(0); }
              30%  { box-shadow: 0 0 24px rgba(34,197,94,.35); transform: translateY(-1px); }
              100% { box-shadow: 0 0 0 rgba(34,197,94,.0); transform: translateY(0); }
            }
            .glow-once{
              animation: glowPulse 1.2s ease-out 1;
            }

            /* Mobile: 1 column badges */
            @media (max-width: 768px){
              .badges-grid{ grid-template-columns: 1fr; }
              .room-title{ font-size: 16px; }
              .j-label{ font-size: 12px; }
            }
            </style>
            """
        ),
        unsafe_allow_html=True,
    )

    # =========================
    # 2) Progress x/3 cho từng mã bài
    # =========================
    prog = {c: 0 for c in all_codes_u}

    if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
        dfx = df.copy()
        if "exercise_code" in dfx.columns:
            dfx["exercise_code"] = dfx["exercise_code"].astype(str).str.strip().str.upper()
        else:
            dfx["exercise_code"] = ""

        if "attempt_no" not in dfx.columns:
            dfx["attempt_no"] = 0

        g = dfx.groupby("exercise_code")["attempt_no"].nunique()
        for k, v in g.to_dict().items():
            ku = str(k).strip().upper()
            if ku in prog:
                prog[ku] = int(min(int(v), 3))

    # =========================
    # 3) Glow per badge khi vừa đạt 3/3 (session flag theo MSSV+code)
    # =========================
    mssv = str(st.session_state.get("LAB_MSSV", "")).strip().upper()
    cache_key = f"BADGE_PROGRESS_CACHE_{mssv}"
    prev_prog = st.session_state.get(cache_key, {}) or {}

    glow_flags = {}
    for code in all_codes_u:
        prev = int(prev_prog.get(code, 0))
        now = int(prog.get(code, 0))
        if prev < 3 and now >= 3:
            glow_flags[code] = True
            st.session_state[f"GLOW_{mssv}_{code}"] = True

    # cập nhật cache progress (để lần sau biết “vừa đạt”)
    st.session_state[cache_key] = dict(prog)

    # =========================
    # 4) Progress Journey (5 phòng)  ✅ FIX: không bị in HTML như code nữa
    # =========================
    def _room_badge_done_count(room_key: str) -> tuple[int, int]:
        items = BADGE_CATALOG[room_key]["items"]
        done = sum(1 for it in items if int(prog.get(it["code"].strip().upper(), 0)) >= 3)
        return done, len(items)

    steps = []
    for rk in BADGE_ORDER:
        done, total = _room_badge_done_count(rk)
        ratio = 0 if total == 0 else int(done / total * 100)
        cls_done = "j-done" if done == total and total > 0 else ""
        # label gọn: bỏ emoji đầu
        label = BADGE_CATALOG[rk]["title"].split(" ", 1)[-1]
        steps.append(
            f'<div class="j-step {cls_done}">'
            f'  <div class="j-fill" style="width:{ratio}%"></div>'
            f'  <div class="j-label">{label} · {done}/{total}</div>'
            f"</div>"
        )

    journey_html = (
        '<div class="journey-wrap">'
        '  <div class="journey-title">'
        '    <div>🧭 Hành trình nghiệp vụ</div>'
        '    <div style="font-weight:900; color:#334155; font-size:13px;">Hoàn tất phòng = đạt đủ 2 huy hiệu</div>'
        "  </div>"
        f'  <div class="journey-bar">{"".join(steps)}</div>'
        "</div>"
    )
    st.markdown(journey_html, unsafe_allow_html=True)

    # =========================
    # 5) Render cards + badges
    # =========================
    def _badge_tile_html(icon, name, code_u, done):
        done = int(done)
        pct = int(min(max(done, 0), 3) / 3 * 100)
        is_done = done >= 3

        cls = "unlocked" if is_done else "locked"

        # glow: nếu badge vừa đạt 3/3 trong session -> thêm class glow-once
        glow = st.session_state.get(f"GLOW_{mssv}_{code_u}", False)
        glow_cls = " glow-once" if glow else ""

        return (
            f'<div class="badge-tile {cls}{glow_cls}">'
            f'  <div class="badge-ico">{icon}</div>'
            f'  <div style="flex:1; min-width:0;">'
            f'    <div style="display:flex; align-items:baseline; gap:8px; flex-wrap:wrap;">'
            f'      <span class="badge-name">{name}</span>'
            f'      <span class="badge-code">({code_u})</span>'
            f"    </div>"
            f'    <div class="badge-progress"><div style="width:{pct}%"></div></div>'
            f'    <div class="badge-sub">Tiến độ chuyên cần: {done}/3 lần</div>'
            f"  </div>"
            f"</div>"
        )

    def _room_card_html(room_title, tiles_html, solved_badges, total_badges):
        return (
            '<div class="room-card">'
            '  <div class="room-head">'
            f'    <div class="room-title">{room_title}</div>'
            f'    <div class="room-meta">🎖️ {solved_badges}/{total_badges} huy hiệu</div>'
            "  </div>"
            f'  <div class="badges-grid">{tiles_html}</div>'
            "</div>"
        )

    for rk in BADGE_ORDER:
        room = BADGE_CATALOG.get(rk)
        if not room:
            continue

        tiles = []
        solved = 0
        for it in room["items"]:
            code_u = it["code"].strip().upper()
            done = int(prog.get(code_u, 0))
            if done >= 3:
                solved += 1
            tiles.append(_badge_tile_html(it["icon"], it["name"], code_u, done))

        st.markdown(
            _room_card_html(room["title"], "".join(tiles), solved, total_badges=len(room["items"])),
            unsafe_allow_html=True,
        )

    st.caption("💡 Huy hiệu sáng lên khi bạn làm đủ **3/3** cho đúng mã bài. Progress bar giúp bạn biết còn thiếu bao nhiêu.")


# ===== KẾT THÚC BADGES HUY HIỆU CHO TỪNG MÃ BÀI ======

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
  "Nhiệm vụ: Hoàn thành các bài tập nghiệp vụ, tích lũy điểm số và cạnh tranh thứ hạng toàn lớp."
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
        else:
            df = pd.DataFrame(rows)

            # chuẩn hóa
            if "score" not in df.columns: df["score"] = 0
            if "attempt_no" not in df.columns: df["attempt_no"] = 0
            if "is_correct" not in df.columns: df["is_correct"] = False
            if "created_at" not in df.columns: df["created_at"] = pd.NaT
            if "exercise_code" not in df.columns: df["exercise_code"] = ""

            df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0).astype(int)
            df["attempt_no"] = pd.to_numeric(df["attempt_no"], errors="coerce").fillna(0).astype(int)
            df["is_correct"] = df["is_correct"].astype(bool)
           
            # Sau khi đã có df (lịch sử nộp bài của SV)
            render_my_badges(df)
            st.markdown("---")

            # Best-of-3 theo từng bài
            per_ex = (
                df.groupby("exercise_code", as_index=False)
                .agg(
                    best_score=("score", "max"),
                    best_correct=("is_correct", "max"),
                    attempts_done=("attempt_no", "nunique"),
                    last_submit=("created_at", "max"),
                )
                .sort_values(["best_score", "best_correct", "attempts_done", "last_submit"],
                            ascending=[False, False, False, False])
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
        
        st.caption("Xếp hạng dựa trên **tổng điểm best-of-3** của mỗi mã bài.")

        # 1) Ưu tiên view
        data = fetch_class_leaderboard_from_view(limit=300)

        # 2) Fallback nếu view chưa có / lỗi
        if data is None or len(data) == 0:
            st.info("ℹ️ Chưa đọc được VIEW `lab_leaderboard` → dùng chế độ tính tạm từ `lab_attempts`.")
            data = compute_class_leaderboard_fallback(limit=300)

        if not data:
            st.warning("Chưa có dữ liệu xếp hạng. Lớp chưa nộp bài nào.")
            return

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
            kw = st.text_input("🔎 Tìm theo MSSV / Họ tên", value="", key=f"lb_search_{mssv}")
        with c2:
            top_n = st.selectbox("Hiển thị Top", [20, 50, 100, 200], index=1, key=f"lb_top_n_{mssv}")

        show = df.copy()

        # nếu có nhập keyword thì lọc
        if kw.strip():
            k = kw.strip().lower()
            show = show[
                show["mssv"].astype(str).str.lower().str.contains(k)
                | show["hoten"].astype(str).str.lower().str.contains(k)
            ]

            # ✅ nếu lọc ra rỗng -> quay về hiển thị toàn lớp (để SV vẫn thấy BXH)
            if show.empty:
                st.warning("Không có kết quả theo bộ lọc hiện tại. Hiển thị lại toàn lớp.")
                show = df.copy()

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
            st.info("Bạn không có dữ liệu xếp hạng cho cá nhân vì chưa nộp bài tập.")

        # QUAY THƯỞNG NGẪU NHIÊN
        st.markdown("---")
        st.subheader("🎁 Quay thưởng ngẫu nhiên")

        cA, cB, cC = st.columns([1.2, 1.2, 2.0])
        with cA:
            draw_pool = st.number_input("Lấy từ Top", min_value=5, max_value=200, value=20, step=5, key="draw_pool")
        with cB:
            draw_k = st.number_input("Số bạn trúng", min_value=1, max_value=20, value=5, step=1, key="draw_k")

        # Pool: lấy từ show (đã lọc/search) hoặc df gốc?
        # Khuyến nghị: dùng df gốc để không bị ảnh hưởng bởi ô search
        pool_df = df.head(int(draw_pool)).copy()

        # Nếu bạn muốn chỉ quay trong những bạn "đồng hạng điểm cao nhất"
        # (ví dụ có 20 bạn cùng điểm cao nhất), bật chế độ này:
        same_top_score_only = st.checkbox("Chỉ quay trong nhóm đồng điểm cao nhất", value=False, key="draw_same_score")

        if same_top_score_only and not pool_df.empty:
            top_score = int(pool_df.iloc[0]["total_score"])
            pool_df = df[df["total_score"] == top_score].copy()

        # Chuẩn hoá tên hiển thị
        pool_df["hoten"] = pool_df["hoten"].fillna("").astype(str)
        pool_df["mssv"] = pool_df["mssv"].fillna("").astype(str)

        # Tạo list ứng viên
        candidates = []
        for _, r in pool_df.iterrows():
            name = r["hoten"].strip() if r["hoten"].strip() else "(Chưa có tên)"
            candidates.append({"hoten": name, "mssv": r["mssv"].strip(), "total_score": int(r["total_score"])})

        # Nút quay + reset
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🎲 QUAY NGAY", type="primary", use_container_width=True, key="btn_draw_now"):
                if len(candidates) < int(draw_k):
                    st.error(f"Không đủ ứng viên để chọn {draw_k} bạn. Hiện có {len(candidates)}.")
                else:
                    # Seed theo thời gian để mỗi lần quay khác nhau
                    random.seed()

                    winners = random.sample(candidates, k=int(draw_k))
                    st.session_state["DRAW_WINNERS"] = winners

        with col2:
            if st.button("🧹 Xóa kết quả quay", use_container_width=True, key="btn_draw_clear"):
                st.session_state.pop("DRAW_WINNERS", None)
                st.rerun()

        # Hiển thị kết quả
        winners = st.session_state.get("DRAW_WINNERS", [])
        if winners:
            st.success("🏆 Kết quả quay thưởng:")
            show_w = pd.DataFrame(winners)
            show_w = show_w.rename(columns={
                "hoten": "Họ tên",
                "mssv": "MSSV",
                "total_score": "Tổng điểm",
            })
            # thêm số thứ tự
            show_w.insert(0, "STT", range(1, len(show_w) + 1))
            st.dataframe(show_w, use_container_width=True, hide_index=True)
        else:
            st.caption("Chưa có kết quả quay.")

        # Sau khi có winners (list dict) => hiển thị podium
        if winners:
            top3 = winners[:3] + [{"hoten":"", "mssv":"", "total_score":""}] * (3 - len(winners))

            podium_html = f"""
            <style>
            .podium-wrap {{
            display:flex; gap:18px; justify-content:center; align-items:flex-end;
            margin: 10px 0 6px 0;
            }}
            .podium-col {{
            width: 180px; border-radius: 16px; padding: 14px 12px;
            background: #1f2937; border:1px solid #374151; text-align:center;
            box-shadow: 0 10px 20px rgba(0,0,0,.25);
            }}
            .podium-step {{
            display:flex; align-items:center; justify-content:center;
            border-radius: 14px; margin-top:10px; font-size: 34px; font-weight: 900;
            color:#111827; background:#e5e7eb;
            }}
            .h1 {{ height: 180px; background:#fbbf24; }}   /* Gold */
            .h2 {{ height: 140px; background:#9ca3af; }}   /* Silver */
            .h3 {{ height: 120px; background:#d97706; }}   /* Bronze */
            .name {{ font-weight: 800; font-size: 18px; color: #fff; }}
            .meta {{ font-size: 13px; color:#cbd5e1; }}
            </style>

            <div class="podium-wrap">
            <div class="podium-col">
                <div class="name">🥈 {top3[1]["hoten"]}</div>
                <div class="meta">{top3[1]["mssv"]}</div>
                <div class="podium-step h2">2</div>
            </div>

            <div class="podium-col">
                <div class="name">🥇 {top3[0]["hoten"]}</div>
                <div class="meta">{top3[0]["mssv"]}</div>
                <div class="podium-step h1">1</div>
            </div>

            <div class="podium-col">
                <div class="name">🥉 {top3[2]["hoten"]}</div>
                <div class="meta">{top3[2]["mssv"]}</div>
                <div class="podium-step h3">3</div>
            </div>
            </div>
            """
            st.markdown("### 🏆 Lễ trao giải Top 3")
            st.markdown(podium_html, unsafe_allow_html=True)


    footer()

# ==============================================================================
# ROUTER (ROOM)
# ==============================================================================
ROOM_HANDLERS = {
    "DEALING": room_1_dealing,
    "RISK": room_2_risk,
    "TRADE": room_3_trade,
    "INVEST": room_4_invest,
    "MACRO": room_5_macro,
    "LEADERBOARD": room_6_leaderboard,
}

room = st.session_state.get("ROOM", "DEALING")
handler = ROOM_HANDLERS.get(room)

if handler is None:
    st.warning("Phòng không hợp lệ. Tự động về Dealing Room.")
    st.session_state["ROOM"] = "DEALING"
    st.rerun()

handler()


