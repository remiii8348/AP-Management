import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import io
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side

# --- [1] 페이지 설정 ---
st.set_page_config(page_title="미지급금 통합 관리 시스템", layout="wide")

st.markdown("""
    <style>
        .block-container { padding-top: 1.5rem; max-width: 98%; }
        .stTabs [data-baseweb="tab-list"] { gap: 24px; }
        .stTabs [data-baseweb="tab"] { height: 50px; font-size: 18px; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- [2] 보안 로그인 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        _, col, _ = st.columns([1, 2, 1])
        with col:
            st.text_input("🔑 관리자 비밀번호", type="password", on_change=password_entered, key="password")
        return False
    return True

# --- [3] 메인 로직 ---
if check_password():
    conn = st.connection("gsheets", type=GSheetsConnection)

    def load_full_data():
        cols = ['Date', 'Vendor', 'Currency', 'Amount_F', 'Ex_Rate', 'Amount_KRW', 'Status', 'Is_Fixed']
        try:
            try: main_df = conn.read(worksheet="Sheet1", ttl=0)
            except: main_df = conn.read(worksheet="시트1", ttl=0)
            if main_df.empty or 'Vendor' not in main_df.columns: main_df = pd.DataFrame(columns=cols)
            else:
                main_df['Date'] = pd.to_datetime(main_df['Date'], errors='coerce')
                main_df = main_df.dropna(subset=['Date'])
                main_df['Amount_KRW'] = pd.to_numeric(main_df['Amount_KRW'], errors='coerce').fillna(0).astype(int)
        except: main_df = pd.DataFrame(columns=cols)
        try:
            notes_df = conn.read(worksheet="special_notes", ttl=0)
            if 'Content' not in notes_df.columns: notes_df = pd.DataFrame(columns=['Content'])
        except: notes_df = pd.DataFrame(columns=['Content'])
        return main_df, notes_df

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
            last_r = len(exp) + 2
            ws.cell(row=last_r, column=1, value="합계").font = Font(bold=True)
            ws.cell(row=last_r, column=3, value=f"=SUM(C2:C{last_r-1})").number_format = '#,##0'
            for col in ws.columns: ws.column_dimensions[col[0].column_letter].width = 20
        return output.getvalue()

    df, notes_df = load_full_data()
    st.title("💸 미지급금 통합 관리 시스템")
    tab1, tab2 = st.tabs(["📋 미지급 관리 & 메모", "🔍 히스토리 조회 & 수정"])

    with tab1:
        # [신규 입력 창]
        with st.form("in_form", clear_on_submit=True):
            st.subheader("📝 신규 내역 입력")
            f1, f2, f3, f4, f5, f6 = st.columns([1, 2, 0.8, 1.2, 1, 1])
            with f1: in_date = st.date_input("지급날짜", datetime.now())
            with f2: in_vendor = st.text_input("거래처명")
            with f3: in_curr = st.selectbox("통화", ["KRW", "USD", "AUD"])
            with f4: in_amt = st.number_input("금액", min_value=0.0)
            with f5:
                d_rate = 1.0 if in_curr == "KRW" else (1350.0 if in_curr == "USD" else 940.0)
                in_rate = st.number_input("환율 (직접수정)", min_value=0.0, value=float(d_rate), format="%.1f", key="rate_wid")
            with f6: st.write(""); in_fixed = st.checkbox("고정지출(1년)")
            
            if st.form_submit_button("➕ 추가", use_container_width=True):
                if in_vendor:
                    final_krw = int(round(in_amt * in_rate, 0))
                    count = 12 if in_fixed else 1
                    new_rows = []
                    for i in range(count):
                        d = pd.to_datetime(in_date) + pd.DateOffset(months=i)
                        new_rows.append({'Date': d, 'Vendor': in_vendor, 'Currency': in_curr, 'Amount_F': in_amt, 'Ex_Rate': in_rate, 'Amount_KRW': final_krw, 'Status': 'Wait', 'Is_Fixed': in_fixed})
                    df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
                    conn.update(worksheet="Sheet1", data=df); st.rerun()

        st.divider()
        # [조회 영역]
        st.subheader("🔍 기간별 미지급 조회")
        c1, c2, c3, c4 = st.columns([1.2, 1.2, 2.5, 1.2])
        with c1: start_d = st.date_input("시작", datetime.now().date())
        with c2: end_d = st.date_input("종료", datetime.now().date() + timedelta(days=14))
        with c3: search_keywords = st.text_input("거래처 검색 (키워드)", placeholder="예: 제이원, 삼성")
            
        if not df.empty and 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
            df = df.dropna(subset=['Date'])
            mask = (df['Date'].dt.date >= start_d) & (df['Date'].dt.date <= end_d) & (df['Status'] == 'Wait')
            view_df = df.loc[mask].sort_values('Date').copy()

            if search_keywords:
                keywords = [k.strip() for k in search_keywords.split(",") if k.strip()]
                pattern = '|'.join(keywords)
                view_df = view_df[view_df['Vendor'].str.contains(pattern, case=False, na=False)]
        else:
            view_df = pd.DataFrame()

        with c4:
            st.write("")
            if not view_df.empty:
                st.download_button("📥 엑셀", data=convert_to_excel(view_df), file_name=f"AP_{datetime.now().strftime('%m%d')}.xlsx", use_container_width=True)

        # --- [다중 선택 테이블 구현] ---
        if not view_df.empty:
            st.write("")
            col_sel_all, _ = st.columns([1, 10])
            select_all = col_sel_all.checkbox("전체 선택")

            # 헤더 (삭제 버튼 제거하고 체크박스에 집중)
            v0, v1, v2, v3 = st.columns([0.6, 1.2, 2.5, 4.6])
            v0.write("**선택**"); v1.write("**날짜**"); v2.write("**거래처**"); v3.write("**금액**")
            
            selected_indices = []
            today = datetime.now().date()

            # 리스트 출력
            for idx, row in view_df.iterrows():
                r0, r1, r2, r3 = st.columns([0.6, 1.2, 2.5, 4.6])
                
                is_selected = r0.checkbox("", key=f"sel_{idx}", value=select_all)
                if is_selected:
                    selected_indices.append(idx)

                d_val = row['Date'].date()
                d_str = d_val.strftime('%Y-%m-%d')
                if d_val == today: r1.write(f":green-background[**{d_str}**]")
                elif d_val < today: r1.write(f":red[**{d_str}**]")
                else: r1.write(f"**{d_str}**")
                
                r2.write(f"**{row['Vendor']}**")
                r3.write(f"**{int(row['Amount_KRW']):,} 원**" + (f" ({row['Amount_F']:,.1f}{row['Currency']})" if row['Currency']!='KRW' else ""))

            st.divider()
            
            # --- [하단 일괄 처리 버튼들] ---
            act1, act2, act3 = st.columns([2, 2, 3])
            
            with act1:
                if st.button(f"✅ {len(selected_indices)}건 완료 처리", use_container_width=True, type="primary"):
                    if selected_indices:
                        df.loc[selected_indices, 'Status'] = 'Done'
                        conn.update(worksheet="Sheet1", data=df); st.rerun()
                    else:
                        st.warning("선택된 항목이 없습니다.")
            
            with act2:
                # [일괄 삭제 버튼 추가]
                if st.button(f"🗑️ {len(selected_indices)}건 일괄 삭제", use_container_width=True):
                    if selected_indices:
                        df = df.drop(selected_indices)
                        conn.update(worksheet="Sheet1", data=df); st.success("삭제 완료!"); st.rerun()
                    else:
                        st.warning("선택된 항목이 없습니다.")
            
            with act3:
                st.write(f"### 합계: :blue[{int(view_df['Amount_KRW'].sum()):,} 원]")
        else:
            st.info("조건에 맞는 내역이 없습니다.")

    with tab2:
        # [히스토리 탭]
        st.subheader("🔎 히스토리 상세 수정")
        h_search = st.text_input("거래처 키워드 검색 (히스토리)", key="hist_search")
        h_df = df.copy()
        if h_search and not h_df.empty:
            h_df = h_df[h_df['Vendor'].str.contains(h_search, case=False, na=False)]
        
        if not h_df.empty:
            edited = st.data_editor(h_df.sort_values('Date', ascending=True), use_container_width=True, hide_index=True)
            if st.button("💾 최종 저장"):
                edited['Amount_KRW'] = (edited['Amount_F'] * edited['Ex_Rate']).round(0).astype(int)
                df.update(edited); conn.update(worksheet="Sheet1", data=df); st.success("저장 완료!"); st.rerun()
