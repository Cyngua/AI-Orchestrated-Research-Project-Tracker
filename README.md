# AI-Orchestrated Research Project Tracker

Quick start:
1. `pip install -r requirements.txt`
2. `cp config/.env.sample .env`
3. Run ETL scripts in `etl/`
4. Launch Streamlit app: `streamlit run streamlit_app.py`

## Environment Setup
### 1. Clone Repository
```bash
git clone <repo-url>
cd <repo-folder>
```
### 2. Create Conda Environment
```bash
conda create -n ai-research-tracker python=3.11 -y
conda activate ai-research-tracker
```
### 3. Install Environment
```bash
pip install -r requirements.txt
```

## Project Workflow (Mermaid Data Pipeline Diagram)
![alt text](figures/mermaid_data_pipeline.png)

## License

This project is provided for viewing and demonstration purposes only.
All rights reserved. Unauthorized copying, modification, or redistribution
is prohibited.
