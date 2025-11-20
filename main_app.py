# main_app.py
import streamlit as st
import boto3
import datetime
import pandas as pd
import joblib
import tempfile
import os
from botocore.exceptions import NoCredentialsError

# ---------------------
# CONFIG
# ---------------------
AWS_REGION = "eu-north-1"
S3_BUCKET = "student-analytics1"
DYNAMO_TABLE = "StudentAnalyticsData1"
MODEL_KEY = "models/student_risk_model.pkl"  # confirm this path in your S3

# AWS clients
s3 = boto3.client("s3", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(DYNAMO_TABLE)

# Streamlit page config
st.set_page_config(page_title="Student Analytics Portal", page_icon="🎓", layout="centered")


# ---------------------
# UTILITIES
# ---------------------
def logout():
    """Clear session state and refresh UI."""
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.success("👋 Logged out successfully!")
    st.experimental_rerun()


def load_model_safe():
    """
    Download the model from S3 into a temporary file and load it.
    This avoids Windows file-lock errors and ensures unique filenames.
    Returns (model, error) — error is None on success.
    """
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pkl")
        tmp_path = tmp.name
        tmp.close()  # close handle so s3 can write to it
        s3.download_file(S3_BUCKET, MODEL_KEY, tmp_path)
        model = joblib.load(tmp_path)
        # Remove temporary file after loading
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        return model, None
    except Exception as e:
        return None, e


# ---------------------
# LOGIN UI
# ---------------------
st.title("🎓 Student Analytics Portal")

role = st.radio("Select Role", ["Teacher", "Student"], key="ui_role")
user_id = st.text_input("Enter ID", key="ui_login_id")
password = st.text_input("Enter Password", type="password", key="ui_login_pwd")

if st.button("Login", key="ui_login_btn"):
    if role == "Teacher":
        # simple demo credentials — replace for production
        if user_id == "teacher01" and password == "pass123":
            st.session_state["role"] = "Teacher"
            st.success("✅ Teacher login successful")
        else:
            st.error("Invalid Teacher ID or password.")
    else:
        # Student login using DynamoDB record
        try:
            resp = table.get_item(Key={"StudentID": user_id})
            student_record = resp.get("Item")
            if student_record and password == str(student_record.get("Password", "")):
                st.session_state["role"] = "Student"
                st.session_state["student_id"] = user_id
                st.success("✅ Student login successful")
            else:
                st.error("Invalid Student ID or Password.")
        except Exception as e:
            st.error(f"Error checking credentials: {e}")


# ---------------------
# TEACHER DASHBOARD
# ---------------------
if st.session_state.get("role") == "Teacher":
    st.title("👩‍🏫 Teacher Dashboard")
    st.button("🚪 Logout", on_click=logout, key="logout_teacher")

    tab1, tab2, tab3, tab4 = st.tabs(
        ["📤 Upload Assignment", "📈 Update Performance", "📊 View Student Data", "📉 Predict Risk"]
    )

    # ---- TAB 1: Upload Assignment ----
    with tab1:
        st.subheader("📤 Upload Assignment / Test")
        upload_student_id = st.text_input("Student ID", key="up_student_id")
        upload_student_name = st.text_input("Student Name (optional)", key="up_student_name")
        upload_file = st.file_uploader(
            "Choose file to upload", type=["pdf", "docx", "pptx", "jpg", "png"], key="up_file"
        )

        if st.button("Upload to S3 & Save metadata", key="up_submit"):
            if not upload_student_id or not upload_file:
                st.warning("Please enter Student ID and choose a file.")
            else:
                try:
                    s3_key = f"assignments/{upload_student_id}_{upload_file.name}"
                    s3.upload_fileobj(upload_file, S3_BUCKET, s3_key)

                    # preserve existing record
                    try:
                        existing = table.get_item(Key={"StudentID": upload_student_id})
                        old = existing.get("Item", {}) if existing else {}
                    except Exception:
                        old = {}

                    item = {
                        "StudentID": upload_student_id,
                        "Name": upload_student_name or old.get("Name", "Unknown"),
                        "Password": old.get("Password", ""),
                        "Marks": old.get("Marks", 0),
                        "Attendance": old.get("Attendance", 0),
                        "Status": old.get("Status", "NA"),
                        "FileName": upload_file.name,
                        "FilePath": s3_key,
                        "Type": "Assignment",
                        "UploadDate": datetime.datetime.utcnow().isoformat(),
                        "LastUpdated": datetime.datetime.utcnow().isoformat(),
                        "RiskStatus": old.get("RiskStatus", "NA"),
                        "LastPredicted": old.get("LastPredicted", ""),
                    }
                    table.put_item(Item=item)
                    st.success(f"✅ {upload_file.name} uploaded and metadata saved for {upload_student_id}")
                except NoCredentialsError:
                    st.error("⚠️ AWS credentials not configured.")
                except Exception as e:
                    st.error(f"Upload failed: {e}")

    # ---- TAB 2: Update Performance ----
    with tab2:
        st.subheader("📈 Update Student Performance")
        perf_student_id = st.text_input("Student ID to update", key="perf_student_id")
        perf_marks = st.number_input("Marks", min_value=0, max_value=100, step=1, key="perf_marks")
        perf_attendance = st.number_input(
            "Attendance (%)", min_value=0, max_value=100, step=1, key="perf_attendance"
        )
        perf_status = st.selectbox("Select Status", ["Pass", "Fail", "NA"], key="perf_status")

        if st.button("Update Performance", key="perf_update_btn"):
            if not perf_student_id:
                st.warning("Please enter a Student ID.")
            else:
                try:
                    resp = table.get_item(Key={"StudentID": perf_student_id})
                    old = resp.get("Item", {}) if resp else {}
                    if not old:
                        st.warning("⚠️ No record found for this Student ID. Please upload student data first.")
                    else:
                        old.update({
                            "Marks": int(perf_marks),
                            "Attendance": int(perf_attendance),
                            "Status": perf_status,
                            "Type": "Performance",
                            "LastUpdated": datetime.datetime.utcnow().isoformat()
                        })
                        table.put_item(Item=old)
                        st.success(f"✅ Performance updated for Student ID {perf_student_id}")
                except Exception as e:
                    st.error(f"Error updating performance: {e}")

    # ---- TAB 3: View Student Data ----
    with tab3:
        st.subheader("📊 All Student Records (from DynamoDB)")
        try:
            response = table.scan()
            items = response.get("Items", [])
            if not items:
                st.info("No records found yet.")
            else:
                df = pd.DataFrame(items).fillna("")
                if "StudentID" in df.columns:
                    df = df.sort_values(by="StudentID")

                def highlight_risk(row):
                    status = row.get("RiskStatus", "")
                    if status == "At Risk / Fail":
                        return ["background-color: #ffcccc"] * len(row)
                    if status == "Safe / Pass":
                        return ["background-color: #ccffcc"] * len(row)
                    return [""] * len(row)

                st.dataframe(df.style.apply(highlight_risk, axis=1), use_container_width=True)

                safe_count = int((df.get("RiskStatus") == "Safe / Pass").sum()) if "RiskStatus" in df.columns else 0
                risk_count = int((df.get("RiskStatus") == "At Risk / Fail").sum()) if "RiskStatus" in df.columns else 0
                st.markdown(f"🟢 **Safe Students:** {safe_count} 🔴 **At Risk Students:** {risk_count}")
        except Exception as e:
            st.error(f"Error loading data: {e}")

    # ---- TAB 4: Predict Risk (AUTO-FETCH marks/attendance) ----
    with tab4:
     st.subheader("📉 Predict Student Risk (ML)")

    psid = st.text_input("Student ID", key="pred_id")
    p_med = st.radio("Medical Certificate Provided?", ["No", "Yes"], key="pred_med")

    if st.button("Predict", key="pred_btn"):
        # 1️⃣ FETCH EXISTING STUDENT DATA
        try:
            resp = table.get_item(Key={"StudentID": psid})
            student = resp.get("Item")

            if not student:
                st.error("⚠️ Student record not found in database!")
                st.stop()

            marks = float(student.get("Marks", 0))
            attendance = float(student.get("Attendance", 0))  # This is the teacher-stored (already corrected) attendance

        except Exception as e:
            st.error(f"Error fetching student data: {e}")
            st.stop()

        # 2️⃣ COMPUTE REAL ATTENDANCE
        if p_med == "Yes":
            A_real = max(0, attendance - 30)
            med_val = 1
        else:
            A_real = attendance
            med_val = 0

        # 3️⃣ LOAD MODEL SAFELY
        model, err = load_model_safe()
        if err:
            st.error(f"Model Load Error: {err}")
            st.stop()

        # 4️⃣ PREPARE INPUT (3 FEATURES!)
        sample = [[marks, A_real, med_val]]

        # 5️⃣ PREDICT
        try:
            pred = model.predict(sample)[0]

            if pred == 1:
                risk = "Safe / Pass"
                st.success("✅ Student is SAFE / PASS")
            else:
                risk = "At Risk / Fail"
                st.error("⚠️ Student is AT RISK / FAIL")

            # 6️⃣ UPDATE DYNAMODB
            student["RiskStatus"] = risk
            student["LastPredicted"] = datetime.datetime.utcnow().isoformat()
            table.put_item(Item=student)

            st.info(f"DynamoDB updated successfully for Student ID: {psid}")

            # 7️⃣ DISPLAY INPUTS USED
            st.write("### 📌 Model Input Used:")
            st.write(f"**Marks:** {marks}")
            st.write(f"**Stored Attendance:** {attendance}%")
            st.write(f"**Real Attendance Used:** {A_real}%")
            st.write(f"**Medical Certificate (0/1):** {med_val}")

        except Exception as e:
            st.error(f"Prediction error: {e}")
# ---------------------
# STUDENT DASHBOARD (Option B: do NOT show RiskStatus to student)
# ---------------------
elif st.session_state.get("role") == "Student":
    st.title("🎓 Student Dashboard")
    st.button("🚪 Logout", on_click=logout, key="logout_student")

    tab1, tab2 = st.tabs(["📂 View Assignments", "📈 My Performance"])

    # View Assignments
    with tab1:
        student_id = st.session_state.get("student_id", "")
        try:
            response = table.scan()
            items = response.get("Items", [])
            student_files = [
                i for i in items if i.get("StudentID") == student_id and i.get("Type") == "Assignment"
            ]
            if not student_files:
                st.info("No assignments found for this Student ID.")
            else:
                for f in student_files:
                    fname = f.get("FileName", "Unknown")
                    fpath = f.get("FilePath", "")
                    st.write(f"📘 {fname}")
                    try:
                        url = s3.generate_presigned_url(
                            "get_object", Params={"Bucket": S3_BUCKET, "Key": fpath}, ExpiresIn=600
                        )
                        st.markdown(f"[⬇️ Download {fname}]({url})", unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"Could not generate download link: {e}")
        except Exception as e:
            st.error(f"Error loading assignments: {e}")

    # My Performance (no RiskStatus shown)
    with tab2:
        student_id = st.session_state.get("student_id", "")
        st.subheader(f"📊 Performance Report for {student_id}")
        try:
            response = table.scan()
            items = response.get("Items", [])
            student_data = [i for i in items if i.get("StudentID") == student_id and i.get("Type") != "Assignment"]
            if not student_data:
                st.info("No performance data found for this student yet.")
            else:
                df = pd.DataFrame(student_data)
                fields = [f for f in ["Marks", "Attendance", "Status", "LastUpdated"] if f in df.columns]
                st.dataframe(df[fields])
                if "Marks" in df.columns and "Attendance" in df.columns:
                    avg_marks = df["Marks"].astype(float).mean()
                    avg_attendance = df["Attendance"].astype(float).mean()
                    st.write(f"📈 **Average Marks:** {avg_marks:.2f}")
                    st.write(f"📅 **Average Attendance:** {avg_attendance:.2f}%")

                    if avg_marks >= 75 and avg_attendance >= 80:
                        st.success("✅ Excellent performance! Keep it up.")
                    elif avg_marks >= 50:
                        st.warning("⚠️ Average performance. You can improve with consistency.")
                    else:
                        st.error("❌ Needs Improvement. Please focus on studies.")

                    # Optional chart
                    try:
                        import matplotlib.pyplot as plt
                        st.subheader("📊 Visual Performance Summary")
                        metrics = ["Marks", "Attendance"]
                        values = [avg_marks, avg_attendance]
                        fig, ax = plt.subplots()
                        ax.bar(metrics, values)
                        ax.set_ylabel("Average (%)")
                        ax.set_title("Marks vs Attendance Comparison")
                        ax.set_ylim(0, 100)
                        for i, v in enumerate(values):
                            ax.text(i, v + 2, f"{v:.1f}%", ha="center", fontweight="bold")
                        st.pyplot(fig)
                    except Exception as e:
                        st.warning(f"Chart generation skipped: {e}")
        except Exception as e:
            st.error(f"Error loading performance: {e}")

# ---------------------
# Not logged in
# ---------------------
else:
    st.info("Please log in as Teacher or Student to continue.")