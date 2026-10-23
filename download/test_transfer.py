"""Offline transfer regression checks; uses a local HTTP range server only."""
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest

import dataset_tools as tool


DATA = bytes(range(256)) * 400


class RangeServer(BaseHTTPRequestHandler):
    def do_GET(self):
        start, end = map(int, self.headers['Range'].removeprefix('bytes=').split('-'))
        self.send_response(206)
        self.send_header('Content-Range', f'bytes {start}-{end}/{len(DATA)}')
        self.send_header('Content-Length', str(end - start + 1))
        self.end_headers()
        self.wfile.write(DATA[start:end + 1])

    def log_message(self, *args):
        pass


class TransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_chunk = tool.CHUNK
        tool.CHUNK = 16 * 1024  # Exercise multiple parallel ranges with a small fixture.
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), RangeServer)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        tool.CHUNK = cls.original_chunk

    def run_case(self, mode):
        with tempfile.TemporaryDirectory(prefix='dataset-transfer-') as temporary:
            root = Path(temporary)
            relative = 'chapter_03_dna/example.bin'
            row = {'path': relative, 'url': f'http://127.0.0.1:{self.server.server_port}/data',
                   'expected_bytes': len(DATA)}
            target = root / relative
            target.parent.mkdir()
            prefix = 1234
            if mode == 'sequential':
                target.with_name(target.name + '.part').write_bytes(DATA[:prefix])
            if mode == 'legacy_ranges':
                part = target.with_name(target.name + '.parallel.part')
                finished = prefix + tool.CHUNK
                part.write_bytes(DATA[:finished] + bytes(len(DATA) - finished))
                # Original progress schema contains only prefix/done.
                tool.write_json(target.with_name(target.name + '.ranges.json'),
                                {'prefix': prefix, 'done': [0]})
            # An old absolute path must resolve inside the new destination.
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps([{**row, 'path': 'X:/old/location/' + relative}]))
            rows = tool.records_from(manifest, root, ['3'])
            with redirect_stdout(io.StringIO()):
                tool.download(rows[0], root, workers=3, retries=1)
                self.assertEqual(target.read_bytes(), DATA)
                tool.download(rows[0], root, workers=3, retries=1)
            self.assertEqual(target.read_bytes(), DATA)

    def test_new_destination(self):
        self.run_case('new')

    def test_partial_prefix(self):
        self.run_case('sequential')

    def test_legacy_range_state(self):
        self.run_case('legacy_ranges')

    def test_destination_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            with tool.exclusive(Path(temporary)):
                with self.assertRaises(RuntimeError):
                    with tool.exclusive(Path(temporary)):
                        pass

    def test_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / 'bad.json'
            manifest.write_text(json.dumps([{'path': 'chapter_03_dna/../../escape',
                                            'url': 'http://localhost/', 'expected_bytes': 1}]))
            with self.assertRaises(ValueError):
                tool.records_from(manifest, root, ['3'])


if __name__ == '__main__':
    unittest.main()
