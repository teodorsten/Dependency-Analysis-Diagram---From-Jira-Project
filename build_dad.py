import os, json, requests
from requests.auth import HTTPBasicAuth
from graphviz import Digraph
import xml.etree.ElementTree as ET
import base64
import zlib
import uuid
import io
from collections import defaultdict
import networkx as nx

# Vilket Jira-fält som är "Flagged" (kan överskridas via env)
FLAGGED_CF = os.getenv("JIRA_FLAGGED_CF", "customfield_10200")

def get_creds():
    email = os.getenv("JIRA_EMAIL")
    token = os.getenv("JIRA_API_TOKEN")
    base = os.getenv("JIRA_BASE_URL")
    packed = os.getenv("JIRA_DEPENDENCY")
    if packed and not (email and token and base):
        d = json.loads(packed)
        email = email or d.get("email")
        token = token or d.get("token")
        base = base or d.get("base_url")
    if not (email and token and base):
        raise RuntimeError("Saknar JIRA-credentials.")
    return email, token, base.rstrip("/")

def fetch_issues(jql: str, fields=None, max_results=200):
    if fields is None:
        fields = f"summary,issuelinks,issuetype,status,priority,{FLAGGED_CF}"
    email, token, base = get_creds()
    url = f"{base}/rest/api/3/search"
    start_at = 0
    issues = []
    while True:
        params = {
            "jql": jql,
            "fields": fields,
            "startAt": start_at,
            "maxResults": min(100, max_results - start_at),
            "expand": "names", 
        }
        r = requests.get(url, params=params, auth=HTTPBasicAuth(email, token))
        r.raise_for_status()
        data = r.json()

        # --- DEBUG: försök hitta "Flagged"/"Flaggad" fältet ---
        if start_at == 0:
            # 1) Försök via 'names' (funkar bara om fältet redan finns i 'fields' urvalet)
            names = data.get("names", {})
            flagged_key = next((k for k, v in names.items() if (v or "").lower() in ("flagged", "flaggad", "impediment")), None)
            print("Flagged field via names:", flagged_key)

            # 2) Om ej hittad: hämta ALLA fält och lista kandidater
            if not flagged_key:
                fields_url = f"{base}/rest/api/3/field"
                fr = requests.get(fields_url, auth=HTTPBasicAuth(email, token))
                fr.raise_for_status()
                all_fields = fr.json()
                cand = []
                for f in all_fields:
                    nm = (f.get("name") or "").lower()
                    if any(x in nm for x in ["flag", "flagg", "imped", "hinder"]):
                        cand.append((f.get("id"), f.get("name")))
                print("Flag candidates (id, name):", cand)


        # Skriv ut vilket customfield som är "Flagged" (görs bara på första sidan)
        if start_at == 0:
            names = data.get("names", {})
            flagged_key = next((k for k, v in names.items() if (v or "").lower() == "flagged"), None)
            print("Flagged field key:", flagged_key)

        issues.extend(data.get("issues", []))
        if start_at + len(data.get("issues", [])) >= min(max_results, data.get("total", 0)):
            break
        start_at += len(data.get("issues", []))
        if len(issues) >= max_results:
            break
    return issues

def is_flagged(issue) -> bool:
    f = issue.get("fields", {})
    val = f.get(FLAGGED_CF)
    # Kan vara None, tom lista, eller lista med options
    if not val:
        return False
    if isinstance(val, list):
        return len(val) > 0
    return True


def extract_edges(issues):
    """
    Bygger kanter baserat på issue-links (Depend, Blocks, Relates etc.)
    Returnerar: lista av (från, till, typ)
    """
    edges = []
    for it in issues:
        key = it["key"]
        links = it["fields"].get("issuelinks") or []
        for ln in links:
            link_type = ln["type"]["name"]  # t.ex. "Blocks", "Relates"
            inward = ln.get("inwardIssue")
            outward = ln.get("outwardIssue")
            # Exempel: "Blocks": outwardIssue = den som blockeras av 'key'
            if outward:
                edges.append((key, outward["key"], link_type))
            if inward:
                edges.append((inward["key"], key, link_type))
    # Ta bort dubbletter
    edges = list(set(edges))
    return edges

def build_mermaid(issues, edges):
    lines = ["flowchart LR",
             "classDef flagged stroke:#ff0000,stroke-width:3px;"]  # NYTT

    for it in issues:
        key = it["key"]
        summary = it["fields"]["summary"].replace("\n", " ")
        status = it["fields"]["status"]["name"]
        summary = summary.replace('"', '\\"')
        node_label = f"{key}\\n{summary}\\nStatus: {status}"
        lines.append(f'    {key}["{node_label}"]')
        if is_flagged(it):                              # NYTT
            lines.append(f"    class {key} flagged;")   # NYTT

    for a, b, t in edges:
        label = t.replace(" ", "_")
        lines.append(f"    {a} -->|{label}| {b}")
    return "\n".join(lines)

def build_graphviz_png(issues, edges, outfile="dad_graph"):
    dot = Digraph(comment="JIRA Dependencies", format="png")
    dot.attr(rankdir="LR", fontsize="10")
    
    # NYTT: bättre edge-routing
    dot.graph_attr.update({
        "splines": "ortho",   # ortogonala linjer
        "overlap": "false",   # försök undvika nod-överlapp
        "sep": "+10",         # extra separationsmarginal
        "esep": "+5",         # edge separation (minska edge-edge overlap)
        "nodesep": "0.6",
        "ranksep": "1.0",
    })

    # Skapa noder med status
    for it in issues:
        key = it["key"]
        summary = it["fields"]["summary"].replace("\n", " ")
        status = it["fields"]["status"]["name"]
        summary = summary.replace('"', '\\"')
        node_label = f"{key}\n{summary}\nStatus: {status}"
        if is_flagged(it):  # NYTT
            dot.node(key, node_label, shape="box", color="red", penwidth="3")
        else:
            dot.node(key, node_label, shape="box")

    # Skapa kanter mellan noder
    for a, b, t in edges:
        dot.edge(a, b, label=t)

    # --- SPARA DOT-KÄLLAN INNAN RENDERING ---
    with open(f"{outfile}.dot", "w", encoding="utf-8") as f:
        f.write(dot.source)

    # Rendera och spara som PNG
    path = dot.render(outfile, cleanup=True)
    return path


def build_graphviz_drawio(issues, edges, outfile="dad_graph"):
    dot = Digraph(comment="JIRA Dependencies", format="png")
    dot.attr(rankdir="LR", fontsize="10")
    
    # Skapa noder med status
    for it in issues:
        key = it["key"]
        summary = it["fields"]["summary"].replace("\n", " ")
        status = it["fields"]["status"]["name"]  # Hämta statusen här
        summary = summary.replace('"', '\\"')  # Escape quotes
        # Lägg till status i node label
        node_label = f"{key}\\n{summary}\\nStatus: {status}"  # Lägg till status i etiketten
        dot.node(key, node_label, shape="box")
    
    # Skapa kanter mellan noder
    for a, b, t in edges:
        dot.edge(a, b, label=t)

    # --- Debugging: Skriv ut dot.source för att se Graphviz-koden ---
    print("Printing Graphviz Source:")
    print(dot.source)  # This line prints the Graphviz source code directly to console

    # Spara DOT-fil (kan användas för felsökning)
    with open(f"{outfile}.dot", "w", encoding="utf-8") as f:
        f.write(dot.source)
    
    # Rendera och spara som PNG
    path = dot.render(outfile, cleanup=True)
    print(f"Skapade PNG: {path}")

    # Konvertera till .drawio-format
    try:
        from graphviz2drawio import graphviz2drawio
        xml = graphviz2drawio.convert(dot.source)
        with open(f"{outfile}.drawio", "w", encoding="utf-8") as f:
            f.write(xml)
        print(f"Skapade .drawio-fil: {outfile}.drawio")
    except Exception as e:
        print(f"Error vid skapande av .drawio-fil: {e}")
    
    return path

def build_drawio(issues, edges, outfile="dad_graph.drawio", base_url="https://companyname.atlassian.net"):
    # Create the root element for Draw.io
    mxfile_root = ET.Element("mxfile", host="app.diagrams.net")
    diagram = ET.SubElement(mxfile_root, "diagram", name="Page-1")

    # Create the graph model for the diagram
    graph_model = ET.SubElement(diagram, "mxGraphModel", dx="1162", dy="666", grid="1", gridSize="10", guides="1", tooltips="1", connect="1", arrows="1", fold="1", page="1", pageScale="1", pageWidth="827", pageHeight="1169", math="0", shadow="0")

    # Create the root cells for nodes and edges
    root_cells = ET.SubElement(graph_model, "root")
    # Create a placeholder for the first "empty" root cell (needed for Draw.io)
    ET.SubElement(root_cells, "mxCell", id="0")
    ET.SubElement(root_cells, "mxCell", id="1", parent="0")

    # Mapping for node ids
    id_map = {}
    next_id = 2  # 0 and 1 are used for root cells in draw.io
    bboxes = {}  # key -> (x, y, w, h)

    # Create a NetworkX graph to compute force-directed layout
    G = nx.DiGraph()

    # Add nodes and edges to the graph
    for it in issues:
        key = it["key"]
        G.add_node(key)

    for a, b, t in edges:
        G.add_edge(a, b, relationship=t)

    # --- Column layout by Status (normalized so existing *1000 scaling still works) ---
    from collections import defaultdict

    # 1) Kolumnordning (anpassa vid behov)
    wanted_order = [
       #gammal: "TO DO", "DESIGN", "SELECTED FOR DEV", "BEING DEVELOPED",
       #"READY FOR CODE REVIEW", "READY FOR TEST", "READY FOR PRODUCTION", "DONE"
       "Backlog", "Selected for Development", "Being developed", "Ready for code review", "Ready for test", "Ready for production", "Ready for Live",
       "DONE"
    ]
    present_statuses = {(it["fields"]["status"]["name"] or "").strip() for it in issues}
    ordered_statuses = [s for s in wanted_order if s in present_statuses] + \
                    sorted(present_statuses - set(wanted_order))
    col_index = {s: i for i, s in enumerate(ordered_statuses)}

    # 2) Prioritetsranking (case-insensitive)
    prio_rank = {"HIGHEST": 1, "HIGH": 2, "MEDIUM": 3, "LOW": 4, "LOWEST": 5}
    def priority_rank(it):
        p = ((it["fields"].get("priority") or {}).get("name") or "").upper()
        return prio_rank.get(p, 999)

    # 3) Gruppera per status och sortera inom kolumnen på prio (högst först)
    grouped = defaultdict(list)
    for it in issues:
        grouped[it["fields"]["status"]["name"]].append(it)
    for s in grouped:
        grouped[s].sort(key=lambda it: (priority_rank(it), it["key"]))

    # 4) Tilldela normaliserade koordinater (0..1), så *1000 i din nod-loop ger px
    positions = {}
    x0, y0 = 0.05, 0.05   # startmarginal
    sx, sy = 0.22, 0.12   # kolumn-/radsteg (justera vid behov)
    for s, col in col_index.items():
        for row, it in enumerate(grouped.get(s, [])):
            positions[it["key"]] = (x0 + col * sx, y0 + row * sy)

    # DEBUG: visa vilka issuetype-namn som kommer från Jira
    unique_types = sorted({((it["fields"].get("issuetype") or {}).get("name") or "") for it in issues})
    print("Issuetypes detected:", unique_types)

    # Create nodes for each issue, using computed positions
    for it in issues:
        key = it["key"]
        summary = (it["fields"].get("summary") or "").replace("\n", " ")
        status = it["fields"]["status"]["name"]
        issue_type = it["fields"]["issuetype"]["name"]
        release_scope = "Release" in it["fields"].get("fixVersions", [])
        
        # gamla: node_label = f"{key}\n{summary}\nStatus: {status}"
        node_label = f'<div><strong><a href="{base_url}/browse/{key}" target="_blank">{key}</a></strong></div><div>{summary}</div><div>Status: {status}</div>'


        node_id = str(next_id); next_id += 1
        id_map[key] = node_id

        issue_url = f"{base_url}/browse/{key}"
        
        # Choose shape based on scope (oval for within release, rectangle otherwise)
        shape = "ellipse" if release_scope else "rectangle"

        # Color scheme based on issue type (EPIC, Story, Task, etc.)
        # gammal: issue_color = "#FFDDC1" if issue_type == "EPIC" else "#D4E1F3" if issue_type == "Story" else "#F0F0F0"
        # Mycket ljusa pasteller för god läsbarhet
        t = (issue_type or "").strip().lower()
        palette = {
            "epic":      "#E7D1FF",  # lila
            "berättelse":     "#C4FFDE",  # grön
        #    "uppgift":      "#B2D6FF",  # blå
        #    "underordnad uppgift":  "#C4E0FF",  # blå ljus
        #    "bugg":       "#FFD6D8",  # röd
        #    "problem/bug":"#FFD6D8",  # röd
        #    "ny funktion":"#C4FFEB",  # grön / turkos
        #   "dokument":   "#FFADF4",  # rosa
        }
        issue_color = palette.get(t, "#F0F0F0")  # fallback: ljusgrå


        # gamla: style = f"rounded=1;whiteSpace=wrap;html=1;fillColor={issue_color};labelBackgroundColor=#FFFFFF;link={issue_url};shape={shape};"
        style = f"rounded=1;whiteSpace=wrap;html=1;fillColor={issue_color};labelBackgroundColor={issue_color};link={issue_url};shape={shape};portConstraint=eastwest;"

        # NYTT: röd ram om flagged
        if is_flagged(it):
            style += "strokeColor=#ff0000;strokeWidth=3;"

        # Get the computed position for the node from the force-directed layout
        pos = positions[key]
        x = pos[0] * 1000  # Scale the position to fit the diagram
        y = pos[1] * 1000

        node = ET.SubElement(
            root_cells, "mxCell",
            id=node_id,
            value=node_label,
            style=style,
            vertex="1",
            parent="1"
        )
        # ... inne i nodloopen, efter att du beräknat x,y ...
        w, h = 200, 80
        ET.SubElement(node, "mxGeometry", attrib={
            "x": str(x), "y": str(y), "width": str(w), "height": str(h), "as": "geometry"
        })
        bboxes[key] = (x, y, w, h)  # NYTT
    
    from collections import defaultdict
    lane_counters = defaultdict(int)

    def col_row_of(key):
        x_norm, y_norm = positions[key]
        col = round((x_norm - x0) / sx)
        row = round((y_norm - y0) / sy)
        return col, row

    # fria zoner
    GUTTER_MARGIN = 20     # px från nodkant i X-led
    LANE_STEP_X   = 14     # separera parallella kanter i “korridor” (X-led)
    LANE_STEP_Y   = 12     # separera parallella kanter i “kanal” (Y-led)

    def route_waypoints(a_key, b_key, lane_index=0):
        ax, ay, aw, ah = bboxes[a_key]
        bx, by, bw, bh = bboxes[b_key]
        a_cy = ay + ah/2.0
        b_cy = by + bh/2.0
        a_right = ax + aw
        b_left  = bx

        (acol, arow) = col_row_of(a_key)
        (bcol, brow) = col_row_of(b_key)

        # om samma kolumn: använd extern korridor till höger (eller vänster)
        if acol == bcol:
            # välj extern korridor till höger om kolumnens högerkant
            # vi tar max(a_right, b_left + bw) som kolumnens högra utbredning
            col_right_edge = max(ax + aw, bx + bw)
            ext_x = col_right_edge + 2 * GUTTER_MARGIN + lane_index * LANE_STEP_X
            return [
                (ext_x, a_cy),
                (ext_x, b_cy),
            ]


        # gutters strax utanför nodernas ytterkanter
        src_gutter_x = a_right + GUTTER_MARGIN + lane_index * LANE_STEP_X
        tgt_gutter_x = b_left  - GUTTER_MARGIN - lane_index * LANE_STEP_X

        # “kanal” mellan rader — välj en y-nivå mitt emellan raderna
        row_mid = (arow + brow) / 2.0
        channel_y = (y0 + row_mid * sy) * 1000 + lane_index * LANE_STEP_Y

        # specialfall: om målnoden är i kolumnen direkt intill källan
        # kan corridor i mitten vara smal — gutters räcker i praktiken.
        # Om kolumnerna är identiska (samma kolumn): ruta utanför kolumnen (Steg 3)

        return [
            (src_gutter_x, a_cy),   # ut i käll-gutter
            (src_gutter_x, channel_y),  # ned/upp till kanal
            (tgt_gutter_x, channel_y),  # horisontellt i fri kanal
            (tgt_gutter_x, b_cy),   # ned/upp till mål-center
        ]


    # Create edges (connections between tasks) with improved labels
    for a, b, t in edges:
        if a in id_map and b in id_map:
            edge_style = "edgeStyle=orthogonalEdgeStyle;orthogonal=1;rounded=0;jettySize=auto;exitPerimeter=1;entryPerimeter=1;avoidObstacle=1;"

            # färgkodning
            if t == "Blocks":
                edge_style += "strokeColor=#FF0000;"
            elif t == "Depends on":
                edge_style += "strokeColor=#0000FF;"

            edge_label = f"{t} Relationship"

            # lanes (separera parallella kanter)
            # alt A: bara kolumner
            pair = (col_row_of(a)[0], col_row_of(b)[0])
            # alt B: kolumn+rad för båda:
            # pair = (*col_row_of(a), *col_row_of(b))

            lane_idx = lane_counters[pair]
            lane_counters[pair] += 1

            edge = ET.SubElement(
                root_cells, "mxCell",
                style=edge_style,
                source=id_map[a], target=id_map[b],
                parent="1", edge="1", value=edge_label
            )

            # Inga waypoints => draw.io auto-routar när noder flyttas
            geom = ET.SubElement(edge, "mxGeometry", attrib={"relative": "1", "as": "geometry"})

            print(f"Edge created (lane {lane_idx}): {a} -> {b} ({t})")
        else:
            print(f"Warning: Edge skipped, node missing: {a}->{b}")

    # Save the XML file as a Draw.io file
    tree = ET.ElementTree(mxfile_root)
    tree.write(outfile, encoding="utf-8", xml_declaration=True)

    print(f"Created Draw.io file: {outfile}")
    return outfile

if __name__ == "__main__":
    # Byt JQL till ditt projekt, t.ex. 'project = YOURKEY AND issuetype in (Story, Task, Bug)'
    # äldst: jql = "project = TDAS ORDER BY created DESC"
    # gammal: jql = 'project = "TraxMate Dashboard" AND (fixVersion = "Traxmate 2.9.4") ORDER BY priority DESC'
    jql = 'project = "ProjectName" AND (fixVersion = "IterationName") ORDER BY priority DESC'
    issues = fetch_issues(jql)
    print(f"Hämtade {len(issues)} issues")
    edges = extract_edges(issues)
    print(f"Hämtade {len(edges)} beroenden")

    build_drawio(issues, edges, outfile="dad_graph.drawio", base_url="https://companyname.atlassian.net")

    # 1) Mermaid-utmatning (kan klistras in i t.ex. Markdown/Confluence som stödjer Mermaid)
    mermaid = build_mermaid(issues, edges)
    with open("dad_mermaid.md", "w", encoding="utf-8") as f:
        f.write("```mermaid\n")
        f.write(mermaid)
        f.write("\n```")
    print("Skapade: dad_mermaid.md")

    print("FLAGGED_CF =", FLAGGED_CF)
    print("Flagged count:", sum(1 for it in issues if is_flagged(it)))

    # 2) Graphviz PNG (bildfil)
    out = build_graphviz_png(issues, edges, outfile="dad_graph")
    print("Skapade bild:", out)  # => dad_graph.png

    # ...removed redundant call...