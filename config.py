import re

# --- The Strategic 6-Tier Corporate Footprint ---
TIER_COMPANIES = {
    "TIER1": ["Johnson & Johnson", "Abbott", "Medtronic", "Philips", "Align Technology", "Thermo Fisher", "Roche", "Siemens Healthineers", "GE HealthCare", "Baxter", "Becton Dickinson", "Boston Scientific", "Stryker", "Zimmer Biomet", "ResMed", "Edwards Lifesciences", "Cardinal Health", "Hologic", "Smith & Nephew", "Danaher", "Bio-Rad", "Illumina", "Terumo", "Olympus"],
    "TIER2": ["Pfizer", "Novartis", "AstraZeneca", "GSK", "MSD", "Sanofi", "Boehringer Ingelheim", "Bayer", "Amgen", "Biogen", "Eli Lilly", "Bristol Myers Squibb", "Takeda", "AbbVie", "Servier"],
    "TIER3": ["Salesforce", "ServiceNow", "Zendesk", "Twilio", "Genesys", "NICE", "Five9", "Talkdesk", "Freshworks", "HubSpot", "Sprinklr", "Qualtrics"],
    "TIER4": ["Microsoft", "Oracle", "SAP", "Workday", "Atlassian", "Adobe", "Intuit", "Box", "Okta", "Datadog", "Snowflake", "MongoDB", "Elastic"],
    "TIER5": ["Grab", "Shopee", "Sea Group", "Lazada", "TikTok", "Bytedance", "Google", "Amazon", "Meta", "Apple", "Dell", "HP", "Cisco"],
    "TIER6": ["Concentrix", "Foundever", "TTEC", "Teleperformance", "Transcom", "Alorica", "Webhelp", "TaskUs"]
}

# Core aliases map to catch short-string edge cases precisely
COMPANY_ALIASES = {
    "jnj": "TIER1", "gehc": "TIER1", "bms": "TIER2", "sfdc": "TIER3"
}

# --- Comprehensive Executive Strategy Keyword Matrix ---
ALL_VALID_KEYWORDS = [
    "lead", "leader", "manager", "senior manager", "principal", "director", "senior director", 
    "associate director", "assistant director", "head", "vp", "vice president", "svp", "avp", 
    "executive director", "chief", "cxo", "country manager", "regional manager", "regional director", 
    "global head", "functional head", "operations manager", "operations director", "business operations", 
    "regional operations", "global operations", "service delivery", "delivery manager", "customer operations", 
    "commercial operations", "operational excellence", "operations excellence", "continuous improvement", 
    "process excellence", "transformation manager", "transformation director", "customer experience", "cx manager", 
    "cx director", "customer success", "contact center", "contact centre", "call center", "call centre", 
    "customer support", "customer service director", "support operations", "technical support manager", 
    "program manager", "program director", "portfolio manager", "pmo manager", "change manager", 
    "digital transformation", "business transformation", "strategic programs", "compliance manager", 
    "compliance director", "risk manager", "quality manager", "quality director", "quality assurance", 
    "qa manager", "regulatory affairs", "regulatory manager", "regulatory director", "audit manager", 
    "governance", "apac", "asia pacific", "sea", "asean", "regional head", "multi country manager", 
    "cluster manager", "territory manager", "staff", "senior principal", "specialist lead", "solution lead", 
    "practice lead", "domain lead", "commercial manager", "commercial director", "business development director", 
    "strategy manager", "strategy director", "growth manager", "revenue operations", "revops", "sales operations", 
    "go-to-market", "gtm manager", "gtm director"
]

def clean_and_tokenize(text):
    """Converts a string to lowercase and breaks it into an isolated list of pure alphanumeric words."""
    cleaned = re.sub(r'[^a-z0-9\s]', ' ', str(text).lower())
    return set(cleaned.split())

def get_company_tier_weight(company_name):
    """Calculates tier affiliation using deterministic tokenized word boundary verification."""
    c_clean_flat = re.sub(r'[^a-z0-9]', '', str(company_name).lower())
    if c_clean_flat in COMPANY_ALIASES:
        return COMPANY_ALIASES[c_clean_flat]

    input_tokens = clean_and_tokenize(company_name)
    if not input_tokens:
        return "BROAD_BOARD"

    for tier, companies in TIER_COMPANIES.items():
        for comp in companies:
            comp_tokens = clean_and_tokenize(comp)
            
            if len(comp_tokens) == 1:
                target_word = list(comp_tokens)[0]
                if target_word in input_tokens:
                    return tier
            else:
                if comp_tokens.issubset(input_tokens):
                    return tier
                    
    return "BROAD_BOARD"