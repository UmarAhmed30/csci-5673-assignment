import sys
from pathlib import Path
import logging
from typing import Optional
import grpc
import seller_pb2
import seller_pb2_grpc

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import mysql.connector

from server.seller.config import SELLER_SERVER_CONFIG, SELLER_GRPC_CONFIG

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# gRPC channel and stub
grpc_address = f"{SELLER_GRPC_CONFIG['host']}:{SELLER_GRPC_CONFIG['port']}"
channel = grpc.insecure_channel(grpc_address)
stub = seller_pb2_grpc.SellerServiceStub(channel)

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
            raise HTTPException(status_code=400, detail="Username and password are required")

        response = stub.CreateSeller(
            seller_pb2.CreateSellerRequest(username=request.username, password=request.password)
        )
        if response.message != "OK":
            if "Duplicate entry" in response.message or "already exists" in response.message.lower():
                raise HTTPException(status_code=409, detail="Username already exists")
            raise HTTPException(status_code=400, detail=response.message)

        logger.info(f"Registration successful for username: {request.username}")
        return AuthResponse(message="Account created successfully")
    except grpc.RpcError as e:
        logger.error(f"gRPC error during registration: {e.details()}")
        raise HTTPException(status_code=500, detail="Service unavailable")
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
            raise HTTPException(status_code=401, detail="Invalid credentials")

        response = stub.LoginSeller(
            seller_pb2.LoginSellerRequest(username=request.username, password=request.password)
        )
        if not response.session_id:
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


async def get_current_seller(authorization: Optional[str] = Header(None)) -> int:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authentication required")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authentication token format")
    token = parts[1]
    try:
        response = stub.ValidateSession(
            seller_pb2.ValidateSessionRequest(session_id=token)
        )
        if not response.user_id:
            raise HTTPException(status_code=401, detail="Invalid or expired session")

        stub.TouchSession(seller_pb2.TouchSessionRequest(session_id=token))
        return response.user_id
    except grpc.RpcError as e:
        logger.error(f"gRPC error during session validation: {e.details()}")
        raise HTTPException(status_code=401, detail="Session validation failed")
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
            raise HTTPException(status_code=401, detail="Authentication required")

        stub.LogoutSeller(seller_pb2.LogoutSellerRequest(session_id=token))
        logger.info(f"Logout successful for seller_id: {seller_id}")
        return AuthResponse(message="Logout successful")
    except grpc.RpcError as e:
        logger.error(f"gRPC error during logout: {e.details()}")
        raise HTTPException(status_code=500, detail="Service unavailable")
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
        response = stub.RegisterItem(
            seller_pb2.RegisterItemRequest(
                seller_id=seller_id,
                item_name=request.name,
                item_category=request.category,
                condition_type=request.condition,
                sale_price=request.price,
                quantity=request.quantity,
                keywords=request.keywords
            )
        )
        if not response.success:
            raise HTTPException(status_code=422, detail=response.message)

        logger.info(f"Item registered successfully, item_id: {response.item_id}")
        return {"message": "Item registered successfully", "item_id": response.item_id}
    except grpc.RpcError as e:
        logger.error(f"gRPC error during item registration: {e.details()}")
        raise HTTPException(status_code=500, detail="Service unavailable")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during item registration: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.get("/api/sellers/items")
async def get_seller_items(seller_id: int = Depends(get_current_seller)):
    try:
        logger.info(f"Fetching items for seller_id: {seller_id}")
        response = stub.DisplayItems(
            seller_pb2.DisplayItemsRequest(seller_id=seller_id)
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
        logger.info(f"Retrieved {len(items)} items for seller_id: {seller_id}")
        return {"items": items}
    except grpc.RpcError as e:
        logger.error(f"gRPC error fetching items: {e.details()}")
        raise HTTPException(status_code=500, detail="Service unavailable")
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
        response = stub.UpdateUnitsForSale(
            seller_pb2.UpdateUnitsForSaleRequest(
                seller_id=seller_id,
                item_id=item_id,
                quantity=request.quantity
            )
        )
        if not response.success:
            raise HTTPException(status_code=400, detail=response.message)

        logger.info(f"Quantity updated successfully for item_id: {item_id}")
        return {"message": response.message}
    except grpc.RpcError as e:
        logger.error(f"gRPC error updating quantity: {e.details()}")
        raise HTTPException(status_code=500, detail="Service unavailable")
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
            raise HTTPException(status_code=422, detail="Price must be a positive number")

        response = stub.ChangeItemPrice(
            seller_pb2.ChangeItemPriceRequest(
                seller_id=seller_id,
                item_id=item_id,
                price=request.price
            )
        )
        if not response.success:
            raise HTTPException(status_code=400, detail=response.message)

        logger.info(f"Price updated successfully for item_id: {item_id}")
        return {"message": "Price updated successfully"}
    except grpc.RpcError as e:
        logger.error(f"gRPC error updating price: {e.details()}")
        raise HTTPException(status_code=500, detail="Service unavailable")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating price: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.get("/api/sellers/rating")
async def get_own_rating(seller_id: int = Depends(get_current_seller)):
    try:
        logger.info(f"Rating retrieval for seller_id: {seller_id}")
        response = stub.GetSellerRating(
            seller_pb2.GetSellerRatingRequest(seller_id=seller_id)
        )
        logger.info(f"Rating retrieved for seller_id: {seller_id}")
        return {"rating": {"thumbs_up": response.thumbs_up, "thumbs_down": response.thumbs_down}}
    except grpc.RpcError as e:
        logger.error(f"gRPC error retrieving rating: {e.details()}")
        raise HTTPException(status_code=500, detail="Service unavailable")
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