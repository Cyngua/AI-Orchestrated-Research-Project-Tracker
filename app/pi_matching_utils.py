"""
Simplified PI-Grant Matching Utilities for Streamlit Integration
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import re
import json
from collections import Counter
from pathlib import Path

# Load comprehensive medical keywords from JSON file
def load_medical_keywords() -> Dict[str, Dict]:
    """Load medical keywords from JSON file"""
    json_path = Path(__file__).parent / "medical_keywords.json"
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # Fallback to basic keywords if JSON file not found
        return {
            'vascular': {'keywords': ['vascular', 'artery', 'arterial', 'vein', 'venous', 'circulation', 'blood vessel']},
            'clinical': {'keywords': ['clinical', 'patient', 'outcome', 'trial', 'study', 'registry']}
        }

# Load medical keywords dictionary
medical_keywords_dict = load_medical_keywords()

def get_keyword_categories() -> List[str]:
    """Get list of all available keyword categories"""
    return list(medical_keywords_dict.keys())

def get_keyword_stats() -> Dict[str, int]:
    """Get statistics about the keyword dictionary"""
    stats = {}
    for category, data in medical_keywords_dict.items():
        stats[category] = len(data.get('keywords', []))
    return stats

def get_pi_research_keywords(pi_name: str, tracker_db_path: str) -> List[str]:
    """Extract research keywords from PI's projects and publications"""
    
    conn = sqlite3.connect(tracker_db_path)
    conn.row_factory = sqlite3.Row
    
    # Get PI ID
    pi_query = "SELECT id FROM people WHERE first_name || ' ' || last_name = ?"
    pi_result = conn.execute(pi_query, (pi_name,)).fetchone()
    
    if not pi_result:
        conn.close()
        return []
    
    pi_id = pi_result['id']
    
    def extract_keywords(text):
        if not text:
            return []
        text_lower = text.lower()
        found = []
        for category, data in medical_keywords_dict.items():
            keywords = data.get('keywords', [])
            for keyword in keywords:
                if keyword in text_lower:
                    found.append(category)
                    break
        return found
    
    # Get projects
    projects_query = """
        SELECT p.title, p.abstract FROM projects p
        JOIN people_project_relation ppr ON p.id = ppr.project_id
        WHERE ppr.person_id = ?
    """
    projects = pd.read_sql_query(projects_query, conn, params=[pi_id])
    
    # Get publications
    pubs_query = """
        SELECT pb.title, pb.topic FROM pubs pb
        JOIN author_pub_relation apr ON pb.id = apr.pub_id
        WHERE apr.person_id = ?
    """
    publications = pd.read_sql_query(pubs_query, conn, params=[pi_id])
    
    conn.close()
    
    # Extract keywords
    pi_keywords = set()
    
    for _, project in projects.iterrows():
        pi_keywords.update(extract_keywords(project['title']))
        pi_keywords.update(extract_keywords(project['abstract']))
    
    for _, pub in publications.iterrows():
        pi_keywords.update(extract_keywords(pub['title']))
        pi_keywords.update(extract_keywords(pub['topic']))
    
    return list(pi_keywords)

def compute_semantic_similarity(pi_keywords: List[str], grant_title: str, grant_description: str = "") -> float:
    """Compute semantic similarity between PI keywords and grant content"""
    
    if not pi_keywords or not grant_title:
        return 0.0
    
    def extract_grant_keywords(text):
        if not text:
            return []
        text_lower = text.lower()
        found = []
        for category, data in medical_keywords_dict.items():
            keywords = data.get('keywords', [])
            for keyword in keywords:
                if keyword in text_lower:
                    found.append(category)
                    break
        return found
    
    grant_keywords = set()
    grant_keywords.update(extract_grant_keywords(grant_title))
    grant_keywords.update(extract_grant_keywords(grant_description))
    
    pi_keywords_set = set(pi_keywords)
    
    # Jaccard similarity
    intersection = len(pi_keywords_set.intersection(grant_keywords))
    union = len(pi_keywords_set.union(grant_keywords))
    
    return intersection / union if union > 0 else 0.0

def compute_time_alignment_score(pi_name: str, tracker_db_path: str, grant_open_date: str, grant_close_date: str) -> float:
    """Compute time alignment score based on PI's active projects"""
    
    conn = sqlite3.connect(tracker_db_path)
    
    # Get PI's active projects
    projects_query = """
        SELECT p.stage, p.start_date, p.end_date FROM projects p
        JOIN people_project_relation ppr ON p.id = ppr.project_id
        JOIN people pe ON pe.id = ppr.person_id
        WHERE pe.first_name || ' ' || pe.last_name = ?
        AND p.stage IN ('idea', 'planning', 'data-collection', 'analysis')
    """
    projects = pd.read_sql_query(projects_query, conn, params=[pi_name])
    conn.close()
    
    if projects.empty:
        return 0.3  # Neutral score if no active projects
    
    current_date = datetime.now().date()
    
    # Check if grant timeline aligns with project needs
    alignment_score = 0.0
    
    for _, project in projects.iterrows():
        # Early stage projects benefit from grants available soon
        if project['stage'] in ['idea', 'planning']:
            if grant_open_date:
                grant_open = datetime.strptime(grant_open_date, '%Y-%m-%d').date()
                if grant_open <= current_date + timedelta(days=180):
                    alignment_score += 0.4
        
        # Active projects benefit from ongoing grant opportunities
        if project['stage'] in ['data-collection', 'analysis']:
            if grant_open_date and grant_close_date:
                grant_open = datetime.strptime(grant_open_date, '%Y-%m-%d').date()
                grant_close = datetime.strptime(grant_close_date, '%Y-%m-%d').date()
                if grant_open <= current_date + timedelta(days=90):
                    alignment_score += 0.3
    
    return min(alignment_score, 1.0)

def compute_eligibility_score(pi_name: str, tracker_db_path: str, grant_agency: str = None) -> float:
    """Compute eligibility score based on PI's grant history"""
    
    conn = sqlite3.connect(tracker_db_path)
    
    # Get PI's grant history
    grants_query = """
        SELECT gc.agency, gc.status, gc.mechanism FROM grants_core gc
        JOIN project_grant_relation pgr ON gc.id = pgr.grant_id
        JOIN people_project_relation ppr ON pgr.project_id = ppr.project_id
        JOIN people pe ON pe.id = ppr.person_id
        WHERE pe.first_name || ' ' || pe.last_name = ?
    """
    grants = pd.read_sql_query(grants_query, conn, params=[pi_name])
    conn.close()
    
    if grants.empty:
        return 0.5  # Neutral score for new PIs
    
    eligibility_score = 0.0
    
    # Agency familiarity (0.5 weight)
    if grant_agency and not grants['agency'].isna().all():
        agency_counts = grants['agency'].value_counts()
        total_grants = len(grants)
        agency_score = agency_counts.get(grant_agency, 0) / total_grants
        eligibility_score += agency_score * 0.5
    
    # Grant success rate (0.5 weight)
    successful_grants = grants[grants['status'].isin(['active', 'completed'])]
    success_rate = len(successful_grants) / len(grants) if len(grants) > 0 else 0
    eligibility_score += success_rate * 0.5
    
    return min(eligibility_score, 1.0)

def apply_binary_filters(pi_name: str, tracker_db_path: str, grant_opportunity: Dict) -> bool:
    """Apply binary filters to determine if grant is a potential match"""
    
    # Filter 1: Grant must be posted or forecasted
    if grant_opportunity.get('opp_status') not in ['posted', 'forecasted']:
        return False
    
    # Filter 2: Must have some keyword overlap
    pi_keywords = get_pi_research_keywords(pi_name, tracker_db_path)
    semantic_score = compute_semantic_similarity(
        pi_keywords, 
        grant_opportunity.get('title', ''), 
        grant_opportunity.get('description', '')
    )
    
    if semantic_score < 0.1:  # Minimum 10% keyword overlap
        return False
    
    # Filter 3: Must have reasonable time alignment
    time_score = compute_time_alignment_score(
        pi_name, 
        tracker_db_path,
        grant_opportunity.get('open_date'), 
        grant_opportunity.get('close_date')
    )
    
    if time_score < 0.2:  # Minimum 20% time alignment
        return False
    
    return True

def compute_pi_grant_match_score(pi_name: str, tracker_db_path: str, grant_opportunity: Dict, 
                                custom_weights: Dict = None) -> Dict:
    """Compute comprehensive match score for a PI-grant pair with optional custom weights"""
    
    # Get PI keywords
    pi_keywords = get_pi_research_keywords(pi_name, tracker_db_path)
    
    # Individual component scores
    semantic_score = compute_semantic_similarity(
        pi_keywords, 
        grant_opportunity.get('title', ''), 
        grant_opportunity.get('description', '')
    )
    
    time_score = compute_time_alignment_score(
        pi_name,
        tracker_db_path,
        grant_opportunity.get('open_date'),
        grant_opportunity.get('close_date')
    )
    
    eligibility_score = compute_eligibility_score(
        pi_name,
        tracker_db_path,
        grant_opportunity.get('agency_name')
    )
    
    # Use custom weights if provided, otherwise use defaults
    if custom_weights:
        weights = custom_weights
    else:
        weights = {'semantic': 0.5, 'time': 0.3, 'eligibility': 0.2}
    
    # Ensure weights sum to 1.0
    total_weight = sum(weights.values())
    if total_weight > 0:
        weights = {k: v/total_weight for k, v in weights.items()}
    
    overall_score = (
        semantic_score * weights['semantic'] +
        time_score * weights['time'] +
        eligibility_score * weights['eligibility']
    )
    
    return {
        'overall_score': round(overall_score, 3),
        'semantic_score': round(semantic_score, 3),
        'time_score': round(time_score, 3),
        'eligibility_score': round(eligibility_score, 3),
        'pi_keywords': pi_keywords,
        'weights_used': weights  # Include weights used for transparency
    }
