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
            if "password" in st.session_state and st.session_state["password"]:
                st.error("😕 비밀번호가 틀렸습니다.")
        return False
    return True

# --- [3] 메인 로직 ---
if check_password():
    conn = st.connection("gsheets", type=GSheetsConnection)

    def load_full_data():
        cols = ['Date', 'Vendor', 'Currency', 'Amount_F', 'Ex_Rate', 'Amount_KRW', 'Status', 'Is_Fixed']
        try:
            try:
                main_df = conn.read(worksheet="Sheet1", ttl=0)
            except:
                main_df = conn.read(worksheet="시트1", ttl=0)
            
            if main_df.empty or 'Vendor' not in main_df.columns:
                main_df = pd.DataFrame(columns=cols)
            else:
                main_df['Date'] = pd.to_datetime(main_df['Date'], errors='coerce')
                main_df = main_df.dropna(subset=['Date'])
                main_df['Amount_KRW'] = pd.to_numeric(main_df['Amount_KRW'], errors='coerce').fillna(0).astype(int)
        except Exception:
            main_df = pd.DataFrame(columns=cols)
        
        try:
            notes_df = conn.read(worksheet="special_notes", ttl=0)
            if 'Content' not in notes_df.columns: notes_df = pd.DataFrame(columns=['Content'])
        except:
            notes_df = pd.DataFrame(columns=['Content'])
            
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
            header_fill = PatternFill(start_color="D9EAD3", fill_type="solid")
            sum_fill = PatternFill(start_color="FFF2CC", fill_type="solid")
            for row in ws.iter_rows(min_row=1, max_row=len(exp)+1, min_col=1, max_col=3):
                for cell in row:
                    cell.font = Font(name='맑은 고딕', size=10)
                    cell.border = thin_border
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                    if cell.row == 1: cell.fill = header_fill
                    if cell.column == 3 and cell.row > 1: cell.number_format = '#,##0'
            last_r = len(exp) + 2
            ws.cell(row=last_r, column=1, value="합계").fill = sum_fill
            ws.cell(row=last_r, column=3, value=f"=SUM(C2:C{last_r-1})").fill = sum_fill
            ws.cell(row=last_r, column=3).number_format = '#,##0'
            for col in ws.columns: ws.column_dimensions[col[0].column_letter].width = 20
        return output.getvalue()

    df, notes_df = load_full_data()
    st.title("💸 미지급금 통합 관리 시스템")
    tab1, tab2 = st.tabs(["📋 미지급 관리 & 메모", "🔍 히스토리 조회 & 수정"])

    with tab1:
        with st.form("in_form", clear_on_submit=True):
            st.subheader("📝 신규 내역 입력")
            f1, f2, f3, f4, f5, f6 = st.columns([1, 2, 0.8, 1.2, 1, 1])
            with f1: in_date = st.date_input("지급날짜", datetime.now())
            with f2: in_vendor = st.text_input("거래처명")
            with f3: in_curr = st.selectbox("통화", ["KRW", "USD", "AUD"])
            with f4: in_amt = st.number_input("금액", min_value=0.0)
            
            with f5:
                # [핵심 수정] key를 부여하여 통화 변경 시 위젯 상태를 강제 리셋함
                # KRW면 1.0 고정 및 비활성화, 외화면 활성화
                is_krw = (in_curr == "KRW")
                default_rate = 1.0 if is_krw else (1350.0 if in_curr == "USD" else 940.0)
                
                in_rate = st.number_input(
                    "환율", 
                    min_value=1.0, 
                    value=float(default_rate), 
                    disabled=is_krw,
                    format="%.1f",
                    key=f"rate_input_{in_curr}" # 이 key 덕분에 통화 바꾸면 즉시 풀림
                )
            
            with f6: st.write(""); in_fixed = st.checkbox("고정지출(1년)")
            
            if st.form_submit_button("➕ 추가", use_container_width=True):
                if in_vendor:
                    count = 12 if in_fixed else 1
                    new_rows = []
                    # 계산 공식: KRW = 외화 * 입력한 환율
                    calculated_krw = int(in_amt * in_rate)
                    
                    for i in range(count):
                        d = pd.to_datetime(in_date) + pd.DateOffset(months=i)
                        new_rows.append({
                            'Date': d, 'Vendor': in_vendor, 'Currency': in_curr, 
                            'Amount_F': in_amt, 'Ex_Rate': in_rate, 
                            'Amount_KRW': calculated_krw, 
                            'Status': 'Wait', 'Is_Fixed': in_fixed
                        })
                    df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
                    conn.update(worksheet="Sheet1", data=df)
                    st.success(f"저장 성공! {in_curr} 환율 {in_rate} 적용됨.")
                    st.rerun()

        st.divider()
        # [메모/조회/히스토리 로직은 이전과 동일하게 유지]
        st.subheader("📌 특이사항 메모")
        n1, n2 = st.columns([6, 1])
        with n1: note_txt = st.text_input("메모 입력", placeholder="예: 체리 파손 건 확인 필요", key="note_input")
        with n2: 
            st.write("")
            if st.button("추가", key="add_note", use_container_width=True):
                if note_txt:
                    notes_df = pd.concat([notes_df, pd.DataFrame([{'Content': note_txt}])], ignore_index=True)
                    conn.update(worksheet="special_notes", data=notes_df); st.rerun()
        
        if not notes_df.empty:
            for idx, row in notes_df.iterrows():
                nc1, nc2 = st.columns([6, 1])
                nc1.info(row['Content'])
                if nc2.button("완료", key=f"nt_{idx}"):
                    notes_df = notes_df.drop(idx)
                    conn.update(worksheet="special_notes", data=notes_df); st.rerun()

        st.divider()
        st.subheader("🔍 기간별 미지급 조회")
        c1, c2, c3, c4 = st.columns([1.2, 1.2, 2, 1.5])
        with c1: start_d = st.date_input("시작", datetime.now().date())
        with c2: end_d = st.date_input("종료", datetime.now().date() + timedelta(days=14))
        
        all_vendors = sorted(df['Vendor'].unique().tolist()) if 'Vendor' in df.columns and not df.empty else []
        with c3: 
            selected_vendors = st.multiselect("거래처 다중 선택 (비워두면 전체 조회)", options=all_vendors, placeholder="거래처를 선택하세요", key="main_multi")
        
        view_df = pd.DataFrame()
        if 'Date' in df.columns and not df.empty:
            mask = (df['Date'].dt.date >= start_d) & (df['Date'].dt.date <= end_d) & (df['Status'] == 'Wait')
            view_df = df.loc[mask].sort_values('Date')
            if selected_vendors:
                view_df = view_df[view_df['Vendor'].isin(selected_vendors)]

        with c4: 
            st.write("") 
            if not view_df.empty:
                xl_data = convert_to_excel(view_df)
                if xl_data: st.download_button("📥 엑셀 다운로드", data=xl_data, file_name=f"AP_Report_{datetime.now().strftime('%m%d')}.xlsx", use_container_width=True)

        if not view_df.empty:
            v0, v1, v2, v3, v4 = st.columns([0.5, 1.2, 2.5, 4, 1])
            v0.write("**삭제**"); v1.write("**날짜**"); v2.write("**거래처**"); v3.write("**금액**"); v4.write("**완료**")
            today = datetime.now().date()
            for idx, row in view_df.iterrows():
                r0, r1, r2, r3, r4 = st.columns([0.5, 1.2, 2.5, 4, 1])
                if r0.button("🗑️", key=f"d_{idx}"):
                    df = df.drop(idx); conn.update(worksheet="Sheet1", data=df); st.rerun()
                d_val = row['Date'].date()
                d_str = d_val.strftime('%Y-%m-%d')
                if d_val == today: r1.write(f":green-background[**{d_str}**]")
                elif d_val < today: r1.write(f":red[**{d_str}**]")
                else: r1.write(f"**{d_str}**")
                r2.write(f"**{row['Vendor']}**")
                r3.write(f"**{int(row['Amount_KRW']):,} 원**" + (f" ({row['Amount_F']:,.1f}{row['Currency']})" if row['Currency']!='KRW' else ""))
                if r4.button("✅", key=f"p_{idx}"):
                    df.at[idx, 'Status'] = 'Done'; conn.update(worksheet="Sheet1", data=df); st.rerun()
            st.divider()
            _, s2, s3 = st.columns([3, 1, 3])
            s2.write("### 합계")
            s3.write(f"### :blue[{int(view_df['Amount_KRW'].sum()):,} 원]")
        else:
            st.info("조회된 내역이 없습니다.")

    with tab2:
        st.subheader("🔎 히스토리 필터 및 상세 수정")
        s_col1, s_col2 = st.columns(2)
        with s_col1: 
            search_cat = st.radio("상태 필터", ["미지급(Wait)", "지급완료(Done)", "전체"], horizontal=True)
        with s_col2: 
            h_vendors = st.multiselect("거래처 필터 (히스토리)", options=all_vendors, key="hist_multi")
        
        h_df = df.copy()
        if not h_df.empty:
            if search_cat == "미지급(Wait)": h_df = h_df[h_df['Status'] == 'Wait']
            elif search_cat == "지급완료(Done)": h_df = h_df[h_df['Status'] == 'Done']
            if h_vendors: h_df = h_df[h_df['Vendor'].isin(h_vendors)]
            
            st.write(f"📊 검색 결과: {len(h_df)}건")
            if not h_df.empty:
                xl_hist = convert_to_excel(h_df)
                if xl_hist: st.download_button(f"📥 엑셀 내보내기", data=xl_hist, file_name=f"History_Search.xlsx", key="hist_xl")
                
                edited = st.data_editor(h_df.sort_values('Date', ascending=True), use_container_width=True, hide_index=True)
                
                if st.button("💾 위 수정사항 구글 시트에 최종 저장"):
                    edited['Amount_KRW'] = (edited['Amount_F'] * edited['Ex_Rate']).round(0).astype(int)
                    df.update(edited)
                    conn.update(worksheet="Sheet1", data=df)
                    st.success("저장 완료!"); st.rerun()
