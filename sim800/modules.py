from . import power

from typing import Iterable, Union, ClassVar
import io
import serial, serial.tools.list_ports
import threading
import time

class SIM800:

    COMMANDS = {}

    def __init__(self, *, apn='h2g2', port: str=None, baudrate=115200, timeout=5.0):
        self._apn = apn
        self._serial = serial.Serial(port=port or serial.tools.list_ports.comports()[0].device, baudrate=baudrate, timeout=timeout)
        self._reading = False
        self._pending = []
        self._queue_lock = threading.Lock()
        self._reader_thread = None
        self._ip_status = None
        self._reg_status = None
        self._network = None
        self._gprs_status = None
        self._ip_address = None

    @property
    def ip_status(self):
        return self._ip_status

    @ip_status.setter
    def ip_status(self, value):
        self._ip_status = value

    @property
    def reg_status(self):
        return self._reg_status

    @reg_status.setter
    def reg_status(self, value):
        self._reg_status = value

    @property
    def network(self):
        return self._network

    @network.setter
    def network(self, value):
        self._network = value

    @property
    def gprs_status(self):
        return self._gprs_status

    @gprs_status.setter
    def gprs_status(self, value):
        self._gprs_status = value

    @property
    def ip_address(self):
        return self.ip_address

    @ip_address.setter
    def ip_address(self, value):
        self._ip_address = value

    def AT(self, command: str='AT', *, params: Union[int, str, Iterable[str]]=None, data: str=None, return_lock=False):
        if command[-1] == '?':
            command = command[:-1]
            params = '?'
        if command in SIM800.COMMANDS:
            command_obj = SIM800.COMMANDS[command](self)
            if self._queue_lock.acquire():
                pending_lock = None
                pending = command_obj(self._serial.write, params=params, data=data)
                if pending:
                    pending_lock = threading.Lock()
                    pending_lock.acquire()
                    self._pending.append((pending, command_obj, pending_lock))
                self._serial.flush()
                self._queue_lock.release()
                if return_lock == False and pending_lock:
                    pending_lock.acquire()
                    pending_lock.release()
                return return_lock and pending_lock

    def monitor(self):
        self._reading = True
        self._reader_thread = threading.Thread(target=self._reader)
        self._reader_thread.start()

    def _reader(self):
        while self._reading and self._serial.is_open:

            # get the line
            line = self._serial.readline().decode('utf-8').strip()

            # check for normal stuff
            if len(line) > 0 and (' ' in line or line == 'OK'):
                line0 = line.split(' ')[0]
                if line0 in map(lambda p: p[0], self._pending) or line0[1:-1] in SIM800.COMMANDS:
                    print('-->', self.process(line0, line))
                elif line not in ['OK', 'ERROR', 'Call Ready', 'SMS Ready']:
                    print('*** unhandled by _reader():', line0, '(%s)' % line)

            # does it seem like we're waiting for an IP address?
            elif '+CIFSR:' in map(lambda x: x[0], self._pending) and len(line.split('.')) == 4:
                print('-->', self.process('+CIFSR:', line))

    def onoff(self):
        power.onoff()

    def remove_pending(self, lock: threading.Lock):
        if self._queue_lock.acquire():
            for i in range(len(self._pending)):
                if lock is self._pending[i][2]:
                    del self._pending[i]
                    break
            self._queue_lock.release()

    def process(self, command: str, line: str):
        if command in map(lambda p: p[0], self._pending):
            if self._queue_lock.acquire():
                for i in range(len(self._pending)):
                    pending, command_obj, lock = self._pending[i]
                    if pending == command:
                        name, result = command_obj.name, command_obj.process(line)
                        del self._pending[i]
                        if lock:
                            lock.release()
                        break
                self._queue_lock.release()
            return (name, 'expected', result)
        elif command[1:-1] in SIM800.COMMANDS:
            command_obj = SIM800.COMMANDS[command[1:-1]](self)
            return (command_obj.name, 'unsolicited', command_obj.process(line))
        else:
            print('*** unhandled by process():', command, '(%s)' % line)

    def stop(self):
        self._reading = False
        self._reader_thread.join()

    @staticmethod
    def register(command: str, command_cls: ClassVar):
        if command not in SIM800.COMMANDS:
            SIM800.COMMANDS[command] = command_cls
