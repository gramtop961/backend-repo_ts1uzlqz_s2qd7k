from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from bson import ObjectId

from database import db, create_document, get_documents

app = FastAPI(title="Adiba's Luxury Hotel API", version="1.0.0")

# CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Pydantic Helpers ----------
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return v
        try:
            return ObjectId(str(v))
        except Exception:
            raise ValueError("Invalid ObjectId")


# ---------- Models (request/response) ----------
class AvailabilityRequest(BaseModel):
    room_type: str
    check_in: datetime
    check_out: datetime
    guests: int = Field(1, ge=1)

class BookingRequest(BaseModel):
    customer_name: str
    customer_email: str
    room_type: str
    guests: int
    check_in: datetime
    check_out: datetime
    payment_method: Optional[str] = Field(None, description="Card | EasyPaisa | JazzCash")

class BookingResponse(BaseModel):
    booking_id: str
    status: str


# ---------- Utility ----------
ROOM_TYPES = [
    {
        "type": "Deluxe",
        "price": 180,
        "beds": 1,
        "capacity": 2,
        "amenities": ["King Bed", "City View", "Breakfast", "Wi‑Fi"],
        "images": [
            "https://images.unsplash.com/photo-1542314831-068cd1dbfeeb?q=80&w=1600&auto=format&fit=crop"
        ],
    },
    {
        "type": "Executive",
        "price": 260,
        "beds": 2,
        "capacity": 3,
        "amenities": ["King Bed", "Lounge Access", "Workspace", "Wi‑Fi"],
        "images": [
            "https://images.unsplash.com/photo-1528909514045-2fa4ac7a08ba?q=80&w=1600&auto=format&fit=crop"
        ],
    },
    {
        "type": "Royal Suite",
        "price": 480,
        "beds": 2,
        "capacity": 4,
        "amenities": ["2 Bedrooms", "Panoramic View", "Butler Service", "Jacuzzi"],
        "images": [
            "https://images.unsplash.com/photo-1505691723518-36a5ac3b2d52?q=80&w=1600&auto=format&fit=crop"
        ],
    },
]


def is_available(room_type: str, check_in: datetime, check_out: datetime) -> bool:
    # Overlap check: (start < existing_end) and (end > existing_start)
    conflicts = db["booking"].count_documents({
        "room_type": room_type,
        "$expr": {
            "$and": [
                {"$lt": ["$check_in", check_out]},
                {"$gt": ["$check_out", check_in]},
            ]
        },
    })
    return conflicts == 0


# ---------- Routes ----------
@app.get("/test")
def test():
    # Try a simple round-trip to DB (rooms collection just for visibility)
    return {"ok": True, "message": "Backend is running", "collections": db.list_collection_names()}


@app.get("/rooms")
def get_rooms():
    return ROOM_TYPES


@app.get("/availability")
def availability(room_type: str = Query(...), check_in: str = Query(...), check_out: str = Query(...), guests: int = Query(1)):
    try:
        ci = datetime.fromisoformat(check_in)
        co = datetime.fromisoformat(check_out)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format. Use ISO format.")
    if ci >= co:
        raise HTTPException(status_code=400, detail="Check-out must be after check-in")

    # Capacity check
    room = next((r for r in ROOM_TYPES if r["type"].lower() == room_type.lower()), None)
    if not room:
        raise HTTPException(status_code=404, detail="Room type not found")
    if guests > room["capacity"]:
        return {"available": False, "reason": "Exceeds capacity"}

    return {"available": is_available(room["type"], ci, co)}


@app.post("/book", response_model=BookingResponse)
def book(body: BookingRequest):
    # Validate date order
    if body.check_in >= body.check_out:
        raise HTTPException(status_code=400, detail="Check-out must be after check-in")

    # Capacity check
    room = next((r for r in ROOM_TYPES if r["type"].lower() == body.room_type.lower()), None)
    if not room:
        raise HTTPException(status_code=404, detail="Room type not found")
    if body.guests > room["capacity"]:
        raise HTTPException(status_code=400, detail="Exceeds room capacity")

    # Availability check
    if not is_available(room["type"], body.check_in, body.check_out):
        raise HTTPException(status_code=409, detail="Selected dates not available")

    # Create booking document
    data = {
        "customer_name": body.customer_name,
        "customer_email": body.customer_email,
        "room_type": room["type"],
        "guests": body.guests,
        "check_in": body.check_in,
        "check_out": body.check_out,
        "payment_method": body.payment_method or "Pending",
        "status": "Booked",
    }
    booking_id = create_document("booking", data)

    return BookingResponse(booking_id=booking_id, status="Booked")


@app.get("/dashboard")
def dashboard():
    total_bookings = db["booking"].count_documents({})
    cleaning = db["booking"].count_documents({"status": "Cleaning"})
    booked = db["booking"].count_documents({"status": "Booked"})

    # Simple line chart data (last 7 days bookings)
    today = datetime.utcnow().date()
    chart = []
    for i in range(7):
        day = today.fromordinal(today.toordinal() - (6 - i))
        start = datetime(day.year, day.month, day.day)
        end = datetime(day.year, day.month, day.day, 23, 59, 59)
        count = db["booking"].count_documents({"created_at": {"$gte": start, "$lte": end}})
        chart.append({"date": str(day), "bookings": count})

    notifications = list(db["notification"].find({}, {"_id": 0}).limit(10))

    return {
        "summary": {
            "total_bookings": total_bookings,
            "booked": booked,
            "cleaning": cleaning,
        },
        "chart": chart,
        "notifications": notifications,
    }


@app.post("/pay")
def pay(method: str = Query(..., description="Card | EasyPaisa | JazzCash"), booking_id: str = Query(...)):
    # This is a mock endpoint to simulate payment confirmation
    try:
        _id = ObjectId(booking_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid booking id")

    updated = db["booking"].update_one({"_id": _id}, {"$set": {"payment_method": method, "status": "Paid"}})
    if updated.matched_count == 0:
        raise HTTPException(status_code=404, detail="Booking not found")
    return {"status": "Paid", "booking_id": booking_id, "method": method}


@app.get("/")
def root():
    return {"name": "Adiba's Luxury Hotel API", "status": "ok"}
