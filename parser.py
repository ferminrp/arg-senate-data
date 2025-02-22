import requests
import pdfplumber
import os
import re
import json
from datetime import datetime

# Base URL for acta votaciones
BASE_URL = "https://www.senado.gob.ar/votaciones/verActaVotacion/{}"

# Folder to store PDFs
SAVE_FOLDER = "senate_votations"
os.makedirs(SAVE_FOLDER, exist_ok=True)

# Starting ID (keep the last successful ID from previous run)
START_ID = 2433

def get_output_filename(date_str):
    """Determines the output filename based on the voting date."""
    if not date_str:
        return None
    try:
        date = datetime.strptime(date_str, "%d/%m/%Y %H:%M:%S")
        return f"senate_voting_data_{date.year}.json"
    except ValueError:
        return None

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
    
    # Print the date being processed
    if data["date"]:
        print(f"Processing date: {data['date']}")

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
    negative_match = re.search(r'Negativos:\s*(\d+)', text)
    abstentions_match = re.search(r'Abstenciones:\s*(\d+)', text)
    
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

    # Extract voting result
    result_match = re.search(r'Resultado:\s*([A-ZÁÉÍÓÚÑ ]+)', text)
    data["result"] = result_match.group(1).strip() if result_match else None

    return data

def main():
    # Dictionary to store results by year
    results_by_year = {}
    
    # Load existing data if available
    for year in range(2023, 2025):  # Adjust range as needed
        filename = f"senate_voting_data_{year}.json"
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                results_by_year[filename] = json.load(f)
    
    current_id = START_ID
    consecutive_failures = 0
    MAX_CONSECUTIVE_FAILURES = 5  # Stop after this many consecutive failures
    
    while consecutive_failures < MAX_CONSECUTIVE_FAILURES:
        current_id += 1
        pdf_path = download_pdf(current_id)
        
        if pdf_path:
            consecutive_failures = 0  # Reset counter on success
            text = extract_text_from_pdf(pdf_path)
            data = parse_votation_data(text)
            data["act_id"] = current_id
            
            # Determine which year file this should go into
            if data["date"]:
                output_file = get_output_filename(data["date"])
                if output_file:
                    if output_file not in results_by_year:
                        results_by_year[output_file] = []
                    results_by_year[output_file].append(data)
                    
                    # Save after each successful download
                    with open(output_file, "w", encoding="utf-8") as json_file:
                        json.dump(results_by_year[output_file], json_file, indent=4, ensure_ascii=False)
                    print(f"✅ Updated {output_file}")
        else:
            consecutive_failures += 1
            print(f"Consecutive failures: {consecutive_failures}")
    
    print(f"Stopped after {MAX_CONSECUTIVE_FAILURES} consecutive failures at ID {current_id}")

if __name__ == "__main__":
    main()