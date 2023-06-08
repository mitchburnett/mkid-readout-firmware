#!/usr/bin/env python3

import time
import logging
import numpy as np
from souk_mkid_readout import SoukMkidReadout

CONFFILE = '/home/casper/git/souk-firmware/software/control_sw/config/souk-single-pipeline-4x2.yaml'
ACCNUM = 0

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
    return dout


def main():
    r = SoukMkidReadout('localhost', configfile=CONFFILE, local=True)
    acc = r.accumulators[ACCNUM]
    addrs, nbytes = get_bram_addresses(acc)
    N=20
    acc._wait_for_acc(0.002)
    t0 = time.time()
    for i in range(N):
        #acc._wait_for_acc(0.002)
        fast_read_bram(acc, addrs, nbytes)
    t1 = time.time()
    print((t1-t0)/N * 1000)

if __name__ == '__main__':
    main()

