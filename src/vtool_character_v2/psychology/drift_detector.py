"""drift_detector.py — DriftDetector: feedback loop comportamiento → personalidad."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from ..types import DriftEntry, PersonaState


class DriftDetector:
    def __init__(
        self,
        log_fn: Optional[Callable] = None,
        drift_threshold: float = 0.15,
        min_samples: int = 5,
    ):
        self._log = log_fn or (lambda msg: None)
        self._threshold = drift_threshold
        self._min_samples = min_samples
        self._recent_responses: list[dict] = []

    def feed(self, response_text: str, expected_persona: PersonaState) -> Optional[DriftEntry]:
        lower = response_text.lower()

        word_count = len(response_text.split())

        warmth_words = ["por favor", "gracias", "entiendo", "lamento", "siento",
                        "please", "thank", "understand", "sorry", "aprecio",
                        "cariño", "amable", "gentil", "corazón"]
        cold_words = ["no me importa", "como sea", "da igual", "cállate",
                      "whatever", "i don't care", "shut up", "leave me"]

        warmth_count = sum(1 for w in warmth_words if w in lower)
        cold_count = sum(1 for w in cold_words if w in lower)
        warmth_ratio = (warmth_count - cold_count) / max(1, word_count * 0.1)
        warmth_ratio = max(-1.0, min(1.0, warmth_ratio))

        expected_verbosity = expected_persona.verbosity
        actual_verbosity = min(1.0, word_count / 50.0)

        sarcasm_markers = ["ah, claro", "por supuesto que no", "obviamente",
                           "oh really", "sure thing", "obviously", "yeah right",
                           "claro que sí", "cómo no"]
        sarcasm_count = sum(1 for m in sarcasm_markers if m in lower)
        actual_sarcasm = min(1.0, sarcasm_count * 0.25)

        verbosity_drift = abs(actual_verbosity - expected_verbosity)
        sarcasm_drift = abs(actual_sarcasm - expected_persona.sarcasm_tendency)
        warmth_drift = abs(warmth_ratio - (expected_persona.warmth * 2 - 1))

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "word_count": word_count,
            "warmth_ratio": warmth_ratio,
            "actual_verbosity": actual_verbosity,
            "actual_sarcasm": actual_sarcasm,
            "verbosity_drift": verbosity_drift,
            "sarcasm_drift": sarcasm_drift,
            "warmth_drift": warmth_drift,
        }
        self._recent_responses.append(entry)

        if len(self._recent_responses) > self._min_samples * 3:
            self._recent_responses = self._recent_responses[-self._min_samples * 3:]

        if len(self._recent_responses) >= self._min_samples:
            recent = self._recent_responses[-self._min_samples:]
            avg_verbosity_drift = sum(r["verbosity_drift"] for r in recent) / len(recent)
            avg_sarcasm_drift = sum(r["sarcasm_drift"] for r in recent) / len(recent)
            avg_warmth_drift = sum(r["warmth_drift"] for r in recent) / len(recent)

            max_drift = max(avg_verbosity_drift, avg_sarcasm_drift, avg_warmth_drift)
            if max_drift > self._threshold:
                if avg_verbosity_drift > self._threshold:
                    axis = "verbosity"
                    old_val = expected_verbosity
                    new_val = actual_verbosity
                elif avg_sarcasm_drift > self._threshold:
                    axis = "sarcasm"
                    old_val = expected_persona.sarcasm_tendency
                    new_val = actual_sarcasm
                else:
                    axis = "warmth"
                    old_val = expected_persona.warmth
                    new_val = max(0.0, min(1.0, (warmth_ratio + 1) / 2))

                drift_entry = DriftEntry(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    axis=axis,
                    old_value=old_val,
                    new_value=new_val,
                    reason=f"Response drift detected: {axis} ({old_val:.2f} -> {new_val:.2f}) over {self._min_samples} samples",
                    source="feedback_loop",
                )
                self._log(f"Drift detected: {drift_entry.reason}")
                self._recent_responses = []
                return drift_entry

        return None

    def clear(self) -> None:
        self._recent_responses = []
