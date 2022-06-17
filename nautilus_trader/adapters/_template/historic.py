# -------------------------------------------------------------------------------------------------
#  Copyright (C) 2015-2022 Nautech Systems Pty Ltd. All rights reserved.
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

import datetime
import logging
from typing import Any, List, TypeVar, Union

import pandas as pd
import pytz

from nautilus_trader.core.datetime import nanos_to_secs
from nautilus_trader.model.data.bar import Bar
from nautilus_trader.model.data.bar import BarSpecification
from nautilus_trader.model.data.tick import QuoteTick
from nautilus_trader.model.data.tick import TradeTick
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import TradeId
from nautilus_trader.model.instruments.base import Instrument
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.persistence.external.core import write_objects


# The 'pragma: no cover' comment excludes a method from test coverage.
# https://coverage.readthedocs.io/en/coverage-4.3.3/excluding.html
# The reason for their use is to reduce redundant/needless tests which simply
# assert that a `NotImplementedError` is raised when calling abstract methods.
# These tests are expensive to maintain (as they must be kept in line with any
# refactorings), and offer little to no benefit in return. However, the intention
# is for all method implementations to be fully covered by tests.

# *** THESE PRAGMA: NO COVER COMMENTS MUST BE REMOVED IN ANY IMPLEMENTATION. ***


logger = logging.getLogger(__name__)


HttpClient = TypeVar("HttpClient")

# ~~~~ Adapter Specific Methods~~~~~~~~~~~~~


def _request_historical_ticks(
    client: HttpClient, instrument: Instrument, start_time: datetime.datetime, what="BID_ASK"
):
    raise NotImplementedError("Requires an implementation by an adapter")


def _request_historical_bars(
    client: HttpClient,
    instrument: Instrument,
    end_time: datetime.datetime,
    bar_spec: BarSpecification,
):
    raise NotImplementedError("Requires an implementation by an adapter")


def parse_historic_bars(historic_bars: List[Any], instrument: Instrument, kind: str) -> List[Bar]:
    raise NotImplementedError("Requires an implementation by an adapter")


def parse_historic_quote_ticks(
    historic_ticks: List[Any], instrument_id: InstrumentId
) -> List[QuoteTick]:
    raise NotImplementedError("Requires an implementation by an adapter")


def parse_historic_trade_ticks(
    historic_ticks: List[Any], instrument_id: InstrumentId
) -> List[TradeTick]:
    raise NotImplementedError("Requires an implementation by an adapter")


# ~~~~ Common Methods ~~~~~~~~~~~~~


def back_fill_catalog(
    client: HttpClient,
    catalog: ParquetDataCatalog,
    instruments: List[Instrument],
    start_date: datetime.date,
    end_date: datetime.date,
    tz_name: str,
    kinds=("BID_ASK", "TRADES"),
):
    """
    Back fill the data catalog with market data from the adapter.

    Parameters
    ----------
    client : HttpClient
        The HTTP client defined by the adapter.
    catalog : DataCatalog
        The DataCatalog to write the data to
    instruments : List[Instrument]
        The list of Binance instruments to collect data for
    start_date : datetime.date
        The start_date for the back fill.
    end_date : datetime.date
        The end_date for the back fill.
    tz_name : str
        The timezone of the instruments
    kinds : tuple[str] (default: ('BID_ASK', 'TRADES')
        The kinds to query data for, can be any of:
        - BID_ASK
        - TRADES
        - A bar specification, i.e. BARS-1-MINUTE-LAST or BARS-5-SECOND-MID
    """
    for date in pd.bdate_range(start_date, end_date, tz=tz_name):
        for instrument in instruments:
            # Check if this instrument exists in the catalog, if not, write it.
            if not catalog.instruments(instrument_ids=[instrument.id.value], as_nautilus=True):
                write_objects(catalog=catalog, chunk=[instrument])

            for kind in kinds:
                if catalog.exists(instrument_id=instrument.id, kind=kind, date=date):
                    continue
                logger.info(f"Fetching {instrument.id.value} {kind} for {date:%Y-%m-%d}")

                data = request_data(
                    instrument=instrument,
                    date=date.date(),
                    kind=kind,
                    tz_name=tz_name,
                    client=client,
                )
                if data is None:
                    continue

                template = f"{date:%Y%m%d}" + "-{i}.parquet"
                write_objects(catalog=catalog, chunk=data, basename_template=template)


def request_data(
    instrument: Instrument,
    date: datetime.date,
    kind: str,
    tz_name: str,
    client: HttpClient,
):
    if kind in ("TRADES", "BID_ASK"):
        raw = request_tick_data(
            instrument=instrument, date=date, kind=kind, tz_name=tz_name, client=client
        )
    elif kind.split("-")[0] == "BARS":
        bar_spec = BarSpecification.from_str(kind.split("-", maxsplit=1)[1])
        raw = request_bar_data(
            instrument=instrument, date=date, bar_spec=bar_spec, tz_name=tz_name, client=client
        )
    else:
        raise RuntimeError(f"Unknown {kind=}")

    if not raw:
        logging.info(f"No ticks for {date=} {kind=} {instrument=}, skipping")
        return
    logger.info(f"Fetched {len(raw)} raw {kind}")
    if kind == "TRADES":
        return parse_historic_trade_ticks(historic_ticks=raw, instrument_id=instrument.id)
    elif kind == "BID_ASK":
        return parse_historic_quote_ticks(historic_ticks=raw, instrument_id=instrument.id)
    elif kind.split("-")[0] == "BARS":
        return parse_historic_bars(historic_bars=raw, instrument=instrument, kind=kind)
    else:
        raise RuntimeError(f"Unknown {kind=}")


def request_tick_data(
    instrument: Instrument,
    date: datetime.date,
    kind: str,
    tz_name: str,
    client: HttpClient,
) -> List:
    assert kind in ("TRADES", "BID_ASK")
    data: List = []

    while True:
        start_time = _determine_next_timestamp(
            date=date, timestamps=[d.time for d in data], tz_name=tz_name
        )
        logger.debug(f"Using start_time: {start_time}")

        ticks = _request_historical_ticks(
            client=client,
            instrument=instrument,
            start_time=start_time.strftime("%Y%m%d %H:%M:%S %Z"),
            what=kind,
        )

        ticks = [t for t in ticks if t not in data]

        if not ticks or ticks[-1].time < start_time:
            break

        logger.debug(f"Received {len(ticks)} ticks between {ticks[0].time} and {ticks[-1].time}")

        last_timestamp = pd.Timestamp(ticks[-1].time)
        last_date = last_timestamp.astimezone(tz_name).date()

        if last_date != date:
            # May contain data from next date, filter this out
            data.extend(
                [
                    tick
                    for tick in ticks
                    if pd.Timestamp(tick.time).astimezone(tz_name).date() == date
                ]
            )
            break
        else:
            data.extend(ticks)
    return data


def request_bar_data(
    instrument: Instrument,
    date: datetime.date,
    tz_name: str,
    bar_spec: BarSpecification,
    client: HttpClient,
) -> List:
    data: List = []

    start_time = pd.Timestamp(date).tz_localize(tz_name).tz_convert("UTC")
    end_time = start_time + datetime.timedelta(days=1)

    while True:
        logger.debug(f"Using end_time: {end_time}")

        bar_data_list = _request_historical_bars(
            client=client,
            instrument=instrument,
            end_time=end_time.strftime("%Y%m%d %H:%M:%S %Z"),
            bar_spec=bar_spec,
        )

        bars = [bar for bar in bar_data_list if bar not in data and bar.volume != 0]

        if not bars:
            break

        logger.info(f"Received {len(bars)} bars between {bars[0].date} and {bars[-1].date}")

        # We're requesting from end_date backwards, set our timestamp to the earliest timestamp
        first_timestamp = pd.Timestamp(bars[0].date).tz_convert(tz_name)
        first_date = first_timestamp.date()

        if first_date != date:
            # May contain data from next date, filter this out
            data.extend(
                [
                    bar
                    for bar in bars
                    if parse_response_datetime(bar.date, tz_name=tz_name).date() == date
                ]
            )
            break
        else:
            data.extend(bars)

        end_time = first_timestamp

    return data


def generate_trade_id(ts_event: int, price: str, size: str) -> TradeId:
    id = TradeId(f"{int(nanos_to_secs(ts_event))}-{price}-{size}")
    assert len(id.value) < 36, f"TradeId too long, was {len(id.value)}"
    return id


def _determine_next_timestamp(timestamps: List[pd.Timestamp], date: datetime.date, tz_name: str):
    """
    While looping over available data, it is possible for very liquid products that a 1s period may contain 1000 ticks,
    at which point we need to step the time forward to avoid getting stuck when iterating.
    """
    if not timestamps:
        return pd.Timestamp(date, tz=tz_name).tz_convert("UTC")
    unique_values = set(timestamps)
    if len(unique_values) == 1:
        timestamp = timestamps[-1]
        return timestamp + pd.Timedelta(seconds=1)
    else:
        return timestamps[-1]


def parse_response_datetime(
    dt: Union[datetime.datetime, pd.Timestamp], tz_name: str
) -> datetime.datetime:
    if isinstance(dt, pd.Timestamp):
        dt = dt.to_pydatetime()
    if dt.tzinfo is None:
        tz = pytz.timezone(tz_name)
        dt = tz.localize(dt)
    return dt
