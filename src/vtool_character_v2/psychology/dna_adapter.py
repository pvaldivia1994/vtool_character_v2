"""dna_adapter.py — dna_traits_to_genome: adaptador de PersonalityDNA a Genome."""

from __future__ import annotations

from ..types import Genome


def dna_traits_to_genome(personality_dna) -> Genome:
    traits_lower = [t.lower() for t in getattr(personality_dna, 'traits', [])]
    flaws_lower = [f.lower() for f in getattr(personality_dna, 'flaws', [])]
    motivations_lower = [m.lower() for m in getattr(personality_dna, 'motivations', [])]

    all_desc = traits_lower + flaws_lower + motivations_lower

    return Genome(
        sociability=_keyword_val(all_desc, ["sociable", "outgoing", "shy", "reserved",
            "introvert", "extrovert", "friendly", "talkative"]),
        emotional_sensitivity=_keyword_val(all_desc, ["sensitive", "emotional", "delicate",
            "easily hurt", "perceptive", "intuitive", "empathic"]),
        impulsivity=_keyword_val(all_desc, ["impulsive", "reckless", "spontaneous",
            "careful", "cautious", "patient", "thoughtful"]),
        risk_aversion=_keyword_val(all_desc, ["cautious", "careful", "timid", "brave",
            "daring", "fearless", "adventurous", "fear of"]),
        empathy=_keyword_val(all_desc, ["empathetic", "compassionate", "kind", "caring",
            "cold", "distant", "detached", "understanding"]),
        curiosity=_keyword_val(all_desc, ["curious", "inquisitive", "wonder", "explore",
            "inquisitive", "questioning", "interested"]),
        security_need=_keyword_val(all_desc, ["security", "safe", "comfort", "stable",
            "routine", "predictable", "familiar"]),
        independence=_keyword_val(all_desc, ["independent", "self-reliant", "loner",
            "alone", "solitary", "autonomous", "self-sufficient"]),
        creativity=_keyword_val(all_desc, ["creative", "artistic", "imaginative",
            "innovative", "inventive", "original", "visionary"]),
        aggression=_keyword_val(all_desc, ["aggressive", "angry", "hostile", "violent",
            "confrontational", "fierce", "intense", "competitive"]),
        emotional_regulation=_keyword_val(all_desc, ["calm", "stoic", "controlled",
            "stable", "balanced", "level-headed", "serene", "patient"]),
        persistence=_keyword_val(all_desc, ["persistent", "determined", "stubborn",
            "resilient", "tenacious", "committed", "dedicated", "patient"]),
        playfulness=_keyword_val(all_desc, ["playful", "humorous", "funny", "cheerful",
            "lighthearted", "jovial", "witty", "silly"]),
    )


def _keyword_val(texts: list[str], keywords: list[str]) -> float:
    if not texts:
        return 0.5
    score = 0.0
    for kw in keywords:
        for t in texts:
            if kw in t:
                score += 0.15
    return max(0.05, min(0.95, 0.5 + score))
