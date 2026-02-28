"""
MCP Roster Server for Mwananyamala Regional Referral Hospital Laboratory
Deploy to Render: https://render.com

Environment Variables:
- PORT: Port to run on (default: 10000 for Render)
- API_KEY: Optional API key for authentication
"""

import os
import json
import io
import base64
from datetime import date, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from fastapi import FastAPI, HTTPException, Header, Depends, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import pandas as pd
import uvicorn

# ============================================================================
# DATA MODELS
# ============================================================================

class RosterRequest(BaseModel):
    month: int = Field(..., ge=1, le=12, description="Month (1-12)")
    year: int = Field(..., ge=2024, le=2030, description="Year (2024-2030)")
    include_excel: bool = Field(default=True, description="Include Excel file in response")
    format: str = Field(default="json", description="Output format: json, excel, or both")

class ShiftValidateRequest(BaseModel):
    roster_data: Dict[str, Any]
    rules: List[str] = Field(default=["night_pattern", "leave_compliance", "sunday_rule"])

class MCPResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}

# ============================================================================
# STAFF DATABASE WITH REALISTIC SHIFT PREFERENCES
# ============================================================================

STAFF_DB = [
    # Management & Senior Staff - Strict OH only
    {"code": "NJAM", "name": "Shauri Ramadhani Njama", "id": "FRP 1083", "role": "Lab Manager", "title": "Lab Technologist", 
     "night_eligible": False, "sections": ["Management"],
     "shift_preference": {"type": "strict_oh", "no_pm": True, "no_emd": True, "no_bima": True, "weekend_day": "Sunday"}},
    
    {"code": "EKI", "name": "Ekinala Christopher Mwasamanyambi", "id": "FRP 368", "role": "Deputy Lab Manager", "title": "Lab Scientist", 
     "night_eligible": False, "sections": ["Management", "Hematology"],
     "shift_preference": {"type": "strict_oh", "no_pm": True, "no_emd": True, "no_bima": True, "weekend_day": "Saturday"}},
    
    {"code": "KIS", "name": "Julius Elias Kissinga", "id": "FRP 0029", "role": "Quality Officer", "title": "Lab Technologist", 
     "night_eligible": False, "sections": ["Quality"],
     "shift_preference": {"type": "strict_oh", "no_pm": True, "no_emd": True, "no_bima": True, "weekend_day": "Saturday"}},
    
    {"code": "LOV", "name": "Loveness Abdallah Sonda", "id": "FRP 1061", "role": "Deputy Hematology & BT", "title": "Lab Technologist", 
     "night_eligible": False, "sections": ["Hematology"],
     "shift_preference": {"type": "strict_oh", "no_pm": True, "no_emd": True, "no_bima": True, "weekend_day": "Saturday"}},
    
    {"code": "CATH", "name": "Catherine Emily Mmari", "id": "FRP 3599", "role": "Head of TB & Leprosy", "title": "Lab Scientist", 
     "night_eligible": False, "sections": ["TB"],
     "shift_preference": {"type": "strict_oh", "no_pm": True, "no_emd": True, "no_bima": True, "weekend_day": "Saturday"}},
    
    {"code": "JOHA", "name": "Joha Nuru Juma", "id": "FRP 1239", "role": "Head of Microbiology", "title": "Lab Scientist", 
     "night_eligible": False, "sections": ["Microbiology"],
     "shift_preference": {"type": "strict_oh", "no_pm": True, "no_emd": True, "no_bima": True, "weekend_day": "Sunday"}},
    
    {"code": "KHAD", "name": "Khadija Seif Issa", "id": "FRP 5468", "role": "Deputy Store Officer", "title": "Lab Technologist-VOL", 
     "night_eligible": False, "sections": ["Store"],
     "shift_preference": {"type": "strict_oh", "no_pm": True, "no_emd": True, "no_bima": True, "weekend_day": "Saturday"}},
    
    {"code": "CELI", "name": "Celine Abel Massawe", "id": "FRP 1107", "role": "Head of Parasitology", "title": "Lab Technologist", 
     "night_eligible": False, "sections": ["Parasitology"],
     "shift_preference": {"type": "strict_oh", "no_pm": True, "no_emd": True, "no_bima": True, "weekend_day": "Saturday"}},
    
    {"code": "TEKEL", "name": "Elphace Amon Tekela", "id": "FRP 3764", "role": "Head of Store", "title": "Lab Technologist", 
     "night_eligible": False, "sections": ["Store"],
     "shift_preference": {"type": "strict_oh", "no_pm": True, "no_emd": True, "no_bima": True, "weekend_day": "Saturday"}},
    
    {"code": "KATU", "name": "Mary James Katungutu", "id": "NaN", "role": "TB & Leprosy Staff", "title": "Lab Attendant", 
     "night_eligible": False, "sections": ["TB"],
     "shift_preference": {"type": "strict_oh", "no_pm": True, "no_emd": True, "no_bima": True, "weekend_day": "Sunday"}},
    
    {"code": "MAY", "name": "Mwajuma Amry Zullu", "id": "FRP 5706", "role": "Chemistry Staff", "title": "Lab Technologist", 
     "night_eligible": False, "sections": ["Chemistry"],
     "shift_preference": {"type": "strict_oh", "no_pm": True, "no_emd": True, "no_bima": True}},
    
    {"code": "BERTHA", "name": "Bertha Luther Mwamkoa", "id": "FRP 1319", "role": "Deputy Head of Phlebotomy", "title": "Lab Scientist", 
     "night_eligible": False, "sections": ["Phlebotomy"],
     "shift_preference": {"type": "strict_oh", "no_pm": True, "no_emd": True, "no_bima": True, "weekend_day": "Saturday"}},
    
    {"code": "ASMA", "name": "Asma Idrisa Kiluwa", "id": "NaN", "role": "-", "title": "-", 
     "night_eligible": False, "sections": [],
     "shift_preference": {"type": "strict_oh", "no_pm": True, "no_emd": True, "no_bima": True}},
    
    # OH weekdays, PM weekends (shuffle Sat/Sun)
    {"code": "OMAR", "name": "Omari Ramadhan Churi", "id": "FRP 6665", "role": "Deputy Quality Officer", "title": "Lab Technologist", 
     "night_eligible": True, "sections": ["Quality"],
     "shift_preference": {"type": "oh_weekdays_pm_weekends", "pm_days": ["Saturday", "Sunday"], "shuffle": True}},
    
    {"code": "AGRIPIN", "name": "Agrippina Julius France", "id": "NaN", "role": "Phlebotomy Staff", "title": "Lab Attendant", 
     "night_eligible": False, "sections": ["Phlebotomy"],
     "shift_preference": {"type": "oh_weekdays_pm_weekends", "pm_days": ["Saturday", "Sunday"], "shuffle": True, "weekend_day": "Saturday"}},
    
    # OH weekdays, PM only Sunday
    {"code": "NYAKUNGA", "name": "Lilian Festo Nyakunga", "id": "FRP 5318", "role": "Head of Serology", "title": "Lab Technologist", 
     "night_eligible": True, "sections": ["Serology"],
     "shift_preference": {"type": "oh_weekdays_pm_sunday", "pm_days": ["Sunday"]}},
    
    # Emergency predominant
    {"code": "MIK", "name": "Mike Levison Sanga", "id": "FRP 6897", "role": "Deputy Quality Officer", "title": "Lab Scientist-VOL", 
     "night_eligible": True, "sections": ["Quality", "EMD"],
     "shift_preference": {"type": "emd_predominant", "night_emd": True}},
    
    {"code": "SANG", "name": "Katawa Obeid Sanga", "id": "FRP 2010", "role": "Deputy Head of Chemistry", "title": "Lab Scientist", 
     "night_eligible": True, "sections": ["Chemistry", "EMD"],
     "shift_preference": {"type": "emd_predominant", "night_emd": True}},
    
    {"code": "FRANK", "name": "Frank Lucas Maiseli", "id": "FRP 7570", "role": "Phlebotomy Staff", "title": "Lab Technologist", 
     "night_eligible": False, "sections": ["Phlebotomy", "EMD"],
     "shift_preference": {"type": "emd_predominant"}},
    
    {"code": "JISKAKA", "name": "Filbert D Jiskaka", "id": "FRP 4550", "role": "Emergency Lab Staff", "title": "Lab Scientist-VOL", 
     "night_eligible": True, "sections": ["EMD"],
     "shift_preference": {"type": "emd_predominant", "weekend_day": "Sunday"}},
    
    {"code": "YSUPH", "name": "Yusuph Hassan Lupinda", "id": "FRP 10638", "role": "Emergency Lab Staff", "title": "Lab Scientist-VOL", 
     "night_eligible": True, "sections": ["EMD"],
     "shift_preference": {"type": "emd_predominant"}},
    
    # PM predominant
    {"code": "DOREEN", "name": "Doreen Damas Massawe", "id": "FRP 4054", "role": "Hematology Staff", "title": "Lab Technologist", 
     "night_eligible": True, "sections": ["Hematology"],
     "shift_preference": {"type": "pm_predominant", "oh_few": True}},
    
    {"code": "HAPPY", "name": "Happyfania James Bakunda", "id": "FRP4980", "role": "Chemistry Staff", "title": "Lab Scientist", 
     "night_eligible": True, "sections": ["Chemistry"],
     "shift_preference": {"type": "pm_predominant", "oh_few": True}},
    
    {"code": "VALENT", "name": "Valentina Opilius Sanga", "id": "FRP 8360", "role": "Deputy Phlebotomy", "title": "Lab Technologist", 
     "night_eligible": False, "sections": ["Phlebotomy"],
     "shift_preference": {"type": "pm_predominant", "oh_few": True}},
    
    # Night predominant
    {"code": "GOD", "name": "Godfrey Kenneth Mhoga", "id": "FRP 1213", "role": "Head of Chemistry", "title": "Lab Technologist", 
     "night_eligible": True, "sections": ["Chemistry"],
     "shift_preference": {"type": "night_predominant"}},
    
    {"code": "JOSEPH", "name": "Joseph Pauline Mhana", "id": "FRP 4066", "role": "Deputy Head of TB", "title": "Lab Scientist", 
     "night_eligible": False, "sections": ["TB"],
     "shift_preference": {"type": "night_predominant"}},
    
    {"code": "DATUS", "name": "Datus Tumwesige Celestini", "id": "FRP 4494", "role": "Chemistry Staff", "title": "Lab Technologist", 
     "night_eligible": True, "sections": ["Chemistry"],
     "shift_preference": {"type": "night_predominant"}},
    
    # BIMA predominant
    {"code": "NEEM", "name": "Neema Nestory Mrema", "id": "FRP 0755", "role": "Safety Officer", "title": "Lab Scientist", 
     "night_eligible": True, "sections": ["Safety", "BIMA"],
     "shift_preference": {"type": "bima_predominant", "weekend_day": "Sunday"}},
    
    {"code": "JENISTER", "name": "Jenister Simon Mrosso", "id": "FRP 4659", "role": "BIMA Lab Staff", "title": "Lab Technologist", 
     "night_eligible": False, "sections": ["BIMA"],
     "shift_preference": {"type": "bima_predominant"}},
    
    # Others - default rules
    {"code": "MAR", "name": "Mariam Charles Lazaro", "id": "FRP 5506", "role": "Head of Phlebotomy", "title": "Lab Technologist", 
     "night_eligible": False, "sections": ["Phlebotomy"]},
    
    {"code": "SALOM", "name": "Salome Deusdedit Mkwawe", "id": "FRP 8950", "role": "Deputy Head of TB", "title": "Lab Scientist", 
     "night_eligible": False, "sections": ["TB"]},
    
    {"code": "SHUW", "name": "Shuweikha Mohammed Ally", "id": "FRP 6115", "role": "Phlebotomy Staff", "title": "Lab Scientist", 
     "night_eligible": False, "sections": ["Phlebotomy"]},
    
    {"code": "PAUL", "name": "Paulo Marungwe Dagano", "id": "ERP 4744", "role": "BIMA Lab Staff", "title": "Assistance Lab Tech-VOL", 
     "night_eligible": False, "sections": ["BIMA"]},
]

# 2026 Leave schedule
LEAVE_2026 = [
    {"code": "LOV", "start": "2026-05-22", "end": "2026-06-19"},
    {"code": "OMAR", "start": "2026-10-19", "end": "2026-11-16"},
    {"code": "EKI", "start": "2026-11-30", "end": "2026-12-28"},
    {"code": "KIS", "start": "2026-11-16", "end": "2026-12-14"},
    {"code": "JOHA", "start": "2026-12-20", "end": "2027-01-18"},
    {"code": "NEEM", "start": "2026-06-12", "end": "2026-07-10"},
    {"code": "CATH", "start": "2026-12-14", "end": "2027-01-10"},
    {"code": "SALOM", "start": "2026-12-15", "end": "2027-01-11"},
    {"code": "CELI", "start": "2026-12-14", "end": "2027-01-10"},
    {"code": "GOD", "start": "2026-11-23", "end": "2026-12-21"},
    {"code": "TEKEL", "start": "2026-12-10", "end": "2027-01-08"},
    {"code": "VALENT", "start": "2026-04-06", "end": "2026-05-04"},
    {"code": "FRANK", "start": "2026-09-20", "end": "2026-10-20"},
    {"code": "MAY", "start": "2026-12-21", "end": "2027-01-17"},
    {"code": "KATU", "start": "2026-11-09", "end": "2026-12-06"},
    {"code": "JOSEPH", "start": "2026-06-30", "end": "2026-07-28"},
    {"code": "HAPPY", "start": "2026-10-20", "end": "2026-11-17"},
    {"code": "MAR", "start": "2026-12-21", "end": "2027-01-17"},
    {"code": "DATUS", "start": "2026-12-14", "end": "2027-01-12"},
    {"code": "SHUW", "start": "2026-09-10", "end": "2026-10-08"},
    {"code": "JENISTER", "start": "2026-03-30", "end": "2026-04-27"},
    {"code": "DOREEN", "start": "2026-06-28", "end": "2026-07-28"},
    {"code": "JISKAKA", "start": "2026-12-08", "end": "2027-07-18"},
    {"code": "YSUPH", "start": "2026-06-29", "end": "2026-07-27"},
    {"code": "AGRIPIN", "start": "2026-06-29", "end": "2026-07-27"},
    {"code": "KHAD", "start": "2026-08-03", "end": "2026-08-31"},
    {"code": "MIK", "start": "2026-04-13", "end": "2026-05-04"},
    {"code": "PAUL", "start": "2026-06-29", "end": "2026-07-27"}
]

# ============================================================================
# ROSTER ENGINE WITH REALISTIC SHIFT PREFERENCES
# ============================================================================

class RosterEngine:
    """
    Production Roster Engine implementing realistic lab shift preferences
    """
    
    def __init__(self):
        self.staff = {s["code"]: s for s in STAFF_DB}
        self.leave_records = LEAVE_2026
        
    def is_on_leave(self, staff_code: str, current_date: date) -> bool:
        """Check if staff is on annual leave"""
        for entry in self.leave_records:
            if entry["code"] == staff_code:
                start = date.fromisoformat(entry["start"])
                end = date.fromisoformat(entry["end"])
                if start <= current_date <= end:
                    return True
                if start.year > end.year:
                    if current_date >= start or current_date <= end:
                        return True
        return False
    
    def get_days_in_month(self, year: int, month: int) -> int:
        """Calculate days in month"""
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        return (next_month - date(year, month, 1)).days
    
    def get_staff_preference(self, code: str) -> Dict[str, Any]:
        """Get shift preference for staff member"""
        staff = self.staff.get(code, {})
        return staff.get("shift_preference", {"type": "default"})
    
    def generate(self, month: int, year: int) -> Dict[str, Any]:
        """
        Generate complete roster with realistic shift preferences
        """
        days = self.get_days_in_month(year, month)
        
        # Get night eligible staff (only those not restricted)
        night_eligible = [
            code for code, s in self.staff.items() 
            if s.get("night_eligible") and 
            self.get_staff_preference(code).get("type") not in ["strict_oh", "pm_predominant"]
        ]
        
        # Initialize schedule
        schedule = {code: [None] * days for code in self.staff.keys()}
        night_counts = {code: 0 for code in night_eligible}
        
        # PHASE 1: Assign night shifts (N→N→SD→DO pattern)
        # Only for night-predominant and night-eligible staff
        night_predominant = [
            code for code in self.staff.keys()
            if self.get_staff_preference(code).get("type") in ["night_predominant", "emd_predominant"]
            and code in night_eligible
        ]
        
        for day in range(days):
            current_date = date(year, month, day + 1)
            
            # Skip Sundays for night shifts (most staff prefer)
            if current_date.weekday() == 6:
                continue
            
            assigned_tonight = 0
            # Prioritize night-predominant staff
            candidates = sorted(
                [c for c in night_predominant if c in night_eligible], 
                key=lambda x: night_counts[x]
            ) + sorted(
                [c for c in night_eligible if c not in night_predominant],
                key=lambda x: night_counts[x]
            )
            
            for candidate in candidates:
                if assigned_tonight >= 2:  # 2 staff per night
                    break
                    
                if self.is_on_leave(candidate, current_date):
                    continue
                
                if schedule[candidate][day] is not None:
                    continue
                
                # Check if can start new sequence
                can_start = True
                if day > 0:
                    prev = schedule[candidate][day - 1]
                    if prev in ["N", "SD"]:
                        can_start = False
                    if prev == "N":
                        if day > 1 and schedule[candidate][day - 2] == "N":
                            can_start = False
                        else:
                            # Continue sequence
                            schedule[candidate][day] = "N"
                            if day + 1 < days:
                                schedule[candidate][day + 1] = "SD"
                            if day + 2 < days:
                                schedule[candidate][day + 2] = "DO"
                            night_counts[candidate] += 1
                            assigned_tonight += 1
                            can_start = False
                            continue
                
                if can_start and day + 3 < days:
                    if all(schedule[candidate][day + i] is None for i in range(4)):
                        leave_check = [self.is_on_leave(candidate, date(year, month, day + i + 1)) for i in range(4)]
                        if not any(leave_check):
                            schedule[candidate][day] = "N"
                            schedule[candidate][day + 1] = "N"
                            schedule[candidate][day + 2] = "SD"
                            schedule[candidate][day + 3] = "DO"
                            night_counts[candidate] += 2
                            assigned_tonight += 1
        
        # PHASE 2: Fill remaining shifts based on preferences
        roster = []
        
        for day in range(days):
            current_date = date(year, month, day + 1)
            day_entry = {
                "date": current_date.isoformat(),
                "day_name": current_date.strftime("%A"),
                "day_number": day + 1,
                "is_weekend": current_date.weekday() >= 5,
                "is_sunday": current_date.weekday() == 6,
                "is_saturday": current_date.weekday() == 5,
                "assignments": {}
            }
            
            for code, staff in self.staff.items():
                # Check leave first
                if self.is_on_leave(code, current_date):
                    day_entry["assignments"][code] = "A"
                    continue
                
                # Use night schedule if assigned
                if schedule[code][day] is not None:
                    day_entry["assignments"][code] = schedule[code][day]
                    continue
                
                # Get staff preferences
                pref = self.get_staff_preference(code)
                pref_type = pref.get("type", "default")
                
                # Apply shift preferences
                if pref_type == "strict_oh":
                    # Strict OH only, specific weekend day or DO
                    if day_entry["is_sunday"]:
                        if pref.get("weekend_day") == "Sunday":
                            day_entry["assignments"][code] = "OH"
                        else:
                            day_entry["assignments"][code] = "DO"
                    elif day_entry["is_saturday"]:
                        if pref.get("weekend_day") == "Saturday":
                            day_entry["assignments"][code] = "OH"
                        else:
                            day_entry["assignments"][code] = "DO"
                    else:
                        day_entry["assignments"][code] = "OH"
                
                elif pref_type == "oh_weekdays_pm_weekends":
                    # OH on weekdays, PM on weekends (shuffle Sat/Sun)
                    if day_entry["is_weekend"]:
                        if pref.get("shuffle"):
                            # Alternate PM between Sat and Sun
                            if (day // 7) % 2 == 0:
                                day_entry["assignments"][code] = "PM" if day_entry["is_saturday"] else "DO"
                            else:
                                day_entry["assignments"][code] = "PM" if day_entry["is_sunday"] else "DO"
                        else:
                            day_entry["assignments"][code] = "PM"
                    else:
                        day_entry["assignments"][code] = "OH"
                
                elif pref_type == "oh_weekdays_pm_sunday":
                    # OH on weekdays, PM only on Sunday
                    if day_entry["is_sunday"]:
                        day_entry["assignments"][code] = "PM"
                    elif day_entry["is_saturday"]:
                        day_entry["assignments"][code] = "DO"
                    else:
                        day_entry["assignments"][code] = "OH"
                
                elif pref_type == "emd_predominant":
                    # Emergency lab predominant
                    if day_entry["is_sunday"] and pref.get("weekend_day") == "Sunday":
                        day_entry["assignments"][code] = "OH"  # or their weekend preference
                    elif day_entry["is_saturday"]:
                        day_entry["assignments"][code] = "DO"
                    else:
                        # Rotate between OH+EMD and OH
                        if pref.get("night_emd") and code in night_counts:
                            # They do night EMD, fewer day EMD
                            day_entry["assignments"][code] = "OH+EMD" if day % 4 == 0 else "OH"
                        else:
                            day_entry["assignments"][code] = "OH+EMD" if day % 2 == 0 else "OH"
                
                elif pref_type == "pm_predominant":
                    # PM predominant, few OH
                    if day_entry["is_weekend"]:
                        day_entry["assignments"][code] = "DO"
                    else:
                        # Mostly PM, some OH
                        day_entry["assignments"][code] = "PM" if day % 3 != 0 else "OH"
                
                elif pref_type == "night_predominant":
                    # Night predominant - already handled in night schedule
                    # If not on night shift, give them DO or occasional OH
                    if day_entry["is_weekend"]:
                        day_entry["assignments"][code] = "DO"
                    else:
                        day_entry["assignments"][code] = "OH" if day % 3 == 0 else "DO"
                
                elif pref_type == "bima_predominant":
                    # BIMA predominant
                    if day_entry["is_sunday"] and pref.get("weekend_day") == "Sunday":
                        day_entry["assignments"][code] = "OH"  # Their Sunday working day
                    elif day_entry["is_saturday"]:
                        day_entry["assignments"][code] = "DO"
                    else:
                        day_entry["assignments"][code] = "OH+BIMA"
                
                else:
                    # Default rules
                    if day_entry["is_sunday"]:
                        day_entry["assignments"][code] = "DO"
                    elif day_entry["is_saturday"]:
                        day_entry["assignments"][code] = "DO"
                    else:
                        day_entry["assignments"][code] = "OH"
            
            roster.append(day_entry)
        
        # Calculate statistics
        shift_counts = {}
        for day in roster:
            for shift in day["assignments"].values():
                shift_counts[shift] = shift_counts.get(shift, 0) + 1
        
        return {
            "month": month,
            "year": year,
            "month_name": date(year, month, 1).strftime("%B"),
            "total_days": days,
            "total_staff": len(self.staff),
            "shift_distribution": shift_counts,
            "night_shift_distribution": night_counts,
            "roster": roster,
            "metadata": {
                "generated_at": date.today().isoformat(),
                "version": "2.1.0",
                "pattern": "N→N→SD→DO",
                "facility": "Mwananyamala Regional Referral Hospital Laboratory",
                "shift_preferences": "Realistic lab patterns implemented"
            }
        }
    
    def export_to_excel(self, roster_data: Dict[str, Any]) -> bytes:
        """Export roster to Excel format"""
        roster = roster_data["roster"]
        rows = []
        staff_codes = list(self.staff.keys())
        
        for day in roster:
            row = {
                "DATE": day["date"],
                "DAY": day["day_name"]
            }
            row.update(day["assignments"])
            rows.append(row)
        
        df = pd.DataFrame(rows)
        cols = ["DATE", "DAY"] + staff_codes
        df = df[cols]
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Duty Roster", index=False)
            workbook = writer.book
            worksheet = writer.sheets["Duty Roster"]
            
            worksheet.insert_rows(1, 4)
            worksheet["A1"] = "Laboratory Duty Roster"
            worksheet["A2"] = f"Effective Date: 01/{roster_data['month']:02d}/{roster_data['year']}"
            worksheet["A3"] = f"Review Date: {roster_data['total_days']}/{roster_data['month']:02d}/{roster_data['year']}"
            worksheet["A4"] = f"Version: 4 | Document No.: MRRL/F/190"
        
        output.seek(0)
        return output.getvalue()

# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title="MCP Roster Server",
    description="AI Roster Generation System with Realistic Lab Shift Patterns",
    version="2.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = RosterEngine()
API_KEY = os.getenv("API_KEY", None)

def verify_api_key(x_api_key: Optional[str] = Header(None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "MCP Roster Server",
        "version": "2.1.0",
        "staff_count": len(STAFF_DB),
        "pattern": "N→N→SD→DO",
        "shift_preferences": "Realistic lab patterns"
    }

@app.get("/staff")
async def get_staff():
    return {
        "total": len(STAFF_DB),
        "staff": STAFF_DB,
        "categories": {
            "strict_oh": [s["code"] for s in STAFF_DB if s.get("shift_preference", {}).get("type") == "strict_oh"],
            "night_predominant": [s["code"] for s in STAFF_DB if s.get("shift_preference", {}).get("type") == "night_predominant"],
            "pm_predominant": [s["code"] for s in STAFF_DB if s.get("shift_preference", {}).get("type") == "pm_predominant"],
            "emd_predominant": [s["code"] for s in STAFF_DB if s.get("shift_preference", {}).get("type") == "emd_predominant"],
            "bima_predominant": [s["code"] for s in STAFF_DB if s.get("shift_preference", {}).get("type") == "bima_predominant"]
        }
    }

@app.get("/leave")
async def get_leave_schedule(year: Optional[int] = None):
    leaves = LEAVE_2026
    if year:
        leaves = [l for l in leaves if year in l["start"] or year in l["end"]]
    return {"total": len(leaves), "leaves": leaves}

@app.post("/generate-roster", response_model=MCPResponse)
async def generate_roster(
    request: RosterRequest,
    background_tasks: BackgroundTasks,
    authorized: bool = Depends(verify_api_key)
):
    try:
        result = engine.generate(request.month, request.year)
        
        response_data = {
            "roster": result,
            "excel_available": request.include_excel
        }
        
        if request.include_excel:
            excel_bytes = engine.export_to_excel(result)
            excel_b64 = base64.b64encode(excel_bytes).decode("utf-8")
            response_data["excel_base64"] = excel_b64
            response_data["excel_filename"] = f"roster_{request.year}_{request.month:02d}.xlsx"
        
        return MCPResponse(
            success=True,
            data=response_data,
            metadata={
                "generated_at": date.today().isoformat(),
                "pattern_compliance": "N→N→SD→DO",
                "shift_preferences": "Realistic lab patterns",
                "total_assignments": sum(result["shift_distribution"].values())
            }
        )
        
    except Exception as e:
        return MCPResponse(
            success=False,
            error=str(e),
            metadata={"request": request.dict()}
        )

@app.post("/validate-roster")
async def validate_roster(request: ShiftValidateRequest):
    violations = []
    roster = request.roster_data.get("roster", [])
    
    if "night_pattern" in request.rules:
        for day_idx, day in enumerate(roster):
            for code, shift in day.get("assignments", {}).items():
                if shift == "N":
                    if day_idx + 3 < len(roster):
                        next1 = roster[day_idx + 1]["assignments"].get(code)
                        next2 = roster[day_idx + 2]["assignments"].get(code)
                        next3 = roster[day_idx + 3]["assignments"].get(code)
                        if [next1, next2, next3] != ["N", "SD", "DO"]:
                            if next1 != "A":
                                violations.append({
                                    "type": "night_pattern",
                                    "staff": code,
                                    "date": day["date"],
                                    "expected": "N,SD,DO",
                                    "actual": f"{next1},{next2},{next3}"
                                })
    
    return {
        "valid": len(violations) == 0,
        "violations": violations,
        "checks_performed": request.rules
    }

@app.get("/download-roster/{year}/{month}")
async def download_roster(year: int, month: int):
    try:
        result = engine.generate(month, year)
        excel_bytes = engine.export_to_excel(result)
        
        return StreamingResponse(
            io.BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=roster_{year}_{month:02d}.xlsx"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/mcp-schema")
async def mcp_schema():
    return {
        "tools": [
            {
                "name": "generate_lab_roster",
                "description": "Generates ISO-compliant laboratory roster with realistic shift preferences (strict OH, PM predominant, night predominant, EMD/BIMA allocation)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "month": {"type": "integer", "minimum": 1, "maximum": 12},
                        "year": {"type": "integer", "minimum": 2024, "maximum": 2030},
                        "include_excel": {"type": "boolean", "default": True}
                    },
                    "required": ["month", "year"]
                }
            }
        ],
        "endpoints": {
            "generate_roster": "/generate-roster",
            "validate_roster": "/validate-roster",
            "download_excel": "/download-roster/{year}/{month}"
        }
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)