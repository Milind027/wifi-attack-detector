# test_smtp.py
import os
import smtplib
from dotenv import load_dotenv

load_dotenv()

sender_email = os.getenv("SENDER_EMAIL")
sender_password = os.getenv("SENDER_PASSWORD")
receiver_email = sender_email  # Send test to self

try:
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(sender_email, sender_password)
        print("Login successful!")
        server.sendmail(sender_email, receiver_email, "Subject: Test\n\nThis is a test email.")
        print("Email sent!")
except Exception as e:
    print(f"Error: {e}")
