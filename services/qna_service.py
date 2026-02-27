import logging
from typing import List, Tuple, Dict, Optional

from services.gemini_service import GeminiService


class QnAService:
    """
    Thin orchestration layer around GeminiService that mirrors the responsibilities
    of the original Streamlit generic_process_qna script, but in a Flask-friendly,
    framework-agnostic way.

    This service is intended to be used by HTTP route handlers (e.g. chat_api)
    and other backend code – it does NOT touch any web framework global state.
    """

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required to initialize QnAService.")
        self._gemini = GeminiService(api_key=api_key)

    # -------------------------------------------------------------------------
    # Single‑project Q&A (core path used by /api/chat/<project_name>)
    # -------------------------------------------------------------------------
    def generate_single_project_answer(
        self,
        question: str,
        project_name: str,
        chat_history: List[Tuple[str, str]] | None = None,
        answer_mode: str = "basic",
        extract_visuals: bool = True,
    ) -> Dict:
        """
        Generate an answer for a single project / process.

        Args:
            question: User question text.
            project_name: Logical project / process name (e.g. DAP, SAP).
            chat_history: List of (question, answer) pairs in chronological order.
            answer_mode: One of the supported modes such as
                         'basic', 'research', 'analytical', 'expert', 'cross_project'.
        """
        history = chat_history or []
        # Defensive: ensure history is always in (q, a) tuple form
        safe_history: List[Tuple[str, str]] = []
        for entry in history:
            try:
                q, a = entry
                safe_history.append((str(q), str(a)))
            except Exception:
                logging.warning("Skipping malformed chat history entry: %r", entry)
                continue

        return self._gemini.generate_answer(
            question=question,
            process_name=project_name,
            chat_history=safe_history,
            answer_mode=answer_mode,
            extract_visuals=extract_visuals,
        )

    def generate_single_project_answer_stream(
        self,
        question: str,
        project_name: str,
        chat_history: List[Tuple[str, str]] | None = None,
        answer_mode: str = "basic",
        extract_visuals: bool = True,
    ):
        """
        Generator that yields SSE-friendly events for streaming the answer.
        Yields {"type": "chunk", "text": "..."} then {"type": "done", "answer", "relevant_files", "visuals"}.
        """
        history = chat_history or []
        safe_history: List[Tuple[str, str]] = []
        for entry in history:
            try:
                q, a = entry
                safe_history.append((str(q), str(a)))
            except Exception:
                continue
        yield from self._gemini.generate_answer_stream(
            question=question,
            process_name=project_name,
            chat_history=safe_history,
            answer_mode=answer_mode,
            extract_visuals=extract_visuals,
        )

    # -------------------------------------------------------------------------
    # Cross‑project Q&A (parent + related processes)
    # -------------------------------------------------------------------------
    def generate_cross_project_answer(
        self,
        question: str,
        parent_project: str,
        related_projects: List[str] | None = None,
        chat_history: List[Tuple[str, str]] | None = None,
        style_mode: str = "basic",
        extract_visuals: bool = True,
    ) -> Dict:
        """
        Generate a cross‑project answer while keeping the same answer style
        options as the single‑project flow (basic / research / analytical / expert).
        """
        history = chat_history or []
        safe_history: List[Tuple[str, str]] = []
        for entry in history:
            try:
                q, a = entry
                safe_history.append((str(q), str(a)))
            except Exception:
                logging.warning("Skipping malformed chat history entry in cross-project call: %r", entry)
                continue

        return self._gemini.generate_answer(
            question=question,
            process_name=parent_project,
            chat_history=safe_history,
            answer_mode="cross_project",
            style_mode=style_mode,
            related_processes=related_projects or [],
            extract_visuals=extract_visuals,
        )

    # -------------------------------------------------------------------------
    # Document comparison (used when mode == 'comparison')
    # -------------------------------------------------------------------------
    def generate_comparison_answer(
        self,
        question: str,
        project_name: str,
        file_ids: List[str],
        chat_history: List[Tuple[str, str]] | None = None,
        style_mode: str = "basic",
        extract_visuals: bool = True,
    ) -> Dict:
        """
        Generate a comparison answer: one user-uploaded file + project-relevant documents.
        """
        logger = logging.getLogger("debug_logger")
        logger.info(
            "QnAService.generate_comparison_answer: start | project=%s | user_files=%s | history_len=%d | style_mode=%s | extract_visuals=%s",
            project_name,
            file_ids,
            len(chat_history or []),
            style_mode,
            extract_visuals,
        )
        result = self._gemini.generate_comparison_with_project_docs(
            question=question,
            process_name=project_name,
            user_file_ids=file_ids or [],
            chat_history=chat_history or [],
            style_mode=style_mode,
            extract_visuals=extract_visuals,
        )
        logger.info(
            "QnAService.generate_comparison_answer: end | project=%s | user_files_count=%d | answer_preview=%s",
            project_name,
            len(file_ids or []),
            (result.get("answer") or "")[:200],
        )
        return result

    # -------------------------------------------------------------------------
    # Helper accessors (kept for parity with the original Streamlit module)
    # -------------------------------------------------------------------------
    def get_relevant_files(
        self,
        question: str,
        project_name: str,
        max_files: int = 3,
    ) -> List[str]:
        """
        Expose underlying metadata‑driven routing.
        """
        return self._gemini.get_relevant_files(
            question=question,
            process_name=project_name,
            max_files=max_files,
        )

    def upload_user_file_for_comparison(self, local_path: str) -> Optional[str]:
        """
        Upload a user-provided file to Gemini for comparison. Returns Gemini file ID or None.
        """
        return self._gemini.upload_user_file_for_comparison(local_path)

    def identify_visual_pages(
        self,
        question: str,
        file_id: str,
    ) -> List[int]:
        """
        Expose visual page identification used by the Visual Intelligence panel.
        """
        return self._gemini.identify_visual_pages(question=question, file_id=file_id)

    def generate_chat_title(self, question: str, max_words: int = 5) -> Optional[str]:
        """
        Generate a short title for a chat from its first question.
        Returns None if generation fails.
        """
        return self._gemini.generate_chat_title(question=question, max_words=max_words)

