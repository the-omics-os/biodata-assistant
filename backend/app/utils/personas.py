from __future__ import annotations

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, EmailStr
import re


class Persona(BaseModel):
    """AI persona for specialized outreach emails"""
    name: str
    title: str
    from_email: EmailStr
    linkedin_url: Optional[str] = None
    modalities: List[str] = []  # routing keywords for modality matching
    repos: List[str] = []       # optional repo routing


# Persona definitions - easily expandable
PERSONAS: Dict[str, Persona] = {
    "transcripta_quillborne": Persona(
        name="Transcripta Quillborne",
        title="Transcriptomics Specialist",
        from_email="transcripta@omics-os.com",
        linkedin_url="https://www.linkedin.com/in/transcripta-quillborne-96a87b384/",
        modalities=["rna-seq", "scrna-seq", "transcriptomics", "single-cell", "bulk-rna"],
        repos=["scverse/scanpy", "scverse/anndata"]
    ),
    
    # Placeholder personas for future expansion
    "proteos_maximus": Persona(
        name="Proteos Maximus",
        title="Proteomics Specialist", 
        from_email="proteos@omics-os.com",
        linkedin_url=None,  # TODO: Add LinkedIn profile
        modalities=["proteomics", "mass-spec", "protein", "peptide"],
        repos=[]
    ),
    
    "genomus_vitale": Persona(
        name="Genomus Vitale",
        title="Genomics Specialist",
        from_email="genomus@omics-os.com", 
        linkedin_url=None,  # TODO: Add LinkedIn profile
        modalities=["genomics", "dna-seq", "wgs", "wes", "variant"],
        repos=[]
    )
}


def select_persona(lead: Dict[str, Any]) -> Persona:
    """
    Select the most appropriate persona for a lead based on repo and inferred modality.
    
    Args:
        lead: Lead dict with repo, issue_title, issue_labels, etc.
        
    Returns:
        Persona: Best matching persona, defaults to Transcripta for scanpy/anndata
    """
    repo = lead.get("repo", "").lower()
    issue_title = (lead.get("issue_title", "") or "").lower()
    issue_labels = [str(label).lower() for label in (lead.get("issue_labels") or [])]
    
    # Combine text for keyword matching
    combined_text = f"{issue_title} {' '.join(issue_labels)}"
    
    # Score each persona
    best_persona = None
    best_score = 0.0
    
    for persona_key, persona in PERSONAS.items():
        score = 0.0
        
        # Repo matching (strong signal)
        if any(repo_pattern.lower() in repo for repo_pattern in persona.repos):
            score += 2.0
            
        # Modality keyword matching
        for modality in persona.modalities:
            # Use word boundaries to avoid false matches
            pattern = r'\b' + re.escape(modality.lower()) + r'\b'
            if re.search(pattern, combined_text):
                score += 1.0
                
        if score > best_score:
            best_score = score
            best_persona = persona
            
    # Default fallback: Transcripta for scanpy/anndata repos
    if best_persona is None:
        if any(target in repo for target in ["scanpy", "anndata", "scverse"]):
            best_persona = PERSONAS["transcripta_quillborne"]
        else:
            # Ultimate fallback - first available persona
            best_persona = next(iter(PERSONAS.values()))
            
    return best_persona


def get_persona_by_key(key: str) -> Optional[Persona]:
    """Get persona by key, return None if not found"""
    return PERSONAS.get(key)


def list_personas() -> List[Persona]:
    """Return all available personas"""
    return list(PERSONAS.values())
