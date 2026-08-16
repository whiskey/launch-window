"""The setup portal: the DNS hijack, the network list, and the form.

The DNS responder is the part worth testing hard. It is forty bytes of packet
construction that decides whether a phone pops the setup page up by itself or
whether the owner has to know to type an IP address — and a malformed answer
fails in the least debuggable way available, by making the phone declare the
network broken and silently switch back to mobile data.
"""

import collections
import json
import math
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "firmware", "lib"))

import portal  # noqa: E402

ADDRESS = bytes((192, 168, 4, 1))


def query_packet(name=b"connectivitycheck.gstatic.com", txid=b"\xab\xcd"):
    labels = b"".join(
        bytes([len(part)]) + part for part in name.split(b".")
    ) + b"\x00"
    return (
        txid
        + b"\x01\x00"  # standard query, recursion desired
        + b"\x00\x01"  # one question
        + b"\x00\x00\x00\x00\x00\x00"
        + labels
        + b"\x00\x01\x00\x01"  # type A, class IN
    )


class TestDnsResponder(unittest.TestCase):
    def test_answers_with_our_address(self):
        response = portal.dns_response(query_packet(), ADDRESS)
        self.assertIsNotNone(response)
        self.assertTrue(response.endswith(ADDRESS))

    def test_transaction_id_is_echoed(self):
        """A resolver ignores an answer whose id does not match its question."""
        response = portal.dns_response(query_packet(txid=b"\x12\x34"), ADDRESS)
        self.assertEqual(response[:2], b"\x12\x34")

    def test_flags_say_response_no_error(self):
        response = portal.dns_response(query_packet(), ADDRESS)
        self.assertEqual(response[2:4], b"\x81\x80")

    def test_counts_are_one_question_one_answer(self):
        response = portal.dns_response(query_packet(), ADDRESS)
        self.assertEqual(response[4:6], b"\x00\x01")  # questions
        self.assertEqual(response[6:8], b"\x00\x01")  # answers
        self.assertEqual(response[8:12], b"\x00\x00\x00\x00")

    def test_question_is_echoed_verbatim(self):
        query = query_packet()
        response = portal.dns_response(query, ADDRESS)
        self.assertIn(query[12:], response)

    def test_answer_uses_a_compression_pointer_to_the_question(self):
        response = portal.dns_response(query_packet(), ADDRESS)
        answer = response[len(query_packet()) :]
        self.assertEqual(answer[:2], b"\xc0\x0c")
        self.assertEqual(answer[2:6], b"\x00\x01\x00\x01")  # type A, class IN
        self.assertEqual(answer[10:12], b"\x00\x04")  # rdlength

    def test_apple_and_android_probes_both_answered(self):
        for host in (b"captive.apple.com", b"connectivitycheck.gstatic.com"):
            self.assertIsNotNone(portal.dns_response(query_packet(host), ADDRESS))

    def test_a_response_is_not_answered_again(self):
        """Answering a response would make two beacons talk to each other forever."""
        packet = bytearray(query_packet())
        packet[2] |= 0x80
        self.assertIsNone(portal.dns_response(bytes(packet), ADDRESS))

    def test_multi_question_query_is_ignored(self):
        packet = bytearray(query_packet())
        packet[5] = 2
        self.assertIsNone(portal.dns_response(bytes(packet), ADDRESS))

    def test_truncated_packets_are_ignored_not_crashed_on(self):
        query = query_packet()
        for length in (0, 4, 11, 14, len(query) - 2):
            self.assertIsNone(portal.dns_response(query[:length], ADDRESS))


class TestSetupPassphrase(unittest.TestCase):
    """It protects the owner's home WiFi password in transit, so it must be
    random rather than derived from anything an attacker can enumerate."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = os.path.join(self.temp.name, "setup.json")

    def test_length_and_alphabet(self):
        passphrase = portal.generate_passphrase()
        self.assertEqual(len(passphrase), 12)
        self.assertTrue(all(c in portal.ALPHABET for c in passphrase))
        self.assertGreaterEqual(len(passphrase), 8)  # WPA2 minimum

    def test_ambiguous_characters_are_excluded(self):
        """0/O and 1/l/i are the ones misread off a phone screen at night."""
        for character in "01lIoO":
            self.assertNotIn(character, portal.ALPHABET)

    def test_draws_differ(self):
        draws = {portal.generate_passphrase() for _ in range(50)}
        self.assertEqual(len(draws), 50)

    def test_entropy_is_not_brute_forceable(self):
        """The rejected chip-ID scheme had 24 bits; this needs far more."""
        bits = portal.PASSPHRASE_LENGTH * math.log2(len(portal.ALPHABET))
        self.assertGreater(bits, 50)

    def test_distribution_is_unbiased(self):
        """Folding bytes with % would favour the first eight symbols."""
        counts = collections.Counter(
            "".join(portal.generate_passphrase(64) for _ in range(200))
        )
        self.assertEqual(len(counts), len(portal.ALPHABET))
        self.assertLess(max(counts.values()) / min(counts.values()), 1.5)

    def test_no_randomness_raises_rather_than_falling_back(self):
        """A predictable passphrase would be worse than no access point."""

        def broken(length):
            raise OSError("no entropy source")

        with self.assertRaises(OSError):
            portal.generate_passphrase(source=broken)

    def test_passphrase_is_remembered_across_boots(self):
        """A power blip must not change the network someone is standing at."""
        first = portal.ensure_passphrase(path=self.path)
        second = portal.ensure_passphrase(path=self.path)
        self.assertEqual(first, second)
        with open(self.path) as handle:
            self.assertEqual(json.load(handle)["passphrase"], first)

    def test_configured_passphrase_wins_and_is_not_persisted(self):
        self.assertEqual(
            portal.ensure_passphrase("chosen-by-hand", path=self.path), "chosen-by-hand"
        )
        self.assertFalse(os.path.exists(self.path))

    def test_constructing_a_portal_writes_nothing(self):
        """Generating a passphrase touches flash; a constructor should not."""
        instance = portal.Portal()
        self.assertIsNone(instance.password)


class FakeStation:
    def __init__(self, results):
        self.results = results

    def scan(self):
        return self.results


class TestNetworkScan(unittest.TestCase):
    def test_strongest_first_and_deduplicated(self):
        """Mesh networks appear once per access point; the list should not."""
        station = FakeStation([
            (b"ExampleNet", b"", 11, -81, 5, False),
            (b"ExampleNet", b"", 6, -38, 5, False),
            (b"OtherNet", b"", 1, -61, 5, False),
        ])
        self.assertEqual(
            portal.scan_networks(station), [("ExampleNet", -38), ("OtherNet", -61)]
        )

    def test_hidden_networks_are_dropped(self):
        """An empty SSID cannot be selected, so listing it only confuses."""
        station = FakeStation([(b"", b"", 6, -50, 5, False), (b"ExampleNet", b"", 6, -40, 5, False)])
        self.assertEqual(portal.scan_networks(station), [("ExampleNet", -40)])

    def test_a_failing_radio_yields_an_empty_list(self):
        class Broken:
            def scan(self):
                raise OSError("radio busy")

        self.assertEqual(portal.scan_networks(Broken()), [])


class TestSetupPage(unittest.TestCase):
    def render(self, networks, message=None):
        return "".join(portal.setup_page(networks, message))

    def test_lists_the_networks(self):
        html = self.render([("ExampleNet", -38), ("OtherNet", -61)])
        self.assertIn("<option", html)
        self.assertIn("ExampleNet", html)
        self.assertIn("-38 dBm", html)

    def test_falls_back_to_a_text_field_when_nothing_is_visible(self):
        html = self.render([])
        self.assertIn('name="ssid"', html)
        self.assertNotIn("<option", html)

    def test_ssid_is_escaped(self):
        """An SSID is attacker-controlled text from the air."""
        html = self.render([('<script>alert("x")</script>', -40)])
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_posts_to_save(self):
        html = self.render([("ExampleNet", -38)])
        self.assertIn('method="POST"', html)
        self.assertIn('action="/save"', html)

    def test_saved_page_names_the_network(self):
        self.assertIn("ExampleNet", portal.saved_page("ExampleNet"))


class TestSaveRoute(unittest.TestCase):
    class Request:
        def __init__(self, method="POST", form=None):
            self.method = method
            self._form = form or {}

        def form(self):
            return self._form

    def portal_with_capture(self):
        captured = {}
        instance = portal.Portal(on_save=lambda s, p: captured.update(ssid=s, password=p))
        instance.networks = [("ExampleNet", -38)]
        return instance, captured

    def test_saves_credentials(self):
        instance, captured = self.portal_with_capture()
        status, _, _ = instance.routes()["/save"](
            self.Request(form={"ssid": "ExampleNet", "password": "hunter2"})
        )
        self.assertEqual(status, 200)
        self.assertEqual(captured, {"ssid": "ExampleNet", "password": "hunter2"})

    def test_empty_ssid_is_rejected_without_saving(self):
        instance, captured = self.portal_with_capture()
        status, _, _ = instance.routes()["/save"](self.Request(form={"ssid": "  "}))
        self.assertEqual(status, 400)
        self.assertEqual(captured, {})

    def test_get_is_not_allowed(self):
        instance, captured = self.portal_with_capture()
        status, _, _ = instance.routes()["/save"](self.Request(method="GET"))
        self.assertEqual(status, 405)
        self.assertEqual(captured, {})

    def test_an_empty_password_is_allowed(self):
        """Open networks exist, and refusing them would be a guess about the user."""
        instance, captured = self.portal_with_capture()
        status, _, _ = instance.routes()["/save"](
            self.Request(form={"ssid": "Freifunk", "password": ""})
        )
        self.assertEqual(status, 200)
        self.assertEqual(captured["password"], "")


if __name__ == "__main__":
    unittest.main()
