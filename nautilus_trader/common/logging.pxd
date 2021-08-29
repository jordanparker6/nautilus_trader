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

from typing import Callable, Dict

from cpython.datetime cimport datetime
from cpython.datetime cimport timedelta

from nautilus_trader.common.clock cimport Clock
from nautilus_trader.common.logging cimport Logger
from nautilus_trader.common.queue cimport Queue
from nautilus_trader.core.uuid cimport UUID4
from nautilus_trader.model.identifiers cimport TraderId


cdef str RECV
cdef str SENT
cdef str CMD
cdef str EVT
cdef str REQ
cdef str RES


cpdef enum LogLevel:
    DEBUG = 10,
    INFO = 20,
    WARNING = 30,
    ERROR = 40,
    CRITICAL = 50,


cpdef enum LogColor:
    NORMAL = 0,
    GREEN = 1,
    BLUE = 2,
    YELLOW = 3,
    RED = 4,


cdef class LogLevelParser:

    @staticmethod
    cdef str to_str(int value)

    @staticmethod
    cdef LogLevel from_str(str value)


cdef class Logger:
    cdef Clock _clock
    cdef LogLevel _log_level_stdout
    cdef list _sinks

    cdef readonly TraderId trader_id
    """The loggers trader ID.\n\n:returns: `TraderId`"""
    cdef readonly str host_id
    """The loggers host ID.\n\n:returns: `str`"""
    cdef readonly UUID4 instance_id
    """The loggers instance ID.\n\n:returns: `UUID4`"""
    cdef readonly bint is_bypassed
    """If the logger is in bypass mode.\n\n:returns: `bool`"""

    cpdef void register_sink(self, handler: Callable[[Dict], None]) except *
    cdef void change_clock_c(self, Clock clock) except *
    cdef void log_c(self, dict record) except *
    cdef dict create_record(self, LogLevel level, LogColor color, str component, str msg, dict annotations=*)

    cdef void _log(self, dict record) except *
    cdef str _format_record(self, LogLevel level, LogColor color, dict record)


cdef class LoggerAdapter:
    cdef Logger _logger

    cdef readonly TraderId trader_id
    """The loggers trader ID.\n\n:returns: `TraderId`"""
    cdef readonly str host_id
    """The loggers host ID.\n\n:returns: `str`"""
    cdef readonly UUID4 instance_id
    """The loggers instance ID.\n\n:returns: `UUID4`"""
    cdef readonly str component
    """The loggers component name.\n\n:returns: `str`"""
    cdef readonly bint is_bypassed
    """If the logger is in bypass mode.\n\n:returns: `bool`"""

    cpdef Logger get_logger(self)
    cpdef void debug(self, str msg, LogColor color=*, dict annotations=*) except *
    cpdef void info(self, str msg, LogColor color=*, dict annotations=*) except *
    cpdef void warning(self, str msg, LogColor color=*, dict annotations=*) except *
    cpdef void error(self, str msg, LogColor color=*, dict annotations=*) except *
    cpdef void critical(self, str msg, LogColor color=*, dict annotations=*) except *
    cpdef void exception(self, ex, dict annotations=*) except *


cpdef void nautilus_header(LoggerAdapter logger) except *
cpdef void log_memory(LoggerAdapter logger) except *


cdef class LiveLogger(Logger):
    cdef object _loop
    cdef object _run_task
    cdef timedelta _blocked_log_interval
    cdef Queue _queue

    cdef readonly bint is_running
    """If the logger is running an event loop task.\n\n:returns: `bool`"""
    cdef readonly datetime last_blocked
    """The timestamp (UTC) the logger last blocked.\n\n:returns: `datetime` or None"""

    cpdef void start(self) except *
    cpdef void stop(self) except *
    cdef void _enqueue_sentinel(self) except *