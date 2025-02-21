import requests
import pdfplumber
import os
import re
import json

# Base URL for acta votaciones
BASE_URL = "https://www.senado.gob.ar/votaciones/verActaVotacion/{}"

# Folder to store PDFs
SAVE_FOLDER = "senate_votations"
os.makedirs(SAVE_FOLDER, exist_ok=True)

# Range of act numbers to pull
START_ID = 2433
END_ID = 2521

OUTPUT_JSON_FILE = "senate_voting_data.json"

def download_pdf(act_id):
    """Downloads the voting act PDF and saves it locally."""
    url = BASE_URL.format(act_id)
    headers = {"Accept": "application/pdf"}
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        pdf_path = os.path.join(SAVE_FOLDER, f"acta_{act_id}.pdf")
        with open(pdf_path, "wb") as f:
            f.write(response.content)
        print(f"✅ Downloaded: acta_{act_id}.pdf")
        return pdf_path
    else:
        print(f"❌ Failed to download Acta {act_id} (Status {response.status_code})")
        return None

def extract_text_from_pdf(pdf_path):
    """Extracts text from a given PDF file."""
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())

def parse_votation_data(text):
    """Parses the extracted text and returns structured voting data."""
    data = {}

    # Extract motion number and date
    motion_match = re.search(r'MOCION SOBRE TABLAS Nº (\d+/\d+)', text)
    date_match = re.search(r'(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})', text)
    
    data["motion_number"] = motion_match.group(1) if motion_match else None
    data["date"] = date_match.group(1) if date_match else None

    # Extract quorum and majority
    quorum_match = re.search(r'Tipo Quorum: ([^\n]+)', text)
    majority_match = re.search(r'Mayoría: ([^\n]+)', text)
    
    data["quorum_type"] = quorum_match.group(1).strip() if quorum_match else None
    data["majority_required"] = majority_match.group(1).strip() if majority_match else None

    # Extract voting results
    members_match = re.search(r'Miembros del cuerpo: (\d+)', text)
    present_match = re.search(r'Presentes: (\d+)', text)
    absent_match = re.search(r'Ausentes: (\d+)', text)
    affirmative_match = re.search(r'Afirmativos: (\d+)', text)
    negative_match = re.search(r'Negativos:\s+(\d+)', text)
    abstentions_match = re.search(r'Abstenciones:\s+(\d+)', text)

    data["total_members"] = int(members_match.group(1)) if members_match else None
    data["present"] = int(present_match.group(1)) if present_match else None
    data["absent"] = int(absent_match.group(1)) if absent_match else None
    data["affirmative"] = int(affirmative_match.group(1)) if affirmative_match else None
    data["negative"] = int(negative_match.group(1)) if negative_match else None
    data["abstentions"] = int(abstentions_match.group(1)) if abstentions_match else None

    # Extract individual votes
    votes = []
    vote_pattern = re.findall(r'(\d+\.\s+([\w\s,ÁÉÍÓÚÑñ]+)\s+(SI|NO|AUSENTE)\s+(\d+|Presidente))', text)

    for match in vote_pattern:
        votes.append({
            "name": match[1].strip(),
            "vote": match[2],
            "seat": match[3] if match[3] != "Presidente" else "Presidente"
        })

    data["votes"] = votes

    return data

def main():
    results = []
    for act_id in range(START_ID, END_ID + 1):
        pdf_path = download_pdf(act_id)
        if pdf_path:
            text = extract_text_from_pdf(pdf_path)
            data = parse_votation_data(text)
            data["act_id"] = act_id  # Store act ID for reference
            results.append(data)

    # Save the results to a JSON file
    with open(OUTPUT_JSON_FILE, "w", encoding="utf-8") as json_file:
        json.dump(results, json_file, indent=4, ensure_ascii=False)
    
    print(f"✅ Data saved to {OUTPUT_JSON_FILE}")

if __name__ == "__main__":
    main()
