# -*- coding: utf-8 -*-
"""
QMOOSA GLOBAL REPOSITORY AUTONOMOUS ENGINEERING SYSTEM
Portfolio Audit Controller & Inventory Engine
======================================================
Author: Martin Luther (elon00)
Architecture: QAPES (QMOOSA Autonomous Portfolio Engineering System)
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
import subprocess
from pathlib import Path
from datetime import datetime, timezone

OWNER = os.getenv("GITHUB_OWNER", "elon00")
OUTPUT = Path("reports")
OUTPUT.mkdir(exist_ok=True)

# Force UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def get_gh_token():
    token = os.getenv("GH_PORTFOLIO_TOKEN") or os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        # Try fetching from gh auth token
        try:
            res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                token = res.stdout.strip()
        except Exception:
            pass
    return token

TOKEN = get_gh_token()
API = "https://api.github.com"

HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "QMOOSA-Portfolio-Auditor",
    "X-GitHub-Api-Version": "2022-11-28",
}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"

def api_get(path):
    request = urllib.request.Request(API + path, headers=HEADERS)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code in (403, 429, 500, 502, 503, 504):
                wait_time = 2 ** (attempt + 1)
                print(f"  [API RETRY] Code {error.code} on {path}. Waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            raise
    raise RuntimeError("API retry limit reached")

def all_owned_repositories():
    print(f"Fetching complete repository catalog for owner: {OWNER}...")
    page = 1
    repositories = []
    
    # Try fetching as organization first, fallback to user
    endpoint_base = f"/orgs/{OWNER}/repos"
    try:
        test = api_get(f"{endpoint_base}?per_page=1")
    except Exception:
        endpoint_base = f"/users/{OWNER}/repos"

    while True:
        url = f"{endpoint_base}?per_page=100&page={page}&type=all&sort=full_name"
        print(f"  Querying Page {page}...", end=" ", flush=True)
        try:
            batch = api_get(url)
        except Exception as e:
            print(f"\n  [ERROR] Page {page} failed: {e}")
            break
            
        if not batch:
            print("Done (empty batch).")
            break
            
        print(f"Fetched {len(batch)} repos.")
        for repo in batch:
            if repo["owner"]["login"].lower() == OWNER.lower() and not repo.get("fork", False):
                repositories.append(repo)
                
        if len(batch) < 100:
            break
        page += 1
        time.sleep(0.5) # Gentle pacing
        
    return repositories

def classify(name, language, description):
    content = f"{name} {language or ''} {description or ''}".lower()
    rules = {
        "pqc-security": ("pqc", "quantum", "cryptography", "tls", "ml-dsa", "ml-kem", "lattice"),
        "blockchain-solana": ("solana", "svm", "anchor", "sealevel", "spl"),
        "blockchain-sui": ("sui", "move", "mysten"),
        "blockchain-evm": ("arbitrum", "ethereum", "stylus", "solidity", "evm", "hardhat"),
        "blockchain-algorand": ("algorand", "algo", "usdc", "asa"),
        "blockchain-icp": ("icp", "motoko", "canister"),
        "blockchain-multichain": ("chain", "polkadot", "mezo", "bridge"),
        "defi-token": ("dex", "amm", "token", "launchpad", "wallet", "bonding", "yield", "lending"),
        "ai-agentics": ("agent", "ai-", "llm", "chatbot", "rsi", "rea", "conway", "invariant"),
        "web-frontend": ("frontend", "dashboard", "web", "ui", "ux", "launchpad"),
    }
    categories = [
        group for group, words in rules.items()
        if any(word in content for word in words)
    ]
    return categories or ["general-systems"]

def calculate_priority_score(repo):
    """
    Autonomous Priority Formula:
    P_i = (I_i * R_i * C_i) / E_i
    Impact (I), Risk (R), Confidence (C), Effort (E > 0)
    """
    categories = repo.get("categories", [])
    
    # Impact (1 to 10)
    impact = 5.0
    if "pqc-security" in categories or "blockchain-solana" in categories:
        impact = 9.0
    elif "defi-token" in categories or "ai-agentics" in categories:
        impact = 8.0
        
    # Risk (1 to 10): higher means higher reliability/security priority
    risk = 6.0
    if "pqc-security" in categories:
        risk = 9.5
    elif "defi-token" in categories:
        risk = 8.5
        
    # Confidence (0.1 to 1.0): confidence in autonomous invariant verification
    confidence = 0.95
    
    # Effort (1 to 10)
    effort = 3.0
    
    p_score = (impact * risk * confidence) / effort
    return round(p_score, 2)

def main():
    print("=" * 70)
    print("    QMOOSA AUTONOMOUS PORTFOLIO ENGINEERING SYSTEM (QAPES)")
    print("=" * 70)
    
    repos = all_owned_repositories()
    inventory = []
    
    for repo in repos:
        cats = classify(
            repo["name"],
            repo.get("language"),
            repo.get("description"),
        )
        item = {
            "repository": repo["full_name"],
            "name": repo["name"],
            "url": repo["html_url"],
            "default_branch": repo.get("default_branch", "main"),
            "language": repo.get("language"),
            "visibility": repo.get("visibility", "public"),
            "archived": repo.get("archived", False),
            "categories": cats,
            "audit": "NOT_RUN",
            "ci": "NOT_VERIFIED",
            "production_score": None,
        }
        item["priority_score"] = calculate_priority_score(item)
        inventory.append(item)
        
    # Sort inventory by priority score descending
    inventory.sort(key=lambda x: x["priority_score"], reverse=True)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "owner": OWNER,
        "accessible_owned_nonfork_repositories": len(inventory),
        "scope": "Public and authorized private repositories",
        "categories_summary": {},
        "repositories": inventory,
    }
    
    # Compute categories summary
    cat_counts = {}
    for item in inventory:
        for c in item["categories"]:
            cat_counts[c] = cat_counts.get(c, 0) + 1
    report["categories_summary"] = cat_counts

    target_json = OUTPUT / "portfolio_inventory.json"
    with open(target_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        
    print("\n" + "=" * 70)
    print(f"Inventory Complete: {len(inventory)} accessible owned repositories.")
    print(f"Categories Breakdown:")
    for cat, count in sorted(cat_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {cat:<24}: {count} repos")
    print(f"Evidence Persisted: {target_json}")
    print("=" * 70)

if __name__ == "__main__":
    main()
