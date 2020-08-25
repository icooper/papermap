from .modules import SIM800

from abc import ABC, abstractmethod
from typing import Union, Iterable, Callable, Any
import serial
import time

"""AT Commands for the SIM800 GSM/GPRS/GNSS/BT module."""

class ATCommand(ABC):
    def __init__(self, sim: SIM800, command: str=None, *, expected=True, keyword: str=None, delay=0.0):
        command = command or self.__class__.__name__
        self._sim = sim
        self._command = command if command[:2] == 'AT' else 'AT+%s' % command
        self._expected = expected
        self._keyword = keyword or '+%s:' % command
        self._delay = delay

    def __call__(self, write: Callable[[bytes], None], *, params: Union[int, str, Iterable[str]]=None, data: str=None):
        output = self._command
        if params != None:
            if isinstance(params, int):
                output += '=%s' % params
            elif isinstance(params, str):
                if params == '?':
                    output += '?'
                else:
                    output += '="%s"' % params
            else:
                output += '="%s"' % '","'.join(params)
        print('<--', output)
        output += '\r\n'
        if data:
            output += data
            output += '\x1a'
        write(bytes(output, encoding='utf-8'))

        if self._delay:
            time.sleep(self._delay)

        return self._expected and self._keyword

    def process(self, line: str):
        return line

    @property
    def name(self):
        return self.__class__.__name__

class AT(ATCommand):
    def __init__(self, sim: SIM800):
        super(AT, self).__init__(sim, keyword='OK')

    def process(self, line: str):
        return line == 'OK'

class ATE0(ATCommand):
    def __init__(self, sim: SIM800):
        super(ATE0, self).__init__(sim, expected=False)

class CSQ(ATCommand):
    def __init__(self, sim: SIM800):
        super(CSQ, self).__init__(sim, "CSQ")

    def process(self, line: str):
        rssi = 99
        if line.startswith('+CSQ: '):
            try:
                rssi = int(line[6:].split(',')[0])
            except OSError:
                pass
        if rssi == 0:
            rssi = (rssi, '<= -115 dBm')
        elif rssi == 1:
            rssi = (rssi, '-111 dBm')
        elif rssi > 1 and rssi < 31:
            rssi = (rssi, '%d dBm' % (2 * rssi - 114))
        elif rssi == 31:
            rssi = (rssi, '>= -52 dBm')
        else:
            rssi = (rssi, 'Unknown')
        return rssi

class CREG(ATCommand):

    STAT = {
        0: 'Not searching for network',
        1: 'Registered, home network',
        2: 'Searching for network',
        3: 'Registration denied',
        4: 'Unknown',
        5: 'Registered, roaming'
    }

    def process(self, line: str):
        status = 4
        try:
            status = line[7:].split(',')
            if len(status) == 2 or len(status) == 4:
                status = int(status[1])
            else:
                status = int(status[0])
        except OSError:
            status = 4
            pass
        if status < 0 or status > 5:
            status = 4
        self._sim.reg_status = status
        return (status, CREG.STAT[status])
                    
class CGATT(ATCommand):

    STAT = {
        -1: 'Unknown',
        0: 'Detached',
        1: 'Attached'
    }

    def process(self, line: str):
        status = -1
        try:
            status = int(line[8:])
        except OSError:
            pass
        self._sim.gprs_status = status
        return (status, CGATT.STAT[status])

class CSTT(ATCommand):
    def __init__(self, sim: SIM800):
        super(CSTT, self).__init__(sim, expected=False)
    
class CIPSHUT(ATCommand):
    def __init__(self, sim: SIM800):
        super(CIPSHUT, self).__init__(sim, keyword='SHUT')

    def process(self, line: str):
        if line.strip() == 'SHUT OK':
            return True

class CIPSTATUS(ATCommand):
    def __init__(self, sim: SIM800):
        super(CIPSTATUS, self).__init__(sim, keyword='STATE:')

    def process(self, line: str):
        status = line[7:]
        self._sim.ip_status = status
        return status

class CIPMUX(ATCommand):
    def __init__(self, sim: SIM800):
        super(CIPMUX, self).__init__(sim, expected=False)

class CIICR(ATCommand):
    def __init__(self, sim: SIM800):
        super(CIICR, self).__init__(sim, expected=False)

class CPIN(ATCommand):
    def process(self, line: str):
        if line == '+CPIN: READY':
            return True

class COPS(ATCommand):
    def process(self, line: str):
        self._sim.network = line.split(',')[2][1:-1]
        return self._sim.network

class CIFSR(ATCommand):
    def process(self, line: str):
        self._sim.ip_address = line
        return line

# CDNSGIP = 'CDNSGIP'
# CIPSTATUS = 'CIPSTATUS'
# CIPSTART = 'CIPSTART'
# CIPSEND = 'CIPSEND'
# CIPCLOSE = 'CIPCLOSE'