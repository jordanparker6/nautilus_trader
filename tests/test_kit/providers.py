# -------------------------------------------------------------------------------------------------
#  Copyright (C) 2015-2021 Nautech Systems Pty Ltd. All rights reserved.
#  https://nautechsystems.io
#
#  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
#  You may not use this file except in compliance with the License.
#  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# -------------------------------------------------------------------------------------------------

import os
from decimal import Decimal
from typing import List

import orjson
import pandas as pd
from pandas import DataFrame

from nautilus_trader.adapters.betfair.common import BETFAIR_VENUE
from nautilus_trader.backtest.loaders import CSVBarDataLoader
from nautilus_trader.backtest.loaders import CSVTickDataLoader
from nautilus_trader.backtest.loaders import ParquetTickDataLoader
from nautilus_trader.backtest.loaders import TardisQuoteDataLoader
from nautilus_trader.backtest.loaders import TardisTradeDataLoader
from nautilus_trader.core.correctness import PyCondition
from nautilus_trader.core.datetime import millis_to_nanos
from nautilus_trader.model.currencies import ADA
from nautilus_trader.model.currencies import BTC
from nautilus_trader.model.currencies import ETH
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.currency import Currency
from nautilus_trader.model.data.tick import TradeTick
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.instruments.betting import BettingInstrument
from nautilus_trader.model.instruments.crypto_swap import CryptoSwap
from nautilus_trader.model.instruments.currency import CurrencySpot
from nautilus_trader.model.objects import Money
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.orderbook.data import Order
from tests.test_kit import PACKAGE_ROOT


class TestDataProvider:
    @staticmethod
    def ethusdt_trades() -> DataFrame:
        path = os.path.join(PACKAGE_ROOT, "data", "binance-ethusdt-trades.csv")
        return CSVTickDataLoader.load(path)

    @staticmethod
    def audusd_ticks() -> DataFrame:
        path = os.path.join(PACKAGE_ROOT, "data", "truefx-audusd-ticks.csv")
        return CSVTickDataLoader.load(path)

    @staticmethod
    def usdjpy_ticks() -> DataFrame:
        path = os.path.join(PACKAGE_ROOT, "data", "truefx-usdjpy-ticks.csv")
        return CSVTickDataLoader.load(path)

    @staticmethod
    def gbpusd_1min_bid() -> DataFrame:
        path = os.path.join(PACKAGE_ROOT, "data", "fxcm-gbpusd-m1-bid-2012.csv")
        return CSVBarDataLoader.load(path)

    @staticmethod
    def gbpusd_1min_ask() -> DataFrame:
        path = os.path.join(PACKAGE_ROOT, "data", "fxcm-gbpusd-m1-ask-2012.csv")
        return CSVBarDataLoader.load(path)

    @staticmethod
    def usdjpy_1min_bid() -> DataFrame:
        path = os.path.join(PACKAGE_ROOT, "data", "fxcm-usdjpy-m1-bid-2013.csv")
        return CSVBarDataLoader.load(path)

    @staticmethod
    def usdjpy_1min_ask() -> DataFrame:
        path = os.path.join(PACKAGE_ROOT, "data", "fxcm-usdjpy-m1-ask-2013.csv")
        return CSVBarDataLoader.load(path)

    @staticmethod
    def tardis_trades() -> DataFrame:
        path = os.path.join(PACKAGE_ROOT, "data", "tardis_trades.csv")
        return TardisTradeDataLoader.load(path)

    @staticmethod
    def tardis_quotes() -> DataFrame:
        path = os.path.join(PACKAGE_ROOT, "data", "tardis_quotes.csv")
        return TardisQuoteDataLoader.load(path)

    @staticmethod
    def parquet_btcusdt_trades() -> DataFrame:
        path = os.path.join(PACKAGE_ROOT, "data", "binance-btcusdt-trades.parquet")
        return ParquetTickDataLoader.load(path)

    @staticmethod
    def parquet_btcusdt_quotes() -> DataFrame:
        path = os.path.join(PACKAGE_ROOT, "data", "binance-btcusdt-quotes.parquet")
        return ParquetTickDataLoader.load(path)

    @staticmethod
    def binance_btcusdt_instrument():
        path = os.path.join(PACKAGE_ROOT, "data", "binance-btcusdt-instrument.txt")
        with open(path, "r") as f:
            return f.readline()

    @staticmethod
    def l1_feed():
        updates = []
        for _, row in TestDataProvider.usdjpy_ticks().iterrows():
            for side, order_side in zip(("bid", "ask"), (OrderSide.BUY, OrderSide.SELL)):
                updates.append(
                    {
                        "op": "update",
                        "order": Order(
                            price=Price(row[side], precision=6),
                            size=Quantity(1e9, precision=2),
                            side=order_side,
                        ),
                    }
                )
        return updates

    @staticmethod
    def l2_feed() -> List:
        def parse_line(d):
            if "status" in d:
                return {}
            elif "close_price" in d:
                # return {'timestamp': d['remote_timestamp'], "close_price": d['close_price']}
                return {}
            if "trade" in d:
                return {
                    "timestamp": d["remote_timestamp"],
                    "op": "trade",
                    "trade": TradeTick(
                        instrument_id=InstrumentId(Symbol("TEST"), Venue("BETFAIR")),
                        price=Price(d["trade"]["price"], 4),
                        size=Quantity(d["trade"]["volume"], 4),
                        aggressor_side=d["trade"]["side"],
                        match_id=(d["trade"]["trade_id"]),
                        ts_event=millis_to_nanos(pd.Timestamp(d["remote_timestamp"]).timestamp()),
                        ts_init=millis_to_nanos(
                            pd.Timestamp(
                                d["remote_timestamp"]
                            ).timestamp()  # TODO(cs): Hardcoded identical for now
                        ),
                    ),
                }
            elif "level" in d and d["level"]["orders"][0]["volume"] == 0:
                op = "delete"
            else:
                op = "update"
            order_like = d["level"]["orders"][0] if op != "trade" else d["trade"]
            return {
                "timestamp": d["remote_timestamp"],
                "op": op,
                "order": Order(
                    price=Price(order_like["price"], precision=6),
                    size=Quantity(abs(order_like["volume"]), precision=4),
                    # Betting sides are reversed
                    side={2: OrderSide.BUY, 1: OrderSide.SELL}[order_like["side"]],
                    id=str(order_like["order_id"]),
                ),
            }

        return [
            parse_line(line)
            for line in orjson.loads(open(PACKAGE_ROOT + "/data/L2_feed.json").read())
        ]

    @staticmethod
    def l3_feed():
        def parser(data):
            parsed = data
            if not isinstance(parsed, list):
                # print(parsed)
                return
            elif isinstance(parsed, list):
                channel, updates = parsed
                if not isinstance(updates[0], list):
                    updates = [updates]
            else:
                raise KeyError()
            if isinstance(updates, int):
                print("Err", updates)
                return
            for values in updates:
                keys = ("order_id", "price", "size")
                data = dict(zip(keys, values))
                side = OrderSide.BUY if data["size"] >= 0 else OrderSide.SELL
                if data["price"] == 0:
                    yield dict(
                        op="delete",
                        order=Order(
                            price=Price(data["price"], precision=10),
                            size=Quantity(abs(data["size"]), precision=10),
                            side=side,
                            id=str(data["order_id"]),
                        ),
                    )
                else:
                    yield dict(
                        op="update",
                        order=Order(
                            price=Price(data["price"], precision=10),
                            size=Quantity(abs(data["size"]), precision=10),
                            side=side,
                            id=str(data["order_id"]),
                        ),
                    )

        return [
            msg
            for data in orjson.loads(open(PACKAGE_ROOT + "/data/L3_feed.json").read())
            for msg in parser(data)
        ]


class TestInstrumentProvider:
    """
    Provides instrument template methods for backtesting.
    """

    @staticmethod
    def btcusdt_binance() -> CurrencySpot:
        """
        Return the Binance BTC/USDT instrument for backtesting.

        Returns
        -------
        CurrencySpot

        """
        return CurrencySpot(
            instrument_id=InstrumentId(
                symbol=Symbol("BTC/USDT"),
                venue=Venue("BINANCE"),
            ),
            base_currency=BTC,
            quote_currency=USDT,
            price_precision=2,
            size_precision=6,
            price_increment=Price(1e-02, precision=2),
            size_increment=Quantity(1e-06, precision=6),
            lot_size=None,
            max_quantity=Quantity(9000, precision=6),
            min_quantity=Quantity(1e-06, precision=6),
            max_notional=None,
            min_notional=Money(10.00000000, USDT),
            max_price=Price(1000000, precision=2),
            min_price=Price(0.01, precision=2),
            margin_init=Decimal(0),
            margin_maint=Decimal(0),
            maker_fee=Decimal("0.001"),
            taker_fee=Decimal("0.001"),
            ts_event=0,
            ts_init=0,
        )

    @staticmethod
    def ethusdt_binance() -> CurrencySpot:
        """
        Return the Binance ETH/USDT instrument for backtesting.

        Returns
        -------
        CurrencySpot

        """
        return CurrencySpot(
            instrument_id=InstrumentId(
                symbol=Symbol("ETH/USDT"),
                venue=Venue("BINANCE"),
            ),
            base_currency=ETH,
            quote_currency=USDT,
            price_precision=2,
            size_precision=5,
            price_increment=Price(1e-02, precision=2),
            size_increment=Quantity(1e-05, precision=5),
            lot_size=None,
            max_quantity=Quantity(9000, precision=5),
            min_quantity=Quantity(1e-05, precision=5),
            max_notional=None,
            min_notional=Money(10.00, USDT),
            max_price=Price(1000000, precision=2),
            min_price=Price(0.01, precision=2),
            margin_init=Decimal("1.00"),
            margin_maint=Decimal("0.35"),
            maker_fee=Decimal("0.0001"),
            taker_fee=Decimal("0.0001"),
            ts_event=0,
            ts_init=0,
        )

    @staticmethod
    def adabtc_binance() -> CurrencySpot:
        """
        Return the Binance ADA/BTC instrument for backtesting.

        Returns
        -------
        CurrencySpot

        """
        return CurrencySpot(
            instrument_id=InstrumentId(
                symbol=Symbol("ADA/BTC"),
                venue=Venue("BINANCE"),
            ),
            base_currency=ADA,
            quote_currency=BTC,
            price_precision=8,
            size_precision=0,
            price_increment=Price(1e-08, precision=8),
            size_increment=Quantity.from_int(1),
            lot_size=None,
            max_quantity=Quantity.from_int(90000000),
            min_quantity=Quantity.from_int(1),
            max_notional=None,
            min_notional=Money(0.00010000, BTC),
            max_price=Price(1000, precision=8),
            min_price=Price(1e-8, precision=8),
            margin_init=Decimal("0"),
            margin_maint=Decimal("0"),
            maker_fee=Decimal("0.0010"),
            taker_fee=Decimal("0.0010"),
            ts_event=0,
            ts_init=0,
        )

    @staticmethod
    def xbtusd_bitmex() -> CryptoSwap:
        """
        Return the BitMEX XBT/USD perpetual contract for backtesting.

        Returns
        -------
        CryptoSwap

        """
        return CryptoSwap(
            instrument_id=InstrumentId(
                symbol=Symbol("XBT/USD"),
                venue=Venue("BITMEX"),
            ),
            base_currency=BTC,
            quote_currency=USD,
            settlement_currency=BTC,
            is_inverse=True,
            price_precision=1,
            size_precision=0,
            price_increment=Price.from_str("0.5"),
            size_increment=Quantity.from_int(1),
            max_quantity=None,
            min_quantity=None,
            max_notional=Money(10_000_000.00, USD),
            min_notional=Money(1.00, USD),
            max_price=Price.from_str("1000000.0"),
            min_price=Price(0.5, precision=1),
            margin_init=Decimal("0.01"),
            margin_maint=Decimal("0.0035"),
            maker_fee=Decimal("-0.00025"),
            taker_fee=Decimal("0.00075"),
            ts_event=0,
            ts_init=0,
        )

    @staticmethod
    def ethusd_bitmex() -> CryptoSwap:
        """
        Return the BitMEX ETH/USD perpetual swap contract for backtesting.

        Returns
        -------
        CryptoSwap

        """
        return CryptoSwap(
            instrument_id=InstrumentId(
                symbol=Symbol("ETH/USD"),
                venue=Venue("BITMEX"),
            ),
            base_currency=ETH,
            quote_currency=USD,
            settlement_currency=BTC,
            is_inverse=True,
            price_precision=2,
            size_precision=0,
            price_increment=Price.from_str("0.05"),
            size_increment=Quantity.from_int(1),
            max_quantity=Quantity.from_int(10000000),
            min_quantity=Quantity.from_int(1),
            max_notional=None,
            min_notional=None,
            max_price=Price.from_str("1000000.00"),
            min_price=Price.from_str("0.05"),
            margin_init=Decimal("0.02"),
            margin_maint=Decimal("0.007"),
            maker_fee=Decimal("-0.00025"),
            taker_fee=Decimal("0.00075"),
            ts_event=0,
            ts_init=0,
        )

    @staticmethod
    def default_fx_ccy(symbol: str, venue: Venue = None) -> CurrencySpot:
        """
        Return a default FX currency pair instrument from the given instrument_id.

        Parameters
        ----------
        symbol : str
            The currency pair symbol.
        venue : Venue
            The currency pair venue.

        Returns
        -------
        CurrencySpot

        Raises
        ------
        ValueError
            If the instrument_id.instrument_id length is not in range [6, 7].

        """
        if venue is None:
            venue = Venue("SIM")
        PyCondition.valid_string(symbol, "symbol")
        PyCondition.in_range_int(len(symbol), 6, 7, "len(symbol)")

        instrument_id = InstrumentId(
            symbol=Symbol(symbol),
            venue=venue,
        )

        base_currency = symbol[:3]
        quote_currency = symbol[-3:]

        # Check tick precision of quote currency
        if quote_currency == "JPY":
            price_precision = 3
        else:
            price_precision = 5

        return CurrencySpot(
            instrument_id=instrument_id,
            base_currency=Currency.from_str(base_currency),
            quote_currency=Currency.from_str(quote_currency),
            price_precision=price_precision,
            size_precision=0,
            price_increment=Price(1 / 10 ** price_precision, price_precision),
            size_increment=Quantity.from_int(1),
            lot_size=Quantity.from_str("1000"),
            max_quantity=Quantity.from_str("1e7"),
            min_quantity=Quantity.from_str("1000"),
            max_price=None,
            min_price=None,
            max_notional=Money(50000000.00, USD),
            min_notional=Money(1000.00, USD),
            margin_init=Decimal("0.03"),
            margin_maint=Decimal("0.03"),
            maker_fee=Decimal("0.00002"),
            taker_fee=Decimal("0.00002"),
            ts_event=0,
            ts_init=0,
        )

    @staticmethod
    def betting_instrument():
        return BettingInstrument(
            venue_name=BETFAIR_VENUE.value,
            betting_type="ODDS",
            competition_id="12282733",
            competition_name="NFL",
            event_country_code="GB",
            event_id="29678534",
            event_name="NFL",
            event_open_date=pd.Timestamp("2022-02-07 23:30:00+00:00").to_pydatetime(),
            event_type_id="6423",
            event_type_name="American Football",
            market_id="1.179082386",
            market_name="AFC Conference Winner",
            market_start_time=pd.Timestamp("2022-02-07 23:30:00+00:00").to_pydatetime(),
            market_type="SPECIAL",
            selection_handicap="",
            selection_id="50214",
            selection_name="Kansas City Chiefs",
            currency="GBP",
            ts_event=0,
            ts_init=0,
        )