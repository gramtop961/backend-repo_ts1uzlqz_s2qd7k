from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime

# Booking collection
class Booking(BaseModel):
    customer_name: str = Field(..., description="Full name of the guest")
    customer_email: EmailStr
    room_type: str = Field(..., description="Deluxe | Executive | Royal Suite")
    guests: int = Field(1, ge=1)
    check_in: datetime
    check_out: datetime
    payment_method: Optional[str] = Field(None, description="Card | EasyPaisa | JazzCash")
    status: str = Field("Booked", description="Booked | Paid | Cleaning | Cancelled")

# Notification collection
class Notification(BaseModel):
    title: str
    message: str
    level: str = Field("info", description="info | warning | success")

# Room (catalog) collection, for flexibility if we want to manage via DB later
class Room(BaseModel):
    type: str
    price: float
    beds: int
    capacity: int
    amenities: List[str]
    images: List[str] = []
