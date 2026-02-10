import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import io
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side

# --- [보안] 비밀번호 체크 함수 ---
def check_password():
    """비밀번호가 맞으면 True를 반환합니다."""
    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # 보안을 위해 세션에서 비밀번호 삭제
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # 로그인 화면 (가운데 정렬을 위해 컬럼 활용)
        _, col, _ = st.columns([1, 2, 1])
        with col:
            st.text_input("🔑 관리자 비밀번호를 입력하세요", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        _, col, _ = st.columns([1, 2, 1])
        with col:
            st.text_input("🔑 관리자 비밀번호를 입력하세요", type="password", on_change=password_entered, key="password")
            st.error("😕 비밀번호가 틀렸습니다.")
        return False
    else:
        return True

# --- [설정] 페이지 설정 (가장 처음에 와야 함) ---
st.set_page_config(page_title="미지급금 통합 관리", layout="wide") # wide 레이아웃 적용

# 로그인 성공 시에만 메인 화면 출력
if check_password():
    
    # CSS를 이용해 화면 여백 최소화 (더 넓게 보기)
    st.markdown("""
        <style>
            .block-container { padding-top: 2rem; padding-bottom: 0rem; max-width: 95%; }
            .stTabs [data-baseweb="tab-list"] { gap: 24px; }
            .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; font-size: 18px; }
        </style>
    """, unsafe_allow_html=True)

    # 파일 설정
    DB_FILE = "unpaid_data.csv"
    NOTE_FILE = "special_notes.csv"

    def load_data():
        if os.path.exists(DB_FILE):
            df = pd.read_csv(DB_FILE)
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
            df = df.dropna(subset=['Date']) 
            df['Amount_KRW'] = pd.to_numeric(df['Amount_KRW'], errors='coerce').fillna(0).astype(int)
            df['Amount_F'] = pd.to_numeric(df['Amount_F'], errors='coerce').fillna(0)
            return df
        else:
            return pd.DataFrame(columns=['Date', 'Vendor', 'Currency', 'Amount_F', 'Ex_Rate', 'Amount_KRW', 'Status', 'Is_Fixed'])

    def save_data(df):
        df.to_csv(DB_FILE, index=False)

    def convert_df_to_excel(df):
        df_export = df[['Date', 'Vendor', 'Amount_KRW']].copy()
        data_count = len(df_export)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_export.to_excel(writer, index=False, sheet_name='미지급목록')
            workbook = writer.book
            worksheet = writer.sheets['미지급목록']
            thin_side = Side(border_style="thin", color="000000")
            border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
            header_fill = PatternFill(start_color="D9EAD3", end_color="D9EAD3", fill_type="solid")
            sum_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
            common_font = Font(name='맑은 고딕', size=10)
            header_font = Font(name='맑은 고딕', size=10, bold=True)
            for row in worksheet.iter_rows(min_row=1, max_row=data_count + 1, min_col=1, max_col=3):
                for cell in row:
                    cell.font = common_font
                    cell.border = border
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                    if cell.row == 1:
                        cell.fill = header_fill
                        cell.font = header_font
                    if cell.column == 3 and cell.row > 1:
                        cell.number_format = '#,##0'
            sum_row_idx = data_count + 2
            worksheet.cell(row=sum_row_idx, column=1, value="합계").font = header_font
            worksheet.cell(row=sum_row_idx, column=1).border = border
            worksheet.cell(row=sum_row_idx, column=1).fill = sum_fill
            worksheet.cell(row=sum_row_idx, column=2, value="").border = border
            worksheet.cell(row=sum_row_idx, column=2).fill = sum_fill
            sum_formula = f"=SUM(C2:C{data_count + 1})"
            sum_cell = worksheet.cell(row=sum_row_idx, column=3, value=sum_formula)
            sum_cell.font = Font(name='맑은 고딕', size=10, bold=True, color="0000FF")
            sum_cell.border = border
            sum_cell.fill = sum_fill
            sum_cell.number_format = '#,##0'
            for col in worksheet.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_length: max_length = len(str(cell.value))
                    except: pass
                worksheet.column_dimensions[column].width = (max_length + 5) * 1.2
        return output.getvalue()

    # --- 메인 로직 시작 ---
    df = load_data()
    st.title("💸 미지급금 통합 관리 시스템")
    
    tab1, tab2, tab3 = st.tabs(["📋 미지급 관리", "🔍 히스토리 조회/수정", "📤 엑셀 일괄 업로드"])

    with tab1:
        st.subheader("📝 신규 내역 입력")
        with st.form("input_form", clear_on_submit=True):
            # 입력 칸 너비 최적화
            f1, f2, f3, f4, f5, f6 = st.columns([1, 2, 0.8, 1.2, 1, 1])
            with f1: in_date = st.date_input("날짜", datetime.now())
            with f2: in_vendor = st.text_input("거래처/항목명")
            with f3: in_curr = st.selectbox("통화", ["KRW", "USD", "AUD"])
            with f4: in_amt = st.number_input("금액", min_value=0.0)
            with f5: in_rate = st.number_input("환율", min_value=1.0, value=1350.0 if in_curr == "USD" else 1.0)
            with f6: st.write(""); in_fixed = st.checkbox("고정지출(1년)")
            submitted = st.form_submit_button("➕ 리스트에 추가하기", use_container_width=True)
            if submitted and in_vendor:
                # 데이터 추가 로직 (생략 - 기존과 동일)
                amount_krw = int(in_amt * in_rate)
                new_row = pd.DataFrame([{'Date': in_date, 'Vendor': in_vendor, 'Currency': in_curr, 'Amount_F': in_amt, 'Ex_Rate': in_rate, 'Amount_KRW': amount_krw, 'Status': 'Wait', 'Is_Fixed': in_fixed}])
                df = pd.concat([df, new_row], ignore_index=True); save_data(df); st.rerun()

        st.divider()
        # 조회 및 목록 출력 (가독성 위해 컬럼 폭 넓게 조정)
        st.subheader("🔍 기간별 미지급 조회")
        unpaid_only = df[df['Status'] == 'Wait']
        oldest_date = pd.to_datetime(unpaid_only['Date']).min().date() if not unpaid_only.empty else datetime.now().date()
        c1, c2, c3 = st.columns([1.5, 1.5, 2])
        with c1: start_d = st.date_input("조회 시작일", oldest_date)
        with c2: end_d = st.date_input("조회 종료일", datetime.now().date() + timedelta(days=14))
        
        mask = (df['Date'] >= start_d) & (df['Date'] <= end_d) & (df['Status'] == 'Wait')
        view_df = df.loc[mask].sort_values(['Date']).copy()

        with c3:
            st.write("")
            if not view_df.empty:
                excel_data = convert_df_to_excel(view_df)
                st.download_button("📥 엑셀 다운로드 (정산용)", data=excel_data, file_name=f"AP_Report_{datetime.now().strftime('%m%d')}.xlsx", use_container_width=True)

        if not view_df.empty:
            # 목록 폭 조정: 삭제(0.4), 날짜(1), 거래처(2.5), 금액(4), 완료(0.8)
            v0, v1, v2, v3, v4 = st.columns([0.4, 1, 2.5, 4, 0.8])
            v0.write("**삭제**"); v1.write("**날짜**"); v2.write("**거래처**"); v3.write("**예정 금액 (원화/외화)**"); v4.write("**완료**")
            for idx, row in view_df.iterrows():
                r0, r1, r2, r3, r4 = st.columns([0.4, 1, 2.5, 4, 0.8])
                if r0.button("🗑️", key=f"del_{idx}"):
                    df = df.drop(idx); save_data(df); st.rerun()
                # 날짜 및 강조 로직 유지...
                r1.write(f"**{row['Date']}**"); r2.write(f"**{row['Vendor']}**")
                amt_text = f"**{int(row['Amount_KRW']):,} 원**" if row['Currency'] == 'KRW' else f"**{int(row['Amount_KRW']):,} 원** ({row['Amount_F']:,.2f} {row['Currency']})"
                r3.write(amt_text)
                if r4.button("✅", key=f"pay_{idx}"):
                    df.at[idx, 'Status'] = 'Done'; save_data(df); st.rerun()
            
            st.divider()
            _, s2, s3 = st.columns([3, 1, 3])
            s2.write("### 합계")
            s3.write(f"### :blue[{int(view_df['Amount_KRW'].sum()):,} 원]")

    # Tab 2 & 3 코드는 기존과 동일하게 유지...
    with tab2:
        st.subheader("🔎 내역 히스토리 수정")
        st.data_editor(df, use_container_width=True) # 히스토리 탭에서도 전체 너비 활용