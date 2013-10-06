#!/usr/bin/env python
#-------------------------------------------------------------------
# Filename: libgse2.py
#  Purpose: Python wrapper for gse_functions of Stefan Stange
#   Author: Moritz Beyreuther
#    Email: moritz.beyreuther@geophysik.uni-muenchen.de
#
# Copyright (C) 2008-2012 Moritz Beyreuther
#---------------------------------------------------------------------
"""
Lowlevel module internally used for handling GSE2 files

Python wrappers for gse_functions - The GSE2 library of Stefan Stange.
Currently CM6 compressed GSE2 files are supported, this should be
sufficient for most cases. Gse_functions is written in C and
interfaced via python-ctypes.

See: http://www.orfeus-eu.org/Software/softwarelib.html#gse

:copyright:
    The ObsPy Development Team (devs@obspy.org)
:license:
    GNU Lesser General Public License, Version 3
    (http://www.gnu.org/copyleft/lesser.html)
"""

from distutils import sysconfig
from obspy import UTCDateTime
#XXX: we might be able to remove c_file_p, check
#from obspy.core.util import c_file_p
import ctypes as C
import doctest
import numpy as np
import os
import platform
import warnings

count = 0

# Import shared libgse2
# create library names
lib_names = [
    # platform specific library name
    'libgse2_%s_%s_py%s' % (
        platform.system(), platform.architecture()[0],
        ''.join([str(i) for i in platform.python_version_tuple()[:2]])),
    # fallback for pre-packaged libraries
    'libgse2']
# get default file extension for shared objects
lib_extension, = sysconfig.get_config_vars('SO')
# initialize library
for lib_name in lib_names:
    try:
        clibgse2 = C.CDLL(os.path.join(os.path.dirname(__file__), os.pardir,
                                       'lib', lib_name + lib_extension))
        break
    except Exception, e:
        pass
else:
    msg = 'Could not load shared library for obspy.gse2.\n\n %s' % (e)
    raise ImportError(msg)


class ChksumError(StandardError):
    """
    Exception type for mismatching checksums
    """
    pass


class GSEUtiError(StandardError):
    """
    Exception type for other errors in GSE_UTI
    """
    pass


# gse_functions decomp_6b_buffer
clibgse2.decomp_6b_buffer.argtypes = [
    C.c_int,
    np.ctypeslib.ndpointer(dtype='int32', ndim=1, flags='C_CONTIGUOUS'),
    C.CFUNCTYPE(C.c_char_p, C.POINTER(C.c_char), C.c_void_p), C.c_void_p]
clibgse2.decomp_6b_buffer.restype = C.c_int

# gse_functions rem_2nd_diff
clibgse2.rem_2nd_diff.argtypes = [
    np.ctypeslib.ndpointer(dtype='int32', ndim=1, flags='C_CONTIGUOUS'),
    C.c_int]
clibgse2.rem_2nd_diff.restype = C.c_int

# gse_functions check_sum
clibgse2.check_sum.argtypes = [
    np.ctypeslib.ndpointer(dtype='int32', ndim=1, flags='C_CONTIGUOUS'),
    C.c_int, C.c_int32]
clibgse2.check_sum.restype = C.c_int  # do not know why not C.c_int32

# gse_functions diff_2nd
clibgse2.diff_2nd.argtypes = [
    np.ctypeslib.ndpointer(dtype='int32', ndim=1, flags='C_CONTIGUOUS'),
    C.c_int, C.c_int]
clibgse2.diff_2nd.restype = C.c_void_p

# gse_functions compress_6b_buffer
clibgse2.compress_6b_buffer.argtypes = [
    np.ctypeslib.ndpointer(dtype='int32', ndim=1, flags='C_CONTIGUOUS'),
    C.c_int,
    C.CFUNCTYPE(C.c_int, C.c_char)]
clibgse2.compress_6b_buffer.restype = C.c_int


def isGse2(f):
    """
    Checks whether a file is GSE2 or not. Returns True or False.

    :type f : file pointer
    :param f : file pointer to start of GSE2 file to be checked.
    """
    pos = f.tell()
    widi = f.read(4)
    f.seek(pos)
    if widi != 'WID2':
        raise TypeError("File is not in GSE2 format")


def readHeader(fh):
    """
    Reads GSE2 header from file pointer and returns it as dictionary.

    The method searches for the next available WID2 field beginning from the
    current file position.
    """
    # example header of tests/data/loc_RNON20040609200559.z:
    #
    # WID2 2009/05/18 06:47:20.255 RNHA  EHN      CM6      750  200.000000
    # 0123456789012345678901234567890123456789012345678901234567890123456789
    # 0         10        20        30        40        50        60
    #  9.49e-02   1.000    M24  -1.0 -0.0
    # 0123456789012345678901234567890123456789012345678901234567890123456789
    # 70        80        90        100
    #
    # search for WID field
    while True:
        line = fh.readline()
        if line.startswith('WID2'):
            # valid GSE2 header
            break
        if line == '':
            raise EOFError
    # fetch header
    header, date = {}, {}
    header['gse2'] = {}
    # starttime
    for key, start, stop in [
        ('year', 5, 9),
        ('month', 10, 12),
        ('day', 13, 15),
        ('hour', 16, 18),
        ('minute', 19, 21),
        ('second', 22, 24),
        ('microsecond', 25, 28),
            ]:
        date[key] = int(line[slice(start, stop)])
    date['microsecond'] *= 1000
    header['starttime'] = UTCDateTime(**date)
    # remaining fields
    _str = lambda s: s.strip()
    for key, start, stop, fct in [
        ('station', 29, 34, _str),
        ('channel', 35, 38, lambda s: s.strip().upper()),
        ('gse2.auxid', 39, 43, _str),
        ('gse2.datatype', 44, 48, _str),
        ('npts', 48, 56, int),
        ('sampling_rate', 57, 68, float),
        ('calib', 69, 79, float),
        ('gse2.calper', 80, 87, float),
        ('gse2.instype', 88, 94, _str),
        ('gse2.hang', 95, 100, float),
        ('gse2.vang', 101, 105, float),
            ]:
        value = fct(line[slice(start, stop)])
        if 'gse2.' in key:
            header['gse2'][key[5:]] = value
        else:
            header[key] = value
    return header


def writeHeader(f, headdict):
    """
    Rewriting the write_header Function of gse_functions.c

    Different operating systems are delivering different output for the
    scientific format of floats (fprinf libc6). Here we ensure to deliver
    in a for GSE2 valid format independent of the OS. For speed issues we
    simple cut any number ending with E+0XX or E-0XX down to E+XX or E-XX.
    This fails for numbers XX>99, but should not occur.

    :type f: File pointer
    :param f: File pointer to to GSE2 file to write
    :type headdict: obspy header
    :param headdict: obspy header
    """
    calib = "%10.2e" % (headdict['calib'])
    date = headdict['starttime']
    fmt = "WID2 %4d/%02d/%02d %02d:%02d:%06.3f %-5s %-3s %-4s %-3s %8d " + \
          "%11.6f %s %7.3f %-6s %5.1f %4.1f\n"
    f.write(fmt % (
            date.year,
            date.month,
            date.day,
            date.hour,
            date.minute,
            date.second + date.microsecond / 1e6,
            headdict['station'],
            headdict['channel'],
            headdict['gse2']['auxid'],
            headdict['gse2']['datatype'],
            headdict['npts'],
            headdict['sampling_rate'],
            calib,
            headdict['gse2']['calper'],
            headdict['gse2']['instype'],
            headdict['gse2']['hang'],
            headdict['gse2']['vang'])
            )


def uncompress_CM6(f, n_samps):
    """
    Uncompress n_samps of CM6 compressed data from file pointer fp.

    :type f: File Pointer
    :param f: File Pointer
    :type n_samps: Int
    :param n_samps: Number of samples
    """
    def read83(cbuf, vptr):
        line = f.readline()
        if line == '':
            return None
        # avoid buffer overflow through clipping to 82
        sb = C.create_string_buffer(line[:82])
        # copy also null termination "\0", that is max 83 bytes
        C.memmove(C.addressof(cbuf.contents), C.addressof(sb), len(line) + 1)
        return C.addressof(sb)

    cread83 = C.CFUNCTYPE(C.c_char_p, C.POINTER(C.c_char), C.c_void_p)(read83)
    if n_samps == 0:
        data = np.empty(0, dtype='int32')
    else:
        # aborts with segmentation fault when n_samps == 0
        data = np.empty(n_samps, dtype='int32')
        n = clibgse2.decomp_6b_buffer(n_samps, data, cread83, None)
        if n != n_samps:
            raise GSEUtiError("Mismatching length in lib.decomp_6b")
        clibgse2.rem_2nd_diff(data, n_samps)
    return data


def verifyChecksum(fh, data, version=2):
    """
    Calculate checksum from data, as in gse_driver.c line 60

    :type fh: File Pointer
    :param fh: File Pointer
    :type version: Int
    :param version: GSE version, either 1 or 2, defaults to 2.
    """
    chksum_data = clibgse2.check_sum(data, len(data), C.c_int32(0))
    # find checksum within file
    buf = fh.readline()
    chksum_file = 0
    CHK_LINE = 'CHK%d' % version
    while buf:
        if buf.startswith(CHK_LINE):
            chksum_file = int(buf.strip().split()[1])
            break
        buf = fh.readline()
    if chksum_data != chksum_file:
        # 2012-02-12, should be deleted in a year from now
        if abs(chksum_data) == abs(chksum_file):
            msg = "Checksum differs only in absolute value. If this file " + \
                "was written with ObsPy GSE2, this is due to a bug in " + \
                "the obspy.gse2.write routine (resolved with [3431]), " + \
                "and thus this message can be safely ignored."
            warnings.warn(msg, UserWarning)
            return
        msg = "Mismatching checksums, CHK %d != CHK %d"
        raise ChksumError(msg % (chksum_data, chksum_file))
    return


def read(f, verify_chksum=True):
    """
    Read GSE2 file and return header and data.

    Currently supports only CM6 compressed GSE2 files, this should be
    sufficient for most cases. Data are in circular frequency counts, for
    correction of calper multiply by 2PI and calper: data * 2 * pi *
    header['calper'].

    :type f: File Pointer
    :param f: Open file pointer of GSE2 file to read, opened in binary mode,
              e.g. f = open('myfile','rb')
    :type test_chksum: Bool
    :param verify_chksum: If True verify Checksum and raise Exception if it
                          is not correct
    :rtype: Dictionary, Numpy.ndarray int32
    :return: Header entries and data as numpy.ndarray of type int32.
    """
    headdict = readHeader(f)
    data = uncompress_CM6(f, headdict['npts'])
    # test checksum only if enabled
    if verify_chksum:
        verifyChecksum(f, data, version=2)
    return headdict, data


def write(headdict, data, f, inplace=False):
    """
    Write GSE2 file, given the header and data.

    Currently supports only CM6 compressed GSE2 files, this should be
    sufficient for most cases. Data are in circular frequency counts, for
    correction of calper multiply by 2PI and calper:
    data * 2 * pi * header['calper'].

    Warning: The data are actually compressed in place for performance
    issues, if you still want to use the data afterwards use data.copy()

    :note: headdict dictionary entries C{'datatype', 'n_samps',
           'samp_rate'} are absolutely necessary
    :type data: numpy.ndarray dtype int32
    :param data: Contains the data.
    :type f: File Pointer
    :param f: Open file pointer of GSE2 file to write, opened in binary
              mode, e.g. f = open('myfile','wb')
    :type inplace: Bool
    :param inplace: If True, do compression not on a copy of the data but
                    on the data itself --- note this will change the data
                    values and make them therefore unusable
    :type headdict: Dictionary
    :param headdict: Obspy Header
    """
    n = len(data)
    #
    chksum = clibgse2.check_sum(data, n, C.c_int32(0))
    # Maximum values above 2^26 will result in corrupted/wrong data!
    # do this after chksum as chksum does the type checking for numpy array
    # for you
    if not inplace:
        data = data.copy()
    if data.max() > 2 ** 26:
        raise OverflowError("Compression Error, data must be less equal 2^26")
    clibgse2.diff_2nd(data, n, 0)
    #XXX: extract as extra function
    global count
    count = 0
    # 4 character bytes per 32 bit integer
    carr = np.zeros(n * 4, dtype='c')

    def writer(char):
        global count
        carr[count] = char
        count += 1
        return 0
    cwriter = C.CFUNCTYPE(C.c_int, C.c_char)(writer)
    ierr = clibgse2.compress_6b_buffer(data, n, cwriter)
    assert ierr == 0, "Error status after compression is NOT 0 but %d" % ierr
    # set some defaults if not available and convert header entries
    headdict.setdefault('calib', 1.0)
    headdict.setdefault('gse2', {})
    headdict['gse2'].setdefault('auxid', '')
    headdict['gse2'].setdefault('datatype', 'CM6')
    headdict['gse2'].setdefault('calper', 1.0)
    headdict['gse2'].setdefault('instype', '')
    headdict['gse2'].setdefault('hang', -1)
    headdict['gse2'].setdefault('vang', -1)
    # This is the actual function where the header is written. It avoids
    # the different format of 10.4e with fprintf on Windows and Linux.
    # For further details, see the __doc__ of writeHeader
    writeHeader(f, headdict)
    f.write("DAT2\n")
    for line in carr[:(count // 80 + 1) * 80].view('|S80'):
        f.write("%s\n" % line)
    f.write("CHK2 %8ld\n\n" % chksum)

if __name__ == '__main__':
    doctest.testmod(exclude_empty=True)
