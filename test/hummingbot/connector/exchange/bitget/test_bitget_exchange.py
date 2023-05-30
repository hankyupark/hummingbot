import asyncio
import json
import re
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, patch

from aioresponses import aioresponses
from aioresponses.core import RequestCall
from bidict import bidict

import hummingbot.connector.exchange.bitget.bitget_constants as CONSTANTS
import hummingbot.connector.exchange.bitget.bitget_web_utils as web_utils
from hummingbot.client.config.client_config_map import ClientConfigMap
from hummingbot.client.config.config_helpers import ClientConfigAdapter
from hummingbot.connector.exchange.bitget.bitget_exchange import BitgetExchange
from hummingbot.connector.test_support.exchange_connector_test import AbstractExchangeConnectorTests
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import combine_to_hb_trading_pair
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.funding_info import FundingInfo
from hummingbot.core.data_type.in_flight_order import InFlightOrder
from hummingbot.core.data_type.trade_fee import AddedToCostTradeFee, TokenAmount, TradeFeeBase, TradeFeeSchema


class BitgetExchangeTests(AbstractExchangeConnectorTests.ExchangeConnectorTests):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.api_key = "someKey"
        cls.api_secret = "someSecret"
        cls.passphrase = "somePassphrase"
        cls.quote_asset = "USDT"  # linear
        cls.trading_pair = combine_to_hb_trading_pair(cls.base_asset, cls.quote_asset)

    @property
    def all_symbols_url(self):
        url = web_utils.get_rest_url_for_endpoint(endpoint=CONSTANTS.QUERY_SYMBOLS_ENDPOINT)
        url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?") + ".*")
        return url

    @property
    def latest_prices_url(self):
        url = web_utils.get_rest_url_for_endpoint(
            endpoint=CONSTANTS.QUERY_SINGLE_TICKER_ENDPOINT
        )
        url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?") + ".*")
        return url

    @property
    def network_status_url(self):
        url = web_utils.get_rest_url_for_endpoint(endpoint=CONSTANTS.QUERY_SERVER_TIME_ENDPOINT)
        return url

    @property
    def trading_rules_url(self):
        url = web_utils.get_rest_url_for_endpoint(endpoint=CONSTANTS.QUERY_SYMBOLS_ENDPOINT)
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?") + ".*")
        return regex_url

    @property
    def order_creation_url(self):
        url = web_utils.get_rest_url_for_endpoint(
            endpoint=CONSTANTS.PLACE_ORDER_ENDPOINT)
        url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?") + ".*")
        return url

    @property
    def balance_url(self):
        url = web_utils.get_rest_url_for_endpoint(endpoint=CONSTANTS.QUERY_WALLET_BALANCE_ENDPOINT)
        return url

    @property
    def all_symbols_request_mock_response(self):
        mock_response = {
            "code": "00000",
            "message": "success",
            "data": [{
                "symbol": self.exchange_trading_pair,
                "symbolName": self.trading_pair,
                "baseCoin": self.base_asset,
                "quoteCoin": self.quote_asset,
                "minTradeAmount": "0.001",
                "maxTradeAmount": "1000000",
                "takerFeeRate": "0.001",
                "makerFeeRate": "0.001",
                "priceScale": "4",
                "quantityScale": "8",
                "minTradeUSDT": "5",
                "status": "online",
                "buyLimitPriceRatio": "0.05",
                "sellLimitPriceRatio": "0.05",
            }],
        }
        return mock_response

    @property
    def latest_prices_request_mock_response(self):
        mock_response = {
            "code": "00000",
            "message": "success",
            "data": {
                "symbol": self.exchange_trading_pair,
                "high24h": "24131.5",
                "low24h": "23660.5",
                "close": "23990.5",
                "quoteVol": "3735854069.908",
                "baseVol": "156243.358",
                "usdtVol": "3735854069.908",
                "ts": "1660705778888",
                "buyOne": "23989.5",
                "sellOne": "23991",
                "bidSz": "0.0663",
                "sellSz": "0.0119",
                "openUtc0": "23841.5",
                "changeUtc0": "0.00625",
                "change": "0.00442",
            }
        }
        return mock_response

    @property
    def all_symbols_including_invalid_pair_mock_response(self) -> Tuple[str, Any]:
        mock_response = self.all_symbols_request_mock_response
        return None, mock_response

    @property
    def network_status_request_successful_mock_response(self):
        mock_response = {"flag": True, "requestTime": 1662584739780}
        return mock_response

    @property
    def trading_rules_request_mock_response(self):
        return self.all_symbols_request_mock_response

    @property
    def trading_rules_request_erroneous_mock_response(self):
        mock_response = {
            "code": "00000",
            "data": [{
                "baseCoin": self.base_asset,
                "quoteCoin": self.quote_asset,
                "symbol": self.exchange_trading_pair,
            }],
            "message": "success",
            "requestTime": 1627114525850
        }
        return mock_response

    @property
    def order_creation_request_successful_mock_response(self):
        mock_response = {
            "code": "00000",
            "data": {
                "orderId": "1627293504612",
                "clientOrderId": "BITGET#1627293504612"
            },
            "message": "success",
            "requestTime": 1627293504612
        }
        return mock_response

    @property
    def balance_request_mock_response_for_base_and_quote(self):
        mock_response = {
            "code": "00000",
            "message": "success",
            "data": [
                {
                    "coinId": "10012",
                    "coinName": self.quote_asset,
                    "available": "2000",
                    "frozen": "0",
                    "lock": "0",
                    "uTime": "1627293504612"
                },
                {
                    "coinId": "10013",
                    "coinName": self.base_asset,
                    "available": "10",
                    "frozen": "5",
                    "lock": "5",
                    "uTime": "1627293504612"
                },
            ],
            "requestTime": 1630901215622
        }
        return mock_response

    @property
    def balance_request_mock_response_only_base(self):
        return {
            "code": "00000",
            "message": "success",
            "data": [
                {
                    "coinId": "10013",
                    "coinName": self.base_asset,
                    "available": "10",
                    "frozen": "5",
                    "lock": "5",
                    "uTime": "1627293504612"
                },
            ],
            "requestTime": 1630901215622
        }

    @property
    def balance_event_websocket_update(self):
        mock_response = {
            "arg": {
                "instType": CONSTANTS.INSTRUMENT_TYPE_SPOT_PRIVATE_CHANNEL,
                "channel": CONSTANTS.WS_SUBSCRIPTION_WALLET_ENDPOINT_NAME,
                "instId": "default"
            },
            "data": [
                {
                    "coinId": "10012",
                    "coinName": self.quote_asset,
                    "available": "2000",
                },
                {
                    "coinId": "10013",
                    "coinName": self.base_asset,
                    "available": "10",
                }
            ]
        }
        return mock_response

    @property
    def expected_latest_price(self):
        return 23990.5

    @property
    def expected_supported_order_types(self):
        return [OrderType.LIMIT, OrderType.MARKET]

    @property
    def expected_trading_rule(self):
        trading_rules_resp = self.trading_rules_request_mock_response["data"][0]
        return TradingRule(
            trading_pair=self.trading_pair,
            min_order_size=Decimal(str(trading_rules_resp["minTradeAmount"])),
            min_price_increment=(1 * Decimal(f"1e-{trading_rules_resp['priceScale']}")),
            min_base_amount_increment=(1 * Decimal(f"1e-{trading_rules_resp['quantityScale']}")),
            min_notional_size=Decimal(str(trading_rules_resp["minTradeUSDT"])),
        )

    @property
    def expected_logged_error_for_erroneous_trading_rule(self):
        erroneous_rule = self.trading_rules_request_erroneous_mock_response["data"][0]
        return f"Error parsing the trading pair rule: {erroneous_rule}. Skipping."

    @property
    def expected_exchange_order_id(self):
        return "1627293504612"

    @property
    def is_order_fill_http_update_included_in_status_update(self) -> bool:
        return True

    @property
    def is_order_fill_http_update_executed_during_websocket_order_event_processing(self) -> bool:
        return False

    @property
    def expected_partial_fill_price(self) -> Decimal:
        return Decimal("100")

    @property
    def expected_partial_fill_amount(self) -> Decimal:
        return Decimal("10")

    @property
    def expected_fill_fee(self) -> TradeFeeBase:
        return AddedToCostTradeFee(
            percent_token=self.quote_asset,
            flat_fees=[TokenAmount(token=self.quote_asset, amount=Decimal("0.001"))],
        )

    @property
    def expected_fill_trade_id(self) -> str:
        return "xxxxxxxx-xxxx-xxxx-8b66-c3d2fcd352f6"

    def exchange_symbol_for_tokens(self, base_token: str, quote_token: str) -> str:
        return f"{base_token}{quote_token}_SPBL"

    def create_exchange_instance(self):
        client_config_map = ClientConfigAdapter(ClientConfigMap())
        exchange = BitgetExchange(
            client_config_map=client_config_map,
            bitget_api_key=self.api_key,
            bitget_secret_key=self.api_secret,
            bitget_passphrase=self.passphrase,
            trading_pairs=[self.trading_pair],
        )
        return exchange

    def validate_auth_credentials_present(self, request_call: RequestCall):
        request_data = request_call.kwargs["headers"]

        self.assertIn("ACCESS-TIMESTAMP", request_data)
        self.assertIn("ACCESS-KEY", request_data)
        self.assertEqual(self.api_key, request_data["ACCESS-KEY"])
        self.assertIn("ACCESS-SIGN", request_data)

    def validate_order_creation_request(self, order: InFlightOrder, request_call: RequestCall):
        request_data = json.loads(request_call.kwargs["data"])
        side = "buy" if order.trade_type == TradeType.BUY else "sell"

        self.assertEqual(self.exchange_trading_pair, request_data["symbol"])
        self.assertEqual(side, request_data["side"])
        self.assertEqual(order.order_type.name.lower(), request_data["orderType"])
        self.assertEqual(CONSTANTS.DEFAULT_TIME_IN_FORCE, request_data["force"])
        if order.order_type == OrderType.LIMIT:
            self.assertEqual(order.price, Decimal(request_data["price"]))
        self.assertEqual(order.amount, Decimal(request_data["quantity"]))
        self.assertEqual(order.client_order_id, request_data["clientOrderId"])

    def validate_order_cancelation_request(self, order: InFlightOrder, request_call: RequestCall):
        request_data = json.loads(request_call.kwargs["data"])
        self.assertEqual(self.exchange_trading_pair, request_data["symbol"])
        self.assertEqual(order.exchange_order_id, request_data["orderId"])

    def validate_order_status_request(self, order: InFlightOrder, request_call: RequestCall):
        request_params = request_call.kwargs["params"]
        self.assertEqual(self.exchange_trading_pair, request_params["symbol"])
        self.assertEqual(order.exchange_order_id, request_params["orderId"])

    def validate_trades_request(self, order: InFlightOrder, request_call: RequestCall):
        request_params = request_call.kwargs["params"]
        self.assertEqual(self.exchange_trading_pair, request_params["symbol"])
        self.assertEqual(order.exchange_order_id, request_params["orderId"])

    def configure_successful_cancelation_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None,
    ) -> str:
        """
        :return: the URL configured for the cancelation
        """
        url = web_utils.get_rest_url_for_endpoint(
            endpoint=CONSTANTS.CANCEL_ORDER_ENDPOINT
        )
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?") + ".*")
        response = self._order_cancelation_request_successful_mock_response(order=order)
        mock_api.post(regex_url, body=json.dumps(response), callback=callback)
        return url

    def configure_erroneous_cancelation_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None,
    ) -> str:
        url = web_utils.get_rest_url_for_endpoint(
            endpoint=CONSTANTS.CANCEL_ORDER_ENDPOINT
        )
        regex_url = re.compile(f"^{url}".replace(".", r"\.").replace("?", r"\?") + ".*")
        response = {
            "code": "43001",
            "message": "The order does not exist",
        }
        mock_api.post(regex_url, body=json.dumps(response), callback=callback)
        return url

    def configure_order_not_found_error_cancelation_response(
            self, order: InFlightOrder, mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None
    ) -> str:
        # Implement the expected not found response when enabling test_cancel_order_not_found_in_the_exchange
        raise NotImplementedError
    
    def configure_one_successful_one_erroneous_cancel_all_response(
            self,
            successful_order: InFlightOrder,
            erroneous_order: InFlightOrder,
            mock_api: aioresponses,
    ) -> List[str]:
        """
        :return: a list of all configured URLs for the cancelations
        """
        all_urls = []
        url = self.configure_successful_cancelation_response(order=successful_order, mock_api=mock_api)
        all_urls.append(url)
        url = self.configure_erroneous_cancelation_response(order=erroneous_order, mock_api=mock_api)
        all_urls.append(url)
        return all_urls

    def configure_completely_filled_order_status_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None
    ) -> str:
        url = web_utils.get_rest_url_for_endpoint(
            endpoint=CONSTANTS.QUERY_ORDER_DETIALS_ENDPOINT
        )
        regex_url = re.compile(url + r"\?.*")
        response = self._order_status_request_completely_filled_mock_response(order=order)
        mock_api.get(regex_url, body=json.dumps(response), callback=callback)
        return url

    def configure_canceled_order_status_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None,
    ) -> str:
        url = web_utils.get_rest_url_for_endpoint(
            endpoint=CONSTANTS.QUERY_ORDER_DETIALS_ENDPOINT
        )
        regex_url = re.compile(url + r"\?.*")
        response = self._order_status_request_canceled_mock_response(order=order)
        mock_api.get(regex_url, body=json.dumps(response), callback=callback)
        return url

    def configure_open_order_status_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None,
    ) -> str:
        url = web_utils.get_rest_url_for_endpoint(
            endpoint=CONSTANTS.QUERY_ORDER_DETIALS_ENDPOINT
        )
        regex_url = re.compile(url + r"\?.*")
        response = self._order_status_request_open_mock_response(order=order)
        mock_api.get(regex_url, body=json.dumps(response), callback=callback)
        return url

    def configure_http_error_order_status_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None,
    ) -> str:
        url = web_utils.get_rest_url_for_endpoint(
            endpoint=CONSTANTS.QUERY_ORDER_DETIALS_ENDPOINT
        )
        regex_url = re.compile(url + r"\?.*")
        mock_api.get(regex_url, status=404, callback=callback)
        return url

    def configure_partially_filled_order_status_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None,
    ) -> str:
        url = web_utils.get_rest_url_for_endpoint(
            endpoint=CONSTANTS.QUERY_ORDER_DETIALS_ENDPOINT
        )
        regex_url = re.compile(url + r"\?.*")
        response = self._order_status_request_partially_filled_mock_response(order=order)
        mock_api.get(regex_url, body=json.dumps(response), callback=callback)
        return url

    def configure_order_not_found_error_order_status_response(
            self, order: InFlightOrder, mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None
    ) -> List[str]:
        # Implement the expected not found response when enabling
        # test_lost_order_removed_if_not_found_during_order_status_update
        raise NotImplementedError

    def configure_partial_fill_trade_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None,
    ) -> str:
        url = web_utils.get_rest_url_for_endpoint(
            endpoint=CONSTANTS.QUERY_USER_TRADE_RECORDS_ENDPOINT
        )
        regex_url = re.compile(url + r"\?.*")
        response = self._order_fills_request_partial_fill_mock_response(order=order)
        mock_api.get(regex_url, body=json.dumps(response), callback=callback)
        return url

    def configure_erroneous_http_fill_trade_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None,
    ) -> str:
        url = web_utils.get_rest_url_for_endpoint(
            endpoint=CONSTANTS.QUERY_ORDER_DETIALS_ENDPOINT
        )
        regex_url = re.compile(url + r"\?.*")
        mock_api.get(regex_url, status=400, callback=callback)
        return url

    def configure_full_fill_trade_response(
            self,
            order: InFlightOrder,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None,
    ) -> str:
        url = web_utils.get_rest_url_for_endpoint(
            endpoint=CONSTANTS.QUERY_USER_TRADE_RECORDS_ENDPOINT
        )
        regex_url = re.compile(url + r"\?.*")
        response = self._order_fills_request_full_fill_mock_response(order=order)
        mock_api.get(regex_url, body=json.dumps(response), callback=callback)
        return url

    def order_event_for_new_order_websocket_update(self, order: InFlightOrder):
        return {
            "action": "snapshot",
            "arg": {
                "instType": "spbl",
                "channel": CONSTANTS.WS_SUBSCRIPTION_ORDERS_ENDPOINT_NAME,
                "instId": "default"
            },
            "data": [
                {
                    "instId": "default",
                    "ordId": order.exchange_order_id or "1640b725-75e9-407d-bea9-aae4fc666d33",
                    "clOrdId": order.client_order_id or "",
                    "px": str(order.price),
                    "sz": str(order.amount),
                    "notional": "100",
                    "ordType": order.order_type.name.capitalize(),
                    "force": "normal",
                    "side": order.trade_type.name.capitalize(),
                    "fillPx": "0",
                    "tradeId": "0",
                    "fillSz": "0",
                    "fillTime": "1627293049406",
                    "fillFee": "0",
                    "fillFeeCcy": "USDT",
                    "execType": "maker",
                    "accFillSz": "0",
                    "avgPx": "0",
                    "status": "new",
                    "eps": "WEB",
                    "cTime": "1627293049406",
                    "uTime": "1627293049406",
                    "orderFee": [
                        {"feeCcy": "USDT",
                        "fee": "0.001"},
                    ],
                }
            ],
        }

    def order_event_for_canceled_order_websocket_update(self, order: InFlightOrder):
        return {
            "arg": {
                "instType": "spbl",
                "channel": CONSTANTS.WS_SUBSCRIPTION_ORDERS_ENDPOINT_NAME,
                "instId": "default"
            },
            "data": [{
                "instId": "default",
                "ordId": order.exchange_order_id or "1640b725-75e9-407d-bea9-aae4fc666d33",
                "clOrdId": order.client_order_id or "",
                "px": str(order.price),
                "sz": str(order.amount),
                "notional": "100",
                "ordType": order.order_type.name.capitalize(),
                "force": "normal",
                "side": order.trade_type.name.capitalize(),
                "fillPx": str(order.price),
                "tradeId": "0",
                "fillSz": "10",
                "fillTime": "1627293049406",
                "fillFee": "0",
                "fillFeeCcy": self.quote_asset,
                "execType": "maker",
                "accFillSz": "10",
                "avgPx": str(order.price),
                "status": "cancelled",
                "eps": "WEB",
                "cTime": "1627293049416",
                "uTime": "1627293049416",
                "orderFee": [
                    {"feeCcy": "USDT",
                     "fee": "0.001"},
                ],
            }],
        }

    def order_event_for_full_fill_websocket_update(self, order: InFlightOrder):
        return {
            "arg": {
                "instType": "spbl",
                "channel": CONSTANTS.WS_SUBSCRIPTION_ORDERS_ENDPOINT_NAME,
                "instId": "default"
            },
            "data": [{
                "instId": "default",
                "ordId": order.exchange_order_id or "1640b725-75e9-407d-bea9-aae4fc666d33",
                "clOrdId": order.client_order_id or "",
                "px": str(order.price),
                "sz": str(order.amount),
                "notional": "100",
                "ordType": order.order_type.name.capitalize(),
                "force": "normal",
                "side": order.trade_type.name.capitalize(),
                "fillPx": str(order.price),
                "tradeId": "0",
                "fillSz": str(order.amount),
                "fillTime": "1627293049406",
                "fillFee": str(self.expected_fill_fee.flat_fees[0].amount),
                "fillFeeCcy": self.quote_asset,
                "execType": "maker",
                "accFillSz": str(order.amount),
                "avgPx": str(order.price),
                "status": "full-fill",
                "cTime": "1627293049406",
                "uTime": "1627293049406",
                "orderFee": [
                    {"feeCcy": self.quote_asset,
                     "fee": str(self.expected_fill_fee.flat_fees[0].amount)},
                ],
            }],
        }
    
    def trade_event_for_full_fill_websocket_update(self, order: InFlightOrder):
        return self.order_event_for_full_fill_websocket_update(order)

    def configure_all_symbols_response(
            self,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None,
    ) -> List[str]:

        all_urls = []

        url = web_utils.get_rest_url_for_endpoint(endpoint=CONSTANTS.QUERY_SYMBOLS_ENDPOINT)
        response = self.all_symbols_request_mock_response
        mock_api.get(url, body=json.dumps(response))
        all_urls.append(url)

        return all_urls

    def configure_trading_rules_response(
            self,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None,
    ) -> List[str]:
        return self.configure_all_symbols_response(mock_api=mock_api, callback=callback)

    def configure_erroneous_trading_rules_response(
            self,
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None,
    ) -> List[str]:

        all_urls = []

        url = web_utils.get_rest_url_for_endpoint(endpoint=CONSTANTS.QUERY_SYMBOLS_ENDPOINT)
        response = self.trading_rules_request_erroneous_mock_response
        mock_api.get(url, body=json.dumps(response))
        all_urls.append(url)

        return all_urls

    def test_time_synchronizer_related_reqeust_error_detection(self):
        error_code_str = self.exchange._format_ret_code_for_print(ret_code=CONSTANTS.RET_CODE_AUTH_TIMESTAMP_ERROR)
        exception = IOError(f"{error_code_str} - Request timestamp expired.")
        self.assertTrue(self.exchange._is_request_exception_related_to_time_synchronizer(exception))

        error_code_str = self.exchange._format_ret_code_for_print(ret_code=CONSTANTS.RET_CODE_ORDER_NOT_EXISTS)
        exception = IOError(f"{error_code_str} - Failed to cancel order because it was not found.")
        self.assertFalse(self.exchange._is_request_exception_related_to_time_synchronizer(exception))

    def test_exchange_symbol_associated_to_pair_without_product_type(self):
        self.exchange._set_trading_pair_symbol_map(
            bidict({
                self.exchange_symbol_for_tokens(self.base_asset, self.quote_asset): self.trading_pair,
                "BTCUSD_SPBL": "BTC-USD",
                "ETHPERP_SPBL": "ETH-USDC",
            }))

        trading_pair = self.async_run_with_timeout(
            self.exchange.trading_pair_associated_to_exchange_instrument_id(
                instrument_id=f"{self.base_asset}{self.quote_asset}"))
        self.assertEqual(self.trading_pair, trading_pair)

        trading_pair = self.async_run_with_timeout(
            self.exchange.trading_pair_associated_to_exchange_instrument_id(
                instrument_id="BTCUSD"))
        self.assertEqual("BTC-USD", trading_pair)

        trading_pair = self.async_run_with_timeout(
            self.exchange.trading_pair_associated_to_exchange_instrument_id(
                instrument_id="ETHPERP"))
        self.assertEqual("ETH-USDC", trading_pair)

        with self.assertRaises(ValueError) as context:
            self.async_run_with_timeout(
                self.exchange.trading_pair_associated_to_exchange_instrument_id(
                    instrument_id="XMRPERP"))
        self.assertEqual("No trading pair associated to instrument ID XMRPERP", str(context.exception))

    @aioresponses()
    def test_cancel_order_not_found_in_the_exchange(self, mock_api):
        # Disabling this test because the connector has not been updated yet to validate
        # order not found during cancellation (check _is_order_not_found_during_cancelation_error)
        pass

    @aioresponses()
    def test_lost_order_removed_if_not_found_during_order_status_update(self, mock_api):
        # Disabling this test because the connector has not been updated yet to validate
        # order not found during status update (check _is_order_not_found_during_status_update_error)
        pass

    def _expected_valid_trading_pairs(self):
        return [self.trading_pair]

    def _order_cancelation_request_successful_mock_response(self, order: InFlightOrder) -> Any:
        return {
            "code": "00000",
            "message": "success",
            "data": "202934892814667",
        }

    def _order_status_request_completely_filled_mock_response(self, order: InFlightOrder) -> Any:
        feeDetail = {}
        feeDetail[order.base_asset] = {
            "deduction": True,
            "feeCoinCode": order.base_asset,
            "totalDeductionFee": "-0.017118519726",
            "totalFee": "-0.017118519726"
        }
        return {
            "code": "00000",
            "message": "success",
            "data": {
                "accountId": "222222222",
                "symbol": self.exchange_trading_pair,
                "orderId": str(order.exchange_order_id),
                "clientOrderId": str(order.client_order_id),
                "price": str(order.price),
                "quantity": str(order.amount),
                "orderType": "limit",
                "side": "buy",
                "state": "full-fill",
                "fillPrice": str(order.price),
                "fillQuantity": str(order.amount),
                "fillTotalAmount": str(float(order.amount)*float(order.price)),
                "enterPointSournce": "WEB",
                "cTime": "1627028708807",
                "feeDetail": json.dumps(feeDetail),
                "orderSource": "normal",
            },
            "requestTime": 1627300098776
        }

    def _order_status_request_canceled_mock_response(self, order: InFlightOrder) -> Any:
        resp = self._order_status_request_completely_filled_mock_response(order)
        resp["data"]["state"] = "canceled"
        resp["data"]["fillQuantity"] = "0"
        resp["data"]["fillPrice"] = "0"
        return resp

    def _order_status_request_open_mock_response(self, order: InFlightOrder) -> Any:
        resp = self._order_status_request_completely_filled_mock_response(order)
        resp["data"]["state"] = "new"
        resp["data"]["fillQuantity"] = "0"
        resp["data"]["fillPrice"] = "0"
        return resp

    def _order_status_request_partially_filled_mock_response(self, order: InFlightOrder) -> Any:
        resp = self._order_status_request_completely_filled_mock_response(order)
        resp["data"]["state"] = "partial_fill"
        resp["data"]["fillQuantity"] = str(self.expected_partial_fill_amount)
        resp["data"]["fillPrice"] = str(self.expected_partial_fill_price)
        return resp

    def _order_fills_request_partial_fill_mock_response(self, order: InFlightOrder):
        return {
            "code": "00000",
            "message": "success",
            "data": [
                {
                    "accountId": "222222222",
                    "symbol": self.exchange_trading_pair,
                    "orderId": str(order.exchange_order_id),
                    "fillId": self.expected_fill_trade_id,
                    "orderType": "limit",
                    "side": "buy",
                    "fillPrice": str(self.expected_partial_fill_price),
                    "fillQuantity": str(self.expected_partial_fill_amount),
                    "fillTotalAmount": str(float(self.expected_partial_fill_price)*float(self.expected_partial_fill_amount)),
                    "cTime": "1627027632241",
                    "feeCcy": order.base_asset,
                    "fees": str(self.expected_fill_fee.flat_fees[0].amount),
                }
            ],
        }

    def _order_fills_request_full_fill_mock_response(self, order: InFlightOrder):
        return {
            "code": "00000",
            "message": "success",
            "data": [
                {
                    "accountId": "222222222",
                    "symbol": self.exchange_trading_pair,
                    "orderId": str(order.exchange_order_id),
                    "fillId": self.expected_fill_trade_id,
                    "orderType": "limit",
                    "side": "buy",
                    "fillPrice": str(order.price),
                    "fillQuantity": str(order.amount),
                    "fillTotalAmount": str(float(order.amount)*float(order.price)),
                    "cTime": "1627027632241",
                    "feeCcy": order.base_asset,
                    "fees": str(self.expected_fill_fee.flat_fees[0].amount),
                }
            ],
        }

    def _configure_balance_response(
            self,
            response: Dict[str, Any],
            mock_api: aioresponses,
            callback: Optional[Callable] = lambda *args, **kwargs: None,
    ) -> str:

        return_url = super()._configure_balance_response(response=response, mock_api=mock_api, callback=callback)
        return return_url

    def _simulate_trading_rules_initialized(self):
        self.exchange._trading_rules = {
            self.trading_pair: TradingRule(
                trading_pair=self.trading_pair,
                min_order_size=Decimal(str(0.01)),
                min_price_increment=Decimal(str(0.0001)),
                min_base_amount_increment=Decimal(str(0.000001)),
            ),
        }
