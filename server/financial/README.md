# Financial Transaction SOAP Service

A simple SOAP/WSDL service that simulates financial transaction processing.

## Overview

This service receives credit card information and returns transaction approval with:
- 90% probability of approval ("Yes")
- 10% probability of decline ("No")

## Running the Service

```bash
python server/financial/financial_soap.py
```

The service will start on `http://localhost:8002`

## WSDL

Access the WSDL at: `http://localhost:8002/?wsdl`

## Service Method

### process_transaction

**Parameters:**
- `card_holder_name` (string): Name on the credit card
- `card_number` (string): Credit card number
- `expiration_date` (string): Card expiration date (MM/YY format)
- `security_code` (string): CVV/Security code

**Returns:**
- `"Yes"` - Transaction approved (90% probability)
- `"No"` - Transaction declined (10% probability)

## Testing with Python

```python
from zeep import Client

client = Client('http://localhost:8002/?wsdl')
result = client.service.process_transaction(
    card_holder_name="John Doe",
    card_number="4111111111111111",
    expiration_date="12/25",
    security_code="123"
)
print(result)  # "Yes" or "No"
```

## Integration

The buyer REST API (`/api/purchases`) calls this service to validate payments before completing purchases.
