import os
import logging
import zipfile
import datetime
import json
try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False
from database import Database
from config import CREDENTIALS_PATH

# Configure logging (relies on main.py’s handler)
logger = logging.getLogger()

class DriveUploader:
    def __init__(self):
        self.SCOPES = ['https://www.googleapis.com/auth/drive.file']
        self.CREDENTIALS_FILE = CREDENTIALS_PATH
        self.db = Database()
        self.service = None
        self.username = None
        self.folder_id = None
        logging.debug("DriveUploader initialized")

    def set_username(self, username):
        self.username = username
        self.service = None  # Reset to force re-auth
        self.folder_id = None
        logging.debug(f"DriveUploader username set to {username}")

    def check_existing_token(self, username):
        if not GOOGLE_API_AVAILABLE: return False
        token = self.db.get_drive_token(username)
        if token:
            try:
                token_data = json.loads(token)
                creds = Credentials.from_authorized_user_info(token_data, self.SCOPES)
                if creds and creds.valid:
                    self.service = build('drive', 'v3', credentials=creds)
                    self.ensure_folder()
                    logging.debug(f"Valid Drive token found for {username}")
                    return True
                elif creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    self.db.store_drive_token(username, json.dumps(creds.to_json()))
                    self.service = build('drive', 'v3', credentials=creds)
                    self.ensure_folder()
                    logging.debug(f"Refreshed Drive token for {username}")
                    return True
                else:
                    logging.warning(f"Token invalid or missing refresh token for {username}")
                    self.db.clear_drive_token(username)
                    self.service = None
                    self.folder_id = None
                    return False
            except (json.JSONDecodeError, ValueError, Exception) as e:
                logging.warning(f"Failed to load token for {username}: {e}")
                self.db.clear_drive_token(username)
                self.service = None
                self.folder_id = None
                return False
        logging.debug(f"No token found for {username}")
        return False

    def authenticate(self, username):
        if not GOOGLE_API_AVAILABLE:
            logging.error("Google APIs not installed. Run: pip install google-auth-oauthlib google-api-python-client")
            return False
        if self.check_existing_token(username):
            return True
        try:
            flow = InstalledAppFlow.from_client_secrets_file(self.CREDENTIALS_FILE, self.SCOPES)
            creds = flow.run_local_server(port=8080, open_browser=True, timeout_seconds=120)
            token = creds.to_json()
            self.db.store_drive_token(username, token)
            self.service = build('drive', 'v3', credentials=creds)
            self.ensure_folder()
            logging.info(f"Authenticated Google Drive for {username}")
            return True
        except Exception as e:
            logging.error(f"Drive auth failed for {username}: {e}")
            self.service = None
            self.folder_id = None
            return False

    def ensure_folder(self):
        if not self.service:
            return
        query = "name='WiFiMonitorLogs' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = self.service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        folders = results.get('files', [])
        if folders:
            self.folder_id = folders[0]['id']
        else:
            folder_metadata = {
                'name': 'WiFiMonitorLogs',
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = self.service.files().create(body=folder_metadata, fields='id').execute()
            self.folder_id = folder.get('id')
        logging.debug(f"Drive folder ID: {self.folder_id}")

    def zip_file(self, file_path):
        zip_path = f"{file_path}.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(os.path.basename(file_path), file_path)
        return zip_path

    def upload_logs(self, username, log_dir):
        if not GOOGLE_API_AVAILABLE:
            return False
        if not username:
            logging.debug("No username; skipping Drive upload")
            return False
        if not self.service and not self.authenticate(username):
            logging.warning("No Drive service; upload skipped")
            return False

        # Export CSV
        csv_path = os.path.join(log_dir, "attacks_log.csv")
        self.db.export_to_csv(csv_path)

        # Find current log
        log_file = os.path.join(log_dir, "wifi_monitor.log")
        files_to_upload = [log_file, csv_path]

        for file_path in files_to_upload:
            if os.path.exists(file_path):
                zip_path = self.zip_file(file_path)
                file_name = os.path.basename(zip_path)
                file_metadata = {
                    'name': file_name,
                    'parents': [self.folder_id]
                }
                media = MediaFileUpload(zip_path)
                query = f"name='{file_name}' and '{self.folder_id}' in parents and trashed=false"
                results = self.service.files().list(q=query, fields='files(id)').execute()
                files = results.get('files', [])
                try:
                    if files:
                        file_id = files[0]['id']
                        self.service.files().update(fileId=file_id, media_body=media).execute()
                        logging.info(f"Updated {file_name} in Drive for {username}")
                    else:
                        self.service.files().create(body=file_metadata, media_body=media, fields='id').execute()
                        logging.info(f"Uploaded {file_name} to Drive for {username}")
                    os.remove(zip_path)
                except Exception as e:
                    logging.error(f"Failed to upload {file_name} for {username}: {e}")
                    return False
                finally:
                    if os.path.exists(zip_path):
                        os.remove(zip_path)
        try:
            # Prune old files (>30 days)
            self.prune_old_files()
        except Exception as e:
            logging.error(f"Failed to prune old files during upload for {username}: {e}")
        return True

    def prune_old_files(self):
        if not self.service or not self.folder_id:
            return
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=30)).replace(microsecond=0).isoformat() + 'Z'
        query = f"'{self.folder_id}' in parents and trashed=false and modifiedTime < {cutoff}"
        try:
            results = self.service.files().list(q=query, fields='files(id)').execute()
            for file in results.get('files', []):
                try:
                    self.service.files().delete(fileId=file['id']).execute()
                    logging.info(f"Deleted old Drive file {file['id']}")
                except Exception as e:
                    logging.error(f"Failed to delete Drive file {file['id']}: {e}")
        except Exception as e:
            logging.error(f"Failed to prune old files: {e}")

    def disconnect(self, username):
        self.db.clear_drive_token(username)
        self.service = None
        self.folder_id = None
        logging.info(f"Disconnected Drive for {username}")
