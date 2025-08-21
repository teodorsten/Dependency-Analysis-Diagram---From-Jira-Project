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

Also, replace all "companyname" with your company name.
