"""
base/schemas/auth.py — Auth & Doctor Login Schemas
"""

from pydantic import BaseModel


class DoctorLoginRequest(BaseModel):
    doctor_id: str
    password:  str


class DoctorLoginResponse(BaseModel):
    token:         str
    doctor_id:     str
    doctor_name:   str
    room_number:   str
    department_id: str
