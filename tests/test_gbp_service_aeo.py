import unittest
from unittest import mock

from app.services import gbp_seo_service
import AEO_analyser


class AnalyzeAeoServiceTests(unittest.TestCase):
    def test_analyze_aeo_returns_expected_payload(self):
        profile = {
            "name": "Sai Ram Motor Driving School",
            "primary_category": "Driving School",
            "address": "Chennai",
            "website": "https://example.com",
        }
        analysis = {
            "overall_score": 88,
            "breakdown": {"ENTITY": {"score": 12, "max": 15, "justification": "ok"}},
            "recommendations": [{
                "category": "ENTITY",
                "issue": "Missing service detail",
                "recommended_action": "Add service list",
                "priority": "MEDIUM",
                "effort": "EASY",
            }],
            "summary": "Solid answerability.",
        }

        with mock.patch.object(gbp_seo_service, "get_profile", return_value=(profile, None)), \
             mock.patch.object(gbp_seo_service, "save_gbp_json", return_value="mock.json"), \
             mock.patch.object(AEO_analyser, "analyze_aeo", return_value=analysis), \
             mock.patch.object(gbp_seo_service, "build_faq_jsonld", return_value={"@context": "https://schema.org"}), \
             mock.patch.object(gbp_seo_service, "_write_faq_jsonld_file"), \
             mock.patch.object(gbp_seo_service, "_write_analysis_file"):
            result = gbp_seo_service.analyze_aeo("place-123")

        self.assertEqual(result["profile"], profile)
        self.assertEqual(result["analysis"], analysis)
        self.assertEqual(result["analysis"]["overall_score"], 88)


if __name__ == "__main__":
    unittest.main()
