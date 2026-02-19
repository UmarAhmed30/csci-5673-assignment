import sys
from pathlib import Path
import logging
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Literal
import mysql.connector
from zeep import Client as SoapClient

from server.buyer.helper import (
    create_buyer,
    login_buyer,
    logout_session,
    validate_session,
    touch_session,
    search_items,
    get_item,
    add_to_cart,
    remove_from_cart,
    get_cart,
    clear_cart,
    save_cart,
    provide_item_feedback,
    get_seller_rating,
    get_buyer_purchases,
)
from server.buyer.config import BUYER_SERVER_CONFIG

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Buyer Server APIs",
    description="API endpoints for buyer operations in the online marketplace",
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


class AddToCartRequest(BaseModel):
    item_id: int
    quantity: int


class RemoveFromCartRequest(BaseModel):
    quantity: int


class FeedbackRequest(BaseModel):
    feedback: Literal["up", "down"]


class PurchaseRequest(BaseModel):
    card_holder_name: str
    card_number: str
    expiration_date: str
    security_code: str


@app.post("/api/buyers/register", status_code=201, response_model=AuthResponse)
async def register_buyer(request: RegisterRequest):
    try:
        logger.info(f"Registration attempt for username: {request.username}")
        if not request.username or not request.password:
            logger.warning("Registration failed: Missing username or password")
            raise HTTPException(status_code=400, detail="Username and password are required")
        result = create_buyer(request.username, request.password)
        if isinstance(result, tuple):
            buyer_id, msg = result
            if not buyer_id:
                if "Duplicate entry" in msg or "already exists" in msg.lower():
                    logger.warning(f"Registration failed: Username {request.username} already exists")
                    raise HTTPException(status_code=409, detail="Username already exists")
                else:
                    logger.warning(f"Registration failed: {msg}")
                    raise HTTPException(status_code=400, detail=msg)
            logger.info(f"Registration successful for username: {request.username}, buyer_id: {buyer_id}")
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


@app.post("/api/buyers/login", response_model=AuthResponse)
async def login_buyer_endpoint(request: LoginRequest):
    try:
        logger.info(f"Login attempt for username: {request.username}")
        if not request.username or not request.password:
            logger.warning("Login failed: Missing username or password")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        session_token = login_buyer(request.username, request.password)
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


async def get_current_buyer(authorization: Optional[str] = Header(None)) -> int:
    if not authorization:
        logger.warning("Session validation failed: Missing Authorization header")
        raise HTTPException(status_code=401, detail="Authentication required")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning("Session validation failed: Invalid Authorization header format")
        raise HTTPException(status_code=401, detail="Invalid authentication token format")
    token = parts[1]
    try:
        buyer_id = validate_session(token)
        if not buyer_id:
            logger.warning(f"Session validation failed: Invalid or expired token")
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        touch_session(token)
        logger.debug(f"Session validated for buyer_id: {buyer_id}")
        return buyer_id
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during session validation: {str(e)}", exc_info=True)
        raise HTTPException(status_code=401, detail="Session validation failed")


@app.post("/api/buyers/logout", response_model=AuthResponse)
async def logout_buyer_endpoint(
    buyer_id: int = Depends(get_current_buyer),
    authorization: Optional[str] = Header(None)
):
    try:
        token = authorization.split()[1] if authorization else None
        if not token:
            logger.warning("Logout failed: Missing token")
            raise HTTPException(status_code=401, detail="Authentication required")
        logger.info(f"Logout request for buyer_id: {buyer_id}")
        logout_session(token)
        logger.info(f"Logout successful for buyer_id: {buyer_id}")
        return AuthResponse(message="Logout successful")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during logout: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "buyer-server"}


@app.get("/api/items/search")
async def search_items_endpoint(category: Optional[str] = None, keywords: Optional[str] = None):
    try:
        if not category:
            logger.warning("Item search failed: Missing category parameter")
            raise HTTPException(status_code=400, detail="Category parameter is required")
        logger.info(f"Item search request: category={category}, keywords={keywords}")
        keywords_list = None
        if keywords:
            keywords_list = [kw.strip() for kw in keywords.split(",") if kw.strip()]
        items = search_items(category, keywords_list)
        logger.info(f"Item search returned {len(items)} items")
        return {"items": items}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during item search: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.get("/api/items/{item_id}")
async def get_item_endpoint(item_id: int):
    try:
        logger.info(f"Item retrieval request for item_id: {item_id}")
        if item_id <= 0:
            logger.warning(f"Item retrieval failed: Invalid item_id {item_id}")
            raise HTTPException(status_code=422, detail="Item ID must be a positive integer")
        item = get_item(item_id)
        if not item:
            logger.warning(f"Item retrieval failed: Item {item_id} not found")
            raise HTTPException(status_code=404, detail=f"Item with ID {item_id} not found")
        logger.info(f"Item retrieval successful for item_id: {item_id}")
        return {"item": item}
    except HTTPException:
        raise
    except ValueError:
        logger.warning(f"Item retrieval failed: Invalid item_id format")
        raise HTTPException(status_code=422, detail="Item ID must be a valid integer")
    except Exception as e:
        logger.error(f"Unexpected error during item retrieval: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.post("/api/cart/items", status_code=201)
async def add_to_cart_endpoint(
    request: AddToCartRequest,
    buyer_id: int = Depends(get_current_buyer)
):
    try:
        logger.info(f"Add to cart request: buyer_id={buyer_id}, item_id={request.item_id}, quantity={request.quantity}")
        success, message = add_to_cart(buyer_id, request.item_id, request.quantity)
        if not success:
            if "not found" in message.lower():
                logger.warning(f"Add to cart failed: {message}")
                raise HTTPException(status_code=404, detail=message)
            else:
                logger.warning(f"Add to cart failed: {message}")
                raise HTTPException(status_code=400, detail=message)
        logger.info(f"Add to cart successful: buyer_id={buyer_id}, item_id={request.item_id}")
        return {"message": "Item added to cart"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during add to cart: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.delete("/api/cart/items/{item_id}")
async def remove_from_cart_endpoint(
    item_id: int,
    request: RemoveFromCartRequest,
    buyer_id: int = Depends(get_current_buyer)
):
    try:
        logger.info(f"Remove from cart request: buyer_id={buyer_id}, item_id={item_id}, quantity={request.quantity}")
        success, message = remove_from_cart(buyer_id, item_id, request.quantity)
        if not success:
            logger.warning(f"Remove from cart failed: {message}")
            raise HTTPException(status_code=400, detail=message)
        logger.info(f"Remove from cart successful: buyer_id={buyer_id}, item_id={item_id}")
        return {"message": "Item removed from cart"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during remove from cart: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.get("/api/cart")
async def get_cart_endpoint(buyer_id: int = Depends(get_current_buyer)):
    try:
        logger.info(f"Get cart request: buyer_id={buyer_id}")
        cart_items = get_cart(buyer_id)
        logger.info(f"Get cart successful: buyer_id={buyer_id}, items={len(cart_items)}")
        return {"cart": cart_items}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during get cart: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.delete("/api/cart")
async def clear_cart_endpoint(buyer_id: int = Depends(get_current_buyer)):
    try:
        logger.info(f"Clear cart request: buyer_id={buyer_id}")
        clear_cart(buyer_id)
        logger.info(f"Clear cart successful: buyer_id={buyer_id}")
        return {"message": "Cart cleared"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during clear cart: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.post("/api/cart/save")
async def save_cart_endpoint(buyer_id: int = Depends(get_current_buyer)):
    try:
        logger.info(f"Save cart request: buyer_id={buyer_id}")
        cart_items = get_cart(buyer_id)
        if not cart_items:
            logger.warning(f"Save cart failed: Empty cart for buyer_id={buyer_id}")
            raise HTTPException(status_code=400, detail="Cart is empty")
        success, message = save_cart(buyer_id)
        if not success:
            logger.warning(f"Save cart failed: {message}")
            raise HTTPException(status_code=400, detail=message)
        logger.info(f"Save cart successful: buyer_id={buyer_id}, {message}")
        return {"message": "Cart saved successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during save cart: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.post("/api/purchases", status_code=201)
async def make_purchase(
    request: PurchaseRequest,
    buyer_id: int = Depends(get_current_buyer)
):
    try:
        logger.info(f"Purchase request from buyer_id: {buyer_id}")
        cart_items = get_cart(buyer_id)
        if not cart_items:
            logger.warning(f"Purchase failed: Empty cart for buyer_id={buyer_id}")
            raise HTTPException(status_code=400, detail="Cart is empty")
        if not request.card_holder_name or not request.card_number or not request.expiration_date or not request.security_code:
            logger.warning("Purchase failed: Missing credit card information")
            raise HTTPException(status_code=400, detail="All credit card fields are required")
        try:
            soap_client = SoapClient('http://localhost:8002/?wsdl')
            result = soap_client.service.process_transaction(
                card_holder_name=request.card_holder_name,
                card_number=request.card_number,
                expiration_date=request.expiration_date,
                security_code=request.security_code
            )
            if result != "Yes":
                logger.warning(f"Purchase failed: Transaction declined for buyer_id={buyer_id}")
                raise HTTPException(status_code=402, detail="Payment declined. Please check your card details and try again.")
            logger.info(f"Transaction approved for buyer_id={buyer_id}")
        except Exception as e:
            logger.error(f"Financial service error: {str(e)}", exc_info=True)
            raise HTTPException(status_code=503, detail="Financial service unavailable. Please try again later.")
        success, message = save_cart(buyer_id)
        if not success:
            logger.warning(f"Purchase failed: {message}")
            raise HTTPException(status_code=400, detail=message)
        from db.client import ProductDBClient
        product_db = ProductDBClient()
        conn = product_db.get_connection()
        cur = conn.cursor()
        try:
            for item in cart_items:
                cur.execute(
                    "INSERT INTO purchases (buyer_id, item_id) VALUES (%s, %s)",
                    (buyer_id, item["item_id"])
                )
                # Decrease item quantity
                cur.execute(
                    "UPDATE items SET quantity = quantity - %s WHERE item_id = %s",
                    (item["quantity"], item["item_id"])
                )
            conn.commit()
            clear_cart(buyer_id)
            logger.info(f"Purchase successful: buyer_id={buyer_id}, items={len(cart_items)}")
            return {"message": "Purchase completed successfully", "items_purchased": len(cart_items)}
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error during purchase: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to record purchase")
        finally:
            cur.close()
            conn.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during purchase: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.post("/api/items/{item_id}/feedback", status_code=201)
async def provide_feedback_endpoint(
    item_id: int,
    request: FeedbackRequest,
    buyer_id: int = Depends(get_current_buyer)
):
    try:
        logger.info(f"Provide feedback request: buyer_id={buyer_id}, item_id={item_id}, feedback={request.feedback}")
        if item_id <= 0:
            logger.warning(f"Provide feedback failed: Invalid item_id {item_id}")
            raise HTTPException(status_code=422, detail="Item ID must be a positive integer")
        success, message = provide_item_feedback(item_id, request.feedback)
        if not success:
            if "not found" in message.lower():
                logger.warning(f"Provide feedback failed: {message}")
                raise HTTPException(status_code=404, detail=message)
            else:
                logger.warning(f"Provide feedback failed: {message}")
                raise HTTPException(status_code=422, detail=message)
        logger.info(f"Provide feedback successful: buyer_id={buyer_id}, item_id={item_id}")
        return {"message": "Feedback recorded"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during provide feedback: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.get("/api/sellers/{seller_id}/rating")
async def get_seller_rating_endpoint(seller_id: int):
    try:
        logger.info(f"Get seller rating request for seller_id: {seller_id}")
        if seller_id <= 0:
            logger.warning(f"Get seller rating failed: Invalid seller_id {seller_id}")
            raise HTTPException(status_code=404, detail=f"Seller with ID {seller_id} not found")
        rating = get_seller_rating(seller_id)
        if not rating:
            logger.warning(f"Get seller rating failed: Seller {seller_id} not found")
            raise HTTPException(status_code=404, detail=f"Seller with ID {seller_id} not found")
        logger.info(f"Get seller rating successful for seller_id: {seller_id}")
        return {"rating": rating}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during get seller rating: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.get("/api/buyers/purchases")
async def get_purchases_endpoint(buyer_id: int = Depends(get_current_buyer)):
    try:
        logger.info(f"Get purchases request: buyer_id={buyer_id}")
        purchases = get_buyer_purchases(buyer_id)
        logger.info(f"Get purchases successful: buyer_id={buyer_id}, purchases={len(purchases)}")
        return {"purchases": purchases}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during get purchases: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


if __name__ == "__main__":
    import uvicorn
    host = BUYER_SERVER_CONFIG.get("host", "0.0.0.0")
    port = BUYER_SERVER_CONFIG.get("port", 8000)
    logger.info(f"Starting Buyer Server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
