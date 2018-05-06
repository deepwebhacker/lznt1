import struct
import sys
import copy
import ctypes
from hashlib import sha1

def _decompress_chunk(chunk):
    size = len(chunk)
    out = ''
    pow2 = 0x10
    while chunk:
        flags = ord(chunk[0])
        chunk = chunk[1:]
        for i in range(8):
            out_start = len(out)
            if not (flags >> i & 1):
                out += chunk[0]
                chunk = chunk[1:]
            else:
                flag = struct.unpack('<H', chunk[:2])[0]
                pos = len(out) - 1
                l_mask = 0xFFF
                o_shift = 12
                while pos >= 0x10:
                    l_mask >>= 1
                    o_shift -= 1
                    pos >>= 1

                length = (flag & l_mask) + 3
                offset = (flag >> o_shift) + 1

                if length >= offset:
                    tmp = out[-offset:] * (0xFFF / len(out[-offset:]) + 1)
                    out += tmp[:length]
                else:
                    out += out[-offset:-offset+length]
                chunk = chunk[2:]
            if len(chunk) == 0:
                break
    return out

def decompress(buf, length_check=True):
    out = ''
    while buf:
        header = struct.unpack('<H', buf[:2])[0]
        length = (header & 0xFFF) + 1
        if length_check and length > len(buf[2:]):
            raise ValueError('invalid chunk length')
        else:
            chunk = buf[2:2+length]
            if header & 0x8000:
                out += _decompress_chunk(chunk)
            else:
                out += chunk
        buf = buf[2+length:]
    return out

def _find(src, target, max_len):
    result_offset = 0
    result_length = 0
    for i in range(1, max_len):
        offset = src.rfind(target[:i])
        if offset == -1:
            break
        tmp_offset = len(src) - offset
        tmp_length = i
        if tmp_offset == tmp_length:
            tmp = src[offset:] * (0xFFF / len(src[offset:]) + 1)
            for j in range(i, max_len+1):
                offset = tmp.rfind(target[:j])
                if offset == -1:
                    break
                tmp_length = j
        if tmp_length > result_length:
            result_offset = tmp_offset
            result_length = tmp_length

    if result_length < 3:
        return 0, 0
    return result_offset, result_length

def _compress_chunk(chunk):
    blob = copy.copy(chunk)
    out = ''
    pow2 = 0x10
    l_mask3 = 0x1002
    o_shift = 12
    while len(blob) > 0:
        bits = 0
        tmp = ''
        for i in range(8):
            bits >>= 1
            while pow2 < (len(chunk) - len(blob)):
                pow2 <<= 1
                l_mask3 = (l_mask3 >> 1) + 1
                o_shift -= 1
            if len(blob) < l_mask3:
                max_len = len(blob)
            else:
                max_len = l_mask3

            offset, length = _find(chunk[:len(chunk) - len(blob)], blob, max_len)

            # try to find more compressed pattern
            offset2, length2 = _find(chunk[:len(chunk) - len(blob)+1], blob[1:], max_len)
            if length < length2+1:
                length = 0

            if length > 0:
                symbol = ((offset-1) << o_shift) | (length - 3)
                tmp += struct.pack('<H', symbol)
                bits |= 0x80 # set the highest bit
                blob = blob[length:]
            else:
                tmp += blob[0]
                blob = blob[1:]
            if len(blob) == 0:
                break

        out += struct.pack('B', bits >> (7 - i))
        out += tmp

    return out

def compress(buf, chunk_size=0x1000):
    out = ''
    while buf:
        chunk = buf[:chunk_size]
        compressed = _compress_chunk(chunk)
        if len(compressed) < len(chunk): # chunk is compressed
            flags = 0xB000
            header = struct.pack('<H' , flags|(len(compressed)-1))
            out += header + compressed
        else:
            flags = 0x3000
            header = struct.pack('<H' , flags|(len(chunk)-1))
            out += header + chunk
        buf = buf[chunk_size:]

    return out

def main():
    import argparse
    parser = argparse.ArgumentParser(description='LZNT1 tester (You must run this on Windows)')
    parser.add_argument("FILE", help="Specify a file for compression/decompression test")
    args = parser.parse_args()
    with open(args.FILE, 'rb') as fp:
        data = fp.read()
    #data = "Hello world!" * 800
    print('[*] input size = {} bytes, sha1 hash = {}'.format(len(data), sha1(data).hexdigest()))
    compressed1 = compress(data)
    decompressed11 = decompress(compressed1)

    buf_decompressed = ctypes.create_string_buffer(len(data)*2)
    final_size = ctypes.c_ulong(0)
    ctypes.windll.ntdll.RtlDecompressBuffer(2, buf_decompressed, ctypes.sizeof(buf_decompressed), ctypes.c_char_p(compressed1), len(compressed1), ctypes.byref(final_size))
    decompressed12 = buf_decompressed.raw[:final_size.value]

    buf_compressed = ctypes.create_string_buffer(len(data)*2)
    work_size = ctypes.c_ulong(0)
    work_frag_size = ctypes.c_ulong(0)
    ctypes.windll.ntdll.RtlGetCompressionWorkSpaceSize(2, ctypes.byref(work_size), ctypes.byref(work_frag_size))
    workspace = ctypes.create_string_buffer(work_size.value)
    final_size = ctypes.c_ulong(0)
    ctypes.windll.ntdll.RtlCompressBuffer(2, ctypes.c_char_p(data), len(data), buf_compressed, ctypes.sizeof(buf_compressed), 4096, ctypes.byref(final_size), workspace)
    compressed2 = buf_compressed.raw[:final_size.value]

    decompressed21 = decompress(compressed2)

    buf_decompressed = ctypes.create_string_buffer(len(data)*2)
    final_size = ctypes.c_ulong(0)
    ctypes.windll.ntdll.RtlDecompressBuffer(2, buf_decompressed, ctypes.sizeof(buf_decompressed), buf_compressed, ctypes.sizeof(buf_compressed), ctypes.byref(final_size))
    decompressed22 = buf_decompressed.raw[:final_size.value]

    print('[*] size of compressed1: {}'.format(len(compressed1)))
    print('[*] size of compressed2: {}'.format(len(compressed2)))
    print('[*] sha1 hash of compressed1: {}'.format(sha1(compressed1).hexdigest()))
    print('[*] sha1 hash of compressed2: {}'.format(sha1(compressed2).hexdigest()))
    print('[*] sha1 hash of decompressed11: {}'.format(sha1(decompressed11).hexdigest()))
    print('[*] sha1 hash of decompressed12: {}'.format(sha1(decompressed12).hexdigest()))
    print('[*] sha1 hash of decompressed21: {}'.format(sha1(decompressed21).hexdigest()))
    print('[*] sha1 hash of decompressed22: {}'.format(sha1(decompressed22).hexdigest()))

if __name__ == '__main__':
    main()