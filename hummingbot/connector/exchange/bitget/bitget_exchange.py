import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from bidict import bidict

import hummingbot.connector.exchange.bitget.bitget_constants as CONSTANTS
import hummingbot.connector.exchange.bitget.bitget_utils as bitget_utils
import hummingbot.connector.exchange.bitget.bitget_web_utils as web_utils
from hummingbot.connector.exchange.bitget.bitget_api_order_book_data_source import BitgetAPIOrderBookDataSource
from hummingbot.connector.exchange.bitget.bitget_api_user_stream_data_source import BitgetApiUserStreamDataSource
from hummingbot.connector.exchange.bitget.bitget_auth import BitgetAuth
from hummingbot.connector.exchange_py_base import ExchangePyBase
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import combine_to_hb_trading_pair
from hummingbot.core.api_throttler.data_types import RateLimit
from hummingbot.core.clock import Clock
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.trade_fee import TokenAmount, TradeFeeBase, TradeFeeSchema
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.network_iterator import NetworkStatus
from hummingbot.core.utils.estimate_fee import build_trade_fee
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory

if TYPE_CHECKING:
    from hummingbot.client.config.config_helpers import ClientConfigAdapter

s_logger = None
s_decimal_NaN = Decimal("nan")


class BitgetExchange(ExchangePyBase):
    web_utils = web_utils

    def __init__(
        self,
        client_config_map: "ClientConfigAdapter",
        bitget_api_key: str = None,
        bitget_secret_key: str = None,
        bitget_passphrase: str = None,
        trading_pairs: Optional[List[str]] = None,
        trading_required: bool = True,
        domain: str = "",
    ):
        self.api_key = bitget_api_key
        self.secret_key = bitget_secret_key
        self.passphrase = bitget_passphrase
        self._domain = domain
        self._trading_required = trading_required
        self._trading_pairs = trading_pairs
        self._last_trade_history_timestamp = None

        super().__init__(client_config_map)

    @property
    def name(self) -> str:
        return CONSTANTS.EXCHANGE_NAME

    @property
    def authenticator(self) -> BitgetAuth:
        return BitgetAuth(
            api_key=self.api_key,
            secret_key=self.secret_key,
            passphrase=self.passphrase,
            time_provider=self._time_synchronizer)

    @property
    def rate_limits_rules(self):
        return CONSTANTS.RATE_LIMITS

    @property
    def domain(self):
        return self._domain

    @property
    def client_order_id_max_length(self):
        return CONSTANTS.MAX_CLIENT_ORDER_ID_LENGTH

    @property
    def client_order_id_prefix(self):
        return ""

    @property
    def trading_rules_request_path(self):
        return CONSTANTS.QUERY_SYMBOLS_ENDPOINT

    @property
    def trading_pairs_request_path(self):
        return CONSTANTS.QUERY_SYMBOLS_ENDPOINT

    @property
    def check_network_request_path(self):
        return CONSTANTS.QUERY_SERVER_TIME_ENDPOINT

    @property
    def trading_pairs(self):
        return self._trading_pairs

    @property
    def is_cancel_request_in_exchange_synchronous(self) -> bool:
        return False

    @property
    def is_trading_required(self) -> bool:
        return self._trading_required

    def supported_order_types(self):
        return [OrderType.LIMIT, OrderType.MARKET]

    async def check_network(self) -> NetworkStatus:
        """
        Checks connectivity with the exchange using the API

        We need to reimplement this for Bitget exchange because the endpoint that returns the server status and time
        by default responds with a 400 status that includes a valid content.
        """
        result = NetworkStatus.NOT_CONNECTED
        try:
            response = await self._api_get(path_url=self.check_network_request_path, return_err=True)
            if response.get("msg", False):
                result = NetworkStatus.CONNECTED
        except asyncio.CancelledError:
            raise
        except Exception:
            result = NetworkStatus.NOT_CONNECTED
        return result

    async def instrument_id_associated_to_pair(self, trading_pair: str) -> str:
        full_symbol = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        return self._symbol_and_product_type(full_symbol=full_symbol)[0]

    def _symbol_and_product_type(self, full_symbol: str) -> List[str]:
        return full_symbol.split(CONSTANTS.SYMBOL_AND_PRODUCT_TYPE_SEPARATOR)

    async def trading_pair_associated_to_exchange_instrument_id(self, instrument_id: str) -> str:
        symbol = f"{instrument_id}_SPBL"

        try:
            trading_pair = await self.trading_pair_associated_to_exchange_symbol(symbol=symbol)
            return trading_pair
        except KeyError:
            raise ValueError(f"No trading pair associated to instrument ID {instrument_id}")


    def _is_request_exception_related_to_time_synchronizer(self, request_exception: Exception):
        error_description = str(request_exception)
        ts_error_target_str = "Request timestamp expired"
        is_time_synchronizer_related = (
            ts_error_target_str in error_description
        )
        return is_time_synchronizer_related

    def _is_order_not_found_during_status_update_error(self, status_update_exception: Exception) -> bool:
        # TODO: implement this method correctly for the connector
        # The default implementation was added when the functionality to detect not found orders was introduced in the
        # ExchangePyBase class. Also fix the unit test test_lost_order_removed_if_not_found_during_order_status_update
        # when replacing the dummy implementation
        return False

    def _is_order_not_found_during_cancelation_error(self, cancelation_exception: Exception) -> bool:
        # TODO: implement this method correctly for the connector
        # The default implementation was added when the functionality to detect not found orders was introduced in the
        # ExchangePyBase class. Also fix the unit test test_cancel_order_not_found_in_the_exchange when replacing the
        # dummy implementation
        return False

    async def _place_cancel(self, order_id: str, tracked_order: InFlightOrder):
        data = {
            "symbol": await self.exchange_symbol_associated_to_pair(tracked_order.trading_pair),
            "orderId": tracked_order.exchange_order_id
        }
        cancel_result = await self._api_post(
            path_url=CONSTANTS.CANCEL_ORDER_ENDPOINT,
            data=data,
            is_auth_required=True,
        )
        response_code = cancel_result["code"]

        if response_code != CONSTANTS.RET_CODE_OK:
            if response_code == CONSTANTS.RET_CODE_ORDER_NOT_EXISTS:
                await self._order_tracker.process_order_not_found(order_id)
            formatted_ret_code = self._format_ret_code_for_print(response_code)
            raise IOError(f"{formatted_ret_code} - {cancel_result['msg']}")

        return True

    async def _place_order(
        self,
        order_id: str,
        trading_pair: str,
        amount: Decimal,
        trade_type: TradeType,
        order_type: OrderType,
        price: Decimal,
        **kwargs,
    ) -> Tuple[str, float]:
        side_str = CONSTANTS.SIDE_BUY if trade_type is TradeType.BUY else CONSTANTS.SIDE_SELL
        data = {
            "symbol": await self.exchange_symbol_associated_to_pair(trading_pair),
            "side": side_str,
            "orderType": "limit" if order_type.is_limit_type() else "market",
            "force": CONSTANTS.DEFAULT_TIME_IN_FORCE,
            "quantity": str(amount),
            "clientOrderId": order_id,
        }
        if order_type.is_limit_type():
            data["price"] = str(price)

        resp = await self._api_post(
            path_url=CONSTANTS.PLACE_ORDER_ENDPOINT,
            data=data,
            is_auth_required=True,
        )

        if resp["code"] != CONSTANTS.RET_CODE_OK:
            formatted_ret_code = self._format_ret_code_for_print(resp["code"])
            raise IOError(f"Error submitting order {order_id}: {formatted_ret_code} - {resp['msg']}")

        return str(resp["data"]["orderId"]), self.current_timestamp

    def _get_fee(self,
                 base_currency: str,
                 quote_currency: str,
                 order_type: OrderType,
                 order_side: TradeType,
                 amount: Decimal,
                 price: Decimal = s_decimal_NaN,
                 is_maker: Optional[bool] = None) -> TradeFeeBase:
        is_maker = is_maker or (order_type is OrderType.LIMIT_MAKER)
        trading_pair = combine_to_hb_trading_pair(base=base_currency, quote=quote_currency)
        if trading_pair in self._trading_fees:
            fee_schema: TradeFeeSchema = self._trading_fees[trading_pair]
            fee_rate = fee_schema.maker_percent_fee_decimal if is_maker else fee_schema.maker_percent_fee_decimal
            fee = TradeFeeBase.new_spot_fee(
                fee_schema=fee_schema,
                trade_type=order_side,
                percent=fee_rate,
            )
        else:
            fee = build_trade_fee(
                self.name,
                is_maker,
                base_currency=base_currency,
                quote_currency=quote_currency,
                order_type=order_type,
                order_side=order_side,
                amount=amount,
                price=price,
            )
        return fee

    async def _update_trading_fees(self):
        """
        Update fees information from the exchange
        """
        pass

    def _create_web_assistants_factory(self) -> WebAssistantsFactory:
        return web_utils.build_api_factory(
            throttler=self._throttler,
            time_synchronizer=self._time_synchronizer,
            auth=self._auth,
        )

    def _create_order_book_data_source(self) -> OrderBookTrackerDataSource:
        return BitgetAPIOrderBookDataSource(
            self.trading_pairs,
            connector=self,
            api_factory=self._web_assistants_factory,
            domain=self._domain,
        )

    def _create_user_stream_data_source(self) -> UserStreamTrackerDataSource:
        return BitgetApiUserStreamDataSource(
            auth=self._auth,
            trading_pairs=self._trading_pairs,
            connector=self,
            api_factory=self._web_assistants_factory,
            domain=self._domain,
        )

    async def _update_balances(self):
        local_asset_names = set(self._account_balances.keys())
        remote_asset_names = set()

        account_info = await self._api_get(
            path_url=CONSTANTS.QUERY_WALLET_BALANCE_ENDPOINT,
            is_auth_required=True)
        
        assets = account_info["data"]
        for asset_entry in assets:
            asset_name = asset_entry["coinName"]
            free_balance = Decimal(asset_entry["available"])
            total_balance = Decimal(asset_entry["available"]) + Decimal(asset_entry["frozen"])
            self._account_available_balances[asset_name] = free_balance
            self._account_balances[asset_name] = total_balance
            remote_asset_names.add(asset_name)

        asset_names_to_remove = local_asset_names.difference(remote_asset_names)

        for asset_name in asset_names_to_remove:
            del self._account_available_balances[asset_name]
            del self._account_balances[asset_name]

    async def _all_trade_updates_for_order(self, order: InFlightOrder) -> List[TradeUpdate]:
        trade_updates = []

        if order.exchange_order_id is not None:
            try:
                all_fills_response = await self._request_order_fills(order=order)
                fills_data = all_fills_response.get("data", [])

                for fill_data in fills_data:
                    trade_update = self._parse_trade_update(trade_msg=fill_data, tracked_order=order)
                    trade_updates.append(trade_update)
            except IOError as ex:
                if not self._is_request_exception_related_to_time_synchronizer(request_exception=ex):
                    raise

        return trade_updates

    async def _request_order_fills(self, order: InFlightOrder) -> Dict[str, Any]:
        exchange_symbol = await self.exchange_symbol_associated_to_pair(order.trading_pair)
        data = {
            "orderId": order.exchange_order_id,
            "symbol": exchange_symbol,
        }
        res = await self._api_post(
            path_url=CONSTANTS.QUERY_USER_TRADE_RECORDS_ENDPOINT,
            data=data,
            is_auth_required=True,
        )
        return res

    async def _request_order_status(self, tracked_order: InFlightOrder) -> OrderUpdate:
        try:
            order_status_data = await self._request_order_status_data(tracked_order=tracked_order)
            order_msg = order_status_data["data"][0]
            client_order_id = str(order_msg["clientOrderId"])
            order_update: OrderUpdate = OrderUpdate(
                trading_pair=tracked_order.trading_pair,
                update_timestamp=self.current_timestamp,
                new_state=CONSTANTS.ORDER_STATE[order_msg["status"]],
                client_order_id=client_order_id,
                exchange_order_id=order_msg["orderId"],
            )

            return order_update

        except IOError as ex:
            if self._is_request_exception_related_to_time_synchronizer(request_exception=ex):
                order_update = OrderUpdate(
                    client_order_id=tracked_order.client_order_id,
                    trading_pair=tracked_order.trading_pair,
                    update_timestamp=self.current_timestamp,
                    new_state=tracked_order.current_state,
                )
            else:
                raise

        return order_update

    async def _request_order_status_data(self, tracked_order: InFlightOrder) -> Dict:
        exchange_symbol = await self.exchange_symbol_associated_to_pair(tracked_order.trading_pair)
        data = {
            "symbol": exchange_symbol,
            "clientOrderid": tracked_order.client_order_id
        }
        if tracked_order.exchange_order_id is not None:
            data["orderId"] = tracked_order.exchange_order_id

        resp = await self._api_post(
            path_url=CONSTANTS.QUERY_ORDER_DETIALS_ENDPOINT,
            data=data,
            is_auth_required=True,
        )

        return resp

    async def _get_last_traded_price(self, trading_pair: str) -> float:
        exchange_symbol = await self.exchange_symbol_associated_to_pair(trading_pair)
        params = {"symbol": exchange_symbol}

        resp_json = await self._api_get(
            path_url=CONSTANTS.QUERY_SINGLE_TICKER_ENDPOINT,
            params=params,
        )

        price = float(resp_json["data"]["close"])
        return price

    async def _user_stream_event_listener(self):
        """
        Listens to message in _user_stream_tracker.user_stream queue.
        """
        async for event_message in self._iter_user_event_queue():
            try:
                endpoint = event_message["arg"]["channel"]
                payload = event_message["data"]

                if endpoint == CONSTANTS.WS_SUBSCRIPTION_ORDERS_ENDPOINT_NAME:
                    for order_msg in payload:
                        self._process_trade_event_message(order_msg)
                        self._process_order_event_message(order_msg)
                        # self._process_balance_update_from_order_event(order_msg)
                elif endpoint == CONSTANTS.WS_SUBSCRIPTION_WALLET_ENDPOINT_NAME:
                    for wallet_msg in payload:
                        self._process_wallet_event_message(wallet_msg)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().exception("Unexpected error in user stream listener loop.")

    def _process_order_event_message(self, order_msg: Dict[str, Any]):
        """
        Updates in-flight order and triggers cancellation or failure event if needed.

        :param order_msg: The order event message payload
        """
        order_status = CONSTANTS.ORDER_STATE[order_msg["status"]]
        client_order_id = str(order_msg["clOrdId"])
        updatable_order = self._order_tracker.all_updatable_orders.get(client_order_id)

        if updatable_order is not None:
            new_order_update: OrderUpdate = OrderUpdate(
                trading_pair=updatable_order.trading_pair,
                update_timestamp=self.current_timestamp,
                new_state=order_status,
                client_order_id=client_order_id,
                exchange_order_id=order_msg["ordId"],
            )
            self._order_tracker.process_order_update(new_order_update)

    # TOOD: derivative가 아닌 exchange에서 이 부분이 필요한지 확실하지 않음
    # def _process_balance_update_from_order_event(self, order_msg: Dict[str, Any]):
    #     order_status = CONSTANTS.ORDER_STATE[order_msg["status"]]
    #     trade_type = TradeType[order_msg["side"].upper()]
    #     states_to_consider = [OrderState.OPEN, OrderState.CANCELED]

    #     is_open_long = position_side == PositionSide.LONG and trade_type == TradeType.BUY
    #     is_open_short = position_side == PositionSide.SHORT and trade_type == TradeType.SELL

    #     order_amount = Decimal(order_msg["sz"])
    #     order_price = Decimal(order_msg["px"])
    #     margin_amount = (order_amount * order_price) / Decimal(order_msg["lever"])

    #     if (collateral_token in self._account_available_balances
    #             and order_status in states_to_consider
    #             and (is_open_long or is_open_short)):

    #         multiplier = Decimal(-1) if order_status == OrderState.OPEN else Decimal(1)
    #         self._account_available_balances[collateral_token] += margin_amount * multiplier

    def _process_trade_event_message(self, trade_msg: Dict[str, Any]):
        """
        Updates in-flight order and trigger order filled event for trade message received. Triggers order completed
        event if the total executed amount equals to the specified order amount.

        :param trade_msg: The trade event message payload
        """

        client_order_id = str(trade_msg["clOrdId"])
        fillable_order = self._order_tracker.all_fillable_orders.get(client_order_id)

        if fillable_order is not None and "tradeId" in trade_msg:
            trade_update = self._parse_websocket_trade_update(trade_msg=trade_msg, tracked_order=fillable_order)
            if trade_update:
                self._order_tracker.process_trade_update(trade_update)

    def _parse_websocket_trade_update(self, trade_msg: Dict, tracked_order: InFlightOrder) -> TradeUpdate:
        trade_id: str = trade_msg["tradeId"]

        if trade_id is not None:
            trade_id = str(trade_id)
            fee_asset = trade_msg["fillFeeCcy"]
            fee_amount = Decimal(trade_msg["fillFee"])
            trade_type = TradeType[trade_msg["side"].upper()]
            flat_fees = [] if fee_amount == Decimal("0") else [TokenAmount(amount=fee_amount, token=fee_asset)]

            fee = TradeFeeBase.new_spot_fee(
                fee_schema=self.trade_fee_schema(),
                trade_type=trade_type,
                percent_token=fee_asset,
                flat_fees=flat_fees,
            )

            exec_price = Decimal(trade_msg["fillPx"]) if "fillPx" in trade_msg else Decimal(trade_msg["px"])
            exec_time = int(trade_msg["fillTime"]) * 1e-3

            trade_update: TradeUpdate = TradeUpdate(
                trade_id=trade_id,
                client_order_id=tracked_order.client_order_id,
                exchange_order_id=str(trade_msg["ordId"]),
                trading_pair=tracked_order.trading_pair,
                fill_timestamp=exec_time,
                fill_price=exec_price,
                fill_base_amount=Decimal(trade_msg["fillSz"]),
                fill_quote_amount=exec_price * Decimal(trade_msg["fillSz"]),
                fee=fee,
            )

            return trade_update

    def _parse_trade_update(self, trade_msg: Dict, tracked_order: InFlightOrder) -> TradeUpdate:
        trade_id: str = str(trade_msg["fillId"])

        fee_asset = tracked_order.quote_asset
        fee_amount = Decimal(trade_msg["fees"])
        flat_fees = [] if fee_amount == Decimal("0") else [TokenAmount(amount=fee_amount, token=fee_asset)]

        fee = TradeFeeBase.new_spot_fee(
            fee_schema=self.trade_fee_schema(),
            trade_type=tracked_order.trade_type,
            percent_token=fee_asset,
            flat_fees=flat_fees,
        )

        exec_price = Decimal(trade_msg["fillPrice"])
        exec_time = int(trade_msg["cTime"]) * 1e-3

        trade_update: TradeUpdate = TradeUpdate(
            trade_id=trade_id,
            client_order_id=tracked_order.client_order_id,
            exchange_order_id=str(trade_msg["orderId"]),
            trading_pair=tracked_order.trading_pair,
            fill_timestamp=exec_time,
            fill_price=exec_price,
            fill_base_amount=Decimal(trade_msg["fillQuantity"]),
            fill_quote_amount=Decimal(trade_msg["fillTotalAmount"]),
            fee=fee,
        )

        return trade_update

    def _process_wallet_event_message(self, wallet_msg: Dict[str, Any]):
        """Updated balances
        Updates account balances.
        :param wallet_msg: The account balance update message payload
        """
        asset = wallet_msg.get("coinName", None)
        if asset is not None:
            available = Decimal(str(wallet_msg["available"]))
            self._account_available_balances[asset] = available
        # TODO: Add support for locked balances

    @staticmethod
    def _format_ret_code_for_print(ret_code: Union[str, int]) -> str:
        return f"ret_code <{ret_code}>"

    def _initialize_trading_pair_symbols_from_exchange_info(self, exchange_info: Dict[str, Any]):
        mapping = bidict()
        for symbol_data in filter(bitget_utils.is_exchange_information_valid, exchange_info["data"]):
            try:
                exchange_symbol = symbol_data["symbol"]
                base = symbol_data["baseCoin"]
                quote = symbol_data["quoteCoin"]
                trading_pair = combine_to_hb_trading_pair(base, quote)
                mapping[exchange_symbol] = trading_pair
            except Exception as exception:
                self.logger().error(f"There was an error parsing a trading pair information ({exception})")
        self._set_trading_pair_symbol_map(mapping)

    async def _format_trading_rules(self, instruments_info: Dict[str, Any]) -> List[TradingRule]:
        """
        Converts JSON API response into a local dictionary of trading rules.

        :param instrument_info_dict: The JSON API response.

        :returns: A dictionary of trading pair to its respective TradingRule.
        """


        """
        Example:
        {
            "code":"00000",
            "msg":"success",
            "data":[
                {
                    "symbol":"BTCUSDT_SPBL",
                    "symbolName":"BTCUSDT",
                    "baseCoin":"BTC",
                    "quoteCoin":"USDT",
                    "minTradeAmount":"0.0001",
                    "maxTradeAmount":"10000",
                    "takerFeeRate":"0.001",
                    "makerFeeRate":"0.001",
                    "priceScale":"4",
                    "quantityScale":"8",
                    "minTradeUSDT":"5",
                    "status":"online",
                    "buyLimitPriceRatio": "0.05",
                    "sellLimitPriceRatio": "0.05"
                }
            ]
        }        
        """
        trading_pair_rules = instruments_info.get("data", [])

        retval = {}
        for rule in trading_pair_rules:
            if bitget_utils.is_exchange_information_valid(exchange_info=rule):
                try:
                    exchange_symbol = rule["symbol"]
                    trading_pair = await self.trading_pair_associated_to_exchange_symbol(symbol=exchange_symbol)
                    retval[trading_pair] = TradingRule(
                        trading_pair=trading_pair,
                        min_order_size=Decimal(rule["minTradeAmount"]),
                        min_price_increment=Decimal(1 * Decimal(f"1e-{rule['priceScale']}")),
                        min_base_amount_increment=Decimal(1 * Decimal(f"1e-{rule['quantityScale']}")),
                        min_notional_size=Decimal(rule["minTradeUSDT"]),
                    )
                except Exception as e:
                    self.logger().exception(f"Error parsing the trading pair rule: {rule}. Skipping.")

        return list(retval.values())




    # async def _api_request(self,
    #                        path_url,
    #                        method: RESTMethod = RESTMethod.GET,
    #                        params: Optional[Dict[str, Any]] = None,
    #                        data: Optional[Dict[str, Any]] = None,
    #                        is_auth_required: bool = False,
    #                        return_err: bool = False,
    #                        limit_id: Optional[str] = None,
    #                        trading_pair: Optional[str] = None,
    #                        **kwargs) -> Dict[str, Any]:
    #     last_exception = None
    #     rest_assistant = await self._web_assistants_factory.get_rest_assistant()
    #     url = web_utils.rest_url(path_url, domain=self.domain)
    #     local_headers = {
    #         "Content-Type": "application/x-www-form-urlencoded"}
    #     for _ in range(2):
    #         try:
    #             request_result = await rest_assistant.execute_request(
    #                 url=url,
    #                 params=params,
    #                 data=data,
    #                 method=method,
    #                 is_auth_required=is_auth_required,
    #                 return_err=return_err,
    #                 headers=local_headers,
    #                 throttler_limit_id=limit_id if limit_id else path_url,
    #             )
    #             return request_result
    #         except IOError as request_exception:
    #             last_exception = request_exception
    #             if self._is_request_exception_related_to_time_synchronizer(request_exception=request_exception):
    #                 self._time_synchronizer.clear_time_offset_ms_samples()
    #                 await self._update_time_synchronizer()
    #             else:
    #                 raise

    #     # Failed even after the last retry
    #     raise last_exception
