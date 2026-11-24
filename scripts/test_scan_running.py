"""The summary of scan_running.py: python -m unittest discover -s scripts"""

import unittest

from scan_running import SHOWN, Package, keys, message, only_new, repository, vulnerable


def match(name: str, version: str, cve: str, severity: str, fix: str) -> dict:
    return {
        "artifact": {"name": name, "version": version},
        "vulnerability": {"id": cve, "severity": severity, "fix": {"versions": [fix]}},
    }


class SummaryTest(unittest.TestCase):
    def test_packages_at_the_threshold_worst_first_with_their_cves_together(self) -> None:
        report = {
            "matches": [
                match("libkrb5-3", "1.21.3-5+deb13u1", "CVE-2", "High", "1.21.3-5+deb13u2"),
                match("libkrb5-3", "1.21.3-5+deb13u1", "CVE-1", "High", "1.21.3-5+deb13u2"),
                match("zlib1g", "1.3", "CVE-9", "Critical", "1.3.1"),
                match("curl", "8", "CVE-5", "Medium", "8.1"),
            ]
        }
        lines = [package.line() for package in vulnerable(report, "high")]
        assert lines == [
            "zlib1g 1.3 → 1.3.1: CVE-9 Critical",
            "libkrb5-3 1.21.3-5+deb13u1 → 1.21.3-5+deb13u2: CVE-1 High +1",
        ]
        assert vulnerable({"matches": None}, "high") == []

    def test_the_message_escapes_names_and_cuts_long_lists(self) -> None:
        packages = [Package(f"p{i}", "1", "High", {"CVE-1"}, {"2"}) for i in range(SHOWN + 2)]
        text = message("app<1>", {"img:<tag>": packages})
        assert "<b>app&lt;1&gt;</b>" in text
        assert "<b>img:&lt;tag&gt;</b>" in text
        assert text.count("• ") == SHOWN
        assert text.endswith("… 2 more packages")

    def test_only_a_new_cve_is_news_a_rebuild_with_another_tag_is_not(self) -> None:
        assert repository("app-backend:2ffec5c") == "app-backend"
        assert repository("registry:5000/app@sha256:ab") == "registry:5000/app"
        assert repository("registry:5000/app") == "registry:5000/app"
        sent = keys("app-backend:old", Package("libkrb5-3", "1", "High", {"CVE-1"}, {"2"}))
        again = {"app-backend:new": [Package("libkrb5-3", "1", "High", {"CVE-1"}, {"2"})]}
        assert only_new(again, sent) == {}
        worse = {"app-backend:new": [Package("libkrb5-3", "1", "High", {"CVE-1", "CVE-2"}, {"2"})]}
        assert list(only_new(worse, sent)) == ["app-backend:new"]
        assert message("app", worse, total=7).endswith("Vulnerable packages in all running images: 7")


if __name__ == "__main__":
    unittest.main()
