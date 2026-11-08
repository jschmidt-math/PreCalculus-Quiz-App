import streamlit as st
import pandas as pd
import os
from datetime import datetime
from supabase import create_client

# --- 1. CONFIGURATION & SUPABASE SETUP ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. SESSION STATE INITIALIZATION ---
if "submitted" not in st.session_state:
    st.session_state.submitted = False
if "quiz_results" not in st.session_state:
    st.session_state.quiz_results = None
if "admin_authenticated" not in st.session_state:
    st.session_state.admin_authenticated = False

@st.dialog("Scientific Calculator", width="large")
def show_calculator():
    st.components.v1.iframe("https://www.desmos.com/scientific", height=500)

# --- 3. SIDEBAR NAVIGATION ---
with st.sidebar:
    st.title("🧮 Navigation")
    app_mode = st.radio("Choose Mode:", ["Take Quiz", "Teacher Admin"])
    
    st.divider()
    if st.button("🧮 Open Calculator", use_container_width=True):
        show_calculator()

# --- 4. LOAD DATA ---
@st.cache_data
def load_data():
    df_q = pd.read_excel("PreCalculusQuiz.xlsx", sheet_name="Sheet1").fillna("")
    
    # Filter out empty/ghost rows where the Question cell is blank
    df_q = df_q[df_q['Question'].astype(str).str.strip() != ""]
    
    # Try reading title from Metadata sheet if it exists
    try:
        df_meta = pd.read_excel("PreCalculusQuiz.xlsx", sheet_name="Metadata")
        title = df_meta["Quiz_Title"].iloc[0]
    except Exception:
        title = "PreCalculus Quiz"  # Fallback title if Metadata tab is missing
        
    return df_q, title

# Unpack questions and quiz title
df_questions, QUIZ_TITLE = load_data()

# ==============================================================================
# MODE 1: STUDENT QUIZ MODE
# ==============================================================================
if app_mode == "Take Quiz":
    st.title(f"🎓 {QUIZ_TITLE}")

    if not st.session_state.submitted:
        with st.form("quiz_form"):
            col_name, col_id = st.columns(2)
            with col_name:
                student_name = st.text_input("Student Name")
            with col_id:
                student_id = st.text_input("Student ID Number")
                
            st.divider()
            student_answers = {}

            for index, row in df_questions.iterrows():
                q_id = row.get('ID', index + 1)
                st.write(f"### Question {q_id}")
                
                q_text = str(row['Question'])
                st.markdown(q_text)
                
                # --- Image Rendering Logic ---
                image_val = str(row.get('Image', '')).strip()
                if image_val and image_val.lower() != 'none' and image_val.lower() != 'nan':
                    if os.path.exists(image_val):
                        st.image(image_val, use_container_width=True)
                    else:
                        st.warning(f"⚠️ Image path not found on server: `{image_val}`")

                # --- Answer Options Logic ---
                possible_cols = ["Option_A", "Option_B", "Option_C", "Option_D", "Option_E", "Option_F"]
                active_options = {col.split("_")[1]: row[col] for col in possible_cols if col in row and str(row[col]).strip() != ""}
                
                options_display = [f"{k}) {v}" for k, v in active_options.items()]
                
                # Unique key using both Q ID and iteration index
                ans_raw = st.radio(f"Select for Q{q_id}:", options_display, key=f"q{q_id}_{index}", index=None)
                student_answers[f"Q{q_id}"] = ans_raw[0] if ans_raw else None
                st.divider()

            submitted_button = st.form_submit_button("Submit Exit Ticket")

        if submitted_button:
            if not student_name or not student_id or None in student_answers.values():
                st.error("Please enter your name, student ID, and answer all questions.")
            else:
                details = []
                score = 0
                item_responses = {}
                
                for index, row in df_questions.iterrows():
                    q_id = row.get('ID', index + 1)
                    student_choice = student_answers.get(f"Q{q_id}")
                    correct_choice = str(row['Correct_Answer']).strip().upper()
                    is_correct = (student_choice == correct_choice)
                    
                    if is_correct: 
                        score += 1
                    
                    # Store detailed item response for concept diagnostics
                    item_responses[f"Q{q_id}"] = {
                        "student_choice": student_choice,
                        "correct_choice": correct_choice,
                        "is_correct": is_correct
                    }
                    
                    details.append({
                        "id": q_id,
                        "question": row['Question'],
                        "student": student_choice,
                        "correct": correct_choice,
                        "is_correct": is_correct,
                        "feedback": row[f"Option_{correct_choice}"]
                    })

                st.session_state.quiz_results = {
                    "score": score,
                    "total": len(df_questions),
                    "name": student_name,
                    "details": details
                }
                
                percentage = (score / len(df_questions)) * 100
                
                # Payload matching Supabase case-sensitive columns
                submission_record = {
                    "Name": student_name,
                    "Student_ID": student_id,
                    "Quiz_Title": QUIZ_TITLE,
                    "Score": score,
                    "Percentage": f"{percentage:.1f}%",
                    "Responses": item_responses,  # Saved as structured JSON
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                try:
                    supabase.table("PreCalculus-Quiz-Submissions").insert(submission_record).execute()
                    st.session_state.submitted = True
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving submission to database: {e}")

    else:
        res = st.session_state.quiz_results
        st.header(f"Results for {res['name']}")
        
        col1, col2 = st.columns(2)
        col1.metric("Final Score", f"{res['score']} / {res['total']}")
        col2.metric("Percentage", f"{(res['score']/res['total'])*100:.1f}%")

        if (res['score']/res['total']) >= 0.7:
            st.balloons()
            st.success("Great job!")

        st.subheader("Review Your Answers")
        for item in res['details']:
            with st.expander(f"Question {item['id']} - {'✅ Correct' if item['is_correct'] else '❌ Incorrect'}"):
                st.markdown(f"**Question:** {item['question']}")
                st.write(f"Your Answer: **{item['student']}**")
                if not item['is_correct']:
                    st.write(f"Correct Answer: **{item['correct']}) {item['feedback']}**")
                else:
                    st.write("Well done!")

# ==============================================================================
# MODE 2: TEACHER ADMIN DASHBOARD
# ==============================================================================
elif app_mode == "Teacher Admin":
    st.title("🔒 Formative Assessment Analytics")

    if not st.session_state.admin_authenticated:
        pwd_input = st.text_input("Enter Admin Password", type="password")
        if st.button("Login"):
            if pwd_input == ADMIN_PASSWORD:
                st.session_state.admin_authenticated = True
                st.success("Authenticated successfully!")
                st.rerun()
            else:
                st.error("Incorrect password.")
    else:
        col_refresh, col_logout = st.columns([1, 1])
        with col_refresh:
            if st.button("🔄 Refresh Data"):
                st.rerun()
        with col_logout:
            if st.button("🚪 Logout"):
                st.session_state.admin_authenticated = False
                st.rerun()

        try:
            response = supabase.table("PreCalculus-Quiz-Submissions").select("*").execute()
            records = response.data
            
            if records:
                results_df = pd.DataFrame(records)
                
                # Class Overview Metrics
                m1, m2, m3 = st.columns(3)
                m1.metric("Total Exit Tickets", len(results_df))
                if "Score" in results_df.columns:
                    m2.metric("Average Class Score", f"{results_df['Score'].mean():.1f}")
                if "Student_ID" in results_df.columns:
                    m3.metric("Unique Students", results_df["Student_ID"].nunique())

                st.subheader("Submissions Log")
                st.dataframe(results_df, use_container_width=True)
                
                # Export Button
                csv_data = results_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Export All Assessment Data (CSV)",
                    data=csv_data,
                    file_name="precalculus_quiz_analytics.csv",
                    mime="text/csv"
                )
            else:
                st.info("No exit tickets submitted yet.")
                
        except Exception as e:
            st.error(f"Could not load data from database: {e}")