import math
from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class MemoryCase(BaseModel):
    case_id: str
    instrument: str
    regime: str
    features: List[float]  # Normalized feature vector
    action: str
    outcome_pnl: float
    outcome_won: bool
    return_r: float
    created_at: str


class VectorMemoryStore:
    """
    Episodic memory store using normalized cosine similarity retrieval.
    Enables retrieving historically analogous market conditions to evaluate empirical win rate.
    """

    def __init__(self):
        self.cases: List[MemoryCase] = []

    @staticmethod
    def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        if len(vec_a) != len(vec_b) or not vec_a:
            return 0.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    def add_case(self, case: MemoryCase):
        self.cases.append(case)
        if len(self.cases) > 2000:
            self.cases.pop(0)

    def retrieve_similar(
        self,
        query_vector: List[float],
        top_k: int = 5,
        min_similarity: float = 0.70
    ) -> List[Dict[str, Any]]:
        scored = []
        for case in self.cases:
            sim = self._cosine_similarity(query_vector, case.features)
            if sim >= min_similarity:
                scored.append((sim, case))

        # Sort descending by similarity
        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for sim, c in scored[:top_k]:
            results.append({
                "similarity": round(sim, 3),
                "case_id": c.case_id,
                "instrument": c.instrument,
                "regime": c.regime,
                "action": c.action,
                "won": c.outcome_won,
                "return_r": c.return_r,
                "pnl": c.outcome_pnl
            })
        return results

    def get_empirical_win_rate(self, query_vector: List[float], top_k: int = 5) -> Optional[float]:
        matches = self.retrieve_similar(query_vector, top_k=top_k)
        if not matches:
            return None
        wins = sum(1 for m in matches if m["won"])
        return round(wins / len(matches), 2)


vector_store = VectorMemoryStore()
