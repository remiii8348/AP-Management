import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import io
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side

# [1] 페이지 설정 (무조건 첫 줄)
st.set_page_config(page_title="미지급금 통합 관리", layout="wide")

# [2] 보안 로그인 (KeyError 방지)
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    if "password_correct" not in st.session_state:
        st.text_input("🔑 관리자 비밀번호", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("🔑 관리자 비밀번호", type="password", on_change=password_entered, key="password")
        st.error("😕 비밀번호가 틀렸습니다.")
        return False
    return True

if check_password():
    conn = st.connection("gsheets", type=GSheetsConnection)

    # [3] 데이터 로드 (TypeError 방지)
    def load_data():
        df = conn.read(ttl=0)
        # 시트 이름이 다를 경우 처리
        if df.empty:
            df = conn.read(worksheet="시트1", ttl=0)
        # 날짜 오류 및 빈 행 제거
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date'])
        df['Amount_KRW'] = pd.to_numeric(df['Amount_KRW'], errors='coerce').fillna(0).astype(int)
        return df

    df = load_data()
    st.title("💸 미지급금 통합 관리 시스템")
    
    tab1, tab2, tab3 = st.tabs(["📋 미지급 관리", "🔍 히스토리 조회/수정", "📤 일괄 업로드"])

    with tab1:
        # 입력 폼 (IndentationError 해결)
        with st.form("input_form", clear_on_submit=True):
            st.subheader("📝 내역 입력")
            f1, f2, f3, f4, f5, f6 = st.columns([1, 2, 0.8, 1.2, 1, 1])
            with f1: in_date = st.date_input("지급날짜", datetime.now())
            with f2: in_vendor = st.text_input("거래처명")
            with f3: in_curr = st.selectbox("통화", ["KRW", "USD", "AUD"])
            with f4: in_amt = st.number_input("금액", min_value=0.0)
            with f5: in_rate = st.number_input("환율", min_value=1.0, value=1350.0 if in_curr == "USD" else 1.0)
            with f6: st.write(""); in_fixed = st.checkbox("고정지출(1년)")
            
            if st.form_submit_button("➕ 추가", use_container_width=True):
                if in_vendor:
                    count = 12 if in_fixed else 1
                    new_rows = []
                    for i in range(count):
                        d = pd.to_datetime(in_date) + pd.DateOffset(months=i)
                        new_rows.append({'Date': d, 'Vendor': in_vendor, 'Currency': in_curr, 
                                         'Amount_F': in_amt, 'Ex_Rate': in_rate, 'Amount_KRW': int(in_amt*in_rate), 
                                         'Status': 'Wait', 'Is_Fixed': in_fixed})
                    df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
                    conn.update(data=df); st.rerun()

        st.divider()
        st.subheader("🔍 기간별 미지급 조회")
        
        # 날짜 계산 안전하게 (TypeError 해결)
        unpaid = df[df['Status'] == 'Wait']
        if not unpaid.empty:
            oldest = pd.to_datetime(unpaid['Date']).min().date()
        else:
            oldest = datetime.now().date()
            
        c1, c2, c3 = st.columns([1.5, 1.5, 2])
        with c1: start_d = st.date_input("시작", oldest)
        with c2: end_d = st.date_input("종료", datetime.now().date() + timedelta(days=14))
        
        mask = (df['Date'].dt.date >= start_d) & (df['Date'].dt.date <= end_d) & (df['Status'] == 'Wait')
        view_df = df.loc[mask].sort_values('Date')

        if not view_df.empty:
            for idx, row in view_df.iterrows():
                r0, r1, r2, r3, r4 = st.columns([0.5, 1.2, 2.5, 4, 1])
                if r0.button("🗑️", key=f"d_{idx}"):
                    df = df.drop(idx); conn.update(data=df); st.rerun()
                r1.write(f"**{row['Date'].date()}**")
                r2.write(f"**{row['Vendor']}**")
                r3.write(f"**{int(row['Amount_KRW']):,} 원**")
                if r4.button("✅", key=f"p_{idx}"):
                    df.at[idx, 'Status'] = 'Done'; conn.update(data=df); st.rerun()