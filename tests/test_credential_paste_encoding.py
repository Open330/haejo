"""Exercise actual Swift Unicode chunking, including literal identity."""
import json
import subprocess
import sys
import unittest
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'darwin', 'Swift Unicode event chunking')
class CredentialPasteEncoding(unittest.TestCase):
    def test_exact_code_units_and_bounded_scalar_chunks(self):
        source = (ROOT / 'helper/TactoHelper.swift').read_text()
        encoder = source[source.index('func credentialUnicodeChunks('):source.index('// Explicit credential paste:')]
        values = ['ASCII-47!', '테스트🔐', unicodedata.normalize('NFD', '테스트🔐'),
                  'e\u0301', 'a\u0315\u0300', 'line\nnext', '', '\U0001f512',
                  'a' * 63 + '🔐' + 'e\u0301' * 100, '가'.join(['x'] * 1000)]
        code = 'import Foundation\n' + encoder + """
let values=try! JSONSerialization.jsonObject(with:FileHandle.standardInput.readDataToEndOfFile()) as! [String]
var results:[[String:Any]]=[]
for value in values {
    let chunks=credentialUnicodeChunks(value)
    results.append(["exact":Array(chunks.joined().utf16)==Array(value.utf16),
                    "chunks":chunks,"lengths":chunks.map {$0.utf16.count}])
}
print(String(data:try! JSONSerialization.data(withJSONObject:results),encoding:.utf8)!)
"""
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / 'encoding.swift'
            script.write_text(code)
            run = subprocess.run(['swift', str(script)], input=json.dumps(values),
                                 capture_output=True, text=True, timeout=45)
        self.assertEqual(0, run.returncode, run.stderr)
        results = json.loads(run.stdout)
        self.assertEqual(len(values), len(results))
        for value, result in zip(values, results):
            self.assertTrue(result['exact'])
            self.assertEqual(value, ''.join(result['chunks']))
            self.assertTrue(all(0 < length <= 64 for length in result['lengths']))
            self.assertTrue(all(not 0xD800 <= ord(c) <= 0xDFFF for chunk in result['chunks'] for c in chunk))
