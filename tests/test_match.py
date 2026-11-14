"""Tests for reading a SerpAPI response: python -m unittest discover tests"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tracker.collector import match_domain, parse_check, result_host, result_url


class ResultHost(unittest.TestCase):
    def test_plain_link(self):
        self.assertEqual(result_host({"link": "https://www.yelp.com/search?x=1"}), "www.yelp.com")

    def test_google_redirect_uses_displayed_link(self):
        item = {"link": "https://www.google.com/goto?url=CAES",
                "displayed_link": "https://www.yelp.com › search"}
        self.assertEqual(result_host(item), "www.yelp.com")

    def test_relative_redirect_uses_displayed_link(self):
        item = {"link": "/goto?url=CAES", "displayed_link": "https://austinfamilydds.com"}
        self.assertEqual(result_host(item), "austinfamilydds.com")

    def test_displayed_link_without_scheme(self):
        item = {"link": "/goto?url=CAES", "displayed_link": "example.com › a › b"}
        self.assertEqual(result_host(item), "example.com")

    def test_redirect_without_site_address_is_unknown(self):
        # social results show "610+ followers" instead of an address
        item = {"link": "/goto?url=CAES", "displayed_link": "610+ followers",
                "source": "Facebook · Austin Family Dentist"}
        self.assertNotIn("facebook", result_host(item))
        self.assertIsNone(match_domain([item], "facebook.com"))

    def test_missing_fields(self):
        self.assertEqual(result_host({}), "")
        self.assertEqual(result_host({"link": None, "displayed_link": None}), "")


class MatchDomain(unittest.TestCase):
    ORGANIC = [
        {"position": 1, "link": "https://www.google.com/goto?url=A",
         "displayed_link": "https://notyelp.com › x", "title": "t1"},
        {"position": 2, "link": "/goto?url=B",
         "displayed_link": "https://www.yelp.com › ... › Dentists", "title": "t2", "snippet": "s" * 400},
        {"position": 3, "link": "https://m.yelp.com/biz/x", "title": "t3"},
    ]

    def test_subdomain_matches_and_lookalike_does_not(self):
        self.assertEqual(match_domain(self.ORGANIC, "yelp.com")["position"], 2)
        self.assertEqual(match_domain(self.ORGANIC, "notyelp.com")["position"], 1)
        self.assertIsNone(match_domain(self.ORGANIC, "elp.com"))

    def test_domain_in_path_does_not_match(self):
        organic = [{"position": 1, "link": "https://example.org/yelp.com"}]
        self.assertIsNone(match_domain(organic, "yelp.com"))

    def test_parse_check_found(self):
        c = parse_check(self.ORGANIC, "yelp.com")
        self.assertEqual((c["status"], c["position"]), ("ok", 2))
        self.assertEqual(c["matched_url"], "https://www.yelp.com")   # not the redirect
        self.assertEqual(len(c["snippet"]), 300)

    def test_parse_check_not_found_has_no_position(self):
        c = parse_check(self.ORGANIC, "missing.com")
        self.assertEqual(c, {"status": "not_found", "position": None, "matched_url": None,
                             "title": None, "snippet": None})

    def test_result_url_keeps_real_link(self):
        self.assertEqual(result_url({"link": "https://m.yelp.com/biz/x"}), "https://m.yelp.com/biz/x")


class Reparse(unittest.TestCase):
    def test_reparse_adds_and_fixes_rows_and_leaves_failed_and_seeded_alone(self):
        import json
        from tracker import reparse as rp
        from tracker.db import connect
        with tempfile.TemporaryDirectory() as tmp:
            raw = os.path.join(tmp, "r.json")
            with open(raw, "w") as f:
                json.dump({"organic_results": MatchDomain.ORGANIC}, f)
            conn = connect(os.path.join(tmp, "t.db"))
            rel = os.path.relpath(raw, rp.ROOT)
            ok = conn.execute("INSERT INTO fetch_runs (ts_utc, keyword, status, raw_path)"
                              " VALUES ('2026-01-01T00:00:00Z','kw','success',?)", (rel,)).lastrowid
            bad = conn.execute("INSERT INTO fetch_runs (ts_utc, keyword, status)"
                               " VALUES ('2026-01-02T00:00:00Z','kw','failed')").lastrowid
            seed = conn.execute("INSERT INTO fetch_runs (ts_utc, keyword, status, layer)"
                                " VALUES ('2025-12-01T00:00:00Z','kw','success','seeded')").lastrowid
            conn.execute("INSERT INTO checks (run_id, ts_utc, keyword, domain, status)"
                         " VALUES (?,'2026-01-01T00:00:00Z','kw','yelp.com','not_found')", (ok,))
            conn.execute("INSERT INTO checks (run_id, ts_utc, keyword, domain, status)"
                         " VALUES (?,'2026-01-02T00:00:00Z','kw','yelp.com','failed')", (bad,))
            conn.execute("INSERT INTO checks (run_id, ts_utc, keyword, domain, position, status, layer)"
                         " VALUES (?,'2025-12-01T00:00:00Z','kw','yelp.com',9,'ok','seeded')", (seed,))
            conn.commit()
            cfg = {"keywords": [{"keyword": "kw", "domains": ["yelp.com", "notyelp.com"]}]}

            added, changed, missing = rp.reparse(conn, cfg, write=False)   # dry run writes nothing
            self.assertEqual((len(added), len(changed), missing), (2, 1, 0))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM checks").fetchone()[0], 3)

            rp.reparse(conn, cfg, write=True)
            rows = {(r["run_id"], r["domain"]): (r["status"], r["position"], r["layer"])
                    for r in conn.execute("SELECT * FROM checks")}
            self.assertEqual(rows[(ok, "yelp.com")], ("ok", 2, "live"))
            self.assertEqual(rows[(ok, "notyelp.com")], ("ok", 1, "live"))
            self.assertEqual(rows[(bad, "yelp.com")], ("failed", None, "live"))
            self.assertEqual(rows[(seed, "yelp.com")], ("ok", 9, "seeded"))
            self.assertEqual(rows[(bad, "notyelp.com")], ("failed", None, "live"))
            self.assertEqual(len(rows), 5)
            self.assertEqual(rp.reparse(conn, cfg, write=True)[:2], ([], []))   # second run: nothing to do


if __name__ == "__main__":
    unittest.main()
