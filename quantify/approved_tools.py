"""Typed internal agent tools; none can compose or alter a verdict."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from quantify.indexed_release import ExactFactKey, IndexedEvidenceRelease, NarrativeContextRetriever
from quantify.policy_control import PolicyControlPlane, PolicyControlPointers

class ToolUnavailableError(RuntimeError): pass

@dataclass(frozen=True, slots=True)
class ReviewTask:
    review_id: str; question: str; derived_from_citation_ids: tuple[str,...]; release_hash: str

class ApprovedReleaseTools:
    def __init__(self, *, release: IndexedEvidenceRelease, policy: PolicyControlPlane, pointers: PolicyControlPointers):
        self._release=release; self._policy=policy; self._pointers=pointers; self._reviews: list[ReviewTask]=[]
    def search_approved_evidence_release(self, *, cik: str, metric: str, period_start: date, period_end: date, unit: str) -> dict[str,object]:
        self._permit("search_approved_evidence_release")
        key=ExactFactKey(self._pointers.evidence_release_manifest_hash,cik,metric,period_start,period_end,unit)
        record=self._release.exact_facts.lookup(key=key)
        if record is None: return {"facts":[],"evidence_release_manifest_hash":self._pointers.evidence_release_manifest_hash}
        return {"facts":[{"fact_id":record.fact_id,"evidence_id":record.evidence.evidence_id,"value":str(record.evidence.value),"filing_accession":record.evidence.accession}],"evidence_release_manifest_hash":self._pointers.evidence_release_manifest_hash}
    def create_review_task(self, *, question: str, derived_from_citation_ids: tuple[str,...]) -> ReviewTask:
        self._permit("create_review_task")
        if not question.strip() or not derived_from_citation_ids: raise ToolUnavailableError("review task is not grounded")
        review=ReviewTask(f"review-{len(self._reviews)+1}",question,tuple(sorted(set(derived_from_citation_ids))),self._pointers.evidence_release_manifest_hash); self._reviews.append(review); return review
    def narrative_context(self, *, cik: str) -> tuple[dict[str,str],...]:
        self._permit("narrative_context")
        chunks=NarrativeContextRetriever(narrative_index=self._release.narrative_context).context(evidence_release_manifest_hash=self._pointers.evidence_release_manifest_hash,cik=cik)
        return tuple({"source_type":"narrative_disclosure","verification_role":"context_only","chunk_hash":c.chunk_hash,"filing_accession":c.filing_accession,"source_span":c.source_span,"text":c.text} for c in chunks)
    def _permit(self, tool: str) -> None:
        try: self._policy.authorize_tool(task_pointers=self._pointers,tool_name=tool)
        except Exception as error: raise ToolUnavailableError("tool is unavailable under current policy") from error
