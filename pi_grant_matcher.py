"""
PI-Grant Matching System

This module implements a comprehensive matching system that scores grants opportunities
against a selected PI based on multiple factors:
1. Keyword/topic semantic similarity
2. Time alignment between project and grant timelines
3. PI eligibility and past grant history
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import re
from collections import Counter
import math

class PIGrantMatcher:
    def __init__(self, tracker_db_path: str, grants_db_path: str):
        self.tracker_db_path = tracker_db_path
        self.grants_db_path = grants_db_path
        
        # Medical/vascular research keywords for semantic matching
        self.medical_keywords = {
            'vascular': ['vascular', 'artery', 'arterial', 'vein', 'venous', 'circulation', 'blood vessel'],
            'aneurysm': ['aneurysm', 'dilatation', 'bulge', 'rupture', 'repair'],
            'carotid': ['carotid', 'carotid artery', 'carotid stenosis', 'carotid endarterectomy'],
            'peripheral': ['peripheral', 'pad', 'peripheral arterial disease', 'limb', 'extremity'],
            'aortic': ['aortic', 'aorta', 'abdominal aortic', 'thoracic aortic'],
            'intervention': ['intervention', 'surgery', 'surgical', 'procedure', 'treatment'],
            'imaging': ['imaging', 'ultrasound', 'ct', 'mri', 'angiography', 'doppler'],
            'clinical': ['clinical', 'patient', 'outcome', 'trial', 'study', 'registry']
        }
        
        # Grant mechanism preferences by career stage
        self.career_stage_mechanisms = {
            'early': ['K23', 'K08', 'K01', 'R21', 'R03'],
            'mid': ['R01', 'R21', 'R03', 'U01'],
            'senior': ['R01', 'U01', 'P01', 'P50']
        }

    def get_pi_data(self, pi_name: str) -> Dict:
        """Extract comprehensive PI data from tracker.db"""
        conn = sqlite3.connect(self.tracker_db_path)
        conn.row_factory = sqlite3.Row
        
        # Get PI basic info
        pi_query = """
            SELECT * FROM people 
            WHERE first_name || ' ' || last_name = ? OR full_name = ?
        """
        pi_data = conn.execute(pi_query, (pi_name, pi_name)).fetchone()
        
        if not pi_data:
            return None
            
        pi_id = pi_data['id']
        
        # Get PI's projects
        projects_query = """
            SELECT p.*, ppr.role as project_role
            FROM projects p
            JOIN people_project_relation ppr ON p.id = ppr.project_id
            WHERE ppr.person_id = ?
        """
        projects = pd.read_sql_query(projects_query, conn, params=[pi_id])
        
        # Get PI's publications
        pubs_query = """
            SELECT pb.*, apr.author_position
            FROM pubs pb
            JOIN author_pub_relation apr ON pb.id = apr.pub_id
            WHERE apr.person_id = ?
        """
        publications = pd.read_sql_query(pubs_query, conn, params=[pi_id])
        
        # Get PI's grant history
        grants_query = """
            SELECT gc.*, pgr.role as grant_role, pgr.notes
            FROM grants_core gc
            JOIN project_grant_relation pgr ON gc.id = pgr.grant_id
            JOIN people_project_relation ppr ON pgr.project_id = ppr.project_id
            WHERE ppr.person_id = ?
        """
        grants = pd.read_sql_query(grants_query, conn, params=[pi_id])
        
        conn.close()
        
        return {
            'pi_info': dict(pi_data),
            'projects': projects,
            'publications': publications,
            'grants': grants
        }

    def extract_keywords_from_text(self, text: str) -> List[str]:
        """Extract relevant medical keywords from text"""
        if not text:
            return []
        
        text_lower = text.lower()
        found_keywords = []
        
        for category, keywords in self.medical_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    found_keywords.append(category)
                    break
        
        return found_keywords

    def compute_semantic_similarity(self, pi_data: Dict, grant_title: str, grant_description: str = "") -> float:
        """Compute semantic similarity score (0-1) based on keyword matching"""
        
        # Extract keywords from PI's research
        pi_keywords = set()
        
        # From projects
        for _, project in pi_data['projects'].iterrows():
            if project['title']:
                pi_keywords.update(self.extract_keywords_from_text(project['title']))
            if project['abstract']:
                pi_keywords.update(self.extract_keywords_from_text(project['abstract']))
        
        # From publications
        for _, pub in pi_data['publications'].iterrows():
            if pub['title']:
                pi_keywords.update(self.extract_keywords_from_text(pub['title']))
            if pub['topic']:
                pi_keywords.update(self.extract_keywords_from_text(pub['topic']))
        
        # Extract keywords from grant
        grant_keywords = set()
        grant_keywords.update(self.extract_keywords_from_text(grant_title))
        if grant_description:
            grant_keywords.update(self.extract_keywords_from_text(grant_description))
        
        # Compute Jaccard similarity
        if not pi_keywords or not grant_keywords:
            return 0.0
        
        intersection = len(pi_keywords.intersection(grant_keywords))
        union = len(pi_keywords.union(grant_keywords))
        
        return intersection / union if union > 0 else 0.0

    def compute_time_alignment_score(self, pi_data: Dict, grant_open_date: str, grant_close_date: str) -> float:
        """Compute time alignment score (0-1) based on project timelines"""
        
        if not grant_open_date and not grant_close_date:
            return 0.5  # Neutral score if no dates available
        
        current_date = datetime.now().date()
        grant_open = datetime.strptime(grant_open_date, '%Y-%m-%d').date() if grant_open_date else None
        grant_close = datetime.strptime(grant_close_date, '%Y-%m-%d').date() if grant_close_date else None
        
        # Check if PI has active projects that could benefit from this grant
        active_projects = pi_data['projects'][
            (pi_data['projects']['stage'].isin(['idea', 'planning', 'data-collection', 'analysis'])) |
            (pi_data['projects']['end_date'].isna()) |
            (pd.to_datetime(pi_data['projects']['end_date'], errors='coerce') > current_date)
        ]
        
        if active_projects.empty:
            return 0.3  # Lower score if no active projects
        
        # Check if grant timeline aligns with project needs
        alignment_score = 0.0
        
        for _, project in active_projects.iterrows():
            project_start = pd.to_datetime(project['start_date'], errors='coerce')
            project_end = pd.to_datetime(project['end_date'], errors='coerce')
            
            # If project is in early stages and grant is available soon
            if project['stage'] in ['idea', 'planning'] and grant_open and grant_open <= current_date + timedelta(days=180):
                alignment_score += 0.4
            
            # If project timeline overlaps with grant period
            if grant_open and grant_close:
                if (project_start and project_start <= grant_close) or (project_end and project_end >= grant_open):
                    alignment_score += 0.3
            
            # If project needs funding soon
            if project['stage'] in ['data-collection', 'analysis'] and grant_open and grant_open <= current_date + timedelta(days=90):
                alignment_score += 0.3
        
        return min(alignment_score, 1.0)

    def compute_eligibility_score(self, pi_data: Dict, grant_mechanism: str = None, grant_agency: str = None) -> float:
        """Compute eligibility score (0-1) based on PI's grant history and career stage"""
        
        pi_grants = pi_data['grants']
        if pi_grants.empty:
            return 0.5  # Neutral score for new PIs
        
        # Analyze grant history
        mechanisms = pi_grants['mechanism'].dropna().tolist()
        agencies = pi_grants['agency'].dropna().tolist()
        
        eligibility_score = 0.0
        
        # Mechanism familiarity (0.4 weight)
        if grant_mechanism and mechanisms:
            mechanism_frequency = Counter(mechanisms)
            total_grants = len(mechanisms)
            mechanism_score = mechanism_frequency.get(grant_mechanism, 0) / total_grants
            eligibility_score += mechanism_score * 0.4
        
        # Agency familiarity (0.3 weight)
        if grant_agency and agencies:
            agency_frequency = Counter(agencies)
            total_grants = len(agencies)
            agency_score = agency_frequency.get(grant_agency, 0) / total_grants
            eligibility_score += agency_score * 0.3
        
        # Grant success rate (0.3 weight)
        successful_grants = pi_grants[pi_grants['status'].isin(['active', 'completed'])]
        success_rate = len(successful_grants) / len(pi_grants) if len(pi_grants) > 0 else 0
        eligibility_score += success_rate * 0.3
        
        return min(eligibility_score, 1.0)

    def apply_binary_filters(self, pi_data: Dict, grant_opportunity: Dict) -> bool:
        """Apply binary filters to determine if grant is a potential match"""
        
        # Filter 1: Grant must be posted or forecasted
        if grant_opportunity.get('opp_status') not in ['posted', 'forecasted']:
            return False
        
        # Filter 2: Must have some keyword overlap
        grant_title = grant_opportunity.get('title', '')
        grant_desc = grant_opportunity.get('description', '')
        semantic_score = self.compute_semantic_similarity(pi_data, grant_title, grant_desc)
        
        if semantic_score < 0.1:  # Minimum 10% keyword overlap
            return False
        
        # Filter 3: Must have reasonable time alignment
        time_score = self.compute_time_alignment_score(
            pi_data, 
            grant_opportunity.get('open_date'), 
            grant_opportunity.get('close_date')
        )
        
        if time_score < 0.2:  # Minimum 20% time alignment
            return False
        
        return True

    def compute_overall_score(self, pi_data: Dict, grant_opportunity: Dict) -> float:
        """Compute overall matching score (0-1) for a grant opportunity"""
        
        # Individual component scores
        semantic_score = self.compute_semantic_similarity(
            pi_data, 
            grant_opportunity.get('title', ''), 
            grant_opportunity.get('description', '')
        )
        
        time_score = self.compute_time_alignment_score(
            pi_data,
            grant_opportunity.get('open_date'),
            grant_opportunity.get('close_date')
        )
        
        eligibility_score = self.compute_eligibility_score(
            pi_data,
            grant_opportunity.get('mechanism'),
            grant_opportunity.get('agency_name')
        )
        
        # Weighted combination
        weights = {
            'semantic': 0.5,    # Most important - research alignment
            'time': 0.3,        # Important - practical timing
            'eligibility': 0.2  # Less important - can be improved
        }
        
        overall_score = (
            semantic_score * weights['semantic'] +
            time_score * weights['time'] +
            eligibility_score * weights['eligibility']
        )
        
        return round(overall_score, 3)

    def match_grants_for_pi(self, pi_name: str, limit: int = 20) -> List[Dict]:
        """Find and score matching grants for a specific PI"""
        
        # Get PI data
        pi_data = self.get_pi_data(pi_name)
        if not pi_data:
            return []
        
        # Get all grants opportunities
        conn = sqlite3.connect(self.grants_db_path)
        grants_query = """
            SELECT * FROM grants_opportunity 
            WHERE opp_status IN ('posted', 'forecasted')
            ORDER BY close_date DESC, open_date DESC
        """
        all_grants = pd.read_sql_query(grants_query, conn)
        conn.close()
        
        # Apply binary filters and compute scores
        matched_grants = []
        
        for _, grant in all_grants.iterrows():
            grant_dict = grant.to_dict()
            
            # Apply binary filters
            if self.apply_binary_filters(pi_data, grant_dict):
                # Compute overall score
                score = self.compute_overall_score(pi_data, grant_dict)
                
                # Add score and PI-specific info
                grant_dict['match_score'] = score
                grant_dict['pi_name'] = pi_name
                grant_dict['semantic_score'] = self.compute_semantic_similarity(
                    pi_data, grant_dict.get('title', ''), grant_dict.get('description', '')
                )
                grant_dict['time_score'] = self.compute_time_alignment_score(
                    pi_data, grant_dict.get('open_date'), grant_dict.get('close_date')
                )
                grant_dict['eligibility_score'] = self.compute_eligibility_score(
                    pi_data, grant_dict.get('mechanism'), grant_dict.get('agency_name')
                )
                
                matched_grants.append(grant_dict)
        
        # Sort by match score and return top results
        matched_grants.sort(key=lambda x: x['match_score'], reverse=True)
        return matched_grants[:limit]

# Example usage and testing
if __name__ == "__main__":
    matcher = PIGrantMatcher("../tracker.db", "../grants_opportunity.db")
    
    # Test with a sample PI
    pi_name = "Isibor Arhuidese"  # Replace with actual PI name
    matches = matcher.match_grants_for_pi(pi_name, limit=10)
    
    print(f"Found {len(matches)} matching grants for {pi_name}:")
    for i, match in enumerate(matches, 1):
        print(f"{i}. {match['opportunity_number']}: {match['title'][:60]}...")
        print(f"   Score: {match['match_score']:.3f} (Semantic: {match['semantic_score']:.3f}, Time: {match['time_score']:.3f}, Eligibility: {match['eligibility_score']:.3f})")
        print()
