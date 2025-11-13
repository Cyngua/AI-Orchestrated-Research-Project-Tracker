# AI Services Design

## Overview
The AI Services module provides GPT-powered summarization, tagging, and report generation for research projects.

## Architecture

### 1. GPT Service (`llm/gpt_service.py`)
Provides three main functions:

#### `summarize_and_tag_project()`
- **Purpose**: Generate AI summary, keywords, stage guess, and funding mechanism suggestions
- **Input**: Project title, abstract, stage, related publications, related grants
- **Output**: 
  ```python
  {
      'summary': str,  # 100-word summary
      'keywords': List[str],  # 5 keywords
      'stage_guess': str,  # One of: idea, planning, data-collection, etc.
      'suggested_mechanisms': List[str]  # 3 funding mechanisms (R01, R21, etc.)
  }
  ```
- **Model**: Uses `gpt-5-nano` with JSON response format
- **Temperature**: 0.3 (for consistent outputs)

#### `generate_project_report()`
- **Purpose**: Generate comprehensive 1-page project report
- **Input**: Project details, milestones, publications, funding matches
- **Output**: Markdown-formatted report ready for DOCX/PDF conversion
- **Includes**: Summary, stage, milestones, publications, funding matches, next actions

#### `generate_summary()` (Legacy)
- Simple text summarization function

### 2. Database Schema Updates
New fields added to `projects` table:
- `ai_summary` (TEXT): Cached AI-generated summary
- `ai_keywords` (TEXT): JSON array of keywords
- `ai_stage_guess` (TEXT): AI-suggested project stage
- `ai_suggested_mechanisms` (TEXT): JSON array of funding mechanisms
- `ai_generated_at` (DATETIME): Timestamp of AI generation
- `ai_manual_override` (BOOLEAN): Flag indicating manual edits

**Migration**: Run `etl/add_ai_fields.sql` to add these fields.

### 3. Frontend Integration (`app/streamlit_app.py`)

#### AI Services Page Features:

1. **Project Selection**
   - Dropdown to select from faculty member's projects
   - Fetches full project details including publications and grants

2. **AI Summary & Tagging Section**
   - Display cached AI summary (if exists)
   - Editable text area for manual override
   - Display keywords, stage guess, and suggested mechanisms
   - "Generate/Regenerate" button to call AI service
   - "Save Manual Edits" button to persist changes
   - Visual indicators for AI-generated vs manually edited content

3. **Report Generation Section**
   - "Generate Project Report" button
   - Displays markdown report in UI
   - Download button for markdown export
   - Report includes: summary, stage, publications, funding matches, next actions

4. **Batch Operations** (Placeholder)
   - Generate AI summaries for all projects
   - Export all project reports

## Usage Flow

1. **Generate AI Summary**:
   - User selects a project
   - Clicks "Generate/Regenerate AI Summary"
   - System calls `summarize_and_tag_project()` with project context
   - Results saved to database
   - UI updates to show new summary

2. **Manual Override**:
   - User edits summary in text area
   - Clicks "Save Manual Edits"
   - Sets `ai_manual_override = 1` in database
   - Prevents AI from overwriting manual edits

3. **Generate Report**:
   - User clicks "Generate Project Report"
   - System gathers project data, publications, funding matches
   - Calls `generate_project_report()` with context
   - Displays markdown report
   - User can download as .md file

## Configuration

### Environment Variables
- `OPENAI_API_KEY`: Required for GPT service

### Model Configuration
- Default model: `gpt-5-nano` (can be changed in `gpt_service.py`)
- JSON response format for structured outputs
- Temperature: 0.3 for summaries, 0.5 for reports

## Future Enhancements

1. **Batch Processing**: Implement batch generation for all projects
2. **DOCX/PDF Export**: Add conversion from markdown to DOCX/PDF
3. **Q&A Feature**: RAG-based question answering about projects
4. **Caching Strategy**: Implement smart caching to avoid redundant API calls
5. **Error Handling**: Enhanced error messages and retry logic
6. **Cost Tracking**: Monitor API usage and costs

## Dependencies
- `openai`: For GPT API access
- `python-dotenv`: For environment variable management
- `asyncio`: For async/await support

