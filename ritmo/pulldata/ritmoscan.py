import os
import sys
import json
from pathlib import Path
from supabase import create_client, Client

PULLDATA_DIR = Path(__file__).resolve().parent
RITMO_DIR = PULLDATA_DIR.parent
ROOT_DIR = RITMO_DIR.parent

BACKUP_FILE = PULLDATA_DIR / "hospital_data.json"

def _load_config() -> dict:
    for p in [ROOT_DIR / "config.json", ROOT_DIR / "rekov" / "config.json"]:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}

def fetch_and_backup_data():
    """Fetches data from Supabase, saves offline backup, and returns data."""
    config = _load_config()
    
    url = config.get("SUPABASE_URL") or config.get("supabase", {}).get("url")
    key = config.get("SUPABASE_KEY") or config.get("supabase", {}).get("key")
    
    if not url or not key:
        return _load_offline_backup()
        
    try:
        supabase: Client = create_client(url, key)
        
        # Fetch departments
        depts_res = supabase.table("departments").select("*").execute()
        departments = depts_res.data if depts_res.data else []
        
        # Fetch doctors
        docs_res = supabase.table("doctors").select("*").execute()
        doctors = docs_res.data if docs_res.data else []
        
        data = {
            "departments": departments,
            "doctors": doctors
        }
        
        # Save offline backup
        BACKUP_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        
        return data
    except Exception as e:
        print(f"[RITMO Scan] Failed to fetch from Supabase: {e}")
        return _load_offline_backup()

def _load_offline_backup():
    """Loads the offline backup if Supabase is unreachable."""
    if BACKUP_FILE.exists():
        try:
            return json.loads(BACKUP_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"departments": [], "doctors": []}

def get_hospital_context() -> str:
    """Returns a formatted string of the hospital data to inject into AI prompt."""
    data = fetch_and_backup_data()
    
    depts = data.get("departments", [])
    docs = data.get("doctors", [])
    
    if not depts and not docs:
        return "Available departments: General, Cardiology, Neurology, Orthopedics, Pediatrics, Emergency."
        
    context = "Available Departments:\n"
    for d in depts:
        context += f"- {d.get('name', 'Unknown')} (ID: {d.get('id', 'N/A')}, Wait time: {d.get('wait_time_minutes', 0)} mins)\n"
        
    context += "\nAvailable Doctors:\n"
    for d in docs:
        dept_id = d.get('department_id')
        dept_name = next((dep.get('name') for dep in depts if dep.get('id') == dept_id), "General")
        is_avail = "Available" if d.get('is_available') else "Unavailable"
        context += f"- Dr. {d.get('name', 'Unknown')} (ID: {d.get('id', 'N/A')}, Dept: {dept_name}, Specialty: {d.get('specialty', 'General')}, Status: {is_avail}, Fee: ${d.get('consultation_fee', 0)})\n"
        
    return context

if __name__ == "__main__":
    print(get_hospital_context())
