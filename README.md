# Dependency-Analysis-Diagram---From-Jira-Project

**Summary**

Quick summary of how to use this repo:

Clone → install Graphviz → create env (conda or pip) → set JIRA_* env vars or .env → run python build_dad.py → open outputs (dad_graph.png, dad_graph.drawio, dad_mermaid.md).


**Credentials**

In the file build_dad.py replace these variables with your own credentials:

    email = os.getenv("JIRA_EMAIL")
    token = os.getenv("JIRA_API_TOKEN")
    base = os.getenv("JIRA_BASE_URL")

...where "JIRA_BASE_URL" is https://companyname.atlassian.net

Also, replace all "companyname" with your domain name at Atlassian.







#

Purpose
- Generate dependency diagrams from Jira issues. Outputs:
  - dad_graph.png (Graphviz)
  - dad_graph.drawio (draw.io / diagrams.net)
  - dad_mermaid.md (Mermaid markdown)
  - dad_graph.dot (Graphviz DOT source)

Quick start (Windows / conda)
1. Clone:
   - git clone https://github.com/<OWNER>/<REPO>.git
   - cd <REPO>

2. Install Graphviz (system binary)
   - Windows (winget): `winget install --id Graphviz.Graphviz`
   - Or download from https://graphviz.org/download/
   - Verify: `dot -V`

3. Create Python environment (recommended: conda)
   - `conda env create -f environment.yml`
   - `conda activate jira-diagram`

   OR using pip + venv:
   - `python -m venv .venv`
   - `.venv\Scripts\activate`
   - `pip install -r requirements.txt`

4. Configure credentials (do NOT commit)
   - Copy `.env.example` → `.env` and fill values OR set environment variables:
     - PowerShell:
       ```
       $env:JIRA_EMAIL = "you@example.com"
       $env:JIRA_API_TOKEN = "your_token"
       $env:JIRA_BASE_URL = "https://yourcompany.atlassian.net"
       ```
   - Required: JIRA_EMAIL, JIRA_API_TOKEN, JIRA_BASE_URL

5. Edit JQL if needed
   - Open `build_dad.py` and change the `jql` variable near the bottom to select issues.

6. Run
   - `python build_dad.py`
   - Check outputs: `dad_graph.png`, `dad_graph.drawio`, `dad_mermaid.md`, `dad_graph.dot`

Troubleshooting
- If Graphviz rendering fails: run `dot -Tpng dad_graph.dot -o test.png` to inspect errors.
- If `pygraphviz` installation fails on Windows: `conda install -c conda-forge pygraphviz`.
- If draw.io file looks empty: ensure Graphviz and Python deps are installed, then re-run and inspect `dad_graph.dot`.

Security
- Never commit `.env` or API tokens. Use `.env.example` only.

License
- Add a LICENSE file if you want to publish under a specific license.
