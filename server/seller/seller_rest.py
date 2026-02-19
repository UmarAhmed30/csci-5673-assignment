import sys
from pathlib import Path
import logging
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import mysql.connector

from server.seller.helper import (
    create_seller,
    login_seller,
    logout_seller,
    validate_session,
    touch_session,
    get_seller_rating,
    register_item_for_sale,
    display_items_for_sale,
    update_units_for_sale,
    change_item_price,
)
from server.seller.config import SELLER_SERVER_CONFIG
from db.client import ProductDBClient

product_db = ProductDBClient()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Seller Server APIs",
    description="API endpoints for seller operations in the online marketplace",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import time


class ErrorLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        try:
            response = await call_next(request)
            if response.status_code >= 400:
                process_time = time.time() - start_time
                logger.warning(
                    f"Error response: {response.status_code} - {request.method} {request.url.path}",
                    extra={
                        "status_code": response.status_code,
                        "method": request.method,
                        "path": request.url.path,
                        "client": request.client.host if request.client else "unknown",
                        "process_time": f"{process_time:.3f}s",
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                    }
                )
            return response
        except Exception as exc:
            process_time = time.time() - start_time
            logger.error(
                f"Request failed: {request.method} {request.url.path} - {type(exc).__name__}: {str(exc)}",
                exc_info=True,
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "client": request.client.host if request.client else "unknown",
                    "process_time": f"{process_time:.3f}s",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                }
            )
            raise


app.add_middleware(ErrorLoggingMiddleware)

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        f"Unexpected error occurred: {type(exc).__name__}: {str(exc)}",
        exc_info=True,
        extra={
            "path": request.url.path,
            "method": request.method,
            "client": request.client.host if request.client else "unknown"
        }
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": "An unexpected error occurred. Please try again later."
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(
        f"Validation error: {str(exc)}",
        extra={
            "path": request.url.path,
            "method": request.method,
            "errors": exc.errors()
        }
    )
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation Error",
            "detail": "Request validation failed",
            "errors": exc.errors()
        }
    )


class RegisterRequest(BaseModel):
    username: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class AuthResponse(BaseModel):
    message: str
    token: Optional[str] = None

class ErrorResponse(BaseModel):
    error: str
    detail: str

class RegisterItemRequest(BaseModel):
    name: str
    category: int
    keywords: list[str]
    condition: str
    price: float
    quantity: int

class UpdateQuantityRequest(BaseModel):
    quantity: int

class UpdatePriceRequest(BaseModel):
    price: float


@app.post("/api/sellers/register", status_code=201, response_model=AuthResponse)
async def register_seller(request: RegisterRequest):
    try:
        logger.info(f"Registration attempt for username: {request.username}")
        if not request.username or not request.password:
            logger.warning("Registration failed: Missing username or password")
            raise HTTPException(status_code=400, detail="Username and password are required")
        result = create_seller(request.username, request.password)
        if isinstance(result, tuple):
            seller_id, msg = result
            if not seller_id:
                if "Duplicate entry" in msg or "already exists" in msg.lower():
                    logger.warning(f"Registration failed: Username {request.username} already exists")
                    raise HTTPException(status_code=409, detail="Username already exists")
                else:
                    logger.warning(f"Registration failed: {msg}")
                    raise HTTPException(status_code=400, detail=msg)
            logger.info(f"Registration successful for username: {request.username}, seller_id: {seller_id}")
            return AuthResponse(message="Account created successfully")
        else:
            logger.info(f"Registration successful for username: {request.username}")
            return AuthResponse(message="Account created successfully")
    except mysql.connector.IntegrityError as e:
        logger.warning(f"Registration failed: Duplicate username {request.username} - {str(e)}")
        raise HTTPException(status_code=409, detail="Username already exists")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during registration: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.post("/api/sellers/login", response_model=AuthResponse)
async def login_seller_endpoint(request: LoginRequest):
    try:
        logger.info(f"Login attempt for username: {request.username}")

        if not request.username or not request.password:
            logger.warning("Login failed: Missing username or password")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        session_token = login_seller(request.username, request.password)
        if not session_token:
            logger.warning(f"Login failed: Invalid credentials for username {request.username}")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        logger.info(f"Login successful for username: {request.username}")
        return AuthResponse(message="Login successful", token=session_token)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during login: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


async def get_current_seller(authorization: Optional[str] = Header(None)) -> int:
    if not authorization:
        logger.warning("Session validation failed: Missing Authorization header")
        raise HTTPException(status_code=401, detail="Authentication required")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning("Session validation failed: Invalid Authorization header format")
        raise HTTPException(status_code=401, detail="Invalid authentication token format")
    token = parts[1]
    try:
        seller_id = validate_session(token)
        if not seller_id:
            logger.warning(f"Session validation failed: Invalid or expired token")
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        touch_session(token)
        logger.debug(f"Session validated for seller_id: {seller_id}")
        return seller_id
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during session validation: {str(e)}", exc_info=True)
        raise HTTPException(status_code=401, detail="Session validation failed")


@app.post("/api/sellers/logout", response_model=AuthResponse)
async def logout_seller_endpoint(
    seller_id: int = Depends(get_current_seller),
    authorization: Optional[str] = Header(None)
):
    try:
        token = authorization.split()[1] if authorization else None
        if not token:
            logger.warning("Logout failed: Missing token")
            raise HTTPException(status_code=401, detail="Authentication required")
        logger.info(f"Logout request for seller_id: {seller_id}")
        logout_seller(token)
        logger.info(f"Logout successful for seller_id: {seller_id}")
        return AuthResponse(message="Logout successful")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during logout: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.post("/api/sellers/items", status_code=201)
async def register_item(
    request: RegisterItemRequest,
    seller_id: int = Depends(get_current_seller)
):
    try:
        logger.info(f"Item registration attempt by seller_id: {seller_id}")
        success, result = register_item_for_sale(
            seller_id=seller_id,
            item_name=request.name,
            item_category=request.category,
            condition_type=request.condition,
            salePrice=request.price,
            quantity=request.quantity,
            keywords=request.keywords
        )
        if not success:
            logger.warning(f"Item registration failed: {result}")
            raise HTTPException(status_code=422, detail=result)
        logger.info(f"Item registered successfully: {result}")
        return {"message": "Item registered successfully", "item_id": result["item_id"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during item registration: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.get("/api/sellers/items")
async def get_seller_items(seller_id: int = Depends(get_current_seller)):
    try:
        logger.info(f"Fetching items for seller_id: {seller_id}")
        items = display_items_for_sale(seller_id)
        logger.info(f"Retrieved {len(items)} items for seller_id: {seller_id}")
        return {"items": items}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching items: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.put("/api/sellers/items/{item_id}/quantity")
async def update_item_quantity(
    item_id: int,
    request: UpdateQuantityRequest,
    seller_id: int = Depends(get_current_seller)
):
    try:
        logger.info(f"Quantity update attempt for item_id: {item_id} by seller_id: {seller_id}")
        conn = product_db.get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT seller_id FROM items WHERE item_id=%s",
            (item_id,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            logger.warning(f"Item not found: {item_id}")
            raise HTTPException(status_code=404, detail="Item not found")
        if row["seller_id"] != seller_id:
            logger.warning(f"Seller {seller_id} does not own item {item_id}")
            raise HTTPException(status_code=403, detail="You do not own this item")
        success, message = update_units_for_sale(seller_id, item_id, request.quantity)
        if not success:
            logger.warning(f"Quantity update failed: {message}")
            raise HTTPException(status_code=400, detail=message)
        logger.info(f"Quantity updated successfully for item_id: {item_id}")
        return {"message": message}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating quantity: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.put("/api/sellers/items/{item_id}/price")
async def update_item_price(
    item_id: int,
    request: UpdatePriceRequest,
    seller_id: int = Depends(get_current_seller)
):
    try:
        logger.info(f"Price update attempt for item_id: {item_id} by seller_id: {seller_id}")
        if request.price <= 0:
            logger.warning(f"Invalid price: {request.price}")
            raise HTTPException(status_code=422, detail="Price must be a positive number")
        conn = product_db.get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT seller_id FROM items WHERE item_id=%s",
            (item_id,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            logger.warning(f"Item not found: {item_id}")
            raise HTTPException(status_code=404, detail="Item not found")
        if row["seller_id"] != seller_id:
            logger.warning(f"Seller {seller_id} does not own item {item_id}")
            raise HTTPException(status_code=403, detail="You do not own this item")
        success, message = change_item_price(seller_id, item_id, request.price)
        if not success:
            logger.warning(f"Price update failed: {message}")
            raise HTTPException(status_code=400, detail=message)
        logger.info(f"Price updated successfully for item_id: {item_id}")
        return {"message": "Price updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating price: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.get("/api/sellers/rating")
async def get_own_rating(seller_id: int = Depends(get_current_seller)):
    try:
        logger.info(f"Rating retrieval for seller_id: {seller_id}")
        rating = get_seller_rating(seller_id)
        if not rating:
            logger.warning(f"Rating not found for seller_id: {seller_id}")
            raise HTTPException(status_code=404, detail="Rating not found")
        logger.info(f"Rating retrieved for seller_id: {seller_id}")
        return {"rating": rating}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving rating: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "seller-server"}


if __name__ == "__main__":
    import uvicorn
    host = SELLER_SERVER_CONFIG.get("host", "0.0.0.0")
    port = SELLER_SERVER_CONFIG.get("port", 8001)
    logger.info(f"Starting Seller Server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
