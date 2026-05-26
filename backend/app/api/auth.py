from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from app.auth import create_admin_token

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

class LoginRequest(BaseModel):
    email: str
    password: str

@router.post("/login")
async def login(credentials: LoginRequest):
    # Dummy authentication for development purposes
    # In production, check against a user database
    if credentials.password == "admin" or credentials.email == "admin@visionguard.ai":
        token = create_admin_token({"email": credentials.email})
        return {
            "success": True,
            "data": {
                "user": {
                    "id": "1",
                    "email": credentials.email,
                    "name": "Admin",
                    "role": "admin",
                    "status": "active"
                },
                "tokens": {
                    "accessToken": token
                }
            }
        }
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials"
    )
