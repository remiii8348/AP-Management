import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta
import io
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side

# 1. 페이지 설정 (가장 처음에 실행되어야 함)
st.set_page_config(page_title="미지급금 통합 관리", layout="wide")

# CSS로 화면 너비 극대화 및 가독성 향상
st.markdown("""
    <style>
        .block-container { padding-top: 2rem; padding-bottom: 0rem; max-width: 98%; }
        .stTabs [data-baseweb="tab-list"] { gap: 24px; }
        .stTabs [data-baseweb="tab"] { height: 50px; font-size: 18px; }
    </style>
""", unsafe_allow_html=True)

# 2. 보안 로그인 로직
def check_password():
    """비밀번호가 일치하면 True를 반환"""
    def password_entered():
        # Secrets의 루트 레벨에 있는 password를 확인합니다.
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
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
    return True

# 3. 메인 앱 실행 (로그인 성공 시)
if check_password():
    # 구글 시트 연결 설정
    conn = st.connection("gsheets", type=GSheetsConnection)

    def load_data():
        # 실시간 데이터 로드
        df = conn.read(ttl=0)
        # 날짜 오류 방지: 날짜 형식이 아니면 NaT로 변환 후 해당 행 삭제
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Date'])
        # 숫자 데이터 정제
        df['Amount_KRW'] = pd.to_numeric(df['Amount_KRW'], errors='coerce').fillna(0).astype(int)
        df['Amount_F'] = pd.to_numeric(df['Amount_F'], errors='coerce').fillna(0)
        return df

    def save_data(df):
        # 구글 시트 업데이트
        conn.update(data=df)

    def convert_to_excel(df_to_export):
        # 엑셀 스타일링 및 내보내기 (Date, Vendor, Amount_KRW)
        output = io.BytesIO()
        df_target = df_to_export[['Date', 'Vendor', 'Amount_KRW']].copy()
        df_target['Date'] = df_target['Date'].dt.strftime('%Y-%m-%d')
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_target.to_excel(writer, index=False, sheet_name='미지급리스트')
            ws = writer.sheets['미지급리스트']
            
            # 스타일 정의
            border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
            header_fill = PatternFill(start_color="D9EAD3", end_color="D9EAD3", fill_type="solid")
            sum_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
            font_10 = Font(name='맑은 고딕', size=10)
            
            # 테두리, 정렬, 10pt 적용
            for row in ws.iter_rows(min_row=1, max_row=len(df_target)+1, min_col=1, max_col=3):
                for cell in row:
                    cell.font = font_10
                    cell.border = border
                    cell.alignment = Alignment(horizontal='center')
                    if cell.row == 1: cell.fill = header_fill
                    if cell.column == 3 and cell.row > 1: cell.number_format = '#,##0'

            # 합계 행 추가 (SUM 함수)
            sum_row = len(df_target) + 2
            ws.cell(row=sum_row, column=1, value="합계").fill = sum_fill
            ws.cell(row=sum_row, column=2).fill = sum_fill
            ws.cell(row=sum_row, column=3, value=f"=SUM(C2:C{sum_row-1})").fill = sum_fill
            ws.cell(row=sum_row, column=3).number_format = '#,##0'
            ws.cell(row=sum_row, column=3).font = Font(bold=True, size=10, color="0000FF")

            # 열 너비 자동 조절
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = 18

        return output.getvalue()

    # 데이터 로드
    df = load_data()
    st.title("💸 미지급금 통합 관리 시스템")
    
    tab1, tab2, tab3 = st.tabs(["📋 미지급 관리", "🔍 히스토리 조회/수정", "📤 일괄 업로드"])

    # --- Tab 1: 미지급 관리 ---
    with tab1:
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
                    new_rows = []
                    amt_krw = int(in_amt * in_rate)
                    count = 12 if in_fixed else 1
                    for i in range(count):
                        target_d = pd.to_datetime(in_date) + pd.DateOffset(months=i)
                        new_rows.append({'Date': target_d.date(), 'Vendor': in_vendor, 'Currency': in_curr, 
                                         'Amount_F': in_amt, 'Ex_Rate': in_rate, 'Amount_KRW': amt_krw, 
                                         'Status': 'Wait', 'Is_Fixed': in_fixed})
                    df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
                    save_data(df); st.rerun()

        st.divider()
        st.subheader("🔍 기간별 미지급 조회")
        
        # 날짜 기본값 로직
        unpaid_only = df[df['Status'] == 'Wait']
        oldest = pd.to_datetime(unpaid_only['Date']).min().date() if not unpaid_only.empty else datetime.now().date()
        two_weeks = datetime.now().date() + timedelta(days=14)
        
        c1, c2, c3 = st.columns([1.5, 1.5, 2])
        with c1: start_d = st.date_input("시작", oldest)
        with c2: end_d = st.date_input("종료", two_weeks)
        
        view_df = df[(df['Date'].dt.date >= start_d) & (df['Date'].dt.date <= end_d) & (df['Status'] == 'Wait')].sort_values('Date')
        
        with c3:
            st.write("")
            if not view_df.empty:
                st.download_button("📥 엑셀 다운로드", data=convert_to_excel(view_df), 
                                   file_name=f"AP_Report_{datetime.now().strftime('%m%d')}.xlsx", use_container_width=True)

        if not view_df.empty:
            v0, v1, v2, v3, v4 = st.columns([0.5, 1.2, 2.5, 4, 1])
            v0.write("**삭제**"); v1.write("**날짜**"); v2.write("**거래처**"); v3.write("**금액**"); v4.write("**완료**")
            today = datetime.now().date()
            for idx, row in view_df.iterrows():
                r0, r1, r2, r3, r4 = st.columns([0.5, 1.2, 2.5, 4, 1])
                if r0.button("🗑️", key=f"d_{idx}"):
                    df = df.drop(idx); save_data(df); st.rerun()
                
                d_val = row['Date'].date()
                d_str = d_val.strftime('%Y-%m-%d')
                if d_val == today: r1.write(f":green-background[**{d_str}**]")
                elif d_val < today: r1.write(f":red[**{d_str}**]")
                else: r1.write(f"**{d_str}**")
                
                r2.write(f"**{row['Vendor']}**")
                amt_txt = f"**{int(row['Amount_KRW']):,} 원**" + (f" ({row['Amount_F']:,.2f} {row['Currency']})" if row['Currency'] != "KRW" else "")
                r3.write(amt_txt)
                if r4.button("✅", key=f"p_{idx}"):
                    df.at[idx, 'Status'] = 'Done'; save_data(df); st.rerun()
            
            st.divider()
            _, s2, s3 = st.columns([3, 1, 3])
            s2.write("### 합계")
            s3.write(f"### :blue[{int(view_df['Amount_KRW'].sum()):,} 원]")

    # --- Tab 2: 히스토리 수정 ---
    with tab2:
        st.subheader("🔎 전체 내역 수정 (구글 시트 동기화)")
        edited = st.data_editor(df, use_container_width=True, hide_index=True)
        if st.button("💾 모든 변경사항 저장하기"):
            edited['Amount_KRW'] = (edited['Amount_F'] * edited['Ex_Rate']).astype(int)
            save_data(edited); st.success("저장 완료!"); st.rerun()

    # --- Tab 3: 일괄 업로드 ---
    with tab3:
        st.subheader("📤 엑셀 파일 업로드")
        up = st.file_uploader("파일 선택", type=["xlsx"])
        if up:
            up_df = pd.read_excel(up)
            if st.button("🚀 시트에 추가하기"):
                up_df['Date'] = pd.to_datetime(up_df['Date'], errors='coerce')
                up_df = up_df.dropna(subset=['Date'])
                up_df['Amount_KRW'] = (up_df['Amount_F'] * up_df['Ex_Rate']).astype(int)
                up_df['Status'] = 'Wait'
                df = pd.concat([df, up_df], ignore_index=True)
                save_data(df); st.rerun()