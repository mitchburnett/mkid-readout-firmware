import struct
import numpy as np
from .block import Block

class Mixer(Block):
    """
    Instantiate a control interface for a Channel Reorder block.

    :param host: CasperFpga interface for host.
    :type host: casperfpga.CasperFpga

    :param name: Name of block in Simulink hierarchy.
    :type name: str

    :param logger: Logger instance to which log messages should be emitted.
    :type logger: logging.Logger

    :param n_chans: Number of channels this block processes
    :type n_chans: int

    :param n_parallel_chans: Number of channels this block processes in parallel
    :type n_parallel_chans: int

    :param phase_bp: Number of phase fractional bits
    :type phase_bp: int

    """
    def __init__(self, host, name,
            n_chans=4096,
            n_parallel_chans=4,
            phase_bp=31,
            phase_offset_bp=31,
            n_scale_bits=8,
            logger=None):
        super(Mixer, self).__init__(host, name, logger)
        self.n_chans = n_chans
        assert n_chans % n_parallel_chans == 0
        self._n_parallel_chans = n_parallel_chans
        self._n_serial_chans = n_chans // n_parallel_chans
        self._phase_bp = phase_bp
        self._phase_offset_bp = phase_offset_bp
        self._n_scale_bits = n_scale_bits

    def enable_power_mode(self):
        """
        Instead of applying a phase rotation to the data streams,
        calculate their power.
        """
        self.write_int('power_en', 1)

    def disable_power_mode(self):
        """
        Use phase rotation, rather than power.
        """
        self.write_int('power_en', 0)

    def is_power_mode(self):
        """
        Get the current block mode.

        :return: True if the block is calculating power, False if it is
            applying phase rotation.
        :rtype: bool
        """
        return bool(self.read_int('power_en'))

    def set_chan_freq(self, chan, freq_offset_hz=None, phase_offset=0, sample_rate_mhz=2500):
        """
        Set the frequency of output channel `chan`.

        :param chan: The channel index to which this phase-rate should be applied
        :type chan: int

        :param freq_offset_hz: The frequency offset, in Hz, from the channel center.
            If None, disable this oscillator.
        :type freq_offset_hz: float

        :param phase_offset: The phase offset at which this oscillator should start
            in units of radians.
        :type phase: float

        :param sample_rate_mhz: DAC sample rate, in MHz
        :type sample_rate_mhz: float

        """
        fft_period_s = self.n_chans / (sample_rate_mhz * 1e6) # seconds
        fft_rbw_hz = 1./fft_period_s # FFT channel width, Hz
        phase_step = freq_offset_hz / fft_rbw_hz * 2 * np.pi
        self.set_phase_step(chan, phase=phase_step, phase_offset=phase_offset)

    def add_freq(self, freq_hz, phase_offset=0, sample_rate_mhz=2500, scaling=1.0):
        """
        Add a frequency to the output.

        :param freq_hz: The frequency, in Hz, to emit.
        :type freq_offset_hz: float

        :param phase_offset: The phase offset at which this oscillator should start
            in units of radians.
        :type phase: float

        :param sample_rate_mhz: DAC sample rate, in MHz
        :type sample_rate_mhz: float

        :param scaling: optional scaling (<=1) to apply to the output tone amplitude.
        :type scaling: float

        """
        fft_period_s = self.n_chans / (sample_rate_mhz * 1e6) # seconds
        fft_rbw_hz = 1./fft_period_s # FFT channel width, Hz
        # Split target frequency into FFT bin number and offset
        chan = int(round(freq_hz / fft_rbw_hz))
        chan_offset_hz = freq_hz - (chan * fft_rbw_hz)
        self._info(f"Placing tone in channel {chan} with an offset of {chan_offset_hz} Hz")
        self.set_chan_freq(chan, freq_offset_hz=chan_offset_hz, phase_offset=phase_offset, sample_rate_mhz=sample_rate_mhz)

    def set_amplitude_scale(self, chan, scale=1.0):
        """
        Apply an amplitude scaling <=1 to an output channel.

        :param chan: The channel index to which this phase-rate should be applied
        :type chan: int

        :param scaling: optional scaling (<=1) to apply to the output tone amplitude.
        :type scaling: float
        """
        p = chan % self._n_parallel_chans  # Parallel stream number
        s = chan // self._n_parallel_chans # Serial channel position
        regname = f'lo{p}_phase_scale'
        assert scale > 0
        # convert to uint
        scale *= 2**self._n_scale_bits
        scale = round(scale)
        # saturate
        scale_max = 2**self._n_scale_bits - 1
        if scale > scale_max:
            scale = scale_max
        self.write_int(regname, scale, word_offset=s)

    def set_phase_step(self, chan, phase=None, phase_offset=0.0):
        """
        Set the phase increment to apply on each successive sample for
        channel `chan`.

        :param chan: The channel index to which this phase-rate should be applied
        :type chan: int

        :param phase: The phase increment to be added each successive sample
            in units of radians. If None, disable this oscillator.
        :type phase: float

        :param phase_offset: The phase offset at which this oscillator should start
            in units of radians.
        :type phase: float

        """
        p = chan % self._n_parallel_chans  # Parallel stream number
        s = chan // self._n_parallel_chans # Serial channel position
        inc_regname = f'lo{p}_phase_inc'
        offset_regname = f'lo{p}_phase_offset'
        if phase is None:
            enable_bit = 0
            phase_scaled = 0
        else:
            enable_bit = 1
            # phase written to register should be +/-1 and in units of pi
            phase_scaled = phase / np.pi
            phase_scaled = ((phase_scaled + 1) % 2) - 1
            phase_scaled = int(phase_scaled * 2**self._phase_bp)
        # Mask top bit for enable
        if phase_scaled < 0:
            phase_scaled_uint = phase_scaled + 2**(self._phase_bp + 1)
        else:
            phase_scaled_uint = phase_scaled
        self.write_int(inc_regname, (enable_bit << 31) + phase_scaled_uint, word_offset=s)
        phase_offset_scaled = phase_offset / np.pi
        phase_offset_scaled = ((phase_offset_scaled + 1) % 2) - 1
        phase_offset_scaled = int(phase_offset_scaled * 2**self._phase_offset_bp)
        self.write_int(offset_regname, phase_offset_scaled, word_offset=s)
 
    def get_phase_offset(self, chan):
        """
        Get the currently loaded phase increment being applied to channel `chan`.

        :return: (phase_step, phase_offset, enabled)
            A tuple containing the phase increment (in radians) being applied
            to channel `chan` on each successive sample, the start phase in radians,
            and a boolean indicating the channel is enabled.
        :rtype: float
        """
        p = chan % self._n_parallel_chans  # Parallel stream number
        s = chan // self._n_parallel_chans # Serial channel position
        inc_regname = f'lo{p}_phase_inc'
        offset_regname = f'lo{p}_phase_offset'
        # Read increment reg and mask off enable bit
        inc_val = self.read_uint(inc_regname, word_offset=s)
        enabled = bool(inc_val >> 31)
        phase_step = inc_val & (2**31 - 1)
        if phase_step > 2**30:
            phase_step -= 2**31
        phase_step = (phase_step / (2**self._phase_bp)) * np.pi
        # Now phase offset
        phase_offset = self.read_int(offset_regname, word_offset=s)
        phase_offset = (phase_offset / (2**self._phase_offset_bp)) * np.pi
        return phase_step, phase_offset, enable
        

    def initialize(self, read_only=False):
        """
        Initialize the block.

        :param read_only: If True, this method is a no-op. If False,
            set this block to phase rotate mode, but initialize 
            with each channel having zero phase increment.
        :type read_only: bool
        """
        if read_only:
            pass
        else:
            self.disable_power_mode()
            for i in range(self.n_chans):
                self.set_phase_step(i, phase=None)
                self.set_amplitude_scale(i, 1)
