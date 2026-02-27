import os
import io
import time
import logging
import json
import re
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from google import genai
from google.genai import types
from models.project import Project, ProjectMetadata, FileUploadCache
from extensions import db
import tempfile
from utils.image_processing import process_image_for_ocr
from flask import current_app

from services.document_storage import get_document_storage

try:
    from config import Config
except ImportError:
    Config = None

# Match old_code process_qna/generic_process_qna.py
RELEVANT_FILES_PROMPT_MAX = 3
MAX_ATTACHMENTS = 3


class GeminiService:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("API Key for Gemini is required.")
        self.client = genai.Client(api_key=api_key)
        # Define model hierarchy (Primary -> Fallback)
        self.routing_models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-3-flash-preview"]
        self.answer_models = ["gemini-2.5-pro", "gemini-2.0-flash", "gemini-3-pro-preview"]
        self.model_routing = self.routing_models[0]
        self.model_answer = self.answer_models[0]

    def _resolve_file_path(self, file_path: str, project_name: str) -> Tuple[Optional[str], bool]:
        """
        Resolve and normalize a file path from the database.
        Returns (resolved_path, found) tuple.
        - Normalizes the path (handles slashes, relative vs absolute)
        - If file not found at normalized path, tries fallback: PROJECT_DOCS_DIR/project_name/basename(file_path)
        - Returns (None, False) if file cannot be found at either location
        """
        logging.debug(f"[DEBUG] _resolve_file_path called: file_path='{file_path}', project_name='{project_name}'")

        if not file_path:
            logging.warning("[DEBUG] Empty file_path provided")
            return None, False

        # Use the unified document storage abstraction so that:
        # - In local mode, we resolve and normalise filesystem paths (with legacy fallbacks).
        # - In S3 mode, we transparently download to a temporary local file.
        try:
            storage = get_document_storage()
            resolved = storage.ensure_local_path(file_path, project_name=project_name)
            if resolved and os.path.exists(resolved):
                logging.info(f"[DEBUG] File resolved via DocumentStorage: {resolved}")
                return resolved, True
        except Exception as e:
            logging.warning(f"[DEBUG] DocumentStorage resolution failed for '{file_path}': {e}", exc_info=True)

        # Fallback to previous behaviour for safety (primarily helps with legacy data)
        try:
            normalized_path = os.path.normpath(os.path.abspath(file_path))
            logging.debug(f"[DEBUG] Normalized fallback path: '{normalized_path}'")
            if os.path.exists(normalized_path):
                logging.info(f"[DEBUG] File found at normalized fallback path: {normalized_path}")
                return normalized_path, True

            logging.warning(f"[DEBUG] File NOT found at normalized fallback path: {normalized_path}")

            if current_app and hasattr(current_app, "config"):
                project_docs_dir = current_app.config.get("PROJECT_DOCS_DIR")
                if project_docs_dir:
                    fallback_path = os.path.join(project_docs_dir, project_name, os.path.basename(file_path))
                    fallback_path = os.path.normpath(os.path.abspath(fallback_path))
                    logging.debug(f"[DEBUG] Trying legacy PROJECT_DOCS_DIR fallback path: {fallback_path}")
                    if os.path.exists(fallback_path):
                        logging.info(f"[DEBUG] File found at legacy fallback path: {fallback_path} (original: {file_path})")
                        return fallback_path, True
                    else:
                        logging.warning(f"[DEBUG] File NOT found at legacy fallback path: {fallback_path}")
                else:
                    logging.warning("[DEBUG] PROJECT_DOCS_DIR not found in config")
            else:
                logging.warning("[DEBUG] current_app not available or has no config")
        except Exception as e:
            logging.warning(f"[DEBUG] Error during legacy fallback resolution: {e}", exc_info=True)

        logging.error(f"[DEBUG] File resolution failed for: '{file_path}' (project: {project_name})")
        return None, False

    def _get_project_id(self, process_name: str) -> Optional[int]:
        """Get project ID from process name."""
        project = Project.query.filter_by(name=process_name).first()
        return project.id if project else None

    def _load_upload_cache(self, process_name: str, local_path: Optional[str] = None) -> Dict[str, str]:
        """
        Load upload cache from database for a project.
        If local_path is provided, returns only that entry; otherwise returns all entries for the project.
        Returns dict mapping local_path -> gemini_file_id.
        """
        project_id = self._get_project_id(process_name)
        if not project_id:
            return {}
        
        try:
            query = FileUploadCache.query.filter_by(project_id=project_id)
            if local_path:
                query = query.filter_by(local_path=local_path)
            
            cache_entries = query.all()
            return {entry.local_path: entry.gemini_file_id for entry in cache_entries}
        except Exception as e:
            logging.warning(f"Error loading upload cache from DB: {e}")
            return {}

    def _save_upload_cache(self, process_name: str, local_path: str, gemini_file_id: str) -> None:
        """
        Save or update upload cache entry in database.
        Uses upsert: updates if exists, creates if not.
        """
        project_id = self._get_project_id(process_name)
        if not project_id:
            logging.error(f"Project {process_name} not found for cache save")
            return
        
        try:
            cache_entry = FileUploadCache.query.filter_by(
                project_id=project_id,
                local_path=local_path
            ).first()
            
            if cache_entry:
                # Update existing entry
                cache_entry.gemini_file_id = gemini_file_id
                cache_entry.updated_at = datetime.utcnow()
            else:
                # Create new entry
                cache_entry = FileUploadCache(
                    project_id=project_id,
                    local_path=local_path,
                    gemini_file_id=gemini_file_id
                )
                db.session.add(cache_entry)
            
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error saving upload cache to DB: {e}")

    def _generate_with_fallback(self, models: List[str], contents, config=None, tools=None) -> Optional[object]:
        """
        Try generating content with a list of models in order.
        """
        # Prepare config with tools if provided
        final_config = config.copy() if config else {}
        if tools:
            final_config['tools'] = tools

        errors = []
        for model in models:
            try:
                logging.info(f"Attempting generation with model: {model}")
                response = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=final_config
                )
                return response
            except Exception as e:
                error_str = str(e)
                logging.warning(f"Model {model} failed: {error_str}")
                errors.append(f"{model}: {error_str}")
                
                # CRITICAL: Do not retry on Client Errors (4xx) - they will fail on all models
                if "400" in error_str or "INVALID_ARGUMENT" in error_str:
                    logging.error(f"Non-retryable error detected: {error_str}")
                    raise Exception(f"Request failed with invalid argument: {error_str}")

        logging.error(f"All models failed: {'; '.join(errors)}")
        raise Exception(f"All AI models failed. Last error: {errors[-1] if errors else 'Unknown'}")

    def _generate_stream_with_fallback(self, models: List[str], contents, config=None, tools=None):
        """
        Try generating content with streaming; yields text chunks. Tries each model until one succeeds.
        """
        final_config = config.copy() if config else {}
        if tools:
            final_config['tools'] = tools

        errors = []
        for model in models:
            try:
                logging.info(f"Attempting streaming generation with model: {model}")
                stream = self.client.models.generate_content_stream(
                    model=model,
                    contents=contents,
                    config=final_config
                )
                for chunk in stream:
                    if chunk and getattr(chunk, "text", None):
                        yield chunk.text
                return  # success
            except Exception as e:
                error_str = str(e)
                logging.warning(f"Model {model} streaming failed: {error_str}")
                errors.append(f"{model}: {error_str}")
                if "400" in error_str or "INVALID_ARGUMENT" in error_str:
                    raise Exception(f"Request failed with invalid argument: {error_str}")

        raise Exception(f"All AI models failed. Last error: {errors[-1] if errors else 'Unknown'}")

    def generate_chat_title(self, question: str, max_words: int = 5) -> Optional[str]:
        """Generate a title for a chat from its first question. No length limit; caller truncates to DB max (255)."""
        try:
            prompt = (
                f"From this chat question, give a short topic title. "
                f"Question: '{question[:500]}'. "
                f"Reply with ONLY the title, no quotes, no period, no explanation."
            )
            response = self._generate_with_fallback(
                models=self.routing_models,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                config={"max_output_tokens": 100}
            )
            if response and getattr(response, "text", None):
                raw = (response.text or "").strip()
                raw = re.sub(r"<br\s*/?>", "\n", raw)
                return raw if raw else None
        except Exception as e:
            logging.warning("Chat title generation failed: %s", e)
        return None

    def get_relevant_files(self, question: str, process_name: str, max_files: int = RELEVANT_FILES_PROMPT_MAX) -> List[str]:
        """
        Identify relevant files from the database (ProjectMetadata) based on the question.
        """
        logging.info(f"[DEBUG] get_relevant_files called: question='{question}', process_name='{process_name}', max_files={max_files}")
        
        # 1. Fetch metadata for the project
        project = Project.query.filter_by(name=process_name).first()
        if not project:
            logging.error(f"[DEBUG] Project {process_name} not found in database.")
            return []
        
        logging.info(f"[DEBUG] Found project: {project.name} (ID: {project.id})")
        
        metadata_items = ProjectMetadata.query.filter_by(project_id=project.id).all()
        if not metadata_items:
            logging.warning(f"[DEBUG] No metadata items found for project {process_name} (ID: {project.id})")
            return []

        logging.info(f"[DEBUG] Found {len(metadata_items)} metadata items for project {process_name}")

        # 2. Create metadata text representation
        lines = []
        for item in metadata_items:
            lines.append(f"{item.id} | {item.type_of_data} | {item.file_name} | {item.file_path}")
        metadata_text = "\n".join(lines)
        
        # Log sample metadata entries
        sample_size = min(5, len(metadata_items))
        logging.info(f"[DEBUG] Sample metadata entries (first {sample_size}):")
        for i, line in enumerate(lines[:sample_size]):
            logging.info(f"[DEBUG]   {i+1}. {line}")
        if len(metadata_items) > sample_size:
            logging.info(f"[DEBUG]   ... and {len(metadata_items) - sample_size} more entries")
        
        # Truncate if too long (same as old_code metadata_to_text: max_chars=30000)
        max_chars = 30000
        original_length = len(metadata_text)
        if len(metadata_text) > max_chars:
            metadata_text = metadata_text[: max_chars - 2000] + "\n...\n" + metadata_text[-1000:]
            logging.warning(f"[DEBUG] Metadata text truncated from {original_length} to {len(metadata_text)} characters")

        # 3. Ask Gemini (same prompt as old_code process_qna/generic_process_qna.py)
        prompt = f"""
You are a chemical process expert working on a {process_name} fertilizer plant.

You are given a metadata list of process-related documents. 
Each line contains: s.no | type_of_data | file_name | file_path.

The metadata describes what each file contains (e.g., process flow diagrams, equipment datasheets, operating procedures, or design calculations).

Your task:
- Read the user's question carefully.
- Identify which files from the metadata are most relevant to answer that question.
- Base your selection on the type_of_data and filename context.
- Return only upto {max_files} matching file_name entries as a JSON array.
- Do NOT use markdown formatting (no backticks).
- If nothing is relevant, return an empty JSON array: []

User question: "{question}"

Metadata:
{metadata_text}
"""
        logging.info(f"[DEBUG] Sending prompt to Gemini (length: {len(prompt)} chars)")
        logging.debug(f"[DEBUG] Full prompt:\n{prompt[:500]}...")  # Log first 500 chars
        
        try:
            response = self._generate_with_fallback(
                models=self.routing_models,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                # Routing step: smaller token budget is sufficient and faster
                config={"max_output_tokens": 4000}
            )

            text = (response.text or "").strip()
            logging.info(f"[DEBUG] Received response from Gemini (length: {len(text)} chars)")
            logging.info(f"[DEBUG] Raw response text: {text}")
            
            # Clean Markdown
            original_text = text
            if text.startswith("```"):
                text = text.strip("` \n")
                text = text.replace("json", "", 1).strip()
                logging.info(f"[DEBUG] Cleaned markdown from response. Original: '{original_text[:100]}...', Cleaned: '{text[:100]}...'")
            
            # Try multiple parsing methods
            parsed_result = None
            parse_method = None
            
            # Method 1: Try ast.literal_eval
            try:
                import ast
                parsed_result = ast.literal_eval(text)
                parse_method = "ast.literal_eval"
                logging.info(f"[DEBUG] Successfully parsed with ast.literal_eval: {parsed_result}")
            except Exception as e1:
                logging.warning(f"[DEBUG] ast.literal_eval failed: {e1}")
                
                # Method 2: Try json.loads
                try:
                    parsed_result = json.loads(text)
                    parse_method = "json.loads"
                    logging.info(f"[DEBUG] Successfully parsed with json.loads: {parsed_result}")
                except Exception as e2:
                    logging.warning(f"[DEBUG] json.loads failed: {e2}")
                    
            # Method 3: Try to extract JSON array from text
                    try:
                        json_match = re.search(r'\[.*?\]', text, re.DOTALL)
                        if json_match:
                            json_str = json_match.group(0)
                            parsed_result = json.loads(json_str)
                            parse_method = "regex_extraction + json.loads"
                            logging.info(f"[DEBUG] Successfully parsed with regex extraction: {parsed_result}")
                    except Exception as e3:
                        logging.warning(f"[DEBUG] Regex extraction failed: {e3}")
            
            # Method 4: Attempt to repair truncated JSON list
            if parsed_result is None:
                try:
                    repaired_text = text.strip()
                    # Check if it looks like a list that was cut off
                    if repaired_text.startswith('['):
                        # If it ends with a comma, remove it
                        if repaired_text.endswith(','):
                            repaired_text = repaired_text[:-1]
                        
                        # If it doesn't end with a bracket, try to close it
                        if not repaired_text.endswith(']'):
                            # Case 1: Ends with ", just add ]
                            if repaired_text.endswith('"'):
                                repaired_text += ']'
                            # Case 2: Ends with unclosed string (e.g. "some text), need to close " then ]
                            else:
                                # Try appending "] first (assuming logic was inside a string)
                                try:
                                    temp_repair = repaired_text + '"]'
                                    parsed_result = json.loads(temp_repair)
                                    parse_method = "repair_truncated_json_string"
                                    logging.info(f"[DEBUG] Successfully parsed with repair (appended '\"]'): {parsed_result}")
                                except json.JSONDecodeError:
                                    # Fallback: just append ] (assuming logic was inside a number or boolean or null)
                                    try:
                                        temp_repair = repaired_text + ']'
                                        parsed_result = json.loads(temp_repair)
                                        parse_method = "repair_truncated_json_bracket"
                                        logging.info(f"[DEBUG] Successfully parsed with repair (appended ']'): {parsed_result}")
                                    except json.JSONDecodeError:
                                        # Last resort: if it ends with unexpected char, maybe trim until last comma and close
                                        if ',' in repaired_text:
                                            rpos = repaired_text.rfind(',')
                                            temp_repair = repaired_text[:rpos] + ']'
                                            parsed_result = json.loads(temp_repair)
                                            parse_method = "repair_truncated_json_trim_last"
                                            logging.info(f"[DEBUG] Successfully parsed with repair (trimmed to last comma): {parsed_result}")
                except Exception as e4:
                    logging.warning(f"[DEBUG] JSON repair failed: {e4}")

            if parsed_result is not None and isinstance(parsed_result, list):
                result = [str(x).strip() for x in parsed_result][:max_files]
                logging.info(f"[DEBUG] Returning {len(result)} relevant files (parsed with {parse_method}): {result}")
                return result
            else:
                logging.error(f"[DEBUG] Failed to parse response as list. Parsed result: {parsed_result}, Type: {type(parsed_result)}")
                logging.error(f"[DEBUG] Response text that failed to parse: '{text}'")
        
        except Exception as e:
            logging.error(f"[DEBUG] Exception in get_relevant_files: {e}", exc_info=True)

        logging.warning(f"[DEBUG] Returning empty list - no relevant files found")
        return []

    def upload_file_if_needed(self, local_path: str, process_name: str, cache_key: Optional[str] = None) -> Optional[str]:
        """
        Upload a file to Gemini if not already cached for this project.

        - local_path: concrete filesystem path used for existence checks and upload.
        - cache_key: stable identifier used for caching (defaults to local_path).
          In local filesystem mode this is typically the resolved absolute path.
          In S3 mode this should be the underlying storage identifier (e.g. S3 key)
          so that multiple temp downloads of the same object reuse the same Gemini file.
        """
        logging.info(f"[DEBUG] upload_file_if_needed called: local_path='{local_path}', process_name='{process_name}', cache_key='{cache_key}'")

        key = cache_key or local_path
        
        # Check cache first (load specific entry for this path/identifier)
        cache = self._load_upload_cache(process_name, local_path=key)
        logging.debug(f"[DEBUG] Cache lookup result for key '{key}': {cache}")
        
        if key in cache:
            file_id = cache[key]
            logging.info(f"[DEBUG] Found cached file ID: {file_id}")
            try:
                file_obj = self.client.files.get(name=file_id)
                logging.debug(f"[DEBUG] Cached file state: {file_obj.state}")
                if file_obj.state == "ACTIVE":
                    logging.info(f"[DEBUG] Using cached file (ACTIVE): {file_id}")
                    return file_id
            except Exception as e:
                logging.warning(f"[DEBUG] Cached file {file_id} invalid. Error: {e}. Re-uploading.")

        if not os.path.exists(local_path):
            logging.error(f"[DEBUG] File not found: {local_path}")
            logging.error(f"[DEBUG] File exists check failed - path may be incorrect or file was moved/deleted")
            return None
        
        logging.info(f"[DEBUG] File exists, proceeding with upload: {local_path}")

        # Check if it's an image and needs processing
        ext = os.path.splitext(local_path)[1].lower()
        is_image = ext in ['.png', '.jpg', '.jpeg', '.bmp', '.tiff']
        
        upload_path = local_path
        temp_file = None
        
        if is_image:
            try:
                # Create a temp file for the processed image
                fd, temp_path = tempfile.mkstemp(suffix=ext)
                os.close(fd)
                
                logging.info(f"Processing image for OCR: {local_path}")
                if process_image_for_ocr(local_path, temp_path):
                    upload_path = temp_path
                    temp_file = temp_path
                else:
                    logging.warning(f"Image processing failed, using original: {local_path}")
            except Exception as e:
                logging.error(f"Error setting up temp file for image processing: {e}")

        # Upload
        try:
            logging.info(f"[DEBUG] Uploading file to Gemini: {upload_path}")
         
            try:
                uploaded_file = self.client.files.upload(file=upload_path)
            except TypeError:
                uploaded_file = self.client.files.upload(path=upload_path)
            logging.info(f"[DEBUG] File uploaded, Gemini file name: {uploaded_file.name}")
            
            # Clean up temp file
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    logging.debug(f"[DEBUG] Cleaned up temp file: {temp_file}")
                except Exception as e:
                    logging.warning(f"[DEBUG] Failed to remove temp file {temp_file}: {e}")
            
            # Wait for processing
            logging.info(f"[DEBUG] Waiting for file to become ACTIVE (max ~15 seconds)...")
            for attempt in range(15):
                file_check = self.client.files.get(name=uploaded_file.name)
                logging.debug(f"[DEBUG] File check attempt {attempt + 1}/30: state={file_check.state}")
                if file_check.state == "ACTIVE":
                    logging.info(f"[DEBUG] File is ACTIVE, saving to cache and returning: {uploaded_file.name}")
                    self._save_upload_cache(process_name, key, uploaded_file.name)
                    return uploaded_file.name
                elif file_check.state == "FAILED":
                    logging.error(f"[DEBUG] File upload failed (state=FAILED): {local_path}")
                    return None
                time.sleep(1)
            
            logging.error(f"[DEBUG] File upload timed out after 15 seconds: {local_path}")
            return None
        except Exception as e:
            logging.error(f"[DEBUG] Exception uploading file {local_path}: {e}", exc_info=True)
            return None

    def upload_user_file_for_comparison(self, local_path: str) -> Optional[str]:
        """
        Upload a user-provided file to Gemini for comparison (no project cache).
        Returns Gemini file name (e.g. "files/xxx") when ACTIVE, else None.
        """
        if not os.path.exists(local_path):
            logging.error(f"[DEBUG] User comparison file not found: {local_path}")
            return None
        try:
            try:
                uploaded_file = self.client.files.upload(file=local_path)
            except TypeError:
                uploaded_file = self.client.files.upload(path=local_path)
            for _ in range(15):
                fobj = self.client.files.get(name=uploaded_file.name)
                if fobj.state == "ACTIVE":
                    return uploaded_file.name
                if fobj.state == "FAILED":
                    logging.error(f"[DEBUG] User comparison file upload FAILED: {local_path}")
                    return None
                time.sleep(1)
            logging.error(f"[DEBUG] User comparison file upload timed out: {local_path}")
            return None
        except Exception as e:
            logging.error(f"[DEBUG] User comparison upload error: {e}", exc_info=True)
            return None

    def identify_visual_pages(self, question: str, file_id: str) -> List[int]:
        """
        Identify pages/indices containing visuals relevant to the question.
        Returns 0-based page numbers.
        """
        # Determine if it's a PDF by checking file metadata from Gemini
        logging.info(f"[Visual Intel] Getting file metadata for: {file_id}")
        file_obj = self.client.files.get(name=file_id)
        is_pdf = file_obj.mime_type == "application/pdf"
        logging.info(f"[Visual Intel] File type: {file_obj.mime_type}, is_pdf: {is_pdf}")

        if not is_pdf:
            # For non-PDF files (images, etc), we assume the whole file is the visual.
            # We return index [0] to indicate the "first page/image".
            logging.info(f"[Visual Intel] Non-PDF file, returning page [0]")
            return [0]

        # Same prompt as old_code process_qna/generic_process_qna.py identify_relevant_pages_via_gemini
        prompt = f"""
    You are analyzing an INTERNAL engineering PDF document.

    THIS IS A VISUAL-ONLY TASK.
    ABSOLUTE RULES:
    - You MUST look at the visual content of each page.
    - You MUST IGNORE all text, paragraphs, tables, and written descriptions.
    - if any visual looks like a table ignore it
    - if any visual looks like complete textual document ignore it

    STRICT EXCLUSIONS:
    - Pages with only text, tables, or bullet points are INVALID.
    - Pages with headings or captions but no drawings are INVALID.
    - Pages with purely descriptive content are INVALID.

    TASK:
    - Identify ONLY those pages that contain ACTUAL images
    relevant to the question below.

    QUESTION:
    {question}

    OUTPUT RULES:
    - Return ONLY a JSON array of 1-based page numbers.
    - Do NOT explain.
    - Do NOT include text.
    - Do NOT include markdown.
    - If any image contain tabular data, ignore it
    - If NO valid visual pages exist, return [].
    """
        try:
            # With google-genai 1.x, pass a simple contents list (string + file).
            response = self._generate_with_fallback(
                models=self.routing_models,
                contents=[prompt, types.Part.from_uri(file_uri=file_obj.uri, mime_type=file_obj.mime_type)],
                config={"max_output_tokens": 300}
            )
            import ast
            text = (response.text or "").strip()
            original_text = text
            # Clean Markdown if any
            if text.startswith("```"):
                text = text.strip("` \n")
                text = text.replace("json", "", 1).strip()

            parsed = None

            # First try ast.literal_eval on the raw (cleaned) text
            try:
                parsed = ast.literal_eval(text)
            except Exception:
                # Fallback: try json.loads
                try:
                    parsed = json.loads(text)
                except Exception:
                    # Fallback: extract the first [...] block and parse it
                    try:
                        match = re.search(r'\[.*?\]', text, re.DOTALL)
                        if match:
                            block = match.group(0)
                            try:
                                parsed = json.loads(block)
                            except Exception:
                                parsed = ast.literal_eval(block)
                    except Exception:
                        parsed = None

            # Last-resort fallback: pull out integers from whatever the model returned
            if parsed is None:
                try:
                    nums = re.findall(r'\d+', text)
                    parsed = [int(n) for n in nums]
                except Exception:
                    parsed = None

            if isinstance(parsed, list):
                return [max(0, int(p) - 1) for p in parsed if isinstance(p, int) or (isinstance(p, str) and p.isdigit())]

            logging.warning(f"[Visual Intel] Failed to parse visual pages from model output: {original_text}")
        except Exception as e:
            # Log as warning so it does not look like a fatal error; visual extraction is best-effort only.
            logging.warning(f"[Visual Intel] Error identifying visual pages: {e}")

        return []

    def generate_document_description(self, local_path: str, max_words: int = 50) -> Optional[str]:
        """
        Generate a short description for a document strictly based on its content.
        Returns a description with at most `max_words` words, or None on failure.
        """
        try:
            if not os.path.exists(local_path):
                logging.error(f"[Doc Summary] File not found for description generation: {local_path}")
                return None

            file_id = self.upload_user_file_for_comparison(local_path)
            if not file_id:
                logging.error(f"[Doc Summary] Failed to upload file for description: {local_path}")
                return None

            file_obj = self.client.files.get(name=file_id)

            prompt = f"""
You are analyzing a single PDF document that an internal admin has uploaded.

TASK:
- Generate a concise description of what this document contains.

STRICT RULES:
- Base your description STRICTLY on the document content only.
- Maximum {max_words} words.
- Use neutral, professional wording.
- Do NOT include any information that is not clearly implied by the document.
- Output ONLY the description text. No quotes, no labels, no bullet points, no explanation.
"""

            response = self._generate_with_fallback(
                models=self.answer_models,
                contents=[
                    prompt,
                    types.Part.from_uri(file_uri=file_obj.uri, mime_type=file_obj.mime_type),
                ],
                config={"max_output_tokens": 150},
            )

            if not response:
                logging.error("[Doc Summary] Empty response object from Gemini for description generation")
                return None

            # Prefer the convenience .text property, but fall back to candidates if needed.
            raw_text = getattr(response, "text", None)

            if not raw_text and hasattr(response, "candidates"):
                try:
                    parts_text: List[str] = []
                    for cand in getattr(response, "candidates", []) or []:
                        content = getattr(cand, "content", None)
                        if not content:
                            continue
                        for part in getattr(content, "parts", []) or []:
                            part_text = getattr(part, "text", None)
                            if part_text:
                                parts_text.append(str(part_text))
                    raw_text = " ".join(parts_text)
                except Exception as extract_err:
                    logging.warning(f"[Doc Summary] Failed to extract text from candidates: {extract_err}", exc_info=True)

            if not raw_text:
                logging.error("[Doc Summary] Gemini returned no text for description generation")
                return None

            text = str(raw_text).strip()
            text = re.sub(r"<br\s*/?>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()

            # Enforce word limit
            words = text.split()
            if len(words) > max_words:
                text = " ".join(words[:max_words])

            return text
        except Exception as e:
            logging.error(f"[Doc Summary] Error generating document description: {e}", exc_info=True)
            return None

    def generate_comparison_with_project_docs(
        self,
        question: str,
        process_name: str,
        user_file_ids: List[str],
        chat_history: Optional[List[Tuple[str, str]]] = None,
        style_mode: Optional[str] = None,
        extract_visuals: bool = True,
    ) -> Dict:
        """
        Compare one (or more) user-uploaded files with project-relevant documents.
        Gets project files via routing, uploads them to Gemini, then runs comparison.
        """
        user_file_ids = [f for f in (user_file_ids or []) if f]
        project_filenames = self.get_relevant_files(question, process_name, max_files=MAX_ATTACHMENTS)
        project_gemini_ids: List[str] = []
        project = Project.query.filter_by(name=process_name).first()
        if project:
            # Determine whether project documents are stored in S3 so we can use a stable cache key (storage identifier)
            try:
                storage = get_document_storage()
                use_s3_for_docs = storage.use_s3
            except Exception:
                use_s3_for_docs = False

            for fname in project_filenames:
                meta = ProjectMetadata.query.filter(
                    ProjectMetadata.project_id == project.id,
                    ProjectMetadata.file_name.ilike(f"%{fname}%"),
                ).first()
                if meta:
                    resolved_path, found = self._resolve_file_path(meta.file_path, process_name)
                    if found and resolved_path:
                        cache_key = meta.file_path if use_s3_for_docs else None
                        fid = self.upload_file_if_needed(resolved_path, process_name, cache_key=cache_key)
                        if fid and fid not in project_gemini_ids:
                            project_gemini_ids.append(fid)
        # Order as in old_code: internal (project) docs first, then user-uploaded doc
        all_ids = list(dict.fromkeys(project_gemini_ids + user_file_ids))
        if len(all_ids) < 2:
            return {
                "answer": "Comparison requires at least one uploaded document and at least one relevant project document. No relevant project documents were found for your question.",
                "files": [],
                "relevant_files": [],
                "visuals": [],
            }
        return self.generate_comparison(
            question=question,
            process_name=process_name,
            internal_file_ids=project_gemini_ids,
            user_file_ids=user_file_ids,
            chat_history=chat_history or [],
            style_mode=style_mode,
        )

    def generate_comparison(
        self,
        question: str,
        process_name: str,
        internal_file_ids: Optional[List[str]] = None,
        user_file_ids: Optional[List[str]] = None,
        chat_history: Optional[List[Tuple[str, str]]] = None,
        style_mode: Optional[str] = None,
    ) -> Dict:
        """
        Compare documents. When user_file_ids is provided, follows old_code authority rule:
        internal (project) docs are the ONLY source of truth; user doc is for comparison/context only.
        Builds labeled payload: INTERNAL AUTHORITATIVE then USER EXTERNAL (same as old_code).
        """
        internal_file_ids = [f for f in (internal_file_ids or []) if f]
        user_file_ids = [f for f in (user_file_ids or []) if f]
        has_user_doc = len(user_file_ids) > 0
        history_list = chat_history or []
        history_text = ""
        for q, a in history_list:
            try:
                history_text += f"User: {q}\nAssistant: {a}\n\n"
            except Exception:
                continue
        style_instruction = "Provide a short, simple, direct answer in 3–5 lines."
        if style_mode == "research":
            style_instruction = "Provide a detailed, research-style answer with supporting points and references from the attached documents."
        elif style_mode == "analytical":
            style_instruction = "Provide an analytical answer including comparisons, evaluation, tables, and reasoning."
        elif style_mode == "expert":
            style_instruction = "Provide a very deep, expert-level process engineering answer with calculations, tables, and professional insights."

        valid_files = []
        contents_payload = []

        # 1. Internal docs with INTERNAL AUTHORITATIVE labels (same as old_code)
        for fid in internal_file_ids:
            try:
                f_obj = self.client.files.get(name=fid)
                if f_obj.state == "ACTIVE":
                    valid_files.append(f_obj.display_name or fid)
                    contents_payload.append({
                        "role": "user",
                        "parts": [
                            {"text": "--- BEGIN INTERNAL AUTHORITATIVE DOCUMENT ---"},
                            {"file_data": {"file_uri": f_obj.uri, "mime_type": f_obj.mime_type}},
                            {"text": "--- END INTERNAL AUTHORITATIVE DOCUMENT ---"},
                        ],
                    })
                else:
                    logging.warning(f"File {fid} is not ACTIVE (State: {f_obj.state}). Skipping.")
            except Exception as e:
                logging.error(f"Error accessing file {fid} for comparison: {e}")

        # 2. User doc(s) with USER EXTERNAL label (same as old_code)
        if has_user_doc:
            for fid in user_file_ids:
                try:
                    f_obj = self.client.files.get(name=fid)
                    if f_obj.state == "ACTIVE":
                        valid_files.append(f_obj.display_name or fid)
                        contents_payload.append({
                            "role": "user",
                            "parts": [
                                {"text": "--- BEGIN USER EXTERNAL DOCUMENT FOR COMPARISON ---"},
                                {"file_data": {"file_uri": f_obj.uri, "mime_type": f_obj.mime_type}},
                                {"text": "--- END USER EXTERNAL DOCUMENT FOR COMPARISON ---"},
                            ],
                        })
                    else:
                        logging.warning(f"User file {fid} is not ACTIVE (State: {f_obj.state}). Skipping.")
                except Exception as e:
                    logging.error(f"Error accessing user file {fid} for comparison: {e}")

        if len(contents_payload) < 2:
            return {
                "answer": "Please provide at least two valid documents to compare (e.g. one uploaded file and project documents).",
                "files": valid_files,
                "relevant_files": valid_files,
                "visuals": [],
            }

        # Full comparison instruction from old_code generic_process_qna.py (when use_uploaded_doc and user_pdf_id)
        comparison_instruction = ""
        if has_user_doc:
            comparison_instruction = """
IMPORTANT IDENTIFICATION RULES:
- Documents wrapped in 'INTERNAL AUTHORITATIVE' tags are internal documents and your ONLY source of truth.
- The document wrapped in 'USER EXTERNAL' tags is the one you are auditing/comparing.
- You MUST NOT compare INTERNAL documents with each other.
- Comparison must ONLY be between:
    USER_EXTERNAL_COMPARISON_DOCUMENT
    vs
    INTERNAL_AUTHORITATIVE_DOCUMENT

IMPORTANT RULES REGARDING UPLOADED USER DOCUMENT:
- The uploaded PDF is NOT an authoritative source.
- It is NOT part of the internal document system but relates to the content present internally.
- It may ONLY be used for comparison or contextual understanding with respect to our internal database.
- All factual statements and verifications MUST come exclusively from the internal documents.
- If the uploaded PDF contains information not relative to what is present in the internal documents,
you MUST ignore it.
- If internal documents do not contain enough information to answer or compare,
clearly state this
- After uploading the document, it should be analysed and should tell the user what this document contains
and how it is relevant or not relevant to the internal dataset.
- Do not specify any company/organisation or any personal detail from the internal documents or uploaded one

MANDATORY COMPARISON REQUIREMENT (ONLY WHEN USER DOCUMENT IS PROVIDED):
If an uploaded user document is attached:
- You MUST perform an explicit comparison.
- You MUST NOT ignore the uploaded document.
- You MUST evaluate it ONLY against internal documents.
Any disagreement or conflict MUST be resolved in favor of internal documents.

FORMAT RULE (STRICT):
If a user-uploaded document is provided, your response MUST follow
this exact structure:

1. Uploaded Document Summary
   - High-level description of what the uploaded document contains
   - Its intended purpose and scope
   - Its relevance or non-relevance to the internal document set

2. Sanity & Correctness Assessment
   - Assess the logical structure, consistency, clarity, and completeness
     of the uploaded document
   - Do NOT treat the uploaded document as factually correct
   - Do NOT validate technical accuracy using the uploaded document itself
   - Identify ambiguities, inconsistencies, outdated framing, or gaps
     strictly from a technical and documentation perspective.

3. Comparison Outcome
   (Alignment: Full / Partial / Conflict / Not Relevant)
   - Explicit comparison ONLY against internal documents
   - Any disagreement MUST be resolved in favor of internal documents

4. Documentation Improvement & Enhancement Suggestions
   - Suggest how the uploaded document could be modified, refined,
     or enhanced to better align with internal documents
   - Focus ONLY on:
     - Structure
     - Clarity
     - Terminology consistency
     - Coverage gaps
     - Formatting and organization
   - Do NOT introduce new facts from the uploaded document

5. Final Conclusion (comparison-based)
   - Provide the final authoritative position strictly based on INTERNAL documents.
   - Clearly state whether the USER_EXTERNAL_COMPARISON_DOCUMENT is aligned,
     partially aligned, conflicting, or not relevant.
   - If internal documents lack sufficient information for comparison,
     clearly state this.

AUTHORITATIVE SOURCE RULE:
- Internal documents are the ONLY source of truth.
- Uploaded user documents are NEVER a source of facts.
"""

        comparison_prompt = f"""
You are a senior chemical process engineer specializing in {process_name} fertilizer plants.

{comparison_instruction}

Below is the ongoing chat history between the user and you (if any):
{history_text}

Use ONLY the INTERNAL process documents (if provided) to answer the question.
If no INTERNAL documents are attached, do not provide any information and say "Relevant documents missing."

Provide a clear, technically accurate answer.
Respond with a clean, direct answer only—
do not include any explanation, reasoning, or background information
unless the question explicitly asks for it (e.g., starts with or contains words like "why", "how", or "explain").

Do not quote or mention any reference documents, tag numbers, equipment or instrument tags, document or drawing numbers,
equipment codes, line numbers, stream numbers, fluid codes, or pipe specification information in your response.
These items must be excluded entirely from the answer.

If the answer involves numerical data, process parameters, or comparisons,
present them in a **well-formatted Markdown table**.

User's new question: {question}
Answer style: {style_instruction}
"""

        # 3. Add prompt last (same order as old_code)
        contents_payload.append({"role": "user", "parts": [{"text": comparison_prompt}]})

        try:
            # Build flat list: label + file + label per doc, then prompt (same structure as old_code)
            api_parts = []
            for item in contents_payload[:-1]:
                for p in item.get("parts", []):
                    if "file_data" in p:
                        api_parts.append(types.Part.from_uri(file_uri=p["file_data"]["file_uri"], mime_type=p["file_data"]["mime_type"]))
                    else:
                        api_parts.append(p["text"])
            api_parts.append(comparison_prompt)
            response = self._generate_with_fallback(
                models=self.answer_models,
                contents=api_parts,
                # Cap output length to keep comparison responses fast and avoid timeouts
                config={"max_output_tokens": 5000}
            )
            answer_text = (response.text or "").strip()
            answer_text = re.sub(r"<br\s*/?>", "\n", answer_text)
            try:
                if response.candidates and response.candidates[0].finish_reason != "STOP":
                    logging.warning("Comparison response may be incomplete (finish_reason=%s).", getattr(response.candidates[0], "finish_reason", "?"))
            except Exception:
                pass
            return {
                "answer": answer_text,
                "files": valid_files,
                "relevant_files": valid_files,
                "visuals": [],
            }
        except Exception as e:
            logging.error(f"Comparison generation failed: {e}")
            return {"answer": f"Error generating comparison: {str(e)}", "files": valid_files, "relevant_files": valid_files, "visuals": []}
    def generate_answer(
        self,
        question: str,
        process_name: str,
        chat_history: List[Tuple[str, str]] = [],
        answer_mode: str = 'basic',
        style_mode: Optional[str] = None,
        related_processes: Optional[List[str]] = None,
        extract_visuals: bool = True,
    ) -> Dict:
        """
        Main method to generate an answer.
        Returns a dict with 'answer', 'relevant_files', 'visual_pages' (optional).
        """
        # 1. Get Relevant Files from DB + Gemini
        # For cross‑project mode, we optionally consider related processes as well.
        relevant_filenames: List[str] = []
        global_context = ""

        # attachment_ids: Gemini file IDs
        # full_file_paths: resolved local filesystem paths (for logging / uploads)
        # storage_paths: stable storage identifiers (ProjectMetadata.file_path / S3 key)
        #                used externally (e.g. visuals, /api/visual) so we never depend on temp paths.
        attachment_ids: List[str] = []
        full_file_paths: List[str] = []
        storage_paths: List[str] = []
        process_file_map: Optional[Dict[str, List[str]]] = None  # process_name -> [file_id]; used for parent/child labels

        # Single‑project routing (default path)
        if answer_mode != "cross_project" or not related_processes:
            relevant_filenames = self.get_relevant_files(question, process_name)

            logging.info(f"[DEBUG] Found {len(relevant_filenames)} relevant filenames from Gemini: {relevant_filenames}")
            
            if relevant_filenames:
                project = Project.query.filter_by(name=process_name).first()
                if project:
                    # Decide cache key strategy once per call based on storage mode
                    try:
                        storage = get_document_storage()
                        use_s3_for_docs = storage.use_s3
                    except Exception:
                        use_s3_for_docs = False

                    for fname in relevant_filenames:
                        logging.info(f"[DEBUG] Searching for file matching: '{fname}' in project {process_name}")
                        meta = ProjectMetadata.query.filter(
                            ProjectMetadata.project_id == project.id,
                            ProjectMetadata.file_name.ilike(f"%{fname}%")  # Flexible match
                        ).first()
                        if meta:
                            logging.info(f"[DEBUG] Found metadata entry: ID={meta.id}, file_name='{meta.file_name}', file_path='{meta.file_path}'")
                            resolved_path, found = self._resolve_file_path(meta.file_path, process_name)
                            if found and resolved_path:
                                logging.info(f"[DEBUG] File resolved successfully: {resolved_path}")
                                cache_key = meta.file_path if use_s3_for_docs else None
                                fid = self.upload_file_if_needed(resolved_path, process_name, cache_key=cache_key)
                                if fid:
                                    logging.info(f"[DEBUG] File uploaded to Gemini with ID: {fid}")
                                    attachment_ids.append(fid)
                                    full_file_paths.append(resolved_path)
                                    # Store the stable storage identifier from metadata (not the temp/local path)
                                    storage_paths.append(meta.file_path)
                                else:
                                    logging.error(f"[DEBUG] Failed to upload file to Gemini: {resolved_path}")
                            else:
                                logging.warning(f"[DEBUG] File not found (skipping): {meta.file_path} for project {process_name}")
                        else:
                            logging.warning(f"[DEBUG] No metadata entry found matching filename: '{fname}' in project {process_name}")
                else:
                    logging.error(f"[DEBUG] Project {process_name} not found when processing relevant files")
            else:
                logging.warning(f"[DEBUG] No relevant filenames returned from Gemini for question: '{question}'")
        else:
            # Cross‑project routing: parent + related processes (build process_file_map for parent/child labels)
            process_file_map = {}
            all_projects = [process_name] + list({p for p in (related_processes or []) if p != process_name})
            seen_paths = set()

            for pname in all_projects:
                files_for_project = self.get_relevant_files(question, pname)
                if not files_for_project:
                    continue

                project = Project.query.filter_by(name=pname).first()
                if not project:
                    continue

                # Decide cache key strategy once per project based on storage mode
                try:
                    storage = get_document_storage()
                    use_s3_for_docs = storage.use_s3
                except Exception:
                    use_s3_for_docs = False

                logging.info(f"[DEBUG] Processing {len(files_for_project)} files for project {pname}: {files_for_project}")
                
                for fname in files_for_project:
                    logging.info(f"[DEBUG] Searching for file matching: '{fname}' in project {pname}")
                    meta = ProjectMetadata.query.filter(
                        ProjectMetadata.project_id == project.id,
                        ProjectMetadata.file_name.ilike(f"%{fname}%")
                    ).first()
                    if not meta:
                        logging.warning(f"[DEBUG] No metadata entry found matching filename: '{fname}' in project {pname}")
                        continue

                    logging.info(f"[DEBUG] Found metadata entry: ID={meta.id}, file_name='{meta.file_name}', file_path='{meta.file_path}'")
                    resolved_path, found = self._resolve_file_path(meta.file_path, pname)
                    if not found or not resolved_path:
                        logging.warning(f"[DEBUG] File not found (skipping): {meta.file_path} for project {pname}")
                        continue

                    if resolved_path in seen_paths:
                        logging.debug(f"[DEBUG] File already processed (duplicate): {resolved_path}")
                        continue
                    seen_paths.add(resolved_path)

                    logging.info(f"[DEBUG] Uploading file: {resolved_path}")
                    cache_key = meta.file_path if use_s3_for_docs else None
                    fid = self.upload_file_if_needed(resolved_path, pname, cache_key=cache_key)
                    if fid:
                        logging.info(f"[DEBUG] File uploaded to Gemini with ID: {fid}")
                        attachment_ids.append(fid)
                        full_file_paths.append(resolved_path)
                        # Use the underlying storage identifier (meta.file_path) for any external references
                        storage_paths.append(meta.file_path)
                        relevant_filenames.append(fname)
                        process_file_map.setdefault(pname, []).append(fid)
                    else:
                        logging.error(f"[DEBUG] Failed to upload file to Gemini: {resolved_path}")

        # 2. Answer only from documents: if no documents found, do not call the LLM (same as old_code)
        logging.info(f"[DEBUG] Total attachment IDs collected: {len(attachment_ids)}")
        logging.info(f"[DEBUG] Attachment IDs: {attachment_ids}")
        logging.info(f"[DEBUG] Full file paths: {full_file_paths}")
        
        if not attachment_ids:
            logging.warning(f"[DEBUG] No attachments found - returning early with error message")
            return {
                "answer": "Relevant documents missing. I can only answer based on the documents available for this process.",
                "relevant_files": [],
                "visuals": []
            }

        # 3. Format Chat History
        history_text = ""
        for q, a in chat_history:
            history_text += f"User: {q}\nAssistant: {a}\n\n"

        # 4. Prepare Prompt & Tools based on Mode (same prompts and style text as old_code generic_process_qna.py)
        tools = None
        style_instruction = "Provide a short, simple, direct answer in 3–5 lines."
        comparison_instruction = ""
        global_context = ""

        mode_for_style = style_mode or answer_mode

        if mode_for_style == "basic":
            style_instruction = "Provide a short, simple, direct answer. If the answer involves numerical data or comparisons, use a Markdown table instead of plain text."
        elif mode_for_style == "research":
            tools = [{"google_search": {}}]
            style_instruction = "Provide a detailed, research-style answer with supporting points and references from the attached documents."
        elif mode_for_style == "analytical":
            style_instruction = "Provide an analytical answer including comparisons, evaluation, tables, and reasoning."
        elif mode_for_style == "expert":
            style_instruction = "Provide a very deep, expert-level process engineering answer with calculations, tables, and professional insights."

        if answer_mode == "cross_project":
            global_context = """
            GLOBAL PROCESS DEPENDENCIES:
            1. Ammonia Plant: Produces Liquid Ammonia, used as raw material for DAP, SAP, and Urea.
            2. Sulfuric Acid Plant (SAP): Produces H2SO4, used in Phosphoric Acid Plant (PAP).
            3. Phosphoric Acid Plant (PAP): Dilute H3PO4 is concentrated and used in DAP plant.
            4. DAP Plant: Uses Ammonia and Phosphoric Acid to produce Di-Ammonium Phosphate.
            """

        # process_relationship_instruction for cross_project with parent/child (same as old_code generic_process_qna.py)
        process_relationship_instruction = ""
        if process_file_map and len(process_file_map) > 1:
            parent_process = list(process_file_map.keys())[0]
            child_processes = list(process_file_map.keys())[1:]
            process_relationship_instruction = f"""
PROCESS HIERARCHY IDENTIFICATION RULES:

- The PRIMARY PROCESS is: {parent_process}
- The following are DEPENDENT / DOWNSTREAM PROCESSES:
{', '.join(child_processes)}

DOCUMENT STRUCTURE RULES:
- Documents wrapped in 'PARENT PROCESS DOCUMENT' belong to the primary process.
- Documents wrapped in 'CHILD PROCESS DOCUMENT' belong to dependent processes.
- You MUST clearly distinguish between parent and child process data.
- Parent process is the primary authority for answering the question.
- Child process documents may only be used for:
    - Dependency clarification
    - Interconnection understanding
    - Downstream impact analysis

- FORMAT REQUIREMENT: Present the answer in clearly separated sections using bold headings in this order:
1) {parent_process} (Primary Process)
2) Each dependent process output separately ({', '.join(child_processes)}) (Dependent process)

- Do NOT mix parent and child process data incorrectly.
- If information conflicts, treat parent process as primary scope unless question explicitly targets child process.
"""

        # Same unified prompt as old_code process_qna/generic_process_qna.py ask_gemini_with_attachments
        prompt = f"""
You are a senior chemical process engineer specializing in {process_name} fertilizer plants.

{comparison_instruction}
{process_relationship_instruction}

Below is the ongoing chat history between the user and you (if any):
{history_text}


Use ONLY the INTERNAL process documents (if provided) to answer the question.
If no INTERNAL documents are attached, do not provide any information and say "Relevant documents missing."


Provide a clear, technically accurate answer.
Respond with a clean, direct answer only—
do not include any explanation, reasoning, or background information
unless the question explicitly asks for it (e.g., starts with or contains words like "why", "how", or "explain").

Do not quote or mention any reference documents, tag numbers, equipment or instrument tags, document or drawing numbers,
equipment codes, line numbers, stream numbers, fluid codes, or pipe specification information in your response.
These items must be excluded entirely from the answer.

If the answer involves numerical data, process parameters, or comparisons,
present them in a **well-formatted Markdown table**.

User’s new question: {question}
Answer style: {style_instruction}
"""


        attachments = []
        for fid in attachment_ids:
            try:
                # Validating file attachment
                file_obj = self.client.files.get(name=fid)
                if file_obj.state == "ACTIVE":
                    attachments.append(types.Part.from_uri(file_uri=file_obj.uri, mime_type=file_obj.mime_type))
                else:
                    logging.warning(f"Skipping attachment {fid} - State is {file_obj.state}")
            except Exception as e:
                logging.error(f"Failed to retrieve attachment {fid}: {e}")
        
        # Check if we have valid attachments for modes that strictly require them?
        # For now, we proceed.
        
        # google-genai 1.x: pass a simple contents list with the prompt text + file objects.
        # This matches the documented pattern: contents=["...", myfile]
        # Build api_contents: labeled PARENT/CHILD when cross_project with multiple processes (same as old_code)
        if process_file_map and len(process_file_map) > 1:
            api_parts = []
            for pname, fids in process_file_map.items():
                for fid in fids:
                    try:
                        f_obj = self.client.files.get(name=fid)
                        if f_obj.state != "ACTIVE":
                            continue
                        is_parent = pname == list(process_file_map.keys())[0]
                        if is_parent:
                            label = f"--- BEGIN PARENT PROCESS DOCUMENT: {pname} ---"
                            end_label = f"--- END PARENT PROCESS DOCUMENT: {pname} ---"
                        else:
                            label = f"--- BEGIN CHILD PROCESS DOCUMENT: {pname} ---"
                            end_label = f"--- END CHILD PROCESS DOCUMENT: {pname} ---"
                        api_parts.append(label)
                        api_parts.append(types.Part.from_uri(file_uri=f_obj.uri, mime_type=f_obj.mime_type))
                        api_parts.append(end_label)
                    except Exception as e:
                        logging.error(f"Failed to retrieve file {fid} for process {pname}: {e}")
            api_parts.append(prompt)
            api_contents = api_parts
        else:
            api_contents = [prompt]
            if attachments:
                api_contents.extend(attachments)
        
        # If no attachments found but we expected some, we might proceed or warn.
        # Proceeding allows the model to maybe use internal training if we allowed it, but prompt says "ONLY INTERNAL".
        
        # Pass tools if any (e.g. Google Search)
        # Note: tools usually requires a specific config structure in newer SDKs, 
        # but pure dict `[{"google_search": {}}]` is often supported or `types.Tool(google_search=...)`
        # We will pass it to `generate_content` via our helper.
        
        # For fallback helper, we need to update it to accept tools/tool_config if we haven't already.
        # But wait, `_generate_with_fallback` passes `config` as `generation_config`. Tools are a separate arg.
        # Let's adjust `_generate_with_fallback` call to pass `tools` inside `config` or modify `_generate_with_fallback`?
        # `genai` SDK usually takes `tools` as a separate argument to `generate_content`.
        # I will modify client.models.generate_content call in `_generate_with_fallback` implicitly? 
        # No, better to pass strictly what is needed.
        # Actually `generate_content` signature is (model, contents, config, tools, ...).
        # I need to update `_generate_with_fallback` to accept `tools`.
        
        response = self._generate_with_fallback(
            models=self.answer_models,
            contents=api_contents,
            # Slightly lower cap to reduce latency while keeping rich answers
            config={"max_output_tokens": 5000},
            tools=tools
        )

        answer_text = (response.text or "").strip()
        answer_text = re.sub(r"<br\s*/?>", "\n", answer_text)
        try:
            if response.candidates and response.candidates[0].finish_reason != "STOP":
                logging.warning("Answer response may be incomplete (finish_reason=%s).", getattr(response.candidates[0], "finish_reason", "?"))
        except Exception:
            pass

        # 6. (Optional) Visual Extraction for the FIRST relevant file
        #    This is for the "Visual Intelligence" panel
        visual_pages = []
        if extract_visuals and attachment_ids:
            logging.info(f"[Visual Intel] Checking {len(attachment_ids)} files for visuals...")
            for idx, fid in enumerate(attachment_ids):
                try:
                    local_path = full_file_paths[idx] if idx < len(full_file_paths) else "Unknown"
                    storage_id = storage_paths[idx] if idx < len(storage_paths) else local_path
                    logging.info(f"[Visual Intel] Checking file: {local_path} (ID: {fid}, storage_id={storage_id})")
                    pages = self.identify_visual_pages(question, fid)
                    if pages:
                        # Include all identified visual pages for this file.
                        # IMPORTANT: expose the stable storage identifier (storage_id) to the rest of the app,
                        # so /api/visual can map it back to ProjectMetadata/file storage, even in S3 mode.
                        visual_pages.append({"file_path": storage_id, "pages": pages})
                        logging.info(f"[Visual Intel] Found visuals in {local_path}: {pages} (storage_id={storage_id})")
                except Exception as e:
                    logging.error(f"[Visual Intel] Error checking file {fid}: {e}")

        return {
            "answer": answer_text,
            "relevant_files": relevant_filenames,
            "visuals": visual_pages
        }

    def generate_answer_stream(
        self,
        question: str,
        process_name: str,
        chat_history: List[Tuple[str, str]] = [],
        answer_mode: str = 'basic',
        style_mode: Optional[str] = None,
        related_processes: Optional[List[str]] = None,
        extract_visuals: bool = True,
    ):
        """
        Same setup as generate_answer but yields SSE-friendly events: {"type": "chunk", "text": "..."}
        then {"type": "done", "answer": full_text, "relevant_files": [...], "visuals": [...]}.
        Used only for single-project flow (no cross_project/comparison streaming for now).
        """
        # Reuse the same file resolution and prompt building as generate_answer (steps 1-4)
        relevant_filenames: List[str] = []
        attachment_ids: List[str] = []
        full_file_paths: List[str] = []
        storage_paths: List[str] = []
        process_file_map: Optional[Dict[str, List[str]]] = None

        if answer_mode != "cross_project" or not related_processes:
            relevant_filenames = self.get_relevant_files(question, process_name)
            if relevant_filenames:
                project = Project.query.filter_by(name=process_name).first()
                if project:
                    # Decide cache key strategy once per call based on storage mode
                    try:
                        storage = get_document_storage()
                        use_s3_for_docs = storage.use_s3
                    except Exception:
                        use_s3_for_docs = False

                    for fname in relevant_filenames:
                        meta = ProjectMetadata.query.filter(
                            ProjectMetadata.project_id == project.id,
                            ProjectMetadata.file_name.ilike(f"%{fname}%")
                        ).first()
                        if meta:
                            resolved_path, found = self._resolve_file_path(meta.file_path, process_name)
                            if found and resolved_path:
                                cache_key = meta.file_path if use_s3_for_docs else None
                                fid = self.upload_file_if_needed(resolved_path, process_name, cache_key=cache_key)
                                if fid:
                                    attachment_ids.append(fid)
                                    full_file_paths.append(resolved_path)
                                    storage_paths.append(meta.file_path)
        else:
            process_file_map = {}
            all_projects = [process_name] + list({p for p in (related_processes or []) if p != process_name})
            seen_paths = set()
            for pname in all_projects:
                files_for_project = self.get_relevant_files(question, pname)
                if not files_for_project:
                    continue
                project = Project.query.filter_by(name=pname).first()
                if not project:
                    continue

                # Decide cache key strategy once per project based on storage mode
                try:
                    storage = get_document_storage()
                    use_s3_for_docs = storage.use_s3
                except Exception:
                    use_s3_for_docs = False

                for fname in files_for_project:
                    meta = ProjectMetadata.query.filter(
                        ProjectMetadata.project_id == project.id,
                        ProjectMetadata.file_name.ilike(f"%{fname}%")
                    ).first()
                    if not meta:
                        continue
                    resolved_path, found = self._resolve_file_path(meta.file_path, pname)
                    if not found or not resolved_path:
                        continue
                    if resolved_path in seen_paths:
                        continue
                    seen_paths.add(resolved_path)
                    cache_key = meta.file_path if use_s3_for_docs else None
                    fid = self.upload_file_if_needed(resolved_path, pname, cache_key=cache_key)
                    if fid:
                        attachment_ids.append(fid)
                        full_file_paths.append(resolved_path)
                        storage_paths.append(meta.file_path)
                        relevant_filenames.append(fname)
                        process_file_map.setdefault(pname, []).append(fid)

        if not attachment_ids:
            yield {"type": "done", "answer": "Relevant documents missing. I can only answer based on the documents available for this process.", "relevant_files": [], "visuals": []}
            return

        history_text = ""
        for q, a in chat_history:
            history_text += f"User: {q}\nAssistant: {a}\n\n"

        # Match prompt building logic from generate_answer (legacy-compatible)
        tools = None
        style_instruction = "Provide a short, simple, direct answer in 3–5 lines."
        comparison_instruction = ""
        global_context = ""

        mode_for_style = style_mode or answer_mode

        if mode_for_style == "basic":
            style_instruction = "Provide a short, simple, direct answer. If the answer involves numerical data or comparisons, use a Markdown table instead of plain text."
        elif mode_for_style == "research":
            tools = [{"google_search": {}}]
            style_instruction = "Provide a detailed, research-style answer with supporting points and references from the attached documents."
        elif mode_for_style == "analytical":
            style_instruction = "Provide an analytical answer including comparisons, evaluation, tables, and reasoning."
        elif mode_for_style == "expert":
            style_instruction = "Provide a very deep, expert-level process engineering answer with calculations, tables, and professional insights."

        if answer_mode == "cross_project":
            global_context = """
            GLOBAL PROCESS DEPENDENCIES:
            1. Ammonia Plant: Produces Liquid Ammonia, used as raw material for DAP, SAP, and Urea.
            2. Sulfuric Acid Plant (SAP): Produces H2SO4, used in Phosphoric Acid Plant (PAP).
            3. Phosphoric Acid Plant (PAP): Dilute H3PO4 is concentrated and used in DAP plant.
            4. DAP Plant: Uses Ammonia and Phosphoric Acid to produce Di-Ammonium Phosphate.
            """

        process_relationship_instruction = ""
        if process_file_map and len(process_file_map) > 1:
            parent_process = list(process_file_map.keys())[0]
            child_processes = list(process_file_map.keys())[1:]
            process_relationship_instruction = f"""
PROCESS HIERARCHY IDENTIFICATION RULES:

- The PRIMARY PROCESS is: {parent_process}
- The following are DEPENDENT / DOWNSTREAM PROCESSES:
{', '.join(child_processes)}

DOCUMENT STRUCTURE RULES:
- Documents wrapped in 'PARENT PROCESS DOCUMENT' belong to the primary process.
- Documents wrapped in 'CHILD PROCESS DOCUMENT' belong to dependent processes.
- You MUST clearly distinguish between parent and child process data.
- Parent process is the primary authority for answering the question.
- Child process documents may only be used for:
    - Dependency clarification
    - Interconnection understanding
    - Downstream impact analysis

- FORMAT REQUIREMENT: Present the answer in clearly separated sections using bold headings in this order:
1) {parent_process} (Primary Process)
2) Each dependent process output separately ({', '.join(child_processes)}) (Dependent process)

- Do NOT mix parent and child process data incorrectly.
- If information conflicts, treat parent process as primary scope unless question explicitly targets child process.
"""

        # Use the exact same unified prompt template as generate_answer
        prompt = f"""
You are a senior chemical process engineer specializing in {process_name} fertilizer plants.

{comparison_instruction}
{process_relationship_instruction}

Below is the ongoing chat history between the user and you (if any):
{history_text}


Use ONLY the INTERNAL process documents (if provided) to answer the question.
If no INTERNAL documents are attached, do not provide any information and say "Relevant documents missing."


Provide a clear, technically accurate answer.
Respond with a clean, direct answer only—
do not include any explanation, reasoning, or background information
unless the question explicitly asks for it (e.g., starts with or contains words like "why", "how", or "explain").

Do not quote or mention any reference documents, tag numbers, equipment or instrument tags, document or drawing numbers,
equipment codes, line numbers, stream numbers, fluid codes, or pipe specification information in your response.
These items must be excluded entirely from the answer.

If the answer involves numerical data, process parameters, or comparisons,
present them in a **well-formatted Markdown table**.

User’s new question: {question}
Answer style: {style_instruction}
"""

        attachments = []
        for fid in attachment_ids:
            try:
                file_obj = self.client.files.get(name=fid)
                if file_obj.state == "ACTIVE":
                    attachments.append(types.Part.from_uri(file_uri=file_obj.uri, mime_type=file_obj.mime_type))
            except Exception as e:
                logging.error(f"Failed to retrieve attachment {fid}: {e}")

        if process_file_map and len(process_file_map) > 1:
            api_parts = []
            for pname, fids in process_file_map.items():
                for fid in fids:
                    try:
                        f_obj = self.client.files.get(name=fid)
                        if f_obj.state != "ACTIVE":
                            continue
                        is_parent = pname == list(process_file_map.keys())[0]
                        if is_parent:
                            label = f"--- BEGIN PARENT PROCESS DOCUMENT: {pname} ---"
                            end_label = f"--- END PARENT PROCESS DOCUMENT: {pname} ---"
                        else:
                            label = f"--- BEGIN CHILD PROCESS DOCUMENT: {pname} ---"
                            end_label = f"--- END CHILD PROCESS DOCUMENT: {pname} ---"
                        api_parts.append(label)
                        api_parts.append(types.Part.from_uri(file_uri=f_obj.uri, mime_type=f_obj.mime_type))
                        api_parts.append(end_label)
                    except Exception as e:
                        logging.error(f"Failed to retrieve file {fid} for process {pname}: {e}")
            api_parts.append(prompt)
            api_contents = api_parts
        else:
            api_contents = [prompt]
            if attachments:
                api_contents.extend(attachments)

        answer_text = ""
        try:
            for chunk_text in self._generate_stream_with_fallback(
                models=self.answer_models,
                contents=api_contents,
                config={"max_output_tokens": 5000},
                tools=tools
            ):
                answer_text += chunk_text
                yield {"type": "chunk", "text": chunk_text}
        except Exception as e:
            logging.error(f"Stream generation failed: {e}")
            yield {"type": "done", "answer": answer_text + f"\n\nError: {str(e)}", "relevant_files": relevant_filenames, "visuals": []}
            return

        answer_text = (answer_text or "").strip()
        answer_text = re.sub(r"<br\s*/?>", "\n", answer_text)

        visual_pages = []
        if extract_visuals and attachment_ids and full_file_paths:
            logging.info(f"[Visual Intel] Checking {len(attachment_ids)} files for visuals (Stream Mode)...")
            for idx, fid in enumerate(attachment_ids):
                try:
                    local_path = full_file_paths[idx] if idx < len(full_file_paths) else "Unknown"
                    storage_id = storage_paths[idx] if idx < len(storage_paths) else local_path
                    pages = self.identify_visual_pages(question, fid)
                    if pages:
                        # Include all identified visual pages for this file using the stable storage identifier.
                        visual_pages.append({"file_path": storage_id, "pages": pages})
                        logging.info(f"[Visual Intel] Found visuals in {local_path}: {pages} (Stream, storage_id={storage_id})")
                except Exception as e:
                    logging.error(f"[Visual Intel] Stream Visual intellectual checking error: {e}")

        logging.info(f"[DEBUG] Final visual_pages (Stream): {visual_pages}")
        yield {"type": "done", "answer": answer_text, "relevant_files": relevant_filenames, "visuals": visual_pages}
