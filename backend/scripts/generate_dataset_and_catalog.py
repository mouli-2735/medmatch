import csv
import json
import os
import random
from pathlib import Path
import numpy as np
import cv2
from rapidfuzz import fuzz
import jellyfish

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
ROOT_DIR = BASE_DIR.parent
TESTSET_DIR = ROOT_DIR / "testset"
IMAGES_DIR = TESTSET_DIR / "images"
CROPS_DIR = TESTSET_DIR / "crops"

DATA_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
CROPS_DIR.mkdir(parents=True, exist_ok=True)

DRUG_RECORDS = [
    {"brand_name": "Celebrex", "generic_name": "Celecoxib", "strengths": "100mg, 200mg, 400mg", "form": "Capsule"},
    {"brand_name": "Celexa", "generic_name": "Citalopram", "strengths": "10mg, 20mg, 40mg", "form": "Tablet"},
    {"brand_name": "Augmentin", "generic_name": "Amoxicillin and Potassium Clavulanate", "strengths": "375mg, 625mg, 1000mg", "form": "Tablet"},
    {"brand_name": "Augmentan", "generic_name": "Amoxicillin", "strengths": "250mg, 500mg", "form": "Capsule"},
    {"brand_name": "Azithral", "generic_name": "Azithromycin", "strengths": "250mg, 500mg", "form": "Tablet"},
    {"brand_name": "Pantocid", "generic_name": "Pantoprazole", "strengths": "20mg, 40mg", "form": "Tablet"},
    {"brand_name": "Pan D", "generic_name": "Pantoprazole + Domperidone", "strengths": "40mg/30mg", "form": "Capsule"},
    {"brand_name": "Dolo 650", "generic_name": "Paracetamol", "strengths": "650mg", "form": "Tablet"},
    {"brand_name": "Crocin", "generic_name": "Paracetamol", "strengths": "500mg, 650mg", "form": "Tablet"},
    {"brand_name": "Calpol", "generic_name": "Paracetamol", "strengths": "120mg/5ml, 250mg/5ml, 500mg, 650mg", "form": "Syrup/Tablet"},
    {"brand_name": "Telma", "generic_name": "Telmisartan", "strengths": "20mg, 40mg, 80mg", "form": "Tablet"},
    {"brand_name": "Telma H", "generic_name": "Telmisartan + Hydrochlorothiazide", "strengths": "40mg/12.5mg, 80mg/12.5mg", "form": "Tablet"},
    {"brand_name": "Met XL", "generic_name": "Metoprolol Succinate", "strengths": "12.5mg, 25mg, 50mg, 100mg", "form": "Tablet"},
    {"brand_name": "Glycomet", "generic_name": "Metformin HCl", "strengths": "250mg, 500mg, 850mg, 1000mg", "form": "Tablet"},
    {"brand_name": "Glycomet GP", "generic_name": "Metformin + Glimepiride", "strengths": "500mg/1mg, 500mg/2mg", "form": "Tablet"},
    {"brand_name": "Amaryl", "generic_name": "Glimepiride", "strengths": "1mg, 2mg, 3mg, 4mg", "form": "Tablet"},
    {"brand_name": "Reminyl", "generic_name": "Galantamine", "strengths": "4mg, 8mg, 16mg", "form": "Tablet"},
    {"brand_name": "Zantac", "generic_name": "Ranitidine", "strengths": "150mg, 300mg", "form": "Tablet"},
    {"brand_name": "Xanax", "generic_name": "Alprazolam", "strengths": "0.25mg, 0.5mg, 1mg", "form": "Tablet"},
    {"brand_name": "Lasix", "generic_name": "Furosemide", "strengths": "20mg, 40mg", "form": "Tablet"},
    {"brand_name": "Losec", "generic_name": "Omeprazole", "strengths": "10mg, 20mg, 40mg", "form": "Capsule"},
    {"brand_name": "Montair LC", "generic_name": "Montelukast + Levocetirizine", "strengths": "10mg/5mg", "form": "Tablet"},
    {"brand_name": "Allegra", "generic_name": "Fexofenadine", "strengths": "120mg, 180mg", "form": "Tablet"},
    {"brand_name": "Cifran", "generic_name": "Ciprofloxacin", "strengths": "250mg, 500mg", "form": "Tablet"},
    {"brand_name": "Ciplox", "generic_name": "Ciprofloxacin", "strengths": "250mg, 500mg", "form": "Tablet"},
    {"brand_name": "Azee", "generic_name": "Azithromycin", "strengths": "250mg, 500mg", "form": "Tablet"},
    {"brand_name": "Omez", "generic_name": "Omeprazole", "strengths": "20mg, 40mg", "form": "Capsule"},
    {"brand_name": "Rabeloc", "generic_name": "Rabeprazole", "strengths": "20mg", "form": "Tablet"},
    {"brand_name": "Rosuvas", "generic_name": "Rosuvastatin", "strengths": "5mg, 10mg, 20mg", "form": "Tablet"},
    {"brand_name": "Atorva", "generic_name": "Atorvastatin", "strengths": "10mg, 20mg, 40mg, 80mg", "form": "Tablet"},
    {"brand_name": "Ecosprin", "generic_name": "Aspirin", "strengths": "75mg, 150mg", "form": "Tablet"},
    {"brand_name": "Combiflam", "generic_name": "Ibuprofen + Paracetamol", "strengths": "400mg/325mg", "form": "Tablet"},
    {"brand_name": "Brufen", "generic_name": "Ibuprofen", "strengths": "200mg, 400mg, 600mg", "form": "Tablet"},
    {"brand_name": "Meftal Spas", "generic_name": "Mefenamic Acid + Dicyclomine", "strengths": "250mg/10mg, 500mg/10mg", "form": "Tablet"},
    {"brand_name": "Taxim O", "generic_name": "Cefixime", "strengths": "100mg, 200mg", "form": "Tablet"},
    {"brand_name": "Monocef", "generic_name": "Ceftriaxone", "strengths": "250mg, 500mg, 1000mg", "form": "Injection"},
    {"brand_name": "Shelcal 500", "generic_name": "Calcium + Vitamin D3", "strengths": "500mg", "form": "Tablet"},
    {"brand_name": "Becosules", "generic_name": "B-Complex + Vitamin C", "strengths": "Standard", "form": "Capsule"},
    {"brand_name": "Thyronorm", "generic_name": "Levothyroxine", "strengths": "25mcg, 50mcg, 75mcg, 88mcg, 100mcg, 125mcg", "form": "Tablet"},
    {"brand_name": "Eltroxin", "generic_name": "Levothyroxine", "strengths": "25mcg, 50mcg, 100mcg", "form": "Tablet"},
    {"brand_name": "Voveran", "generic_name": "Diclofenac Sodium", "strengths": "50mg, 75mg", "form": "Tablet"},
    {"brand_name": "Dynapar", "generic_name": "Diclofenac", "strengths": "50mg, 75mg", "form": "Tablet"},
    {"brand_name": "Asthalin", "generic_name": "Salbutamol", "strengths": "2mg, 4mg, 100mcg", "form": "Tablet/Inhaler"},
    {"brand_name": "Budecort", "generic_name": "Budesonide", "strengths": "100mcg, 200mcg, 400mcg", "form": "Inhaler"},
    {"brand_name": "Omnacortil", "generic_name": "Prednisolone", "strengths": "5mg, 10mg, 20mg, 40mg", "form": "Tablet"},
    {"brand_name": "Limcee", "generic_name": "Ascorbic Acid (Vitamin C)", "strengths": "500mg", "form": "Chewable Tablet"},
    {"brand_name": "Celin", "generic_name": "Vitamin C", "strengths": "500mg", "form": "Tablet"},
    {"brand_name": "Neurobion Forte", "generic_name": "Vitamin B Complex with B12", "strengths": "Standard", "form": "Tablet"},
    {"brand_name": "Stamlo", "generic_name": "Amlodipine", "strengths": "2.5mg, 5mg, 10mg", "form": "Tablet"},
    {"brand_name": "Amlong", "generic_name": "Amlodipine", "strengths": "2.5mg, 5mg, 10mg", "form": "Tablet"},
    {"brand_name": "Cardace", "generic_name": "Ramipril", "strengths": "2.5mg, 5mg, 10mg", "form": "Tablet"},
    {"brand_name": "Cilacar", "generic_name": "Cilnidipine", "strengths": "5mg, 10mg, 20mg", "form": "Tablet"},
    {"brand_name": "Jardiance", "generic_name": "Empagliflozin", "strengths": "10mg, 25mg", "form": "Tablet"},
    {"brand_name": "Forxiga", "generic_name": "Dapagliflozin", "strengths": "5mg, 10mg", "form": "Tablet"},
    {"brand_name": "Metrogyl", "generic_name": "Metronidazole", "strengths": "200mg, 400mg", "form": "Tablet"},
    {"brand_name": "Norflox TZ", "generic_name": "Norfloxacin + Tinidazole", "strengths": "400mg/600mg", "form": "Tablet"},
    {"brand_name": "Zifi", "generic_name": "Cefixime", "strengths": "100mg, 200mg", "form": "Tablet"},
    {"brand_name": "Gudcef", "generic_name": "Cefpodoxime Proxetil", "strengths": "100mg, 200mg", "form": "Tablet"},
    {"brand_name": "Doxy 1", "generic_name": "Doxycycline", "strengths": "100mg", "form": "Capsule"},
    {"brand_name": "Novamox", "generic_name": "Amoxicillin", "strengths": "250mg, 500mg", "form": "Capsule"},
    {"brand_name": "Althrocin", "generic_name": "Erythromycin", "strengths": "250mg, 500mg", "form": "Tablet"},
    {"brand_name": "Roxid", "generic_name": "Roxithromycin", "strengths": "150mg, 300mg", "form": "Tablet"},
    {"brand_name": "Klacid", "generic_name": "Clarithromycin", "strengths": "250mg, 500mg", "form": "Tablet"},
    {"brand_name": "Dalacin C", "generic_name": "Clindamycin", "strengths": "150mg, 300mg", "form": "Capsule"},
    {"brand_name": "Linezolid", "generic_name": "Linezolid", "strengths": "600mg", "form": "Tablet"},
    {"brand_name": "Septran", "generic_name": "Co-trimoxazole", "strengths": "480mg, 960mg", "form": "Tablet"},
    {"brand_name": "Urimax", "generic_name": "Tamsulosin", "strengths": "0.4mg", "form": "Capsule"},
    {"brand_name": "Lonazep", "generic_name": "Clonazepam", "strengths": "0.25mg, 0.5mg, 1mg, 2mg", "form": "Tablet"},
    {"brand_name": "Nexito", "generic_name": "Escitalopram", "strengths": "5mg, 10mg, 20mg", "form": "Tablet"},
    {"brand_name": "Sertima", "generic_name": "Sertraline", "strengths": "25mg, 50mg, 100mg", "form": "Tablet"},
    {"brand_name": "Flunil", "generic_name": "Fluoxetine", "strengths": "20mg", "form": "Capsule"},
    {"brand_name": "Dulane", "generic_name": "Duloxetine", "strengths": "20mg, 30mg, 40mg", "form": "Capsule"},
    {"brand_name": "Tegretol", "generic_name": "Carbamazepine", "strengths": "100mg, 200mg, 400mg", "form": "Tablet"},
    {"brand_name": "Levera", "generic_name": "Levetiracetam", "strengths": "250mg, 500mg, 750mg, 1000mg", "form": "Tablet"},
    {"brand_name": "Eptoin", "generic_name": "Phenytoin Sodium", "strengths": "100mg", "form": "Tablet"},
    {"brand_name": "Zentel", "generic_name": "Albendazole", "strengths": "400mg", "form": "Chewable Tablet"},
    {"brand_name": "Ivecop", "generic_name": "Ivermectin", "strengths": "6mg, 12mg", "form": "Tablet"},
    {"brand_name": "Drotikind", "generic_name": "Drotaverine", "strengths": "40mg, 80mg", "form": "Tablet"},
    {"brand_name": "Buscopan", "generic_name": "Hyoscine Butylbromide", "strengths": "10mg", "form": "Tablet"},
    {"brand_name": "Ultracet", "generic_name": "Tramadol + Paracetamol", "strengths": "37.5mg/325mg", "form": "Tablet"},
    {"brand_name": "Aciloc", "generic_name": "Ranitidine", "strengths": "150mg, 300mg", "form": "Tablet"},
    {"brand_name": "Domstal", "generic_name": "Domperidone", "strengths": "10mg", "form": "Tablet"},
    {"brand_name": "Emeset", "generic_name": "Ondansetron", "strengths": "4mg, 8mg", "form": "Tablet"},
    {"brand_name": "Vertin", "generic_name": "Betahistine", "strengths": "8mg, 16mg, 24mg", "form": "Tablet"},
    {"brand_name": "Avomine", "generic_name": "Promethazine Theoclate", "strengths": "25mg", "form": "Tablet"},
    {"brand_name": "Duphalac", "generic_name": "Lactulose", "strengths": "10g/15ml", "form": "Syrup"},
    {"brand_name": "Lopamide", "generic_name": "Loperamide", "strengths": "2mg", "form": "Tablet"},
    {"brand_name": "Electral", "generic_name": "Oral Rehydration Salts", "strengths": "21.8g", "form": "Sachet"},
    {"brand_name": "Vinblastine", "generic_name": "Vinblastine Sulfate", "strengths": "10mg", "form": "Injection"},
    {"brand_name": "Vincristine", "generic_name": "Vincristine Sulfate", "strengths": "1mg", "form": "Injection"},
    {"brand_name": "Cetirizine", "generic_name": "Cetirizine HCl", "strengths": "5mg, 10mg", "form": "Tablet"}
]

KNOWN_LASA_PAIRS = [
    ("Celebrex", "Celexa", "Celebrex (anti-inflammatory NSAID) vs Celexa (SSRI antidepressant). Critical confusable pair!"),
    ("Augmentin", "Augmentan", "Augmentin (Amoxicillin-Clavulanate) vs Augmentan (plain Amoxicillin)."),
    ("Zantac", "Xanax", "Zantac (H2 blocker antacid) vs Xanax (Alprazolam sedative/anxiolytic). Severe overdose risk."),
    ("Losec", "Lasix", "Losec (Omeprazole PPI) vs Lasix (Furosemide loop diuretic). Severe dehydration/electrolyte risk."),
    ("Vinblastine", "Vincristine", "Fatal chemotherapy dosing confusion! Vincristine max 2mg, Vinblastine 10mg+."),
    ("Amaryl", "Reminyl", "Amaryl (Glimepiride antidiabetic) vs Reminyl (Galantamine dementia drug). Severe hypoglycemia risk."),
    ("Metformin", "Metronidazole", "Metformin (antidiabetic) vs Metronidazole (antibiotic/antiprotozoal)."),
    ("Pantocid", "Paracetamol", "Pantocid (PPI antacid) vs Paracetamol (antipyretic analgesic)."),
    ("Taxim O", "Taxim", "Taxim O (oral cefixime) vs Taxim (IV cefotaxime)."),
    ("Lonazep", "Lorazepam", "Lonazep (Clonazepam) vs Lorazepam (Ativan). Dosing and duration differences.")
]

def build_drugs_csv():
    csv_path = DATA_DIR / "drugs.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["brand_name", "generic_name", "strengths", "form"])
        writer.writeheader()
        for row in DRUG_RECORDS:
            writer.writerow(row)
    print(f"Created drugs.csv with {len(DRUG_RECORDS)} medicines at {csv_path}")

def build_lookalikes_csv():
    csv_path = DATA_DIR / "lookalikes.csv"
    pairs = []
    seen = set()
    for drug_a, drug_b, reason in KNOWN_LASA_PAIRS:
        key = tuple(sorted([drug_a.lower(), drug_b.lower()]))
        if key not in seen:
            seen.add(key)
            pairs.append({
                "drug_1": drug_a,
                "drug_2": drug_b,
                "similarity_score": 0.88,
                "metaphone_match": "YES",
                "risk_reason": reason
            })
            
    for i in range(len(DRUG_RECORDS)):
        for j in range(i + 1, len(DRUG_RECORDS)):
            name_1 = DRUG_RECORDS[i]["brand_name"]
            name_2 = DRUG_RECORDS[j]["brand_name"]
            key = tuple(sorted([name_1.lower(), name_2.lower()]))
            if key in seen:
                continue
            
            sim = fuzz.ratio(name_1.lower(), name_2.lower()) / 100.0
            m1 = jellyfish.metaphone(name_1)
            m2 = jellyfish.metaphone(name_2)
            is_meta = (m1 == m2) or (len(m1) > 2 and len(m2) > 2 and m1[:3] == m2[:3])
            
            if (sim >= 0.72) or (is_meta and sim >= 0.55):
                seen.add(key)
                pairs.append({
                    "drug_1": name_1,
                    "drug_2": name_2,
                    "similarity_score": round(sim, 2),
                    "metaphone_match": "YES" if m1 == m2 else "PARTIAL",
                    "risk_reason": f"Phonetically or orthographically similar ({name_1} vs {name_2})"
                })

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["drug_1", "drug_2", "similarity_score", "metaphone_match", "risk_reason"])
        writer.writeheader()
        for p in pairs:
            writer.writerow(p)
    print(f"Created lookalikes.csv with {len(pairs)} confusable pairs at {csv_path}")

def generate_synthetic_prescriptions():
    PRESCRIPTION_TEMPLATES = [
        ("rx_001", "Dr. A. Sharma, MD", "City Care Hospital, Delhi", "clean", [
            ("Augmentin", "625mg", "1-0-1", "5d", "Tab. Augmentin 625mg  1 - 0 - 1  x 5 days", "clean"),
            ("Pantocid", "40mg", "1-0-0", "5d", "Tab. Pantocid 40mg  1 - 0 - 0 (Before food)", "clean"),
            ("Dolo 650", "650mg", "SOS", "3d", "Tab. Dolo 650  SOS (for fever/pain)", "clean")
        ]),
        ("rx_002", "Dr. Rajesh Gupta, MBBS", "Gupta Clinic, Bangalore", "clean", [
            ("Azithral", "500mg", "OD", "3d", "Tab. Azithral 500 mg OD x 3 days", "clean"),
            ("Montair LC", "10mg/5mg", "0-0-1", "5d", "Tab Montair LC  0-0-1 HS x 5 d", "clean")
        ]),
        ("rx_003", "Dr. Sneha Verma, MD", "Metro Heart Center, Mumbai", "clean", [
            ("Telma", "40mg", "1-0-0", "30d", "Tab Telma 40mg  1 - 0 - 0 x 1 month", "clean"),
            ("Ecosprin", "75mg", "0-1-0", "30d", "Tab Ecosprin 75mg  0 - 1 - 0 After lunch", "clean"),
            ("Rosuvas", "10mg", "0-0-1", "30d", "Tab Rosuvas 10mg  0 - 0 - 1 at night", "clean")
        ]),
        ("rx_004", "Dr. Vikram Seth, MS (Ortho)", "Orthopedic Center, Hyderabad", "clean", [
            ("Combiflam", "400mg/325mg", "1-0-1", "3d", "Tab Combiflam  1-0-1 after food x 3d", "clean"),
            ("Pan D", "40mg/30mg", "1-0-0", "5d", "Cap Pan-D  1-0-0 empty stomach", "clean")
        ]),
        ("rx_005", "Dr. Priya Nair, MD (Pediatrics)", "Child Health Clinic, Chennai", "clean", [
            ("Calpol", "250mg/5ml", "TDS", "3d", "Syp Calpol 250mg/5ml  5ml TDS x 3 days", "clean"),
            ("Cetirizine", "5mg", "0-0-1", "5d", "Syp Cetirizine 5ml at bedtime x 5 days", "clean")
        ]),
        ("rx_006", "Dr. K. Raman, MD", "Apollo Polyclinic, Pune", "lookalike", [
            ("Celebrex", "200mg", "1-0-1", "5d", "Cap. Celebrex 200mg  1-0-1 x 5d (Arthritis)", "messy"),
            ("Pantocid", "40mg", "1-0-0", "5d", "Tab Pantocid 40mg  1-0-0", "clean")
        ]),
        ("rx_007", "Dr. M. Roy, MD (Psychiatry)", "Mind Clinic, Kolkata", "lookalike", [
            ("Celexa", "20mg", "0-0-1", "14d", "Tab Celexa 20mg  0-0-1 HS x 2 weeks", "messy"),
            ("Lonazep", "0.5mg", "0-0-1", "7d", "Tab Lonazep 0.5mg  0-0-1 HS x 7 days", "clean")
        ]),
        ("rx_008", "Dr. S. K. Bose, MD", "Woodlands Medical, Kolkata", "lookalike", [
            ("Lasix", "40mg", "1-0-0", "7d", "Tab Lasix 40mg  1 - 0 - 0 (Morning)", "messy"),
            ("Cardace", "5mg", "1-0-0", "14d", "Tab Cardace 5mg  1 - 0 - 0", "clean")
        ]),
        ("rx_009", "Dr. T. Joseph, MD", "Lakeshore Hospital, Kochi", "lookalike", [
            ("Losec", "20mg", "1-0-0", "14d", "Cap. Losec 20mg  1-0-0 empty stomach x 14d", "messy"),
            ("Domstal", "10mg", "1-0-1", "5d", "Tab Domstal 10mg  15 min before food", "clean")
        ]),
        ("rx_010", "Dr. H. Mehta, MD", "Sterling Hospital, Ahmedabad", "lookalike", [
            ("Zantac", "150mg", "1-0-1", "7d", "Tab Zantac 150mg  1-0-1 BD x 7d", "messy"),
            ("Omez", "20mg", "1-0-0", "14d", "Cap Omez 20mg  1-0-0 x 14 days", "clean")
        ]),
        ("rx_011", "Dr. N. Iyer, MD", "Fortis Hospital, Bengaluru", "lookalike", [
            ("Amaryl", "2mg", "1-0-0", "30d", "Tab Amaryl 2mg  1-0-0 before breakfast", "messy"),
            ("Glycomet", "500mg", "1-0-1", "30d", "Tab Glycomet 500mg  1-0-1 after food", "clean")
        ]),
        ("rx_012", "Dr. R. Kapoor, MBBS", "Govt Civil Hospital, Chandigarh", "messy", [
            ("Augmentin", "625mg", "1-0-1", "5d", "Augmntn 625  1-0-1 5d", "very_messy"),
            ("Crocin", "650mg", "TDS", "3d", "Crocn 650  TDS 3/7", "very_messy")
        ]),
        ("rx_013", "Dr. V. Prasad, MD", "Prasad Care Clinic, Lucknow", "messy", [
            ("Met XL", "25mg", "1-0-0", "30d", "Met-XL 25mg 1-0-0 x 1m", "messy"),
            ("Cilacar", "10mg", "0-0-1", "30d", "Cilacar 10 0-0-1 x 30d", "messy")
        ]),
        ("rx_014", "Dr. P. Bansal, MS", "Bansal Nursing Home, Jaipur", "messy", [
            ("Voveran", "50mg", "BD", "3d", "Vovran 50  BD pc 3d", "very_messy"),
            ("Rabeloc", "20mg", "OD", "5d", "Rabloc 20  OD ac 5d", "very_messy")
        ]),
        ("rx_015", "Dr. A. Sen, MD", "Peerless Hospital, Kolkata", "messy", [
            ("Thyronorm", "50mcg", "1-0-0", "60d", "Thyronorm 50mcg 1-0-0 early morning x 2m", "messy"),
            ("Shelcal 500", "500mg", "0-1-0", "30d", "Shelcal-500  0-1-0 post lunch x 1m", "messy")
        ]),
        ("rx_016", "Dr. S. Kulkarni, MD", "KEM Clinic, Pune", "messy", [
            ("Taxim O", "200mg", "1-0-1", "5d", "Txm-O 200  1-0-1 5d", "very_messy"),
            ("Dolo 650", "650mg", "SOS", "3d", "Dolo 650mg  SOS", "messy")
        ]),
        ("rx_017", "Dr. J. Fernandez, MD", "Holy Family, Goa", "messy", [
            ("Cifran", "500mg", "1-0-1", "5d", "Cifrn 500  1-0-1 x 5d", "very_messy"),
            ("Pantocid", "40mg", "1-0-0", "7d", "Panto 40  1-0-0", "messy")
        ]),
        ("rx_018", "Dr. N. Joshi, MD", "Deccan Medical, Nagpur", "messy", [
            ("Allegra", "120mg", "0-0-1", "10d", "Allgra 120  0-0-1 HS 10d", "messy"),
            ("Budecort", "200mcg", "1-0-1", "14d", "Budcort 200 inh 1-0-1 x 14d", "messy")
        ]),
        ("rx_019", "Dr. B. Das, MD", "AMRI Hospital, Bhubaneswar", "blurry", [
            ("Augmentin", "625mg", "1-0-1", "5d", "Tab Augmentin 625mg 1-0-1 x 5 days", "clean"),
            ("Dolo 650", "650mg", "TDS", "3d", "Tab Dolo 650mg TDS x 3 days", "clean")
        ]),
        ("rx_020", "Dr. C. Chawla, MD", "Chawla Polyclinic, Amritsar", "blurry", [
            ("Azithral", "500mg", "OD", "3d", "Tab Azithral 500mg OD x 3d", "clean"),
            ("Limcee", "500mg", "OD", "10d", "Tab Limcee 500mg chewable OD x 10d", "clean")
        ]),
        ("rx_021", "Dr. G. Reddy, MD", "Yashoda Hospital, Hyderabad", "dark", [
            ("Telma", "40mg", "1-0-0", "30d", "Tab Telma 40mg 1-0-0 x 1 month", "clean"),
            ("Met XL", "50mg", "1-0-0", "30d", "Tab Met XL 50mg 1-0-0 x 1 month", "clean")
        ]),
        ("rx_022", "Dr. T. Ghosh, MBBS", "Ghosh Clinic, Siliguri", "dark", [
            ("Glycomet", "500mg", "1-0-1", "30d", "Tab Glycomet 500mg 1-0-1 x 30d", "clean"),
            ("Januvia", "50mg", "1-0-0", "30d", "Tab Januvia 50mg 1-0-0 x 30d", "clean")
        ]),
        ("rx_023", "Dr. S. Nair, MD", "Aster Medcity, Kochi", "glare", [
            ("Celebrex", "200mg", "1-0-1", "5d", "Cap Celebrex 200mg 1-0-1 x 5d", "clean"),
            ("Pan D", "40mg/30mg", "1-0-0", "5d", "Cap Pan D 1-0-0 ac x 5d", "clean")
        ]),
        ("rx_024", "Dr. K. Singhania, MS", "Singhania Bone Clinic, Kanpur", "glare", [
            ("Ultracet", "37.5mg/325mg", "1-0-1", "3d", "Tab Ultracet 1-0-1 pc x 3d", "clean"),
            ("Pantocid", "40mg", "1-0-0", "5d", "Tab Pantocid 40mg 1-0-0", "clean")
        ]),
        ("rx_025", "Dr. R. Alva, MD (Geriatrics)", "Manipal Hospital, Mangalore", "edge_case", [
            ("Cardace", "2.5mg", "1-0-0", "30d", "Tab Cardace 2.5mg 1-0-0", "clean"),
            ("Jardiance", "10mg", "1-0-0", "30d", "Tab Jardiance 10mg 1-0-0", "clean"),
            ("Atorva", "20mg", "0-0-1", "30d", "Tab Atorva 20mg 0-0-1", "clean"),
            ("Ecosprin", "75mg", "0-1-0", "30d", "Tab Ecosprin 75mg 0-1-0", "clean")
        ]),
        ("rx_026", "Dr. I. Khan, MD", "Ruby General Hospital, Kolkata", "edge_case", [
            ("Meftal Spas", "500mg/10mg", "SOS", "3d", "Tab Meftal-Spas SOS for cramp", "messy"),
            ("Emeset", "4mg", "SOS", "3d", "Tab Emeset 4mg SOS", "messy")
        ]),
        ("rx_027", "Dr. P. Deshmukh, MD", "Lilavati Hospital, Mumbai", "edge_case", [
            ("unreadable", "unknown", "unknown", "unknown", "illegible scribble ~~~~~~~~", "very_messy"),
            ("Augmentin", "625mg", "1-0-1", "5d", "Tab Augmentin 625mg 1-0-1 x 5d", "clean")
        ]),
        ("rx_028", "Dr. M. Swaminathan, MD", "Apollo Hospital, Chennai", "edge_case", [
            ("Urimax", "0.4mg", "0-0-1", "30d", "Cap Urimax 0.4mg 0-0-1 at night", "clean"),
            ("Cilacar", "10mg", "1-0-0", "30d", "Tab Cilacar 10mg 1-0-0 morning", "clean")
        ])
    ]
    
    truth_data = {
        "dataset_name": "MedMatch Rx Synthetic Prescription Benchmark",
        "total_prescriptions": len(PRESCRIPTION_TEMPLATES),
        "created_date": "2026-10-23",
        "prescriptions": []
    }
    
    print(f"Generating {len(PRESCRIPTION_TEMPLATES)} synthetic prescription images and crops using OpenCV...")
    
    for rx_idx, (rx_id, doctor, clinic, category, lines) in enumerate(PRESCRIPTION_TEMPLATES):
        # Canvas: 1000 height, 800 width, 3 channels (BGR for OpenCV)
        bg_val = 248 if category != "dark" else 30
        img = np.full((1000, 800, 3), bg_val, dtype=np.uint8)
        
        # Add subtle paper texture
        noise = np.random.randint(-4, 5, (1000, 800, 3), dtype=np.int16)
        img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        
        # Colors (BGR)
        header_color = (90, 45, 20) if category != "dark" else (25, 15, 8)
        sub_color = (80, 80, 80) if category != "dark" else (35, 35, 35)
        border_color = (200, 200, 200) if category != "dark" else (50, 50, 50)
        
        # Header text
        cv2.putText(img, clinic.upper(), (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, header_color, 2, cv2.LINE_AA)
        cv2.putText(img, f"{doctor} | Reg No: MCI-{random.randint(10000, 99999)}", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.45, sub_color, 1, cv2.LINE_AA)
        cv2.line(img, (50, 100), (750, 100), border_color, 2)
        
        # Patient details
        cv2.putText(img, f"Patient: Test Patient {rx_idx+1}   Age/Sex: {random.randint(22, 68)}/M   Date: 23/10/2026", (50, 125), cv2.FONT_HERSHEY_SIMPLEX, 0.45, sub_color, 1, cv2.LINE_AA)
        cv2.line(img, (50, 145), (750, 145), border_color, 1)
        
        # Rx symbol
        cv2.putText(img, "Rx", (50, 190), cv2.FONT_HERSHEY_TRIPLEX, 1.2, header_color, 2, cv2.LINE_AA)
        
        # Doctor pen ink (BGR)
        ink_color = random.choice([
            (130, 40, 20),   # Deep blue ballpoint
            (100, 30, 10),   # Dark blue gel
            (35, 35, 35),    # Black ballpoint
            (45, 45, 45)     # Dark charcoal gel
        ])
        if category == "dark":
            ink_color = (int(ink_color[0]*0.2), int(ink_color[1]*0.2), int(ink_color[2]*0.2))
            
        line_records = []
        current_y = 250
        
        for l_idx, (drug, dose, freq, dur, text_to_draw, style) in enumerate(lines):
            line_id = l_idx + 1
            crop_filename = f"{rx_id}_line_{line_id}.png"
            crop_path = CROPS_DIR / crop_filename
            
            y_start = current_y - 30
            y_end = current_y + 35
            x_start = 60
            x_end = 740
            
            # Draw line text on main prescription
            font_scale = 0.65 if style == "clean" else 0.70
            thickness = 2 if style != "clean" else 1
            font_type = cv2.FONT_HERSHEY_SIMPLEX if style == "clean" else (cv2.FONT_HERSHEY_SCRIPT_SIMPLEX if style == "messy" else cv2.FONT_HERSHEY_SCRIPT_COMPLEX)
            
            line_text = f"{line_id}) {text_to_draw}"
            cv2.putText(img, line_text, (80, current_y), font_type, font_scale, ink_color, thickness, cv2.LINE_AA)
            
            # Isolated line crop
            crop_w = x_end - x_start
            crop_h = y_end - y_start
            crop_img = np.full((crop_h, crop_w, 3), bg_val, dtype=np.uint8)
            cv2.putText(crop_img, line_text, (20, crop_h // 2 + 10), font_type, font_scale, ink_color, thickness, cv2.LINE_AA)
            
            cv2.imwrite(str(crop_path), crop_img)
            
            if drug == "unreadable":
                guesses = ["unreadable"]
            else:
                g1 = drug
                g2 = drug[:-1] + ("x" if drug[-1] != "x" else "s") if len(drug) > 3 else drug + "x"
                g3 = drug[:2] + "t" + drug[3:] if len(drug) > 4 else drug + "ol"
                guesses = [g1, g2, g3]
                
            line_records.append({
                "line_id": line_id,
                "crop": crop_filename,
                "crop_relative_path": f"crops/{crop_filename}",
                "bbox": [x_start, y_start, x_end, y_end],
                "ground_truth": {
                    "drug": drug,
                    "dose": dose,
                    "frequency": freq,
                    "duration": dur
                },
                "guesses": guesses,
                "dose_raw": dose if dose != "unknown" else "",
                "freq_raw": freq if freq != "unknown" else "",
                "duration_raw": dur if dur != "unknown" else ""
            })
            
            current_y += 85
            
        # Signature
        cv2.line(img, (550, 880), (730, 880), (140, 140, 140) if category != "dark" else (40, 40, 40), 1)
        cv2.putText(img, "Doctor's Signature", (570, 905), cv2.FONT_HERSHEY_SIMPLEX, 0.45, sub_color, 1, cv2.LINE_AA)
        
        # Apply distortion filters for blurry or glare
        if category == "blurry":
            img = cv2.GaussianBlur(img, (29, 29), 9)
        elif category == "glare":
            # Add a severe bright overexposure circle in center
            h, w = img.shape[:2]
            y, x = np.ogrid[:h, :w]
            mask = ((x - 400)**2 + (y - 450)**2) <= (220**2)
            img[mask] = 255
            
        img_filename = f"{rx_id}.png"
        img_path = IMAGES_DIR / img_filename
        cv2.imwrite(str(img_path), img)
        
        truth_data["prescriptions"].append({
            "prescription_id": rx_id,
            "filename": img_filename,
            "category": category,
            "doctor": doctor,
            "clinic": clinic,
            "lines": line_records
        })
        
    truth_json_path = TESTSET_DIR / "truth.json"
    with open(truth_json_path, "w", encoding="utf-8") as f:
        json.dump(truth_data, f, indent=2)
        
    print(f"Created truth.json with {len(truth_data['prescriptions'])} prescriptions at {truth_json_path}")

if __name__ == "__main__":
    build_drugs_csv()
    build_lookalikes_csv()
    generate_synthetic_prescriptions()
