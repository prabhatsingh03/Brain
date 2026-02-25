import os
import tempfile
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from flask import current_app


class DocumentStorage:
    """
    Abstraction over project document storage.
    - Local mode: uses PROJECT_DOCS_DIR on the filesystem.
    - S3 mode: uses an S3 bucket; the stored identifier is the S3 object key.
    """

    def __init__(self) -> None:
        # current_app must be available whenever methods are called
        if not current_app:
            raise RuntimeError("DocumentStorage requires an active Flask application context.")

    @property
    def _config(self):
        return current_app.config

    @property
    def use_s3(self) -> bool:
        return bool(self._config.get("USE_S3_FOR_PROJECT_DOCS"))

    # ---------- S3 helpers ----------

    def _get_s3_client(self):
        """
        Build an S3 client. Explicit credentials are optional; if not provided,
        boto3 will fall back to its default credential chain (env/IAM, etc.).
        """
        aws_access_key_id = self._config.get("AWS_ACCESS_KEY_ID")
        aws_secret_access_key = self._config.get("AWS_SECRET_ACCESS_KEY")
        region_name = self._config.get("AWS_REGION")

        session = boto3.session.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name,
        )
        return session.client("s3")

    def _build_s3_key(self, project_name: str, filename: str) -> str:
        prefix = (self._config.get("S3_PROJECT_DOCS_PREFIX") or "").strip("/")
        parts = [p for p in [prefix, project_name, filename] if p]
        return "/".join(parts)

    def build_storage_id(self, project_name: str, filename: str) -> str:
        """
        Compute the storage identifier for a document without writing it.
        - Local mode: absolute filesystem path under PROJECT_DOCS_DIR.
        - S3 mode: S3 object key.
        """
        if not self.use_s3:
            base_dir = self._config.get("PROJECT_DOCS_DIR")
            if not base_dir:
                raise RuntimeError("PROJECT_DOCS_DIR is not configured.")
            return os.path.normpath(
                os.path.abspath(os.path.join(base_dir, project_name, filename))
            )

        return self._build_s3_key(project_name, filename)

    def exists(self, storage_id: str) -> bool:
        """Return True if the given storage identifier exists."""
        if not storage_id:
            return False

        if not self.use_s3:
            return os.path.exists(storage_id)

        bucket = self._config.get("S3_PROJECT_DOCS_BUCKET")
        if not bucket:
            return False

        client = self._get_s3_client()
        try:
            client.head_object(Bucket=bucket, Key=storage_id)
            return True
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code in ("404", "NoSuchKey", "NotFound"):
                return False
            current_app.logger.error(
                f"Error checking existence for S3 object (bucket={bucket}, key={storage_id}): {e}"
            )
            return False

    # ---------- Public API ----------

    def save_pdf(self, project_name: str, filename: str, file_storage) -> str:
        """
        Save an uploaded PDF for a project.
        Returns a storage identifier:
          - local mode: absolute filesystem path
          - S3 mode: S3 object key
        """
        if not filename:
            raise ValueError("Filename is required for document storage.")

        storage_id = self.build_storage_id(project_name, filename)

        if not self.use_s3:
            # Ensure local directory exists
            save_dir = os.path.dirname(storage_id)
            os.makedirs(save_dir, exist_ok=True)
            file_storage.save(storage_id)
            return storage_id

        # S3 mode
        bucket = self._config.get("S3_PROJECT_DOCS_BUCKET")
        if not bucket:
            raise RuntimeError("S3_PROJECT_DOCS_BUCKET must be configured when USE_S3_FOR_PROJECT_DOCS is enabled.")

        key = storage_id
        client = self._get_s3_client()

        # Ensure stream is at beginning
        stream = getattr(file_storage, "stream", None) or file_storage
        try:
            stream.seek(0)
        except Exception:
            pass

        try:
            client.upload_fileobj(stream, bucket, key)
        except (BotoCoreError, ClientError) as e:
            current_app.logger.error(f"Failed to upload document to S3 (bucket={bucket}, key={key}): {e}")
            raise

        return key

    def delete(self, storage_id: Optional[str]) -> None:
        """Delete a stored document, if it exists."""
        if not storage_id:
            return

        if not self.use_s3:
            try:
                if os.path.exists(storage_id):
                    os.remove(storage_id)
            except OSError as e:
                current_app.logger.error(f"Failed to remove local document {storage_id}: {e}")
            return

        # S3 mode
        bucket = self._config.get("S3_PROJECT_DOCS_BUCKET")
        if not bucket:
            current_app.logger.error("S3_PROJECT_DOCS_BUCKET is not configured; cannot delete document from S3.")
            return

        client = self._get_s3_client()
        try:
            client.delete_object(Bucket=bucket, Key=storage_id)
        except (BotoCoreError, ClientError) as e:
            current_app.logger.error(f"Failed to delete document from S3 (bucket={bucket}, key={storage_id}): {e}")

    def read_bytes(self, storage_id: str) -> Optional[bytes]:
        """
        Read the full contents of a stored document into memory.
        Returns bytes or None if not found.
        """
        if not storage_id:
            return None

        if not self.use_s3:
            try:
                if not os.path.exists(storage_id):
                    return None
                with open(storage_id, "rb") as f:
                    return f.read()
            except OSError as e:
                current_app.logger.error(f"Failed to read local document {storage_id}: {e}")
                return None

        # S3 mode
        bucket = self._config.get("S3_PROJECT_DOCS_BUCKET")
        if not bucket:
            current_app.logger.error("S3_PROJECT_DOCS_BUCKET is not configured; cannot read document from S3.")
            return None

        client = self._get_s3_client()
        try:
            obj = client.get_object(Bucket=bucket, Key=storage_id)
            return obj["Body"].read()
        except (BotoCoreError, ClientError) as e:
            current_app.logger.error(f"Failed to read document from S3 (bucket={bucket}, key={storage_id}): {e}")
            return None

    def ensure_local_path(self, storage_id: str, project_name: Optional[str] = None) -> Optional[str]:
        """
        For components that require a filesystem path (e.g. PyMuPDF, Gemini uploads):
        - Local mode: returns the existing path if it exists.
        - S3 mode: downloads the object to a temporary file and returns that path.
        """
        if not storage_id:
            return None

        if not self.use_s3:
            # Normalise, then optionally try a project-based fallback similar to existing behaviour.
            normalized = os.path.normpath(os.path.abspath(storage_id))
            if os.path.exists(normalized):
                return normalized

            base_dir = self._config.get("PROJECT_DOCS_DIR")
            if base_dir and project_name:
                fallback = os.path.join(base_dir, project_name, os.path.basename(storage_id))
                fallback = os.path.normpath(os.path.abspath(fallback))
                if os.path.exists(fallback):
                    return fallback
            return None

        # S3 mode: download to a temporary file
        data = self.read_bytes(storage_id)
        if data is None:
            return None

        # Derive extension from storage_id (best-effort)
        _, ext = os.path.splitext(storage_id)
        try:
            fd, temp_path = tempfile.mkstemp(suffix=ext or ".bin")
            with os.fdopen(fd, "wb") as tmp:
                tmp.write(data)
            return temp_path
        except OSError as e:
            current_app.logger.error(f"Failed to create temp file for document {storage_id}: {e}")
            return None


def get_document_storage() -> DocumentStorage:
    """Convenience helper to obtain a storage instance."""
    return DocumentStorage()

