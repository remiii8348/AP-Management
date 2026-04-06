import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import io
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side

# --- [1] 페이지 설정 및 스타일 ---
st.set_page_config(page_title="미지급금 통합 관리 시스템 v2", layout="wide")

st.markdown("""
    <style>
        .block-container { padding-top: 1.5rem; max-width: 98%; }
        [data-testid="stMetricValue"] { font-size: 1.8rem; }
    </style>
""", unsafe_allow_html=True)

# --- [2] 데이터 로드 및 전처리 함수 (안정성 핵심) ---
def load_and_clean_data(conn):
    cols = ['Date', 'Vendor', 'Currency', 'Amount_F', 'Ex_Rate', 'Amount_KRW', 'Status', 'Is_Fixed']
    try:
        # 시트 이름 호환성 체크
        try:
            raw_df = conn.read(worksheet="Sheet1", ttl=0)
        except:
            raw_df = conn.read(worksheet="시트1", ttl=0)
        
        if raw_df.empty:
            return pd.DataFrame(columns=cols)
        
        # 데이터 타입 강제 고정 (오류 방지)
        df = raw_df.copy()
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date']) # 날짜 없는 행 제거
        df['Amount_F'] = pd.to_numeric(df['Amount_F'], errors='coerce').fillna(0)
        df['Ex_Rate'] = pd.to_numeric(df['Ex_Rate'], errors='coerce').fillna(1.0)
        df['Amount_KRW'] = (df['Amount_F'] * df['Ex_Rate']).round(0).astype(int)
        df['Status'] = df['Status'].fillna('Wait').astype(str)
        df['Vendor'] = df['Vendor'].fillna('알수없음').astype(str)
        
        return df.reset_index(drop=True) # 인덱스 초기화로 꼬임 방지
    except Exception as e:
        st.error(f"데이터 로드 중 오류 발생: {e}")
        return pd.DataFrame(columns=cols)

# --- [3] 보안 로그인 ---
def check_password():
    if st.session_state.get("password_correct", False):
        return True
    
    def password_entered():
        if st.session_state["password"] == st.secrets.get("password", "1234"): # 비밀번호 미설정시 1234
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.error("😕 비밀번호가 틀렸습니다.")
    
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.text_input("🔑 관리자 비밀번호", type="password", on_change=password_entered, key="password")
    return False

# --- [4] 엑셀 변환 함수 ---
def convert_to_excel(df_export):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_export[['Date', 'Vendor', 'Amount_KRW']].to_excel(writer, index=False, sheet_name='미지급목록')
        ws = writer.sheets['미지급목록']
        # 엑셀 스타일링 생략 (기존 로직 유지 가능)
    return output.getvalue()

# --- [메인 실행부] ---
if check_password():
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = load_and_clean_data(conn)
    
    st.title("💸 미지급금 통합 관리 시스템")
    
    tab1, tab2 = st.tabs(["📋 미지급 관리", "🔍 전체 히스토리"])

    with tab1:
        # [A] 신규 입력 섹션
        with st.expander("📝 신규 내역 입력", expanded=False):
            with st.form("in_form", clear_on_submit=True):
                f1, f2, f3, f4, f5 = st.columns([1, 1.5, 0.8, 1, 1])
                in_date = f1.date_input("지급예정일", datetime.now())
                in_vendor = f2.text_input("거래처명")
                in_curr = f3.selectbox("통화", ["KRW", "USD", "AUD"])
                in_amt = f4.number_input("금액", min_value=0.0, step=100.0)
                d_rate = 1.0 if in_curr == "KRW" else (1350.0 if in_curr == "USD" else 940.0)
                in_rate = f5.number_input("환율", value=float(d_rate))
                in_fixed = st.checkbox("고정지출 (12개월 반복 입력)")
                
                if st.form_submit_button("➕ 내역 추가", use_container_width=True):
                    if in_vendor:
                        new_data = []
                        for i in range(12 if in_fixed else 1):
                            target_date = pd.to_datetime(in_date) + pd.DateOffset(months=i)
                            new_data.append({
                                'Date': target_date, 'Vendor': in_vendor, 'Currency': in_curr,
                                'Amount_F': in_amt, 'Ex_Rate': in_rate, 
                                'Amount_KRW': int(in_amt * in_rate), 'Status': 'Wait', 'Is_Fixed': in_fixed
                            })
                        df = pd.concat([df, pd.DataFrame(new_data)], ignore_index=True)
                        conn.update(worksheet="Sheet1", data=df)
                        st.success("데이터가 추가되었습니다."); st.rerun()

        # [B] 조회 및 처리 섹션
        st.subheader("🔍 미지급 건 조회 및 처리")
        c1, c2, c3 = st.columns([1, 1, 2])
        s_date = c1.date_input("시작일", datetime.now().date())
        e_date = c2.date_input("종료일", datetime.now().date() + timedelta(days=30))
        search_v = c3.text_input("거래처 검색", placeholder="검색어 입력 (여러 개는 콤마로 구분)")

        # 필터링 로직
        mask = (df['Date'].dt.date >= s_date) & (df['Date'].dt.date <= e_date) & (df['Status'] == 'Wait')
        if search_v:
            keywords = [k.strip() for k in search_v.split(",")]
            mask = mask & (df['Vendor'].str.contains('|'.join(keywords), case=False))
        
        view_df = df[mask].sort_values('Date').copy()

        if not view_df.empty:
            # 상태 요약 대시보드
            total_sum = view_df['Amount_KRW'].sum()
            st.metric("조회 기간 합계", f"{total_sum:,} 원")

            # --- 중요: 데이터 에디터를 이용한 선택 방식 (안정성 최상) ---
            # 사용자가 체크박스로 선택할 수 있도록 '선택' 컬럼 임시 생성
            view_df.insert(0, "선택", False)
            
            edited_df = st.data_editor(
                view_df,
                column_config={
                    "선택": st.column_config.CheckboxColumn(help="완료/삭제할 항목 선택"),
                    "Date": st.column_config.DateColumn("지급일", format="YYYY-MM-DD"),
                    "Amount_KRW": st.column_config.NumberColumn("금액(KRW)", format="%d 원"),
                    "Status": None, "Is_Fixed": None # 불필요한 컬럼 숨기기
                },
                disabled=["Date", "Vendor", "Currency", "Amount_F", "Ex_Rate", "Amount_KRW"],
                hide_index=True,
                use_container_width=True,
                key="main_editor"
            )

            # 처리 버튼
            selected_indices = edited_df[edited_df["선택"] == True].index
            
            act1, act2, act3 = st.columns([1, 1, 2])
            if act1.button(f"✅ {len(selected_indices)}건 완료 처리", type="primary", use_container_width=True):
                if not selected_indices.empty:
                    df.loc[selected_indices, 'Status'] = 'Done'
                    conn.update(worksheet="Sheet1", data=df)
                    st.toast("처리 완료!"); st.rerun()
            
            if act2.button(f"🗑️ {len(selected_indices)}건 삭제", use_container_width=True):
                if not selected_indices.empty:
                    df = df.drop(selected_indices)
                    conn.update(worksheet="Sheet1", data=df)
                    st.toast("삭제 완료!"); st.rerun()
            
            act3.download_button("📥 현재 리스트 엑셀 다운로드", data=convert_to_excel(view_df), file_name="AP_List.xlsx")
        else:
            st.info("해당 조건에 맞는 미지급 내역이 없습니다.")

    with tab2:
        st.subheader("📑 전체 데이터 수정 및 히스토리")
        # 전체 데이터 수정 (직접 수정 후 저장)
        history_editor = st.data_editor(df, use_container_width=True, hide_index=False)
        if st.button("💾 변경사항 전체 저장"):
            # 저장 전 자동 재계산
            history_editor['Amount_KRW'] = (history_editor['Amount_F'] * history_editor['Ex_Rate']).round(0).astype(int)
            conn.update(worksheet="Sheet1", data=history_editor)
            st.success("전체 데이터가 업데이트되었습니다."); st.rerun()
