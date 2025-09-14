from __future__ import annotations

import re
from typing import Dict, Any, List
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


def extract_signals(issue: Dict[str, Any], profile_meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract scoring signals from an issue and profile metadata.
    
    Args:
        issue: Issue dict with title, labels, created_at, issue_body, etc.
        profile_meta: Profile metadata dict (could include account_age, followers, etc.)
        
    Returns:
        Dict with scoring signals for novice calculation
    """
    signals = {}
    
    # Issue content analysis
    issue_title = (issue.get("issue_title") or "").lower()
    issue_body = (issue.get("issue_body") or "").lower()
    issue_labels = [str(label).lower() for label in (issue.get("issue_labels") or [])]
    
    # Calculate issue body length (important for scoring)
    signals["issue_body_length"] = len(str(issue_body)) if issue_body else None
    
    # Extract labels
    signals["labels"] = issue_labels
    
    # Look for novice keywords in BOTH title AND body (more comprehensive)
    novice_keywords = [
        "beginner", "new", "help", "install", "installation", "error", "problem",
        "stuck", "confused", "how to", "tutorial", "guide", "basic", "simple",
        "start", "getting started", "first time", "newbie", "documentation",
        "can't", "cannot", "unable", "fail", "failed", "wrong", "issue",
        "struggling", "trouble", "difficulty", "please help", "need help",
        "not working", "broken", "fix", "solve", "solution"
    ]
    
    matched_keywords = []
    combined_text = f"{issue_title} {issue_body}"
    
    for keyword in novice_keywords:
        if keyword in combined_text:
            matched_keywords.append(keyword)
    
    signals["keywords"] = matched_keywords
    
    # Check for code blocks in issue body (indicates technical sophistication)
    if issue_body:
        code_block_patterns = [
            r"```[\s\S]*?```",  # Triple backticks
            r"`[^`\n]+`",       # Inline code
            r"    [^\n]+",      # Indented code blocks
            r"^\s*[a-zA-Z_][a-zA-Z0-9_]*\s*=",  # Variable assignments
            r"import\s+\w+",    # Python imports
            r"from\s+\w+\s+import",  # Python from imports
        ]
        has_code = any(re.search(pattern, str(issue_body), re.MULTILINE) for pattern in code_block_patterns)
        signals["code_blocks_present"] = has_code
        
        # Look for stack traces/error messages (sign of struggle)
        error_patterns = [
            r"traceback",
            r"error:",
            r"exception:",
            r"attributeerror",
            r"keyerror", 
            r"valueerror",
            r"modulenotfounderror",
            r"importerror",
        ]
        has_errors = any(re.search(pattern, str(issue_body), re.IGNORECASE) for pattern in error_patterns)
        signals["has_error_traces"] = has_errors
        
        # Check for expressions of frustration
        frustration_patterns = [
            r"frustrat",
            r"annoying",
            r"driving me crazy",
            r"pulling my hair",
            r"spent hours",
            r"been trying for",
            r"why (is|does|doesn't|won't)",
            r"this (is|doesn't) work",
        ]
        has_frustration = any(re.search(pattern, str(issue_body), re.IGNORECASE) for pattern in frustration_patterns)
        signals["shows_frustration"] = has_frustration
        
    else:
        signals["code_blocks_present"] = None
        signals["has_error_traces"] = None
        signals["shows_frustration"] = None
    
    # Check for excessive punctuation (sign of frustration/inexperience)
    if issue_title:
        punctuation_count = len([c for c in issue_title if c in "!?"])
        signals["punctuation_excess"] = punctuation_count > 2
    else:
        signals["punctuation_excess"] = None
    
    # Profile-based signals (if available)
    signals["account_age_days"] = profile_meta.get("account_age_days")
    signals["followers"] = profile_meta.get("followers") 
    signals["public_repos"] = profile_meta.get("public_repos")
    
    return signals


def calculate_novice_score(signals: Dict[str, Any]) -> float:
    """
    Calculate a novice likelihood score from extracted signals.
    
    Args:
        signals: Dict of scoring signals from extract_signals()
        
    Returns:
        Float score between 0.0 and 1.0 (higher = more likely to be novice)
        Threshold for selection should be >= 0.6 as specified
    """
    score = 0.0
    
    # Account age scoring (+0.2 if < 1 year)
    account_age = signals.get("account_age_days")
    if isinstance(account_age, (int, float)) and account_age < 365:
        score += 0.2
    
    # Followers scoring (+0.2 if < 5 followers)
    followers = signals.get("followers")
    if isinstance(followers, (int, float)) and followers < 5:
        score += 0.2
    
    # Public repos scoring (+0.1 if < 5 repos)
    public_repos = signals.get("public_repos")
    if isinstance(public_repos, (int, float)) and public_repos < 5:
        score += 0.1
    
    # Keyword matching (+0.2 for novice keywords)
    keywords = signals.get("keywords") or []
    if len(keywords) > 0:
        score += 0.2
    
    # Code blocks absence (+0.1 if no code blocks)
    has_code = signals.get("code_blocks_present")
    if has_code is False:  # Explicitly False (None means we couldn't determine)
        score += 0.1
    
    # Labels indicating novice status (+0.1)
    labels = signals.get("labels") or []
    novice_labels = {"question", "help wanted", "usage", "documentation", "beginner"}
    if any(label in novice_labels for label in labels):
        score += 0.1
    
    # Issue body length (+0.1 if very short < 400 chars)
    body_length = signals.get("issue_body_length")
    if isinstance(body_length, int) and body_length < 400:
        score += 0.1
    
    # Excessive punctuation (+0.05 for frustration indicators)
    if signals.get("punctuation_excess"):
        score += 0.05
    
    # Clamp to [0, 1] range
    return max(0.0, min(1.0, score))


def is_novice_prospect(signals: Dict[str, Any], threshold: float = 0.6) -> bool:
    """
    Determine if the signals indicate a novice prospect worth contacting.
    
    Args:
        signals: Scoring signals dict
        threshold: Minimum score to be considered a novice (default 0.6)
        
    Returns:
        True if score >= threshold
    """
    score = calculate_novice_score(signals)
    return score >= threshold


def enrich_with_github_profile_data(issue: Dict[str, Any]) -> Dict[str, Any]:
    """
    Placeholder for enriching issue with GitHub profile data.
    In a real implementation, this would make GitHub API calls to get:
    - Account creation date
    - Follower count  
    - Public repository count
    - Contribution activity
    
    For now, returns mock data for demonstration.
    """
    user_login = issue.get("user_login", "")
    
    # Mock profile data based on username patterns
    # In production, this would be replaced with actual GitHub API calls
    mock_profiles = {
        "biouser123": {"account_age_days": 90, "followers": 2, "public_repos": 1},
        "newbie_scientist": {"account_age_days": 180, "followers": 8, "public_repos": 3},
        "confused_researcher": {"account_age_days": 45, "followers": 1, "public_repos": 0},
    }
    
    profile_data = mock_profiles.get(user_login, {
        "account_age_days": None,
        "followers": None, 
        "public_repos": None,
    })
    
    return profile_data


def score_issue_for_outreach(issue: Dict[str, Any]) -> Dict[str, Any]:
    """
    Complete scoring pipeline for a single GitHub issue.
    
    Args:
        issue: Issue dict from GitHubIssuesScraper
        
    Returns:
        Issue dict enhanced with signals and novice_score
    """
    try:
        # Get profile data (mock for now)
        profile_data = enrich_with_github_profile_data(issue)
        
        # Extract scoring signals
        signals = extract_signals(issue, profile_data)
        
        # Calculate novice score
        novice_score = calculate_novice_score(signals)
        
        # Add to issue
        issue["signals"] = signals
        issue["novice_score"] = novice_score
        
        return issue
        
    except Exception as e:
        logger.error(f"Scoring failed for issue {issue.get('issue_number')}: {e}")
        issue["signals"] = {}
        issue["novice_score"] = 0.0
        return issue


def filter_high_scoring_leads(issues: List[Dict[str, Any]], threshold: float = 0.6) -> List[Dict[str, Any]]:
    """
    Filter issues to only those with high novice scores and email contact info.
    
    Args:
        issues: List of scored issue dicts
        threshold: Minimum novice score (default 0.6)
        
    Returns:
        Filtered list of high-scoring leads with contact info
    """
    filtered = []
    
    for issue in issues:
        score = issue.get("novice_score", 0.0)
        email = issue.get("email")
        
        # Must meet score threshold and have email for outreach
        if score >= threshold and email:
            filtered.append(issue)
    
    # Sort by score descending for prioritization
    filtered.sort(key=lambda x: x.get("novice_score", 0.0), reverse=True)
    
    return filtered
