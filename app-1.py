import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import io
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side

# --- [1] 페이지 설정 및 보안 ---
st.set_page_config(page_title="미지급금 통합 관리 시스템", layout="wide")

st.markdown("""
    <style>
        .block-container { padding-top: 2rem; max-width: 98%; }
        .stTabs [data-baseweb="tab-list"] { gap: 24px; }
        .stTabs [data-baseweb="tab"] { height: 50px; font-size: 18px; }
    </style>
""", unsafe_allow_html=True)

def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    if "password_correct" not in st.session_state:
        _, col, _ = st.columns([1, 2, 1])
        with col: st.text_input("🔑 관리자 비밀번호", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        _, col, _ = st.columns([1, 2, 1])
        with col:
            st.text_input("🔑 관리자 비밀번호", type="password", on_change=password_entered, key="password")
            st.error("😕 비밀번호가 틀렸습니다.")
        return False
    return True

# --- [2] 메인 앱 로직 ---
if check_password():
    conn = st.connection("gsheets", type=GSheetsConnection)

    # 데이터 로드 (메인 DB와 메모장 두 개를 가져옵니다)
    def load_full_data():
        main_df = conn.read(worksheet="시트1", ttl=0) # 시트 이름 확인 필요
        main_df['Date'] = pd.to_datetime(main_df['Date'], errors='coerce')
        main_df = main_df.dropna(subset=['Date'])
        main_df['Amount_KRW'] = pd.to_numeric(main_df['Amount_KRW'], errors='coerce').fillna(0).astype(int)
        
        notes_df = conn.read(worksheet="special_notes", ttl=0)
        return main_df, notes_df

    def save_main_data(df):
        conn.update(worksheet="시트1", data=df)

    def save_notes_data(df):
        conn.update(worksheet="special_notes", data=df)

    # 엑셀 스타일링 함수
    def convert_to_excel(df_export):
        output = io.BytesIO()
        exp = df_export[['Date', 'Vendor', 'Amount_KRW']].copy()
        exp['Date'] = exp['Date'].dt.strftime('%Y-%m-%d')
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            exp.to_excel(writer, index=False, sheet_name='미지급목록')
            ws = writer.sheets['미지급목록']
            border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
            for row in ws.iter_rows(min_row=1, max_row=len(exp)+1, min_col=1, max_col=3):
                for cell in row:
                    cell.font = Font(name='맑은 고딕', size=10)
                    cell.border = border
                    cell.alignment = Alignment(horizontal='center')
                    if cell.row == 1: cell.fill = PatternFill(start_color="D9EAD3", fill_type="solid")
            # SUM 함수 추가
            last_row = len(exp) + 2
            ws.cell(row=last_row, column=1, value="합계").fill = PatternFill(start_color="FFF2CC", fill_type="solid")
            ws.cell(row=last_row, column=3, value=f"=SUM(C2:C{last_row-1})").number_format = '#,##0'
        return output.getvalue()

    # 데이터 가져오기
    df, notes_df = load_full_data()
    st.title("💸 미지급금 통합 관리 시스템")
    
    tab1, tab2, tab3 = st.tabs(["📋 미지급 관리", "🔍 히스토리 조회/수정", "📤 일괄 업로드"])

    # --- Tab 1: 미지급 관리 및 메모장 ---
    with tab1:
        with st.form("in_form", clear_on_submit=True):
            st.subheader("📝 신규 내역 입력")
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
                    new_entries = []
                    for i in range(count):
                        d = pd.to_datetime(in_date) + pd.DateOffset(months=i)
                        new_entries.append({'Date': d, 'Vendor': in_vendor, 'Currency': in_curr, 'Amount_F': in_amt, 'Ex_Rate': in_rate, 'Amount_KRW': int(in_amt*in_rate), 'Status': 'Wait', 'Is_Fixed': in_fixed})
                    df = pd.concat([df, pd.DataFrame(new_entries)], ignore_index=True)
                    save_main_data(df); st.rerun()

        st.divider()
        # 📌 메모장 섹션 다시 추가
        st.subheader("📌 특이사항 체크리스트")
        n_c1, n_c2 = st.columns([6, 1])
        with n_c1: note_input = st.text_input("메모 입력", placeholder="예: 일부 송금 완료...")
        with n_c2: st.write(""); 
            if st.button("추가", use_container_width=True):
                if note_input:
                    notes_df = pd.concat([notes_df, pd.DataFrame([{'Content': note_input}])], ignore_index=True)
                    save_notes_data(notes_df); st.rerun()
        
        if not notes_df.empty:
            for idx, row in notes_df.iterrows():
                nc1, nc2 = st.columns([6, 1])
                nc1.info(row['Content'])
                if nc2.button("완료", key=f"nt_{idx}"):
                    notes_df = notes_df.drop(idx); save_notes_data(notes_df); st.rerun()

        st.divider()
        st.subheader("🔍 기간별 미지급 조회")
        unpaid = df[df['Status'] == 'Wait']
        oldest = pd.to_datetime(unpaid['Date']).min().date() if not unpaid.empty else datetime.now().date()
        c1, c2, c3 = st.columns([1.5, 1.5, 2])
        with c1: start_d = st.date_input("조회 시작", oldest)
        with c2: end_d = st.date_input("조회 종료", datetime.now().date() + timedelta(days=14))
        
        view_df = df[(df['Date'].dt.date >= start_d) & (df['Date'].dt.date <= end_d) & (df['Status'] == 'Wait')].sort_values('Date')
        with c3: st.write(""); 
            if not view_df.empty: st.download_button("📥 엑셀 다운로드", data=convert_to_excel(view_df), file_name="Report.xlsx", use_container_width=True)

        if not view_df.empty:
            v0, v1, v2, v3, v4 = st.columns([0.5, 1.2, 2.5, 4, 1])
            v0.write("**삭제**"); v1.write("**날짜**"); v2.write("**거래처**"); v3.write("**금액**"); v4.write("**완료**")
            today = datetime.now().date()
            for idx, row in view_df.iterrows():
                r0, r1, r2, r3, r4 = st.columns([0.5, 1.2, 2.5, 4, 1])
                if r0.button("🗑️", key=f"del_{idx}"):
                    df = df.drop(idx); save_main_data(df); st.rerun()
                d_v = row['Date'].date()
                d_s = d_v.strftime('%Y-%m-%d')
                if d_v == today: r1.write(f":green-background[**{d_s}**]")
                elif d_v < today: r1.write(f":red[**{d_s}**]")
                else: r1.write(f"**{d_s}**")
                r2.write(f"**{row['Vendor']}**")
                r3.write(f"**{int(row['Amount_KRW']):,} 원**" + (f" ({row['Amount_F']:,.1f}{row['Currency']})" if row['Currency']!='KRW' else ""))
                if r4.button("✅", key=f"pay_{idx}"):
                    df.at[idx, 'Status'] = 'Done'; save_main_data(df); st.rerun()

    # --- Tab 2: 히스토리 검색 및 수정 ---
    with tab2:
        st.subheader("🔎 히스토리 필터 및 수정")
        # 검색 필터 다시 추가
        s_col1, s_col2 = st.columns(2)
        with s_col1:
            search_cat = st.radio("조회 분류", ["전체", "일반", "고정비"], horizontal=True)
        with s_col2:
            vendors = ["전체"] + sorted(df['Vendor'].unique().tolist())
            search_vendor = st.selectbox("거래처 선택", vendors)
        
        h_df = df.copy()
        if search_cat == "일반": h_df = h_df[h_df['Is_Fixed'] == False]
        elif search_cat == "고정비": h_df = h_df[h_df['Is_Fixed'] == True]
        if search_vendor != "전체": h_df = h_df[h_df['Vendor'] == search_vendor]
        
        st.write(f"결과: {len(h_df)}건")
        edited = st.data_editor(h_df.sort_values('Date', ascending=False), use_container_width=True, hide_index=True)
        if st.button("💾 변경사항 저장하기"):
            edited['Amount_KRW'] = (edited['Amount_F'] * edited['Ex_Rate']).astype(int)
            # 전체 데이터프레임에서 수정된 부분만 업데이트하는 로직이 필요하지만 간단히 덮어쓰기
            df.update(edited) # 주의: 인덱스가 맞아야 함
            save_main_data(df); st.success("저장 완료!"); st.rerun()

    # --- Tab 3: 일괄 업로드 ---
    with tab3:
        st.subheader("📤 엑셀 일괄 업로드")
        up_file = st.file_uploader("파일 선택", type=["xlsx"])
        if up_file and st.button("🚀 업로드 실행"):
            up_df = pd.read_excel(up_file)
            up_df['Date'] = pd.to_datetime(up_df['Date'], errors='coerce')
            up_df = up_df.dropna(subset=['Date'])
            up_df['Amount_KRW'] = (up_df['Amount_F'] * up_df['Ex_Rate']).astype(int)
            up_df['Status'] = 'Wait'
            df = pd.concat([df, up_df], ignore_index=True)
            save_main_data(df); st.success("업로드 완료!"); st.rerun()