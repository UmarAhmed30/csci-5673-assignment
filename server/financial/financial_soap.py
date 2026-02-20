import random
from spyne import Application, rpc, ServiceBase, Unicode
from spyne.protocol.soap import Soap11
from spyne.server.wsgi import WsgiApplication
from wsgiref.simple_server import make_server
import logging
from datetime import datetime
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def validate_card_number(card_number: str) -> tuple[bool, str]:
    card_number = card_number.replace(" ", "").replace("-", "")
    if not card_number.isdigit():
        return False, "Card number must contain only digits"
    if len(card_number) < 13 or len(card_number) > 19:
        return False, "Card number must be between 13 and 19 digits"
    return True, ""


def validate_expiration_date(expiration_date: str) -> tuple[bool, str]:
    if len(expiration_date) != 5 or expiration_date[2] != '/':
        return False, "Expiration date must be in MM/YY format"
    try:
        month_str, year_str = expiration_date.split('/')
        month = int(month_str)
        year = int(year_str)
        if month < 1 or month > 12:
            return False, "Invalid expiration month"
        full_year = 2000 + year
        current_date = datetime.now()
        expiration_datetime = datetime(full_year, month, 1)
        if expiration_datetime < current_date.replace(day=1):
            return False, "Card has expired"
        return True, ""
    except ValueError:
        return False, "Invalid expiration date format"


def validate_security_code(security_code: str) -> tuple[bool, str]:
    security_code = security_code.strip()
    if not security_code.isdigit():
        return False, "Security code must contain only digits"
    if len(security_code) < 3 or len(security_code) > 4:
        return False, "Security code must be 3 or 4 digits"
    return True, ""


def validate_card_holder_name(name: str) -> tuple[bool, str]:
    if not name or not name.strip():
        return False, "Card holder name is required"
    if len(name.strip()) < 2:
        return False, "Card holder name must be at least 2 characters"
    if len(name) > 50:
        return False, "Card holder name is too long"
    if not re.match(r"^[a-zA-Z\s\-'\.]+$", name):
        return False, "Card holder name contains invalid characters"
    return True, ""

class FinancialTransactionService(ServiceBase):
    @rpc(Unicode, Unicode, Unicode, Unicode, _returns=Unicode)
    def process_transaction(ctx, card_holder_name, card_number, expiration_date, security_code):
        """
        Process a financial transaction
        
        Args:
            card_holder_name: Name on the card
            card_number: Credit card number
            expiration_date: Card expiration date (MM/YY format)
            security_code: CVV/Security code
            
        Returns:
            "Yes" for approved (90% probability)
            "No" for declined (10% probability)
        """
        logger.info(f"Processing transaction for {card_holder_name}")

        # Validate all fields are present
        if not card_holder_name or not card_number or not expiration_date or not security_code:
            logger.warning("Transaction declined: Missing required fields")
            return "No"

        # Validate card holder name
        is_valid, error_msg = validate_card_holder_name(card_holder_name)
        if not is_valid:
            logger.warning(f"Transaction declined: Invalid card holder name - {error_msg}")
            return "No"

        # Validate card number
        is_valid, error_msg = validate_card_number(card_number)
        if not is_valid:
            logger.warning(f"Transaction declined: Invalid card number - {error_msg}")
            return "No"

        # Validate expiration date
        is_valid, error_msg = validate_expiration_date(expiration_date)
        if not is_valid:
            logger.warning(f"Transaction declined: Invalid expiration date - {error_msg}")
            return "No"

        # Validate security code
        is_valid, error_msg = validate_security_code(security_code)
        if not is_valid:
            logger.warning(f"Transaction declined: Invalid security code - {error_msg}")
            return "No"

        # If all validations pass, process transaction (90% approval rate)
        result = "Yes" if random.random() < 0.9 else "No"
        logger.info(f"Transaction result: {result}")
        return result

application = Application(
    [FinancialTransactionService],
    tns='financial.transaction.service',
    in_protocol=Soap11(validator='lxml'),
    out_protocol=Soap11()
)

wsgi_app = WsgiApplication(application)

if __name__ == '__main__':
    host = '0.0.0.0'
    port = 8002
    logger.info(f"Starting Financial Transaction SOAP Service on {host}:{port}")
    logger.info(f"WSDL available at: http://{host}:{port}/?wsdl")
    server = make_server(host, port, wsgi_app)
    server.serve_forever()
