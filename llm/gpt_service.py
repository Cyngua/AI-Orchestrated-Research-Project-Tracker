"""
GPT Service for AI-powered project summarization, tagging, and report generation.
"""
import os
from pathlib import Path
import json
from typing import Dict, List, Optional, Any
from openai import AsyncOpenAI
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = SCRIPT_DIR.parent
load_dotenv("config/.env")

# Import configuration
try:
    from config.config import is_gpt_enabled, _get_config_value
except ImportError:
    # Fallback if config module not available
    def is_gpt_enabled():
        return os.getenv("GPT_SERVICES_ENABLED", "false").lower() == "true"
    def _get_config_value(key: str, default: Any = None):
        return os.getenv(key, default)

# Initialize client only if GPT is enabled
# Get API key from either st.secrets or environment variables
if is_gpt_enabled():
    try:
        api_key = _get_config_value('OPENAI_API_KEY')
    except NameError:
        # Fallback if _get_config_value not available
        api_key = os.getenv('OPENAI_API_KEY')
    
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required when GPT_SERVICES_ENABLED=true")
    client = AsyncOpenAI(api_key=api_key)
else:
    client = None

# Default model - can be overridden
DEFAULT_MODEL = "gpt-5-nano"


async def summarize_and_tag_project(
    project_title: str,
    project_abstract: Optional[str] = None,
    project_stage: Optional[str] = None,
    related_publications: Optional[List[Dict]] = None,
    related_grants: Optional[List[Dict]] = None,
    temperature: Optional[float] = 1
) -> Dict[str, any]:
    """
    Generate AI summary, keywords, stage guess, and funding mechanism suggestions for a project.
    
    Returns:
        {
            'summary': str (100 words),
            'keywords': List[str] (5 keywords),
            'stage_guess': str (one of: idea, planning, data-collection, analysis, manuscript, submitted, funded, inactive),
            'suggested_mechanisms': List[str] (3 funding mechanisms like R01, R21, K23)
        }
    """
    # Check if GPT services are enabled
    if not is_gpt_enabled() or client is None:
        return {
            'summary': 'GPT services are disabled. Please enable GPT_SERVICES_ENABLED in configuration.',
            'keywords': [],
            'stage_guess': project_stage or 'idea',
            'suggested_mechanisms': []
        }
    # Build context from related data
    context_parts = []
    
    if project_abstract:
        context_parts.append(f"Abstract: {project_abstract}")
    
    if related_publications:
        pub_titles = [pub.get('title', '') for pub in related_publications[:5]]
        context_parts.append(f"Related Publications: {', '.join(pub_titles)}")
    
    if related_grants:
        grant_info = [f"{g.get('mechanism', '')} - {g.get('core_project_num', '')}" for g in related_grants[:3]]
        context_parts.append(f"Related Grants: {', '.join(grant_info)}")
    
    context = "\n".join(context_parts) if context_parts else "No additional context available."
    
    prompt = f"""You are a research grant advisor. Analyze the following project and provide:

1. A concise 100-word summary of the project
2. Exactly 5 keywords that best describe this research
3. A stage guess based on the project information (choose one: idea, planning, data-collection, analysis, manuscript, submitted, funded, inactive)
4. Three funding mechanism suggestions (use the NIH grant "activity codes" from https://reporter.nih.gov/grant-activity-codes)

Project Title: {project_title}

Additional Context:
{context}

Respond in JSON format:
{{
    "summary": "100-word summary here",
    "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
    "stage_guess": "one of the stage options",
    "suggested_mechanisms": ["mechanism1", "mechanism2", "mechanism3"]
}}"""

    try:
        response = await client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful research grant advisor. Always respond with valid JSON only."
                },
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=temperature
        )
        
        content = response.choices[0].message.content
        result = json.loads(content)
        
        # Validate and clean the response
        return {
            'summary': result.get('summary', ''),  # Limit summary length
            'keywords': result.get('keywords', [])[:5],  # Ensure max 5 keywords
            'stage_guess': result.get('stage_guess', project_stage or 'idea'),
            'suggested_mechanisms': result.get('suggested_mechanisms', [])[:3]  # Max 3 mechanisms
        }
    except Exception as e:
        # Fallback on error
        return {
            'summary': f"Error generating summary: {str(e)}",
            'keywords': [],
            'stage_guess': project_stage or 'idea',
            'suggested_mechanisms': []
        }


async def generate_project_report(
    project_id: int,
    project_title: str,
    project_summary: str,
    project_stage: str,
    milestones: Optional[List[Dict]] = None,
    publications: Optional[List[Dict]] = None,
    funding_matches: Optional[List[Dict]] = None,
    next_actions: Optional[List[str]] = None,
    temperature: Optional[float] = 1
) -> str:
    """
    Generate a comprehensive 1-page project report in markdown format.
    
    Returns markdown text that can be converted to DOCX/PDF.
    """
    # Build report sections
    sections = []
    
    # Title
    sections.append(f"# {project_title}\n")
    
    # Summary
    sections.append(f"## Summary\n{project_summary}\n")
    
    # Current Stage
    sections.append(f"## Current Stage\n**{project_stage}**\n")
    
    # Milestones
    if milestones:
        sections.append("## Milestones")
        for milestone in milestones:
            sections.append(f"- {milestone.get('description', '')} ({milestone.get('date', '')})")
        sections.append("")
    
    # Publications
    if publications:
        sections.append("## Related Publications")
        for pub in publications[:10]:  # Limit to top 10
            title = pub.get('title', 'N/A')
            journal = pub.get('journal', '')
            year = pub.get('year', '')
            pmid = pub.get('pmid', '')
            sections.append(f"- **{title}** ({journal}, {year}) PMID: {pmid}")
        sections.append("")
    
    # Funding Matches
    if funding_matches:
        sections.append("## Funding Opportunities")
        for match in funding_matches[:5]:  # Top 5 matches
            opp_num = match.get('opportunity_number', 'N/A')
            title = match.get('title', 'N/A')
            score = match.get('overall_score', 0)
            link = match.get('funding_desc_link', '')
            
            # Add link if available
            if link and link.strip() and not link.startswith('http://localhost'):
                sections.append(f"- **{opp_num}**: {title} (Match Score: {score:.2f}) [Link]({link})")
            else:
                sections.append(f"- **{opp_num}**: {title} (Match Score: {score:.2f})")
        sections.append("")
    
    # Next Actions
    if next_actions:
        sections.append("## Recommended Next Actions")
        for action in next_actions:
            sections.append(f"- {action}")
        sections.append("")
    else:
        # Generate AI-suggested next actions
        if is_gpt_enabled() and client is not None:
            prompt = f"""Based on this project, suggest 3-5 concrete next actions:

Project: {project_title}
Stage: {project_stage}
Summary: {project_summary[:200]}

Provide 3-5 actionable next steps as a JSON array of strings."""
            
            try:
                response = await client.chat.completions.create(
                    model=DEFAULT_MODEL,
                    messages=[
                        {"role": "system", "content": "You are a research project advisor. Respond with JSON only."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=temperature
                )
                content = response.choices[0].message.content
                result = json.loads(content)
                actions = result.get('actions', [])
                sections.append("## Recommended Next Actions")
                if len(actions) > 0:
                    for action in actions:
                        sections.append(f"- {action}")
                else:
                    sections.append("No recommended next actions found.")
            except:
                sections.append("## Recommended Next Actions\n- Review grants details\n- Update milestones")
        else:
            sections.append("## Recommended Next Actions\n- Review grants details\n- Update milestones\n- Enable GPT services for AI-generated recommendations")
    
    return "\n".join(sections)

if __name__ == "__main__":
    import asyncio
    asyncio.run(summarize_and_tag_project(
        project_title="Test Project",
        project_abstract="This is a test project abstract",
        project_stage="idea",
        related_publications=[{"title": "Test Publication 1"}, {"title": "Test Publication 2"}],
        related_grants=[{"mechanism": "R01", "core_project_num": "123456"}]
    ))