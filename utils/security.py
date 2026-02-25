import os
import re
import bleach
from typing import List


def sanitize_input(text: str, max_length: int = 5000) -> str:
    """
    Sanitize and validate text input by removing HTML/script tags and enforcing length limits.
    
    Args:
        text: The input text to sanitize
        max_length: Maximum allowed length for the text
        
    Returns:
        Sanitized text string
        
    Raises:
        ValueError: If text exceeds max_length
    """
    if not text:
        return ""
    
    if len(text) > max_length:
        raise ValueError(f"Input exceeds maximum length of {max_length} characters")
    
    # Remove all HTML tags and attributes
    sanitized = bleach.clean(text, tags=[], strip=True)
    
    return sanitized.strip()


def validate_file_path(file_path: str, allowed_dirs: List[str]) -> bool:
    """
    Validate that a file path is within one of the allowed directories.
    Protects against path traversal attacks.
    
    Args:
        file_path: The absolute file path to validate
        allowed_dirs: List of allowed directory paths
        
    Returns:
        True if the path is valid and within allowed directories, False otherwise
    """
    if not file_path or not allowed_dirs:
        return False
    
    # Reject paths containing suspicious patterns
    if '..' in file_path or file_path.startswith('/etc') or file_path.startswith('\\\\'):
        return False
    
    # Convert to absolute path
    try:
        abs_file_path = os.path.abspath(file_path)
    except (ValueError, OSError):
        return False
    
    # Check if path is within any allowed directory
    for allowed_dir in allowed_dirs:
        try:
            abs_allowed_dir = os.path.abspath(allowed_dir)
            # Use commonpath to verify the file is within the allowed directory
            common = os.path.commonpath([abs_file_path, abs_allowed_dir])
            if common == abs_allowed_dir:
                return True
        except (ValueError, OSError):
            continue
    
    return False


def is_safe_filename(filename: str) -> bool:
    """
    Check if a filename is safe and doesn't contain path traversal characters.
    
    Args:
        filename: The filename to validate
        
    Returns:
        True if filename is safe, False otherwise
    """
    if not filename:
        return False
    
    # Reject filenames with path traversal or path separators
    dangerous_patterns = ['..', '/', '\\', '\x00', '\n', '\r']
    for pattern in dangerous_patterns:
        if pattern in filename:
            return False
    
    # Only allow alphanumeric, dots, underscores, hyphens, and spaces
    if not re.match(r'^[a-zA-Z0-9._\- ]+$', filename):
        return False
    
    return True


def validate_mode(mode: str, allowed_modes: List[str]) -> bool:
    """
    Validate that a mode parameter is in the whitelist of allowed modes.
    
    Args:
        mode: The mode string to validate
        allowed_modes: List of allowed mode values
        
    Returns:
        True if mode is in the allowed list, False otherwise
    """
    if not mode or not allowed_modes:
        return False
    
    return mode in allowed_modes


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename by removing potentially dangerous characters.
    
    Args:
        filename: The filename to sanitize
        
    Returns:
        Sanitized filename
        
    Raises:
        ValueError: If filename contains path traversal or invalid characters
    """
    if not is_safe_filename(filename):
        raise ValueError(f"Invalid filename: {filename}")
    
    # Remove any leading/trailing whitespace
    sanitized = filename.strip()
    
    # Replace multiple spaces with single space
    sanitized = re.sub(r'\s+', ' ', sanitized)
    
    return sanitized


def validate_selected_files(selected_files: list) -> List[str]:
    """
    Validate and sanitize a list of selected filenames or Gemini file IDs.
    Gemini file IDs (e.g. "files/xxx") are allowed and returned as-is.
    
    Args:
        selected_files: List of filenames or Gemini file IDs to validate
        
    Returns:
        List of sanitized filenames / file IDs
        
    Raises:
        ValueError: If any entry is invalid
    """
    if not isinstance(selected_files, list):
        raise ValueError("selected_files must be a list")
    
    sanitized_files = []
    for filename in selected_files:
        if not isinstance(filename, str):
            raise ValueError(f"Invalid file entry: {filename}")
        s = filename.strip()
        if not s:
            raise ValueError("Empty file entry")
        # Allow Gemini file IDs (e.g. "files/abc123...")
        if s.startswith("files/") and len(s) > 6 and re.match(r"^files/[a-zA-Z0-9._\-]+$", s):
            sanitized_files.append(s)
            continue
        # Allow comparison upload IDs (e.g. "upload:uuid") - resolved to Gemini file_id in chat API
        if s.startswith("upload:") and len(s) > 7 and re.match(r"^upload:[a-zA-Z0-9\-]+$", s):
            sanitized_files.append(s)
            continue
        sanitized = sanitize_filename(s)
        sanitized_files.append(sanitized)
    
    return sanitized_files
