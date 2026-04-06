import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import io
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side

# --- [1] 페이지 설정 및 스타일 ---
st.set_page_config(page_title="미지급금 통합 관리 시스템 v2.1", layout="wide")

st.markdown("""
    <style>
        .block-container { padding-top: 1.5rem; max-width: 98%; }
        .stTabs [data-baseweb="tab-list"] { gap: 24px; }
        .stTabs [data-baseweb="tab"] { height: 50px; font-size: 18px; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- [2] 데이터 로드 및 정제 ---
def load_and_clean_data(conn):
    cols = ['Date', 'Vendor', 'Currency', 'Amount_F', 'Ex_Rate', 'Amount_KRW', 'Status', 'Is_Fixed']
    try:
        try: raw_df = conn.read(worksheet="Sheet1", ttl=0)
        except: raw_df = conn.read(worksheet="시트1", ttl=0)
        
        if raw_df is None or raw_df.empty:
            return pd.DataFrame(columns=cols)

        df = raw_df.copy()
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date'])
        df['Amount_F'] = pd.to_numeric(df['Amount_F'], errors='coerce').fillna(0)
        df['Ex_Rate'] = pd.to_numeric(df['Ex_Rate'], errors='coerce').fillna(1.0)
        df['Amount_KRW'] = pd.to_numeric(df['Amount_KRW'], errors='coerce').fillna(0).astype(int)
        df['Status'] = df['Status'].fillna('Wait').astype(str)
        df['Vendor'] = df['Vendor'].fillna('-').astype(str)
        
        return df.reset_index(drop=True)
    except Exception as e:
        st.error(f"데이터 로드 오류: {e}")
        return pd.DataFrame(columns=cols)

# --- [3] 보안 로그인 ---
def check_password():
    if st.session_state.get("password_correct", False): return True
    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
    if not st.session_state.get("password_correct", False):
        _, col, _ = st.columns([1, 2, 1])
        with col:
            st.text_input("🔑 관리자 비밀번호", type="password", on_change=password_entered, key="password")
        return False
    return True

# --- [4] 엑셀 변환 ---
def convert_to_excel(df_export):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_export[['Date', 'Vendor', 'Amount_KRW']].to_excel(writer, index=False, sheet_name='미지급목록')
    return output.getvalue()

# --- [5] 메인 로직 ---
if check_password():
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = load_and_clean_data(conn)
    
    st.title("💸 미지급금 통합 관리 시스템")
    tab1, tab2 = st.tabs(["📋 미지급 관리", "🔍 히스토리 & 전체수정"])

    with tab1:
        # [신규 입력]
        with st.expander("📝 신규 내역 입력", expanded=False):
            with st.form("in_form", clear_on_submit=True):
                f1, f2, f3, f4, f5, f6 = st.columns([1, 2, 0.8, 1.2, 1, 1])
                in_date = f1.date_input("지급날짜", datetime.now())
                in_vendor = f2.text_input("거래처명")
                in_curr = f3.selectbox("통화", ["KRW", "USD", "AUD"])
                in_amt = f4.number_input("금액", min_value=0.0)
                d_rate = 1.0 if in_curr == "KRW" else (1350.0 if in_curr == "USD" else 940.0)
                in_rate = f5.number_input("환율", value=float(d_rate))
                in_fixed = f6.checkbox("고정지출(1년 반복)")
                
                if st.form_submit_button("➕ 추가"):
                    if in_vendor:
                        new_rows = []
                        for i in range(12 if in_fixed else 1):
                            new_rows.append({
                                'Date': pd.to_datetime(in_date) + pd.DateOffset(months=i),
                                'Vendor': in_vendor, 'Currency': in_curr, 'Amount_F': in_amt,
                                'Ex_Rate': in_rate, 'Amount_KRW': int(in_amt * in_rate),
                                'Status': 'Wait', 'Is_Fixed': in_fixed
                            })
                        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
                        conn.update(worksheet="Sheet1", data=df); st.rerun()

        st.divider()

        # [조회 및 필터링]
        c1, c2, c3 = st.columns([1, 1, 2])
        start_d = c1.date_input("시작", datetime.now().date())
        end_d = c2.date_input("종료", datetime.now().date() + timedelta(days=14))
        search_kw = c3.text_input("거래처 검색", placeholder="쉼표(,)로 구분 가능")

        if not df.empty:
            mask = (df['Date'].dt.date >= start_d) & (df['Date'].dt.date <= end_d) & (df['Status'] == 'Wait')
            if search_kw:
                mask = mask & (df['Vendor'].str.contains('|'.join([k.strip() for k in search_kw.split(",") if k.strip()]), case=False, na=False))
            view_df = df[mask].sort_values('Date').copy()
        else:
            view_df = pd.DataFrame()

        # [리스트 출력 및 실시간 수정]
        if not view_df.empty:
            st.info(f"💡 금액 칸을 더블 클릭해서 바로 수정할 수 있습니다. 수정 후 반드시 하단 '저장' 버튼을 눌러주세요.")
            
            # 선택용 컬럼 추가
            view_df.insert(0, "선택", False)
            
            # --- 수정 포인트: Amount_KRW와 Amount_F를 수정 가능하게 개방 ---
            edited_view = st.data_editor(
                view_df,
                column_config={
                    "선택": st.column_config.CheckboxColumn("선택"),
                    "Date": st.column_config.DateColumn("지급일", format="YYYY-MM-DD", disabled=True),
                    "Vendor": st.column_config.TextColumn("거래처", disabled=True),
                    "Amount_F": st.column_config.NumberColumn("외화금액", format="%.1f"),
                    "Amount_KRW": st.column_config.NumberColumn("금액(KRW)", format="%d 원"),
                    "Status": None, "Is_Fixed": None, "Currency": None, "Ex_Rate": None
                },
                hide_index=True,
                use_container_width=True,
                key="editor_main"
            )

            # [버튼 영역]
            b1, b2, b3, b4 = st.columns([1, 1, 1.2, 1.5])
            selected_indices = edited_view[edited_view["선택"] == True].index
            
            # 1. 완료 처리
            if b1.button(f"✅ 완료 처리", type="primary", use_container_width=True):
                if not selected_indices.empty:
                    df.loc[selected_indices, 'Status'] = 'Done'
                    conn.update(worksheet="Sheet1", data=df); st.rerun()
            
            # 2. 삭제 처리
            if b2.button(f"🗑️ 삭제", use_container_width=True):
                if not selected_indices.empty:
                    df = df.drop(selected_indices)
                    conn.update(worksheet="Sheet1", data=df); st.rerun()

            # 3. ★ 핵심: 수정 내용 저장 버튼
            if b3.button("💾 변경사항 저장", use_container_width=True):
                # 화면에서 수정한 내용을 원본 데이터프레임에 덮어씌우기
                # index가 보존되어 있으므로 update()가 정확히 작동함
                df.update(edited_view.drop(columns=['선택']))
                # 저장 전 KRW 타입 강제 (실수 방지)
                df['Amount_KRW'] = df['Amount_KRW'].astype(int)
                conn.update(worksheet="Sheet1", data=df)
                st.toast("변경사항이 구글 시트에 저장되었습니다!"); st.rerun()
            
            with b4:
                st.download_button("📥 엑셀 다운로드", data=convert_to_excel(view_df.drop(columns=['선택'])), file_name="AP_List.xlsx", use_container_width=True)
            
            st.subheader(f"합계: :blue[{int(view_df['Amount_KRW'].sum()):,} 원]")
        else:
            st.write("조회 조건에 맞는 데이터가 없습니다.")

    with tab2:
        st.subheader("🔎 히스토리 상세 수정")
        if not df.empty:
            edited_hist = st.data_editor(df.sort_values('Date', ascending=False), use_container_width=True)
            if st.button("💾 전체 데이터 업데이트"):
                conn.update(worksheet="Sheet1", data=edited_hist); st.success("저장 완료!"); st.rerun()
