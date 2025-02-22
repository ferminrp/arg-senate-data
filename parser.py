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
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())
            if not text.strip():
                print(f"⚠️ Warning: No text extracted from {pdf_path}")
                return None
            return text
    except Exception as e:
        print(f"❌ Error processing PDF {pdf_path}: {str(e)}")
        return None

def parse_votation_data(text):
    """Parses the extracted text and returns structured voting data."""
    data = {}

    # Extract project information with improved patterns
    project_match = re.search(r'Proyecto:\s*([^\n]+)', text)
    if project_match:
        project_text = project_match.group(1).strip()
        # Try to extract ORDEN DEL DIA number
        orden_match = re.search(r'ORDEN DEL DIA (\d+)', project_text)
        if orden_match:
            data["motion_number"] = orden_match.group(1)
            # Extract project title (everything after the number in parentheses)
            title_match = re.search(r'ORDEN DEL DIA \d+\s*\((.*?)\)', project_text)
            if title_match:
                data["project_title"] = title_match.group(1).strip()
        else:
            # If no ORDEN DEL DIA number, store the full project text
            data["project_title"] = project_text
    else:
        # Try old format MOCION SOBRE TABLAS
        motion_match = re.search(r'MOCION SOBRE TABLAS Nº (\d+/\d+)', text)
        if motion_match:
            data["motion_number"] = motion_match.group(1)
        else:
            data["motion_number"] = None

    # Extract description if available
    description_match = re.search(r'Descripción:\s*([^\n]+)', text)
    data["description"] = description_match.group(1).strip() if description_match else None

    date_match = re.search(r'(?:Fecha:|Fecha )?(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})', text)
    
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

    # Validate total members
    if data["total_members"] is not None:
        if data["present"] is not None and data["absent"] is not None:
            if data["total_members"] != data["present"] + data["absent"]:
                print(f"⚠️ Warning: Total members ({data['total_members']}) != Present ({data['present']}) + Absent ({data['absent']})")

    # Extract individual votes with improved pattern
    votes = []
    # Updated pattern to better handle various formats and special characters
    vote_pattern = re.findall(r'(?:\d+\s*\.\s*|\b)([A-ZÁÉÍÓÚÑ][^()\n]+?)\s+(SI|NO|AUSENTE)\s+(\d+|Presidente)', text, re.UNICODE)

    for match in vote_pattern:
        name = match[0].strip().replace('  ', ' ')  # Clean up multiple spaces
        vote_type = match[1]
        seat = match[2]
        
        # Skip empty or malformed entries
        if not name or len(name) < 2:
            continue
            
        votes.append({
            "name": name,
            "vote": vote_type,
            "seat": seat if seat != "Presidente" else "Presidente"
        })

    data["votes"] = votes

    # Validate vote counts
    vote_counts = {
        "SI": sum(1 for v in votes if v["vote"] == "SI"),
        "NO": sum(1 for v in votes if v["vote"] == "NO"),
        "AUSENTE": sum(1 for v in votes if v["vote"] == "AUSENTE")
    }

    if data["affirmative"] is not None and vote_counts["SI"] != data["affirmative"]:
        print(f"⚠️ Warning: Affirmative votes mismatch - Counted: {vote_counts['SI']}, Reported: {data['affirmative']}")
    if data["negative"] is not None and vote_counts["NO"] != data["negative"]:
        print(f"⚠️ Warning: Negative votes mismatch - Counted: {vote_counts['NO']}, Reported: {data['negative']}")
    if data["absent"] is not None and vote_counts["AUSENTE"] != data["absent"]:
        print(f"⚠️ Warning: Absent votes mismatch - Counted: {vote_counts['AUSENTE']}, Reported: {data['absent']}")

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
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    results_by_year[filename] = json.load(f)
            except json.JSONDecodeError as e:
                print(f"❌ Error loading {filename}: {str(e)}")
                results_by_year[filename] = []
            except Exception as e:
                print(f"❌ Unexpected error loading {filename}: {str(e)}")
                results_by_year[filename] = []
    
    current_id = START_ID
    consecutive_failures = 0
    MAX_CONSECUTIVE_FAILURES = 5  # Stop after this many consecutive failures
    
    while consecutive_failures < MAX_CONSECUTIVE_FAILURES:
        current_id += 1
        pdf_path = download_pdf(current_id)
        
        if pdf_path:
            text = extract_text_from_pdf(pdf_path)
            if text:
                try:
                    data = parse_votation_data(text)
                    if not data.get("date"):
                        print(f"⚠️ Warning: No date found in Acta {current_id}")
                        consecutive_failures += 1
                        continue
                        
                    data["act_id"] = current_id
                    consecutive_failures = 0  # Reset counter on success
                    
                    # Determine which year file this should go into
                    output_file = get_output_filename(data["date"])
                    if output_file:
                        if output_file not in results_by_year:
                            results_by_year[output_file] = []
                        results_by_year[output_file].append(data)
                        
                        # Save after each successful download
                        try:
                            with open(output_file, "w", encoding="utf-8") as json_file:
                                json.dump(results_by_year[output_file], json_file, indent=4, ensure_ascii=False)
                            print(f"✅ Updated {output_file}")
                        except Exception as e:
                            print(f"❌ Error saving {output_file}: {str(e)}")
                except Exception as e:
                    print(f"❌ Error parsing Acta {current_id}: {str(e)}")
                    consecutive_failures += 1
            else:
                consecutive_failures += 1
        else:
            consecutive_failures += 1
            print(f"Consecutive failures: {consecutive_failures}")
    
    print(f"Stopped after {MAX_CONSECUTIVE_FAILURES} consecutive failures at ID {current_id}")

if __name__ == "__main__":
    main()