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
        .stTabs [data-baseweb="tab-list"] { gap: 24px; }
        .stTabs [data-baseweb="tab"] { height: 50px; font-size: 18px; font-weight: bold; }
        /* 에디터 내 체크박스 강조 */
        [data-testid="stTable"] { font-size: 16px; }
    </style>
""", unsafe_allow_html=True)

# --- [2] 데이터 로드 및 정제 (오류 방지 핵심) ---
def load_and_clean_data(conn):
    cols = ['Date', 'Vendor', 'Currency', 'Amount_F', 'Ex_Rate', 'Amount_KRW', 'Status', 'Is_Fixed']
    try:
        # 시트 읽기 (시트명 호환성 처리)
        try:
            raw_df = conn.read(worksheet="Sheet1", ttl=0)
        except:
            raw_df = conn.read(worksheet="시트1", ttl=0)
        
        if raw_df is None or raw_df.empty:
            return pd.DataFrame(columns=cols)

        df = raw_df.copy()
        
        # 날짜 컬럼 강제 변환 (가장 중요한 부분)
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        
        # 날짜가 깨진 행(NaT)은 데이터 정합성을 위해 제거
        df = df.dropna(subset=['Date'])
        
        # 숫자형 데이터 안전하게 변환
        df['Amount_F'] = pd.to_numeric(df['Amount_F'], errors='coerce').fillna(0)
        df['Ex_Rate'] = pd.to_numeric(df['Ex_Rate'], errors='coerce').fillna(1.0)
        df['Amount_KRW'] = (df['Amount_F'] * df['Ex_Rate']).round(0).astype(int)
        
        # 상태값 비어있으면 'Wait'으로 채움
        df['Status'] = df['Status'].fillna('Wait').astype(str)
        df['Vendor'] = df['Vendor'].fillna('-').astype(str)
        
        # 인덱스를 초기화하여 관리 효율 증대
        return df.reset_index(drop=True)
    except Exception as e:
        st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
        return pd.DataFrame(columns=cols)

# --- [3] 보안 로그인 ---
def check_password():
    if st.session_state.get("password_correct", False):
        return True
    
    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    
    if not st.session_state.get("password_correct", False):
        _, col, _ = st.columns([1, 2, 1])
        with col:
            st.text_input("🔑 관리자 비밀번호", type="password", on_change=password_entered, key="password")
            if "password_correct" in st.session_state and not st.session_state["password_correct"]:
                st.error("😕 비밀번호가 틀렸습니다.")
        return False
    return True

# --- [4] 엑셀 변환 (기존 로직 유지) ---
def convert_to_excel(df_export):
    if df_export.empty: return None
    output = io.BytesIO()
    exp = df_export[['Date', 'Vendor', 'Amount_KRW']].copy()
    exp['Date'] = exp['Date'].dt.strftime('%Y-%m-%d')
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        exp.to_excel(writer, index=False, sheet_name='미지급목록')
        ws = writer.sheets['미지급목록']
        thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
        for row in ws.iter_rows(min_row=1, max_row=len(exp)+1, min_col=1, max_col=3):
            for cell in row:
                cell.font = Font(name='맑은 고딕', size=10); cell.border = thin_border
                cell.alignment = Alignment(horizontal='center', vertical='center')
                if cell.row == 1: cell.fill = PatternFill(start_color="D9EAD3", fill_type="solid")
                if cell.column == 3 and cell.row > 1: cell.number_format = '#,##0'
        for col in ws.columns: ws.column_dimensions[col[0].column_letter].width = 20
    return output.getvalue()

# --- [5] 메인 로직 실행 ---
if check_password():
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = load_and_clean_data(conn)
    
    st.title("💸 미지급금 통합 관리 시스템")
    tab1, tab2 = st.tabs(["📋 미지급 관리", "🔍 히스토리 & 수정"])

    with tab1:
        # [신규 입력]
        with st.expander("📝 신규 내역 입력 (열기/닫기)", expanded=False):
            with st.form("in_form", clear_on_submit=True):
                f1, f2, f3, f4, f5, f6 = st.columns([1, 2, 0.8, 1.2, 1, 1])
                in_date = f1.date_input("지급날짜", datetime.now())
                in_vendor = f2.text_input("거래처명")
                in_curr = f3.selectbox("통화", ["KRW", "USD", "AUD"])
                in_amt = f4.number_input("금액", min_value=0.0)
                d_rate = 1.0 if in_curr == "KRW" else (1350.0 if in_curr == "USD" else 940.0)
                in_rate = f5.number_input("환율", min_value=0.0, value=float(d_rate))
                in_fixed = f6.checkbox("고정지출(1년 반복)")
                
                if st.form_submit_button("➕ 추가", use_container_width=True):
                    if in_vendor:
                        new_rows = []
                        count = 12 if in_fixed else 1
                        for i in range(count):
                            d = pd.to_datetime(in_date) + pd.DateOffset(months=i)
                            new_rows.append({
                                'Date': d, 'Vendor': in_vendor, 'Currency': in_curr, 
                                'Amount_F': in_amt, 'Ex_Rate': in_rate, 
                                'Amount_KRW': int(round(in_amt * in_rate, 0)), 
                                'Status': 'Wait', 'Is_Fixed': in_fixed
                            })
                        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
                        conn.update(worksheet="Sheet1", data=df)
                        st.success("추가 완료!"); st.rerun()

        st.divider()

        # [조회 및 필터링]
        st.subheader("🔍 미지급 건 조회")
        c1, c2, c3 = st.columns([1, 1, 2])
        start_d = c1.date_input("시작", datetime.now().date())
        end_d = c2.date_input("종료", datetime.now().date() + timedelta(days=14))
        search_kw = c3.text_input("거래처 검색", placeholder="쉼표(,)로 여러 거래처 동시 검색 가능")

        # 필터링 로직 (df가 비어있지 않을 때만 실행)
        if not df.empty:
            mask = (df['Date'].dt.date >= start_d) & (df['Date'].dt.date <= end_d) & (df['Status'] == 'Wait')
            if search_kw:
                keywords = [k.strip() for k in search_kw.split(",") if k.strip()]
                mask = mask & (df['Vendor'].str.contains('|'.join(keywords), case=False, na=False))
            
            view_df = df[mask].sort_values('Date').copy()
        else:
            view_df = pd.DataFrame()

        # [리스트 출력 및 일괄 처리]
        if not view_df.empty:
            st.info(f"조회된 미지급 건수: {len(view_df)}건 / 합계: {int(view_df['Amount_KRW'].sum()):,} 원")
            
            # 선택용 컬럼 추가
            view_df.insert(0, "선택", False)
            
            # 데이터 에디터 (여기서 체크박스 선택)
            edited_view = st.data_editor(
                view_df,
                column_config={
                    "선택": st.column_config.CheckboxColumn("선택", default=False),
                    "Date": st.column_config.DateColumn("지급일", format="YYYY-MM-DD"),
                    "Amount_KRW": st.column_config.NumberColumn("금액(KRW)", format="%d 원"),
                    "Status": None, "Is_Fixed": None # 불필요한 열 숨기기
                },
                disabled=["Date", "Vendor", "Currency", "Amount_F", "Ex_Rate", "Amount_KRW"],
                hide_index=True,
                use_container_width=True,
                key="editor_main"
            )

            # 버튼 영역
            b1, b2, b3 = st.columns([1.5, 1.5, 2])
            selected_indices = edited_view[edited_view["선택"] == True].index
            
            if b1.button(f"✅ {len(selected_indices)}건 완료 처리", type="primary", use_container_width=True):
                if not selected_indices.empty:
                    df.loc[selected_indices, 'Status'] = 'Done'
                    conn.update(worksheet="Sheet1", data=df)
                    st.toast("처리 완료!"); st.rerun()
                else: st.warning("선택된 항목이 없습니다.")

            if b2.button(f"🗑️ {len(selected_indices)}건 삭제", use_container_width=True):
                if not selected_indices.empty:
                    df = df.drop(selected_indices)
                    conn.update(worksheet="Sheet1", data=df)
                    st.toast("삭제 완료!"); st.rerun()
                else: st.warning("선택된 항목이 없습니다.")
            
            with b3:
                excel_data = convert_to_excel(view_df.drop(columns=['선택']))
                st.download_button("📥 엑셀 다운로드", data=excel_data, file_name=f"AP_{datetime.now().strftime('%m%d')}.xlsx", use_container_width=True)
        else:
            st.write("조회 조건에 맞는 데이터가 없습니다.")

    with tab2:
        st.subheader("🔎 히스토리 상세 수정")
        st.write("데이터를 직접 수정한 후 하단의 저장 버튼을 누르세요.")
        
        if not df.empty:
            # 히스토리 탭에서도 검색 가능하도록
            h_search = st.text_input("거래처 검색 (히스토리)", key="hist_search")
            h_df = df.copy()
            if h_search:
                h_df = h_df[h_df['Vendor'].str.contains(h_search, case=False, na=False)]
            
            edited_hist = st.data_editor(
                h_df.sort_values('Date', ascending=False),
                use_container_width=True,
                num_rows="dynamic" # 행 삭제/추가 가능
            )
            
            if st.button("💾 모든 변경사항 저장", use_container_width=True):
                # 저장 전 금액 재계산
                edited_hist['Amount_KRW'] = (edited_hist['Amount_F'] * edited_hist['Ex_Rate']).round(0).astype(int)
                conn.update(worksheet="Sheet1", data=edited_hist)
                st.success("데이터가 성공적으로 업데이트되었습니다."); st.rerun()
        else:
            st.info("표시할 데이터가 없습니다.")
