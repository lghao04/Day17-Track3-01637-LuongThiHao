from __future__ import annotations

from typing import Any

from .config import settings
from .context_budget import ContextBudgetManager
from .utils import cap_query
from .zep_common import prime_eval_thread, render_graph_search


class StudentMemory:
    """Only this file needs to be edited by students."""

    def __init__(self, client: Any):
        self.client = client
        self.budget = ContextBudgetManager(settings.context_tokens)

    # NOTE: Zep rejects graph.search queries longer than 400 characters. Some
    # eval queries are longer than that, so wrap every query with
    # `cap_query(query)` (see src/utils.py) before passing it to graph.search.

    def retrieve_long_term(self, user_id: str, thread_id: str, query: str) -> str:
        # LAB TODO 1/4
        # 1) prime_eval_thread(...) has already been provided as scaffolding.
        # 2) call thread.get_user_context(thread_id=...)
        # 3) return the .context string.
        # Bonus: append graph.search(scope="edges", limit>=20) facts with
        #        validity ranges (a low limit can miss deadline/open-loop facts).
        prime_eval_thread(self.client, user_id, thread_id, query)
        context = self.client.thread.get_user_context(thread_id=thread_id)
        base_context = context.context or ""

        facts_block = self._render_edge_facts(user_id, query)
        if not facts_block:
            return base_context

        return f"{base_context}\n\n[Facts with validity]\n{facts_block}".strip()

    def _render_edge_facts(self, user_id: str, query: str, limit: int = 20) -> str:
        """Bonus: pull raw edges so recency/conflict-sensitive facts (e.g. a
        changed deadline or an open-loop task) survive even when
        get_user_context's own summarization drops them.
        """
        try:
            edge_results = self.client.graph.search(
                user_id=user_id,
                query=cap_query(query),
                scope="edges",
                limit=limit,
            )
        except Exception:
            # Non-fatal: long-term retrieval still works from the context block alone.
            return ""

        edges = getattr(edge_results, "edges", None) or []
        lines: list[str] = []
        for edge in edges:
            fact = getattr(edge, "fact", None) or getattr(edge, "name", None)
            if not fact:
                continue

            valid_at = getattr(edge, "valid_at", None)
            invalid_at = getattr(edge, "invalid_at", None)
            expired_at = getattr(edge, "expired_at", None)

            validity_bits = []
            if valid_at:
                validity_bits.append(f"valid_from={valid_at}")
            if invalid_at:
                validity_bits.append(f"invalid_from={invalid_at}")
            if expired_at:
                validity_bits.append(f"expired={expired_at}")

            if validity_bits:
                lines.append(f"- {fact} ({', '.join(validity_bits)})")
            else:
                lines.append(f"- {fact}")

        return "\n".join(lines)

    def retrieve_episodic(self, user_id: str, query: str) -> str:
        # LAB TODO 2/4
        # Use client.graph.search(user_id=..., query=cap_query(query),
        #     scope="episodes", limit=...) then render_graph_search(...).
        # Tip: verbose session episodes can crowd out concise, marker-bearing
        # reflections under the tight episodic budget — render_graph_search
        # accepts an `episode_char_cap` to keep more distinct episodes.
        results = self.client.graph.search(
            user_id=user_id,
            query=cap_query(query),
            scope="episodes",
            limit=5,
        )
        return render_graph_search(results, episode_char_cap=600)

    def retrieve_semantic(self, graph_id: str, query: str) -> str:
        # LAB TODO 3/4
        # Search the standalone graph (graph_id, NOT user_id).
        # Recommended: scope="episodes" — it returns raw document text that keeps
        # literal markers (e.g. PAYMENT-RULE-3). The "auto" scope returns
        # extracted facts that DROP those literal codes, so avoid it here.
        # Fallback: scope="nodes".
        capped_query = cap_query(query)
        results = self.client.graph.search(
            graph_id=graph_id,
            query=capped_query,
            scope="episodes",
            limit=8,
        )
        rendered = render_graph_search(results)
        if rendered.strip():
            return rendered

        fallback = self.client.graph.search(
            graph_id=graph_id,
            query=capped_query,
            scope="nodes",
            limit=8,
        )
        return render_graph_search(fallback)

    def assemble_context(self, layers: dict[str, str]) -> tuple[str, dict[str, dict[str, int]]]:
        # LAB TODO 4/4
        # Use ContextBudgetManager to enforce 10/4/3/3 budget and priority order.
        return self.budget.assemble(layers)