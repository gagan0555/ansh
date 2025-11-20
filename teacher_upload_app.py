import streamlit as st
import boto3
import datetime
from botocore.exceptions import NoCredentialsError

# --- AWS Setup ---
AWS_REGION = "eu-north-1"  # your region
S3_BUCKET = "student-analytics1"  # your S3 bucket name
DYNAMO_TABLE = "StudentAnalyticsData1"  # your DynamoDB table name

s3 = boto3.client("s3", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(DYNAMO_TABLE)

# --- Streamlit Page ---
st.title("📚 Teacher Assignment Upload Portal")

student_id = st.text_input("Enter Student ID")
student_name = st.text_input("Enter Student Name")
file = st.file_uploader("Upload Assignment/Test File", type=["pdf", "docx", "pptx", "jpg", "png"])

if st.button("Upload"):
    if student_id and file:
        try:
            # --- Upload file to S3 ---
            filename = f"assignments/{student_id}_{file.name}"
            s3.upload_fileobj(file, S3_BUCKET, filename)

            # --- Record metadata in DynamoDB ---
            # Fetch existing student record (if any)
            try:
                existing = table.get_item(Key={"StudentID": student_id})
                old_data = existing.get("Item", {})
            except Exception as e:
                old_data = {}

            # Merge old data with new fields
            merged_item = {
                "StudentID": student_id,
                "Name": student_name or old_data.get("Name", "Unknown"),
                "Password": old_data.get("Password", ""),
                "Marks": old_data.get("Marks", 0),
                "Attendance": old_data.get("Attendance", 0),
                "Status": old_data.get("Status", "NA"),
                "FileName": file.name,
                "FilePath": filename,
                "Type": "Assignment",
                "UploadDate": datetime.datetime.utcnow().isoformat(),
                "LastUpdated": datetime.datetime.utcnow().isoformat()
            }

            # Save merged record
            table.put_item(Item=merged_item)

            st.success(f"✅ {file.name} uploaded successfully for Student ID {student_id}")
        except NoCredentialsError:
            st.error("⚠️ AWS credentials not configured.")
        except Exception as e:
            st.error(f"❌ Upload failed: {e}")
    else:
        st.warning("Please enter Student ID and select a file.")