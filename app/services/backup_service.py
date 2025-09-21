import os
import shutil
import zipfile
import tempfile
import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
import requests
from bson import json_util
from motor.motor_asyncio import AsyncIOMotorClient

# Configure logging
logger = logging.getLogger(__name__)

class BackupService:
    def __init__(self):
        # MongoDB connection
        self.mongodb_uri = os.getenv("MONGODB_URI", "")

        # Dropbox configuration
        self.dropbox_access_token = os.getenv("DROPBOX_ACCESS_TOKEN", "")
        self.backup_enabled = bool(self.mongodb_uri and self.dropbox_access_token)

        if not self.backup_enabled:
            logger.warning("Backup service disabled - MongoDB URI or Dropbox token not configured")
        else:
            logger.info("Backup service initialized successfully")

    def _extract_db_name(self) -> str:
        """Extract database name from MongoDB URI"""
        try:
            # Extract DB name from URI like: mongodb+srv://user:pass@cluster.mongodb.net/dbname
            if "//" in self.mongodb_uri and "/" in self.mongodb_uri.split("//")[1]:
                return self.mongodb_uri.split("/")[-1].split("?")[0]
            return "iskandar_db"  # fallback
        except:
            return "iskandar_db"

    async def create_backup(self) -> Dict[str, Any]:
        """Create a complete database backup and upload to Dropbox"""
        if not self.backup_enabled:
            return {
                "success": False,
                "message": "Backup service not configured properly",
                "timestamp": datetime.utcnow().isoformat()
            }

        temp_dir = None
        try:
            logger.info("Starting database backup process...")

            # Create temporary directory
            temp_dir = tempfile.mkdtemp(prefix="yskandar_backup_")
            backup_timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            db_name = self._extract_db_name()

            # Paths
            dump_dir = os.path.join(temp_dir, "dump")
            zip_path = os.path.join(temp_dir, f"yskandar_backup_{backup_timestamp}.zip")

            # Step 1: Create MongoDB dump
            logger.info("Creating MongoDB dump...")
            dump_result = await self._create_mongo_dump(dump_dir)
            if not dump_result["success"]:
                return dump_result

            # Step 2: Create backup metadata
            metadata = {
                "timestamp": datetime.utcnow().isoformat(),
                "database_name": db_name,
                "backup_type": "full",
                "collections": dump_result.get("collections", []),
                "total_documents": dump_result.get("total_documents", 0),
                "version": "1.0"
            }

            # Save metadata
            metadata_path = os.path.join(dump_dir, "backup_metadata.json")
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)

            # Step 3: Compress backup
            logger.info("Compressing backup...")
            await self._create_zip_archive(dump_dir, zip_path)

            # Step 4: Upload to Dropbox
            logger.info("Uploading to Dropbox...")
            upload_result = await self._upload_to_dropbox(zip_path, f"yskandar_backup_{backup_timestamp}.zip")

            if upload_result["success"]:
                # Step 5: Cleanup old backups (keep last 4 weekly backups)
                await self._cleanup_old_backups()

                return {
                    "success": True,
                    "message": "Backup completed successfully",
                    "timestamp": backup_timestamp,
                    "file_size_mb": round(os.path.getsize(zip_path) / (1024 * 1024), 2),
                    "metadata": metadata,
                    "dropbox_path": upload_result.get("dropbox_path")
                }
            else:
                return upload_result

        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return {
                "success": False,
                "message": f"Backup failed: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            }
        finally:
            # Cleanup temporary files
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    logger.info("Temporary files cleaned up")
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp dir: {e}")

    async def _create_mongo_dump(self, output_dir: str) -> Dict[str, Any]:
        """Create MongoDB dump using Python pymongo"""
        try:
            logger.info(f"Creating MongoDB dump using pymongo...")

            # Connect to MongoDB
            client = AsyncIOMotorClient(self.mongodb_uri)
            db_name = self._extract_db_name()
            db = client[db_name]

            # Create database dump directory
            db_dump_dir = os.path.join(output_dir, db_name)
            os.makedirs(db_dump_dir, exist_ok=True)

            # Get list of collections
            collection_names = await db.list_collection_names()
            logger.info(f"Found {len(collection_names)} collections: {collection_names}")

            collections = []
            total_documents = 0

            # Export each collection
            for collection_name in collection_names:
                try:
                    logger.info(f"Exporting collection: {collection_name}")

                    collection = db[collection_name]

                    # Get all documents from collection
                    documents = []
                    async for doc in collection.find({}):
                        documents.append(doc)

                    # Write collection to JSON file
                    collection_file = os.path.join(db_dump_dir, f"{collection_name}.json")
                    with open(collection_file, 'w', encoding='utf-8') as f:
                        # Use json_util to handle MongoDB types (ObjectId, datetime, etc.)
                        json_data = json_util.dumps(documents, indent=2)
                        f.write(json_data)

                    # Get collection stats
                    doc_count = len(documents)
                    file_size = os.path.getsize(collection_file)

                    collections.append({
                        "name": collection_name,
                        "document_count": doc_count,
                        "file_size_mb": round(file_size / (1024 * 1024), 3)
                    })

                    total_documents += doc_count
                    logger.info(f"Exported {collection_name}: {doc_count} documents, {file_size} bytes")

                except Exception as e:
                    logger.error(f"Error exporting collection {collection_name}: {e}")
                    # Continue with other collections
                    continue

            # Close connection
            client.close()

            # Create database info file
            db_info = {
                "database_name": db_name,
                "export_timestamp": datetime.utcnow().isoformat(),
                "total_collections": len(collections),
                "total_documents": total_documents,
                "collections": collections,
                "export_method": "pymongo_json",
                "version": "1.0"
            }

            info_file = os.path.join(db_dump_dir, "database_info.json")
            with open(info_file, 'w', encoding='utf-8') as f:
                json.dump(db_info, f, indent=2)

            logger.info(f"Dump completed: {len(collections)} collections, {total_documents} documents")

            return {
                "success": True,
                "collections": [col["name"] for col in collections],
                "total_documents": total_documents,
                "database_info": db_info
            }

        except Exception as e:
            logger.error(f"Error creating MongoDB dump: {e}")
            return {
                "success": False,
                "message": f"MongoDB dump error: {str(e)}"
            }

    async def _create_zip_archive(self, source_dir: str, zip_path: str) -> None:
        """Create compressed ZIP archive"""
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
            for root, dirs, files in os.walk(source_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arc_path = os.path.relpath(file_path, source_dir)
                    zipf.write(file_path, arc_path)

        logger.info(f"Archive created: {round(os.path.getsize(zip_path) / (1024 * 1024), 2)} MB")

    async def _ensure_backup_folder_exists(self) -> bool:
        """Ensure the backup folder exists in Dropbox"""
        try:
            url = "https://api.dropboxapi.com/2/files/create_folder_v2"
            headers = {
                "Authorization": f"Bearer {self.dropbox_access_token}",
                "Content-Type": "application/json"
            }
            data = {
                "path": "/yskandar_backups",
                "autorename": False
            }

            response = requests.post(url, headers=headers, json=data)

            if response.status_code == 200:
                logger.info("Backup folder created successfully")
                return True
            elif response.status_code == 409:
                # Folder already exists
                logger.info("Backup folder already exists")
                return True
            else:
                logger.warning(f"Failed to create backup folder: {response.status_code}")
                return False

        except Exception as e:
            logger.warning(f"Error creating backup folder: {e}")
            return False

    async def _upload_to_dropbox(self, file_path: str, remote_filename: str) -> Dict[str, Any]:
        """Upload file to Dropbox"""
        try:
            # Ensure backup folder exists
            await self._ensure_backup_folder_exists()

            url = "https://content.dropboxapi.com/2/files/upload"

            headers = {
                "Authorization": f"Bearer {self.dropbox_access_token}",
                "Content-Type": "application/octet-stream",
                "Dropbox-API-Arg": json.dumps({
                    "path": f"/yskandar_backups/{remote_filename}",
                    "mode": "add",
                    "autorename": True
                })
            }

            with open(file_path, 'rb') as f:
                response = requests.post(url, headers=headers, data=f, timeout=600)

            if response.status_code == 200:
                result = response.json()
                logger.info(f"Upload successful: {result.get('path_display')}")
                return {
                    "success": True,
                    "dropbox_path": result.get("path_display"),
                    "file_id": result.get("id")
                }
            else:
                logger.error(f"Dropbox upload failed: {response.status_code} - {response.text}")
                return {
                    "success": False,
                    "message": f"Dropbox upload failed: {response.status_code}"
                }

        except Exception as e:
            logger.error(f"Dropbox upload error: {e}")
            return {
                "success": False,
                "message": f"Upload error: {str(e)}"
            }

    async def _cleanup_old_backups(self) -> None:
        """Remove old backups from Dropbox (keep last 4)"""
        try:
            # List files in Dropbox backup folder
            url = "https://api.dropboxapi.com/2/files/list_folder"
            headers = {
                "Authorization": f"Bearer {self.dropbox_access_token}",
                "Content-Type": "application/json"
            }
            data = {"path": "/yskandar_backups"}

            response = requests.post(url, headers=headers, json=data)

            if response.status_code == 200:
                files = response.json().get("entries", [])

                # Filter backup files and sort by date
                backup_files = [
                    f for f in files
                    if f.get("name", "").startswith("yskandar_backup_") and f.get("name", "").endswith(".zip")
                ]
                backup_files.sort(key=lambda x: x.get("name", ""), reverse=True)

                # Delete old backups (keep newest 4)
                files_to_delete = backup_files[4:]

                for file_to_delete in files_to_delete:
                    await self._delete_dropbox_file(file_to_delete.get("path_display"))

                if files_to_delete:
                    logger.info(f"Cleaned up {len(files_to_delete)} old backup files")

        except Exception as e:
            logger.warning(f"Failed to cleanup old backups: {e}")

    async def _delete_dropbox_file(self, file_path: str) -> None:
        """Delete a file from Dropbox"""
        try:
            url = "https://api.dropboxapi.com/2/files/delete_v2"
            headers = {
                "Authorization": f"Bearer {self.dropbox_access_token}",
                "Content-Type": "application/json"
            }
            data = {"path": file_path}

            response = requests.post(url, headers=headers, json=data)

            if response.status_code == 200:
                logger.info(f"Deleted old backup: {file_path}")
            else:
                logger.warning(f"Failed to delete {file_path}: {response.status_code}")

        except Exception as e:
            logger.warning(f"Error deleting file {file_path}: {e}")

    async def list_backups(self) -> Dict[str, Any]:
        """List all available backups in Dropbox"""
        try:
            url = "https://api.dropboxapi.com/2/files/list_folder"
            headers = {
                "Authorization": f"Bearer {self.dropbox_access_token}",
                "Content-Type": "application/json"
            }
            data = {"path": "/yskandar_backups"}

            response = requests.post(url, headers=headers, json=data)

            if response.status_code == 200:
                files = response.json().get("entries", [])

                backup_files = []
                for file in files:
                    if file.get("name", "").startswith("yskandar_backup_") and file.get("name", "").endswith(".zip"):
                        backup_files.append({
                            "name": file.get("name"),
                            "path": file.get("path_display"),
                            "size_mb": round(file.get("size", 0) / (1024 * 1024), 2),
                            "modified": file.get("client_modified"),
                            "id": file.get("id")
                        })

                backup_files.sort(key=lambda x: x.get("name", ""), reverse=True)

                return {
                    "success": True,
                    "backups": backup_files,
                    "total_count": len(backup_files)
                }
            elif response.status_code == 409:
                # Folder doesn't exist yet - this is normal for first-time setup
                logger.info("Backup folder doesn't exist yet - will be created on first backup")
                return {
                    "success": True,
                    "backups": [],
                    "total_count": 0,
                    "message": "No backups found - folder will be created on first backup"
                }
            else:
                error_detail = ""
                try:
                    error_response = response.json()
                    error_detail = f" - {error_response.get('error_summary', 'Unknown error')}"
                except:
                    pass

                return {
                    "success": False,
                    "message": f"Failed to list backups: HTTP {response.status_code}{error_detail}"
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"Error listing backups: {str(e)}"
            }

# Global backup service instance
backup_service = BackupService()