import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('stock_records', Path(__file__).parents[1] / 'build/inspect-stock-records.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def record(kind, payload):
    header = bytearray(80)
    header[:12] = module.ROM_ID
    header[14:16] = module.checksum(payload).to_bytes(2, 'big')
    header[44:48] = len(payload).to_bytes(4, 'big')
    header[70] = kind
    header[78:80] = (0xffff-module.checksum(header)).to_bytes(2, 'big')
    return bytes(header)+payload


def fixture():
    return b'MH01'+bytes(12)+b''.join(record(kind, b'example'+bytes([kind])) for kind, _ in module.RECORDS)+bytes(256)


class StockRecordTests(unittest.TestCase):
    def test_checksum_carry_and_vendor_odd_byte_padding(self):
        self.assertEqual(module.checksum(bytes.fromhex('ffff0001')), 1)
        self.assertEqual(module.checksum(bytes.fromhex('01')), 0x01ff)
        self.assertEqual(module.checksum(bytes.fromhex('123456')), 0x6933)

    def test_valid_inner_records_do_not_authorize_flashing_or_claim_authenticity(self):
        result = module.inspect(fixture())
        self.assertEqual(len(result['records']), 3)
        for name in ('flashable', 'authenticity_verified', 'trailer_validated',
                     'outer_container_validated', 'board_compatibility_verified', 'flash_layout_verified'):
            self.assertIs(result[name], False)

    def test_payload_corruption_rejected(self):
        data = bytearray(fixture()); data[96] ^= 1
        with self.assertRaisesRegex(ValueError, 'payload checksum'):
            module.inspect(data)

    def test_header_corruption_rejected(self):
        data = bytearray(fixture()); data[48] ^= 1
        with self.assertRaisesRegex(ValueError, 'header checksum'):
            module.inspect(data)

    def test_valid_checksum_on_wrong_kind_is_rejected(self):
        data = b'MH01'+bytes(12)+record(4, b'example')+bytes(256)
        with self.assertRaisesRegex(ValueError, 'kind/order'):
            module.inspect(data)

    def test_different_rom_id_is_rejected_even_with_valid_checksum(self):
        data = bytearray(fixture()); data[16] = ord('X');data[94:96] = bytes(2)
        data[94:96] = (0xffff-module.checksum(data[16:96])).to_bytes(2, 'big')
        with self.assertRaisesRegex(ValueError, 'ROM ID'):
            module.inspect(data)

    def test_truncated_and_extra_data_rejected(self):
        for data in (fixture()[:40], fixture()[:100], fixture()[:-1], fixture()+b'x'):
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                module.inspect(data)

    def test_checksum_cannot_authenticate_a_modified_trailer(self):
        data = bytearray(fixture()); data[-1] = 1
        self.assertIs(module.inspect(data)['trailer_validated'], False)


if __name__ == '__main__':
    unittest.main()
