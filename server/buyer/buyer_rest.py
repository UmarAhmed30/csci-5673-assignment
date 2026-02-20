import sys
from pathlib import Path
import logging
from typing import Optional
import grpc
import buyer_pb2
import buyer_pb2_grpc

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Literal
import mysql.connector
from zeep import Client as SoapClient

from server.buyer.config import BUYER_SERVER_CONFIG, BUYER_GRPC_CONFIG

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# gRPC channel and stub
grpc_address = f"{BUYER_GRPC_CONFIG['host']}:{BUYER_GRPC_CONFIG['port']}"
channel = grpc.insecure_channel(grpc_address)
stub = buyer_pb2_grpc.BuyerServiceStub(channel)

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
        response = stub.CreateBuyer(
            buyer_pb2.CreateBuyerRequest(username=request.username, password=request.password)
        )
        if response.buyer_id == 0:
            if "Duplicate entry" in response.message or "already exists" in response.message.lower():
                logger.warning(f"Registration failed: Username {request.username} already exists")
                raise HTTPException(status_code=409, detail="Username already exists")
            else:
                logger.warning(f"Registration failed: {response.message}")
                raise HTTPException(status_code=400, detail=response.message)
        logger.info(f"Registration successful for username: {request.username}, buyer_id: {response.buyer_id}")
        return AuthResponse(message="Account created successfully")
    except grpc.RpcError as e:
        logger.error(f"gRPC error during registration: {e.details()}")
        raise HTTPException(status_code=500, detail="Service unavailable")
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
        response = stub.LoginBuyer(
            buyer_pb2.LoginBuyerRequest(username=request.username, password=request.password)
        )
        if not response.session_id:
            logger.warning(f"Login failed: Invalid credentials for username {request.username}")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        logger.info(f"Login successful for username: {request.username}")
        return AuthResponse(message="Login successful", token=response.session_id)
    except grpc.RpcError as e:
        logger.error(f"gRPC error during login: {e.details()}")
        raise HTTPException(status_code=500, detail="Service unavailable")
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
        response = stub.ValidateSession(
            buyer_pb2.ValidateSessionRequest(session_id=token)
        )
        if not response.user_id:
            logger.warning(f"Session validation failed: Invalid or expired token")
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        stub.TouchSession(buyer_pb2.TouchSessionRequest(session_id=token))
        logger.debug(f"Session validated for buyer_id: {response.user_id}")
        return response.user_id
    except grpc.RpcError as e:
        logger.error(f"gRPC error during session validation: {e.details()}")
        raise HTTPException(status_code=401, detail="Session validation failed")
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
        stub.LogoutBuyer(buyer_pb2.LogoutBuyerRequest(session_id=token))
        logger.info(f"Logout successful for buyer_id: {buyer_id}")
        return AuthResponse(message="Logout successful")
    except grpc.RpcError as e:
        logger.error(f"gRPC error during logout: {e.details()}")
        raise HTTPException(status_code=500, detail="Service unavailable")
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
        keywords_list = []
        if keywords:
            keywords_list = [kw.strip() for kw in keywords.split(",") if kw.strip()]
        response = stub.SearchItems(
            buyer_pb2.SearchItemsRequest(category=int(category), keywords=keywords_list)
        )
        items = [
            {
                "item_id": item.item_id,
                "item_name": item.item_name,
                "category": item.category,
                "condition_type": item.condition_type,
                "price": item.price,
                "quantity": item.quantity,
                "thumbs_up": item.thumbs_up,
                "thumbs_down": item.thumbs_down
            }
            for item in response.items
        ]
        logger.info(f"Item search returned {len(items)} items")
        return {"items": items}
    except grpc.RpcError as e:
        logger.error(f"gRPC error during item search: {e.details()}")
        raise HTTPException(status_code=500, detail="Service unavailable")
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
        response = stub.GetItem(buyer_pb2.GetItemRequest(item_id=item_id))
        if not response.success:
            logger.warning(f"Item retrieval failed: Item {item_id} not found")
            raise HTTPException(status_code=404, detail=f"Item with ID {item_id} not found")
        item = {
            "item_id": response.item.item_id,
            "item_name": response.item.item_name,
            "category": response.item.category,
            "condition_type": response.item.condition_type,
            "price": response.item.price,
            "quantity": response.item.quantity,
            "thumbs_up": response.item.thumbs_up,
            "thumbs_down": response.item.thumbs_down
        }
        logger.info(f"Item retrieval successful for item_id: {item_id}")
        return {"item": item}
    except grpc.RpcError as e:
        logger.error(f"gRPC error during item retrieval: {e.details()}")
        raise HTTPException(status_code=500, detail="Service unavailable")
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
        response = stub.AddToCart(
            buyer_pb2.AddToCartRequest(
                buyer_id=buyer_id,
                item_id=request.item_id,
                quantity=request.quantity
            )
        )
        if not response.success:
            if "not found" in response.message.lower():
                logger.warning(f"Add to cart failed: {response.message}")
                raise HTTPException(status_code=404, detail=response.message)
            else:
                logger.warning(f"Add to cart failed: {response.message}")
                raise HTTPException(status_code=400, detail=response.message)
        logger.info(f"Add to cart successful: buyer_id={buyer_id}, item_id={request.item_id}")
        return {"message": "Item added to cart"}
    except grpc.RpcError as e:
        logger.error(f"gRPC error during add to cart: {e.details()}")
        raise HTTPException(status_code=500, detail="Service unavailable")
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
        response = stub.RemoveFromCart(
            buyer_pb2.RemoveFromCartRequest(
                buyer_id=buyer_id,
                item_id=item_id,
                quantity=request.quantity
            )
        )
        if not response.success:
            logger.warning(f"Remove from cart failed: {response.message}")
            raise HTTPException(status_code=400, detail=response.message)
        logger.info(f"Remove from cart successful: buyer_id={buyer_id}, item_id={item_id}")
        return {"message": "Item removed from cart"}
    except grpc.RpcError as e:
        logger.error(f"gRPC error during remove from cart: {e.details()}")
        raise HTTPException(status_code=500, detail="Service unavailable")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during remove from cart: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.get("/api/cart")
async def get_cart_endpoint(buyer_id: int = Depends(get_current_buyer)):
    try:
        logger.info(f"Get cart request: buyer_id={buyer_id}")
        response = stub.GetCart(buyer_pb2.GetCartRequest(buyer_id=buyer_id))
        cart_items = [
            {
                "item_id": item.item_id,
                "quantity": item.quantity,
                "saved": item.saved
            }
            for item in response.items
        ]
        logger.info(f"Get cart successful: buyer_id={buyer_id}, items={len(cart_items)}")
        return {"cart": cart_items}
    except grpc.RpcError as e:
        logger.error(f"gRPC error during get cart: {e.details()}")
        raise HTTPException(status_code=500, detail="Service unavailable")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during get cart: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.delete("/api/cart")
async def clear_cart_endpoint(buyer_id: int = Depends(get_current_buyer)):
    try:
        logger.info(f"Clear cart request: buyer_id={buyer_id}")
        stub.ClearCart(buyer_pb2.ClearCartRequest(buyer_id=buyer_id))
        logger.info(f"Clear cart successful: buyer_id={buyer_id}")
        return {"message": "Cart cleared"}
    except grpc.RpcError as e:
        logger.error(f"gRPC error during clear cart: {e.details()}")
        raise HTTPException(status_code=500, detail="Service unavailable")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during clear cart: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.post("/api/cart/save")
async def save_cart_endpoint(buyer_id: int = Depends(get_current_buyer)):
    try:
        logger.info(f"Save cart request: buyer_id={buyer_id}")
        cart_response = stub.GetCart(buyer_pb2.GetCartRequest(buyer_id=buyer_id))
        if not cart_response.items:
            logger.warning(f"Save cart failed: Empty cart for buyer_id={buyer_id}")
            raise HTTPException(status_code=400, detail="Cart is empty")
        response = stub.SaveCart(buyer_pb2.SaveCartRequest(buyer_id=buyer_id))
        if not response.success:
            logger.warning(f"Save cart failed: {response.message}")
            raise HTTPException(status_code=400, detail=response.message)
        logger.info(f"Save cart successful: buyer_id={buyer_id}, {response.message}")
        return {"message": "Cart saved successfully"}
    except grpc.RpcError as e:
        logger.error(f"gRPC error during save cart: {e.details()}")
        raise HTTPException(status_code=500, detail="Service unavailable")
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
        cart_response = stub.GetCart(buyer_pb2.GetCartRequest(buyer_id=buyer_id))
        if not cart_response.items:
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
        
        # Convert cart items to protobuf format
        cart_items_pb = [
            buyer_pb2.CartItem(
                item_id=item.item_id,
                quantity=item.quantity,
                saved=item.saved
            )
            for item in cart_response.items
        ]
        
        # Make purchase via gRPC (records purchases and decreases quantities)
        purchase_response = stub.MakePurchase(
            buyer_pb2.MakePurchaseRequest(
                buyer_id=buyer_id,
                cart_items=cart_items_pb
            )
        )
        if not purchase_response.success:
            logger.warning(f"Purchase failed: {purchase_response.message}")
            raise HTTPException(status_code=500, detail=purchase_response.message)
        
        # Clear cart after successful purchase
        stub.ClearCart(buyer_pb2.ClearCartRequest(buyer_id=buyer_id))
        logger.info(f"Purchase successful: buyer_id={buyer_id}, items={purchase_response.items_purchased}")
        return {"message": "Purchase completed successfully", "items_purchased": purchase_response.items_purchased}
    except grpc.RpcError as e:
        logger.error(f"gRPC error during purchase: {e.details()}")
        raise HTTPException(status_code=500, detail="Service unavailable")
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
        response = stub.ProvideItemFeedback(
            buyer_pb2.ProvideItemFeedbackRequest(
                item_id=item_id,
                feedback=request.feedback
            )
        )
        if not response.success:
            if "not found" in response.message.lower():
                logger.warning(f"Provide feedback failed: {response.message}")
                raise HTTPException(status_code=404, detail=response.message)
            else:
                logger.warning(f"Provide feedback failed: {response.message}")
                raise HTTPException(status_code=422, detail=response.message)
        logger.info(f"Provide feedback successful: buyer_id={buyer_id}, item_id={item_id}")
        return {"message": "Feedback recorded"}
    except grpc.RpcError as e:
        logger.error(f"gRPC error during provide feedback: {e.details()}")
        raise HTTPException(status_code=500, detail="Service unavailable")
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
        response = stub.GetSellerRating(buyer_pb2.GetSellerRatingRequest(seller_id=seller_id))
        if not response.success:
            logger.warning(f"Get seller rating failed: Seller {seller_id} not found")
            raise HTTPException(status_code=404, detail=f"Seller with ID {seller_id} not found")
        rating = {
            "thumbs_up": response.thumbs_up,
            "thumbs_down": response.thumbs_down
        }
        logger.info(f"Get seller rating successful for seller_id: {seller_id}")
        return {"rating": rating}
    except grpc.RpcError as e:
        logger.error(f"gRPC error during get seller rating: {e.details()}")
        raise HTTPException(status_code=500, detail="Service unavailable")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during get seller rating: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.get("/api/buyers/purchases")
async def get_purchases_endpoint(buyer_id: int = Depends(get_current_buyer)):
    try:
        logger.info(f"Get purchases request: buyer_id={buyer_id}")
        response = stub.GetBuyerPurchases(buyer_pb2.GetBuyerPurchasesRequest(buyer_id=buyer_id))
        purchases = [
            {
                "item_id": purchase.item_id,
                "quantity": purchase.quantity,
                "timestamp": purchase.timestamp
            }
            for purchase in response.purchases
        ]
        logger.info(f"Get purchases successful: buyer_id={buyer_id}, purchases={len(purchases)}")
        return {"purchases": purchases}
    except grpc.RpcError as e:
        logger.error(f"gRPC error during get purchases: {e.details()}")
        raise HTTPException(status_code=500, detail="Service unavailable")
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
