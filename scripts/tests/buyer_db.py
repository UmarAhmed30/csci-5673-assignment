import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

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
    provide_item_feedback,
    get_buyer_purchases,
    get_seller_rating
)

buyer_id = create_buyer("Admin", "admin")
session_id = login_buyer("Admin", "admin")
validate_session(session_id)
touch_session(session_id)
logout_session(session_id)

session_id = "3518dbbd-7d2d-49f2-9b11-dc380362361e"

category = 1
keywords = ["ios", "laptop"]
search_items(category, keywords)

item_id = 1
get_item(item_id)

buyer_id = 1
qty = 2
add_to_cart(buyer_id, item_id, qty)
qty = 1
remove_from_cart(buyer_id, item_id, qty)

get_cart(buyer_id)

clear_cart(buyer_id)

feedback = "up"
provide_item_feedback(item_id, feedback)

seller_id = 1
get_seller_rating(seller_id)

get_buyer_purchases(buyer_id)
