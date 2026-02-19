import random
from spyne import Application, rpc, ServiceBase, Unicode
from spyne.protocol.soap import Soap11
from spyne.server.wsgi import WsgiApplication
from wsgiref.simple_server import make_server
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
        if not card_holder_name or not card_number or not expiration_date or not security_code:
            logger.warning("Transaction declined: Missing required fields")
            return "No"
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
