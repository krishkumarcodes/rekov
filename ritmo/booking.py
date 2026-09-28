"""
ritmo/booking.py
================
Independent local ticket booking for RITMO.
Writes directly to local SQLite database so the FastAPI backend is completely optional.
"""
import uuid
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

def book_ticket_local(action_data: dict) -> str:
    """Inserts a ticket into the local database directly."""
    try:
        from base.database import SessionLocal, init_db
        from base.models import TicketModel
    except ImportError:
        return "Failed to import database modules."

    # Ensure DB tables exist
    init_db()
    
    db = SessionLocal()
    try:
        dept = action_data.get("dept_id", action_data.get("dept", "dep_gen"))
        pname = action_data.get("patient_name", "Unknown Patient")
        phone = action_data.get("phone", "")
        
        dept_name = "General"
        if "card" in dept.lower(): dept_name = "Cardiology"
        elif "neuro" in dept.lower(): dept_name = "Neurology"
        elif "ortho" in dept.lower(): dept_name = "Orthopedics"
        elif "ped" in dept.lower(): dept_name = "Pediatrics"
        elif "emg" in dept.lower(): dept_name = "Emergency"
        
        token = f"T{uuid.uuid4().hex[:4].upper()}"
        tid = str(uuid.uuid4())
        
        ticket = TicketModel(
            ticket_id=tid,
            token_number=token,
            department_id=dept,
            department_name=dept_name,
            patient_name=pname,
            patient_phone=phone,
            status="WAITING"
        )
        db.add(ticket)
        db.commit()
        return f"Ticket {token} booked for {pname} in {dept_name} (Saved locally)."
    except Exception as e:
        return f"Booking failed: {e}"
    finally:
        db.close()
