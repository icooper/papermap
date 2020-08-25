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

# echo off, multiplex off
sim.AT('ATE0')
sim.AT('CIPMUX', params=0)

# wait for a registration
sim.AT('CREG?')
while sim.reg_status not in [1, 4]:
    time.sleep(30.0)
    sim.AT('CREG?')

sim.AT('COPS?')
sim.AT('CSQ')

# wait for a GPRS attachment
sim.AT('CGATT?')
while sim.gprs_status != 1:
    time.sleep(30.0)
    sim.AT('CGATT?')

sim.AT('CSTT', params='h2g2')
sim.AT('CIICR')
sim.AT('CIPSTATUS', timeout=10)

# are we connected?
while sim.ip_status != 'IP GPRSACT':
    sim.AT('CIPSTATUS', timeout=10)

print('=== Data connection established')
sim.AT('CIFSR')

sim.AT('CIPSHUT')
sim.stop()
#sim.onoff()
#print('=== Module powered off')