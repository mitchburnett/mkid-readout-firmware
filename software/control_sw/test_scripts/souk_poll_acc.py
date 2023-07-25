#!/usr/bin/env python3

import time
import logging
import numpy as np
from mkid_readout import MkidReadout

CONFFILE = '/home/casper/git/souk-firmware/software/control_sw/config/souk-single-pipeline-4x2.yaml'
ACCNUM = 0
WAIT_FOR_IP_ADDR = True
NLOOP = 20

def get_bram_addresses(acc):
    addrs = []
    nbytes = acc._n_serial_chans * np.dtype(acc._dtype).itemsize
    if acc._is_complex:
        nbytes *= 2
    for i in range(acc._n_parallel_chans):
        ramname = f'{acc.prefix}dout{i}'
        addrs += [acc.host.transport._get_device_address(ramname)]
    for i in range(1,acc._n_parallel_chans):
        assert addrs[i] == addrs[i-1] + nbytes
    return addrs, nbytes

def fast_read_bram(acc, addrs, nbytes):
    """
    Read RAM containing accumulated spectra.
    
    :return: Array of complex valued data, in int32 format. Array
        dimensions are [FREQUENCY CHANNEL].
    :rtype: numpy.array
    """
    nbranch = len(addrs)
    base_addr = addrs[0]
    dout = np.zeros(acc.n_chans, dtype='>i8')
    start_acc_cnt = acc.get_acc_cnt()
    for i, addr in enumerate(addrs):
        raw = acc.host.transport.axil_mm[addr:addr + nbytes]
        dout[i::nbranch] = np.frombuffer(raw, dtype='>i8')
    stop_acc_cnt = acc.get_acc_cnt()
    if start_acc_cnt != stop_acc_cnt:
        acc.logger.warning('Accumulation counter changed while reading data!')
        return None
    return dout

def wait_non_zero_ip(acc, poll_time_s=5):
    loop_cnt = 0
    while True:
        ip = acc.get_dest_ip()
        if ip == '0.0.0.0':
            time.sleep(poll_time_s)
            ip = acc.get_dest_ip()
        else:
            if loop_cnt > 0:
                print('Got non-zero IP')
            break
        loop_cnt += 1
    return

def main():
    r = MkidReadout('localhost', configfile=CONFFILE, local=True)
    acc = r.accumulators[ACCNUM]
    addrs, nbytes = get_bram_addresses(acc)
    acc._wait_for_acc(0.00005)
    t0 = time.time()
    err_cnt = 0
    loop_cnt = 0
    times = []
    while True:
        if WAIT_FOR_IP_ADDR:
            wait_non_zero_ip(acc)
        acc._wait_for_acc(0.00005)
        tt0 = time.time()
        x = fast_read_bram(acc, addrs, nbytes)
        if x is None:
            err_cnt += 1
        tt1 = time.time()
        times += [tt1 - tt0]
        loop_cnt += 1
        if loop_cnt == NLOOP:
            break
    t1 = time.time()
    avg_read_ms = np.mean(times)*1000
    max_read_ms = np.max(times)*1000
    avg_loop_ms = (t1-t0)/loop_cnt * 1000
    print(f'Average read time: {avg_read_ms}')
    print(f'Max read time: {max_read_ms}')
    print(f'Average loop time: {avg_loop_ms}')
    print(f'Number of too slow reads: {err_cnt}')

if __name__ == '__main__':
    main()

