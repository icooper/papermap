#!/usr/bin/env python

#
# gsm_fetch.py
#
# Fetches a URL using the SIM800 module.
#

import sim800
import threading
import time

sim = sim800.SIM800()
sim.monitor()

# make sure the module is powered on
lock = sim.AT(return_lock=True)
if lock.acquire(timeout=1.0):
    lock.release()
    sim.AT('CIPSHUT')
else:
    sim.remove_pending(lock)
    print("=== Powering the module on")
    sim.onoff()
    lock = sim.AT(return_lock=True)
    if lock.acquire(timeout=5.0):
        lock.release()
        sim.AT('CPIN')
    else:
        print("=== Power on attempt failed :(")
        sim.stop()
        exit(1)

# wait for a registration
sim.AT('CREG?')
while sim.reg_status not in [1, 4]:
    time.sleep(3.0)
    sim.AT('CREG?')

sim.AT('COPS?')
sim.AT('CIPMUX', params=0)
sim.AT('CSQ')

# wait for a GPRS attachment
sim.AT('CGATT?')
while sim.gprs_status != 1:
    time.sleep(3.0)
    sim.AT('CGATT?')

sim.AT('CSTT', params='h2g2')
sim.AT('CIICR')
sim.AT('CIPSTATUS')

# are we connected?
if sim.ip_status == 'IP GPRSACT':
    print('=== Data connection established')
    sim.AT('CIFSR')

sim.AT('CIPSHUT')
sim.stop()
sim.onoff()
print('=== Module powered off')