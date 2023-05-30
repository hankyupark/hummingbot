from hummingbot.core.api_throttler.data_types import RateLimit
from hummingbot.core.data_type.common import OrderType, PositionMode
from hummingbot.core.data_type.in_flight_order import OrderState

EXCHANGE_NAME = "bitget"

DEFAULT_DOMAIN = ""

DEFAULT_TIME_IN_FORCE = "normal"

REST_URL = "https://api.bitget.com"
WSS_URL = "wss://ws.bitget.com/spot/v1/stream"

SECONDS_TO_WAIT_TO_RECEIVE_MESSAGE = 20  # According to the documentation this has to be less than 30 seconds
MAX_CLIENT_ORDER_ID_LENGTH = 40

ORDER_TYPE_MAP = {
    OrderType.LIMIT: "limit",
    OrderType.MARKET: "market",
}

SYMBOL_AND_PRODUCT_TYPE_SEPARATOR = "_"


# REST API Public Endpoints
QUERY_SERVER_TIME_ENDPOINT = "/api/spot/v1/public/time"
QUERY_COIN_LIST_ENDPOINT = "/api/spot/v1/public/currencies"
QUERY_SYMBOLS_ENDPOINT = "/api/spot/v1/public/products"
QUERY_SINGLE_SYMBOL_ENDPOINT = "/api/spot/v1/public/product"

# REST API Market Endpoints
QUERY_SINGLE_TICKER_ENDPOINT = "/api/spot/v1/market/ticker"
QUERY_DEPTH_ENDPOINT = "/api/spot/v1/market/depth"

# REST API Trade Endpoints
PLACE_ORDER_ENDPOINT = "/api/spot/v1/trade/orders"
CANCEL_ORDER_ENDPOINT = "/api/spot/v1/trade/cancel-order"
QUERY_ORDER_DETIALS_ENDPOINT = "/api/spot/v1/trade/orderInfo"

# REST API Private Endpoints
QUERY_WALLET_BALANCE_ENDPOINT = "/api/spot/v1/account/assets"
QUERY_USER_TRADE_RECORDS_ENDPOINT = "/api/spot/v1/trade/fills"

# WebSocket Public Endpoints
WS_PING_REQUEST = "ping"
WS_PONG_RESPONSE = "pong"
WS_ORDER_BOOK_EVENTS_TOPIC = "books"
WS_TRADES_TOPIC = "trade"
WS_TICKER_TOPIC = "ticker"
WS_AUTHENTICATE_USER_ENDPOINT_NAME = "login"
WS_SUBSCRIPTION_ORDERS_ENDPOINT_NAME = "orders"
WS_SUBSCRIPTION_WALLET_ENDPOINT_NAME = "account"

SYMBOL_AND_PRODUCT_TYPE_SEPARATOR
# Instrudement Type
INSTRUMENT_TYPE_SPOT_PUBLIC_CHANNEL = "sp"
INSTRUMENT_TYPE_SPOT_PRIVATE_CHANNEL = "spbl"

# Side types
SIDE_BUY = "buy"
SIDE_SELL = "sell"

# Order Statuses
ORDER_STATE = {
    "new": OrderState.OPEN,
    "filled": OrderState.FILLED,
    "full-fill": OrderState.FILLED,
    "partial-fill": OrderState.PARTIALLY_FILLED,
    "partial_fill": OrderState.PARTIALLY_FILLED,
    "partially_filled": OrderState.PARTIALLY_FILLED,
    "canceled": OrderState.CANCELED,
    "cancelled": OrderState.CANCELED,
}

# Request error codes
RET_CODE_OK = "00000"
RET_CODE_PARAMS_ERROR = "40007"
RET_CODE_API_KEY_INVALID = "40006"
RET_CODE_AUTH_TIMESTAMP_ERROR = "40005"
RET_CODE_ORDER_NOT_EXISTS = "43025"
RET_CODE_API_KEY_EXPIRED = "40014"


RATE_LIMITS = [
    RateLimit(
        limit_id=QUERY_SERVER_TIME_ENDPOINT,
        limit=20,
        time_interval=1,
    ),
    RateLimit(
        limit_id=QUERY_COIN_LIST_ENDPOINT,
        limit=3,
        time_interval=1,
    ),
    RateLimit(
        limit_id=QUERY_SYMBOLS_ENDPOINT,
        limit=20,
        time_interval=1,
    ),
    RateLimit(
        limit_id=QUERY_SINGLE_SYMBOL_ENDPOINT,
        limit=20,
        time_interval=1,
    ),
    RateLimit(
        limit_id=QUERY_SINGLE_TICKER_ENDPOINT,
        limit=20,
        time_interval=1,
    ),
    RateLimit(
      limit_id=QUERY_DEPTH_ENDPOINT,
        limit=20,
        time_interval=1,
    ),
    RateLimit(
        limit_id=PLACE_ORDER_ENDPOINT,
        limit=10,
        time_interval=1,
    ),
    RateLimit(
        limit_id=CANCEL_ORDER_ENDPOINT,
        limit=10,
        time_interval=1,
    ),
    RateLimit(
        limit_id=QUERY_ORDER_DETIALS_ENDPOINT,
        limit=20,
        time_interval=1,
    ),
    RateLimit(
        limit_id=QUERY_WALLET_BALANCE_ENDPOINT,
        limit=10,
        time_interval=1,
    ),
    RateLimit(
        limit_id=QUERY_USER_TRADE_RECORDS_ENDPOINT,
        limit=20,
        time_interval=1,
    ),
]
