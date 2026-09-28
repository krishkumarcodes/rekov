"""
base/schemas/kiosk.py — Kiosk & Queue Pydantic Schemas
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class Department(BaseModel):
    id: str
    name: str
    code: str
    description: str
    active_doctors_count: int
    wait_time_minutes: int


class Doctor(BaseModel):
    id: str
    name: str
    department_id: str
    specialty: str
    room_number: str
    is_available: bool
    estimated_wait_minutes: int
    consultation_fee: float
    rating: float
    experience_years: int
    arrival_time: Optional[str] = None
    pin: Optional[str] = None
    shift_schedule: Optional[str] = None


class Receptionist(BaseModel):
    id: str
    name: str
    pin: str


class AuthLoginRequest(BaseModel):
    username: str
    pin: str


class AuthLoginResponse(BaseModel):
    token: str
    role: str
    user_id: str
    name: str


class HealthComboPackage(BaseModel):
    id: str
    title: str
    category: str
    description: str
    included_tests: List[str]
    price: float
    priority_bump: int


class VitalsInput(BaseModel):
    systolic_bp:   int   = Field(default=120, ge=60, le=240)
    diastolic_bp:  int   = Field(default=80,  ge=40, le=140)
    heart_rate:    int   = Field(default=75,  ge=40, le=220)
    temperature_c: float = Field(default=36.8, ge=34.0, le=42.0)
    pain_score:    int   = Field(default=0,  ge=0,  le=10)
    symptoms:      List[str] = Field(default_factory=list)


class PatientRegistration(BaseModel):
    national_id:      str
    full_name:        str
    phone:            str
    age:              int
    gender:           str
    insurance_member: bool = False
    insurance_id:     Optional[str] = None


class TicketCreateRequest(BaseModel):
    department_id:     str
    doctor_id:         Optional[str] = None
    combo_package_ids: List[str] = Field(default_factory=list)
    vitals:            Optional[VitalsInput] = None
    patient:           PatientRegistration
    payment_method:    str = "EXPRESS_CARD"


class QueueTicket(BaseModel):
    ticket_id:           str
    token_number:        str
    department_id:       str
    department_name:     str
    doctor_id:           Optional[str] = None
    doctor_name:         str
    room_number:         str
    patient_name:        str
    patient_phone:       Optional[str] = None
    status:              str            # WAITING | IN_CONSULTATION | COMPLETED | CANCELLED | SKIPPED
    priority_level:      str            # EMERGENCY | URGENT | STANDARD
    triage_score:        int
    combos_selected:     List[str] = Field(default_factory=list)
    total_fee:           float
    created_at:          str
    estimated_call_time: str
    receipt_pdf_url:     Optional[str] = None


class QueueBoardResponse(BaseModel):
    now_calling:        Optional[QueueTicket] = None
    recently_called:    List[QueueTicket] = Field(default_factory=list)
    waiting_queue:      List[QueueTicket] = Field(default_factory=list)
    completed_today:    int = 0
    average_wait_minutes: int = 8


class CallNextRequest(BaseModel):
    doctor_id:   str
    room_number: str


class UpdateTicketStatusRequest(BaseModel):
    ticket_id:  str
    new_status: str
