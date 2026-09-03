#!/usr/bin/env python3
"""
tools.py — 모델에게 주는 도구 등록부 (19장 "도구를 붙이다")

여기 있는 것은 실제 서른 개 중 뼈대 여덟이다. 각 도구는 (스키마, 실행 함수) 한 쌍이다.
바깥 API 를 부르는 도구(ChEMBL · NCBI · AlphaFold · BioNeMo)는 FAKE 모드에서 정해진 가짜 결과를 돌려준다.

    search_papers          내 우물 (MCP 서버 — mcp_server_papers.py)
    get_paper_details      논문 한 편
    chembl_search_compound 공개 화합물 DB (REST)
    chembl_get_bioactivity 표적·활성
    analyze_molecule       분자식(SMILES) 성질 — RDKit 이 있으면 계산, 없으면 원자 수만
    ncbi_search            세상의 우물 — PubMed E-utilities (429 면 쉰다)
    alphafold_get_structure  AlphaFold DB 조회 — 계산이 아니라 조회
    dock_molecule          DiffDock — NVIDIA API. 키가 없으면 도구를 끈다
"""
import json
import os
import re
import time

FAKE = os.getenv("AGENT_FAKE", "0") == "1"
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_API_BASE = os.getenv("NVIDIA_API_BASE", "https://health.api.nvidia.com")


def _schema(name, desc, props, required):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required}}}


SCHEMAS = [
    _schema("search_papers", "내 논문 DB 검색 (16장). 서브쿼리마다 한 번.", {"query": {"type": "string"}, "top_k": {"type": "integer"}}, ["query"]),
    _schema("get_paper_details", "search_papers 가 돌려준 paper_id 로 상세.", {"paper_id": {"type": "string"}}, ["paper_id"]),
    _schema("chembl_search_compound", "ChEMBL 에서 화합물 찾기.", {"name": {"type": "string"}}, ["name"]),
    _schema("chembl_get_bioactivity", "ChEMBL ID 의 표적·활성.", {"chembl_id": {"type": "string"}}, ["chembl_id"]),
    _schema("analyze_molecule", "SMILES 의 분자 성질.", {"smiles": {"type": "string"}}, ["smiles"]),
    _schema("ncbi_search", "PubMed 최신 논문 검색 (오늘까지).", {"query": {"type": "string"}, "max_results": {"type": "integer"}}, ["query"]),
    _schema("alphafold_get_structure", "UniProt ID 의 AlphaFold 예측 구조 (조회).", {"uniprot_id": {"type": "string"}}, ["uniprot_id"]),
    _schema("dock_molecule", "DiffDock 도킹 (NVIDIA API). 공개된 구조·화합물만.", {"protein_pdb_url": {"type": "string"}, "ligand_smiles": {"type": "string"}}, ["protein_pdb_url", "ligand_smiles"]),
]


# ---------------------------------------------------------------- 바깥 API 도구

def chembl_search_compound(name):
    if FAKE:
        return {"chembl_id": "CHEMBL0000", "pref_name": name.upper(), "smiles": "CS(=O)CCCCN=C=S", "fake": True}
    import requests
    r = requests.get("https://www.ebi.ac.uk/chembl/api/data/molecule/search.json", params={"q": name, "limit": 1}, timeout=30)
    r.raise_for_status()
    m = (r.json().get("molecules") or [{}])[0]
    return {"chembl_id": m.get("molecule_chembl_id"), "pref_name": m.get("pref_name"),
            "smiles": (m.get("molecule_structures") or {}).get("canonical_smiles")}


def chembl_get_bioactivity(chembl_id):
    if FAKE:
        return {"chembl_id": chembl_id, "activities": [{"target": "HDAC1", "type": "IC50", "value": "15", "units": "uM"}], "fake": True}
    import requests
    r = requests.get("https://www.ebi.ac.uk/chembl/api/data/activity.json",
                     params={"molecule_chembl_id": chembl_id, "limit": 20}, timeout=30)
    r.raise_for_status()
    acts = r.json().get("activities", [])
    return {"chembl_id": chembl_id, "activities": [{"target": a.get("target_pref_name"), "type": a.get("standard_type"),
                                                    "value": a.get("standard_value"), "units": a.get("standard_units")} for a in acts]}


def analyze_molecule(smiles):
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors
        m = Chem.MolFromSmiles(smiles)
        if m is None:
            return {"error": "SMILES 를 읽지 못했다"}
        return {"smiles": smiles, "mol_weight": round(Descriptors.MolWt(m), 2), "logp": round(Descriptors.MolLogP(m), 2),
                "h_donors": Descriptors.NumHDonors(m), "h_acceptors": Descriptors.NumHAcceptors(m)}
    except ImportError:                                            # RDKit 없으면 원자만 센다
        atoms = re.findall(r"Cl|Br|[A-Z][a-z]?", smiles)
        counts = {}
        for a in atoms:
            counts[a] = counts.get(a, 0) + 1
        return {"smiles": smiles, "atom_counts": counts, "note": "rdkit 없음 — 원자 수만"}


_last_ncbi = 0.0


def ncbi_search(query, max_results=5):
    global _last_ncbi
    if FAKE:
        return {"query": query, "results": [{"pmid": "40000001", "title": f"(fake) latest paper on {query}", "year": 2026}], "fake": True}
    import requests
    wait = 0.4 - (time.time() - _last_ncbi)                        # 연속 호출 사이에 쉰다 — 429 방지
    if wait > 0:
        time.sleep(wait)
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    ids = requests.get(f"{base}/esearch.fcgi", params={"db": "pubmed", "term": query, "retmax": max_results, "retmode": "json", "sort": "date"}, timeout=30)
    ids.raise_for_status()
    idlist = ids.json()["esearchresult"].get("idlist", [])
    _last_ncbi = time.time()
    if not idlist:
        return {"query": query, "results": []}
    s = requests.get(f"{base}/esummary.fcgi", params={"db": "pubmed", "id": ",".join(idlist), "retmode": "json"}, timeout=30)
    s.raise_for_status()
    docs = s.json().get("result", {})
    return {"query": query, "results": [{"pmid": i, "title": docs.get(i, {}).get("title"), "year": (docs.get(i, {}).get("pubdate") or "")[:4]} for i in idlist]}


def alphafold_get_structure(uniprot_id):
    if FAKE:
        return {"uniprot_id": uniprot_id, "pdb_url": f"https://alphafold.ebi.ac.uk/files/AF-{uniprot_id}-F1-model_v4.pdb",
                "mean_plddt": 87.3, "note": "조회일 뿐 — 맞는지는 사람이 본다", "fake": True}
    import requests
    r = requests.get(f"https://alphafold.ebi.ac.uk/api/prediction/{uniprot_id}", timeout=30)
    r.raise_for_status()
    e = r.json()[0]
    return {"uniprot_id": uniprot_id, "pdb_url": e.get("pdbUrl"), "mean_plddt": e.get("globalMetricValue"),
            "note": "조회일 뿐 — 맞는지는 사람이 본다"}


def dock_molecule(protein_pdb_url, ligand_smiles):
    if not NVIDIA_API_KEY and not FAKE:
        return {"error": "BioNeMo 도구 사용 불가 — NVIDIA_API_KEY 를 확인하라 (키가 없으면 도구를 끈다)"}
    if FAKE:
        return {"poses": [{"confidence": 0.62, "note": "도구가 이렇게 말했다 — 맞는지는 아직 사람이 확인한다"}], "fake": True}
    import requests
    r = requests.post(f"{NVIDIA_API_BASE}/v1/biology/mit/diffdock", headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"},
                      json={"protein": protein_pdb_url, "ligand": ligand_smiles, "num_poses": 3}, timeout=600)
    r.raise_for_status()
    return r.json()


EXTERNAL = {"chembl_search_compound": chembl_search_compound, "chembl_get_bioactivity": chembl_get_bioactivity,
            "analyze_molecule": analyze_molecule, "ncbi_search": ncbi_search,
            "alphafold_get_structure": alphafold_get_structure, "dock_molecule": dock_molecule}


def enabled_schemas():
    """키가 없으면 도킹 도구는 목록에서 뺀다 — 모델에게 없는 손을 보이지 않는다."""
    names = {s["function"]["name"] for s in SCHEMAS}
    if not NVIDIA_API_KEY and not FAKE:
        names.discard("dock_molecule")
    return [s for s in SCHEMAS if s["function"]["name"] in names]
