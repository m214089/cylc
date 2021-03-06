#!/usr/bin/env python

# THIS FILE IS PART OF THE CYLC SUITE ENGINE.
# Copyright (C) 2008-2017 NIWA
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Port scan utilities."""

from multiprocessing import cpu_count, Process, Pipe
import sys
from time import sleep, time
import traceback
from uuid import uuid4

from cylc.cfgspec.globalcfg import GLOBAL_CFG
import cylc.flags
from cylc.network import ConnectionError, ConnectionTimeout
from cylc.network.https.suite_identifier_client import (
    SuiteIdClientAnon, SuiteIdClient)
from cylc.suite_srv_files_mgr import (
    SuiteSrvFilesManager, SuiteServiceFileError)
from cylc.suite_host import is_remote_host, get_host_ip_by_name


CONNECT_TIMEOUT = 5.0
INACTIVITY_TIMEOUT = 10.0
MSG_QUIT = "QUIT"
MSG_TIMEOUT = "TIMEOUT"
SLEEP_INTERVAL = 0.01


def _scan_worker(conn, timeout, my_uuid):
    """Port scan worker."""
    srv_files_mgr = SuiteSrvFilesManager()
    while True:
        try:
            if not conn.poll(SLEEP_INTERVAL):
                continue
            item = conn.recv()
            if item == MSG_QUIT:
                break
            conn.send(_scan_item(timeout, my_uuid, srv_files_mgr, item))
        except KeyboardInterrupt:
            break
    conn.close()


def _scan_item(timeout, my_uuid, srv_files_mgr, item):
    """Connect to item host:port (item) to get suite identify."""
    host, port = item
    host_anon = host
    if is_remote_host(host):
        host_anon = get_host_ip_by_name(host)  # IP reduces DNS traffic
    client = SuiteIdClientAnon(
        None, host=host_anon, port=port, my_uuid=my_uuid,
        timeout=timeout)
    try:
        result = client.identify()
    except ConnectionTimeout as exc:
        return (host, port, MSG_TIMEOUT)
    except ConnectionError as exc:
        return (host, port, None)
    else:
        owner = result.get('owner')
        name = result.get('name')
        states = result.get('states', None)
        if cylc.flags.debug:
            print >> sys.stderr, '   suite:', name, owner
        if states is None:
            # This suite keeps its state info private.
            # Try again with the passphrase if I have it.
            try:
                pphrase = srv_files_mgr.get_auth_item(
                    srv_files_mgr.FILE_BASE_PASSPHRASE,
                    name, owner, host, content=True)
            except SuiteServiceFileError:
                pass
            else:
                if pphrase:
                    client = SuiteIdClient(
                        name, owner=owner, host=host, port=port,
                        my_uuid=my_uuid, timeout=timeout)
                    try:
                        result = client.identify()
                    except ConnectionError as exc:
                        # Nope (private suite, wrong passphrase).
                        if cylc.flags.debug:
                            print >> sys.stderr, (
                                '    (wrong passphrase)')
                    else:
                        if cylc.flags.debug:
                            print >> sys.stderr, (
                                '    (got states with passphrase)')
        return (host, port, result)


def scan_all(hosts=None, timeout=None, updater=None):
    """Scan all hosts."""
    try:
        timeout = float(timeout)
    except:
        timeout = CONNECT_TIMEOUT
    my_uuid = uuid4()
    # Determine hosts to scan
    if not hosts:
        hosts = GLOBAL_CFG.get(["suite host scanning", "hosts"])
    # Ensure that it does "localhost" only once
    hosts = set(hosts)
    for host in list(hosts):
        if not is_remote_host(host):
            hosts.remove(host)
            hosts.add("localhost")
    # Determine ports to scan
    base_port = GLOBAL_CFG.get(['communication', 'base port'])
    max_ports = GLOBAL_CFG.get(['communication', 'maximum number of ports'])
    # Number of child processes
    max_procs = GLOBAL_CFG.get(["process pool size"])
    if max_procs is None:
        max_procs = cpu_count()
    # To do and wait (submitted, waiting for results) sets
    todo_set = set()
    wait_set = set()
    for host in hosts:
        for port in range(base_port, base_port + max_ports):
            todo_set.add((host, port))
    proc_items = []
    results = []
    try:
        while todo_set or proc_items:
            no_action = True
            # Get results back from child processes where possible
            busy_proc_items = []
            while proc_items:
                if updater and updater.quit:
                    raise KeyboardInterrupt()
                proc, my_conn, terminate_time = proc_items.pop()
                if my_conn.poll():
                    host, port, result = my_conn.recv()
                    if result is None:
                        # Can't connect, ignore
                        wait_set.remove((host, port))
                    elif result == MSG_TIMEOUT:
                        # Connection timeout, leave in "wait_set"
                        pass
                    else:
                        # Connection success
                        results.append((host, port, result))
                        wait_set.remove((host, port))
                    if todo_set:
                        # Immediately give the child process something to do
                        host, port = todo_set.pop()
                        wait_set.add((host, port))
                        my_conn.send((host, port))
                        busy_proc_items.append(
                            (proc, my_conn, time() + INACTIVITY_TIMEOUT))
                    else:
                        # Or quit if there is nothing left to do
                        my_conn.send(MSG_QUIT)
                        my_conn.close()
                        proc.join()
                    no_action = False
                elif time() > terminate_time:
                    # Terminate child process if it is taking too long
                    proc.terminate()
                    proc.join()
                    no_action = False
                else:
                    busy_proc_items.append((proc, my_conn, terminate_time))
            proc_items += busy_proc_items
            # Create some child processes where necessary
            while len(proc_items) < max_procs and todo_set:
                if updater and updater.quit:
                    raise KeyboardInterrupt()
                my_conn, conn = Pipe()
                try:
                    proc = Process(
                        target=_scan_worker, args=(conn, timeout, my_uuid))
                except OSError:
                    # Die if unable to start any worker process.
                    # OK to wait and see if any worker process already running.
                    if not proc_items:
                        raise
                    if cylc.flags.debug:
                        traceback.print_exc()
                else:
                    proc.start()
                    host, port = todo_set.pop()
                    wait_set.add((host, port))
                    my_conn.send((host, port))
                    proc_items.append(
                        (proc, my_conn, time() + INACTIVITY_TIMEOUT))
                    no_action = False
            if no_action:
                sleep(SLEEP_INTERVAL)
    except KeyboardInterrupt:
        return []
    # Report host:port with no results
    if wait_set:
        print >> sys.stderr, (
            'WARNING, scan timed out, no result for the following:')
        for key in sorted(wait_set):
            print >> sys.stderr, '  %s:%s' % key
    return results
