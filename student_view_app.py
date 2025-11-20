import streamlit as st
import boto3
import urllib.parse

# --- AWS Setup ---
AWS_REGION = "eu-north-1"
S3_BUCKET = "student-analytics1"
DYNAMO_TABLE = "StudentAnalyticsData1"

s3 = boto3.client("s3", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(DYNAMO_TABLE)

# --- Streamlit UI ---
st.title("🎓 Student Assignment Portal")

student_id = st.text_input("Enter your Student ID")

if st.button("View Assignments"):
    if not student_id:
        st.warning("Please enter your Student ID.")
    else:
        # --- Fetch from DynamoDB ---
        response = table.scan()
        items = response.get("Items", [])
        student_files = [i for i in items if i.get("StudentID") == student_id]

        if not student_files:
            st.info("No assignments found for this Student ID.")
        else:
            st.success(f"📂 Found {len(student_files)} file(s):")
            for file in student_files:
                file_name = file.get("FileName", "Unknown")
                file_path = file.get("FilePath", "")
                st.write(f"📘 {file_name}")

                # --- Generate pre-signed download URL ---
                try:
                    url = s3.generate_presigned_url(
                        "get_object",
                        Params={"Bucket": S3_BUCKET, "Key": file_path},
                        ExpiresIn=600  # link valid for 10 minutes
                    )
                    # Properly encode URL for Streamlit download button
                    encoded_url = urllib.parse.quote(url, safe=':/?&=%')
                    st.markdown(f"[⬇️ Download {file_name}]({encoded_url})", unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Could not generate download link: {e}")